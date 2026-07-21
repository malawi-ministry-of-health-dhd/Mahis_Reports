"""
Overnight aggregation job.

Runs daily at 02:00 via APScheduler (see start_scheduler.py), or right after
data_storage.py refreshes the parquet, by calling run_aggregation_job directly.
Route-scoped jobs read from data/<route>/parquet unless an explicit data source is
provided.

Writes indicator_aggregates.parquet + meta.json, then invalidates the in-memory
store cache so the next dashboard request picks up fresh data. A lock file
(mnid_aggregates/.agg_running) stops two runs overlapping. meta.json is always
written, even on failure, so the dashboard can show last-run status. Logs go
to logs/mnid_aggregation.log once log_to_file() is called from start_scheduler.py.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

_LOG = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_data_source(data_source: str | None, route: str) -> str:
    if data_source:
        return data_source
    return f'data/{route}/parquet'


def _data_source_exists(data_source: str) -> bool:
    source_path = Path(data_source)
    if not source_path.is_absolute():
        source_path = _PROJECT_ROOT / source_path
    return source_path.exists()


def _write_meta_error(output_dir: str, error: str) -> None:
    """Write a failure record to meta.json so the dashboard can surface it."""
    meta_path = Path(output_dir) / 'meta.json'
    try:
        existing = {}
        if meta_path.exists():
            with open(meta_path, encoding='utf-8') as f:
                existing = json.load(f)
        existing.update({
            'last_run_at':     datetime.utcnow().isoformat(),
            'last_run_status': 'error',
            'last_error':      error,
        })
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass  # don't let meta write failures obscure the real error


def run_aggregation_job(
    viz_dir: str | None = None,
    output_dir: str | None = None,
    grains: list | None = None,
    data_source: str | None = None,
    route: str = 'default',
) -> bool:
    """
    Entry point called by the scheduler (and directly after data refresh).

    output_dir/data_source default to the given `route`'s own folders, so
    concurrent builds for different routes use separate lock files and never
    block each other.

    Returns True on success, False on failure or if another run is in progress.
    """
    root        = _PROJECT_ROOT
    viz_dir     = viz_dir     or str(root / 'data' / 'visualizations')
    output_dir  = output_dir  or str(root / 'data' / 'mnid_aggregates' / route)
    data_source = _resolve_data_source(data_source, route)
    if not _data_source_exists(data_source):
        _LOG.info(
            'Aggregation skipped for route=%s because data source does not exist: %s',
            route,
            data_source,
        )
        return False

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    lock_file = Path(output_dir) / '.agg_running'

    # don't let two runs for the same route overlap
    if lock_file.exists():
        age = datetime.utcnow().timestamp() - lock_file.stat().st_mtime
        # negative age means the lock file's mtime is in the future (clock skew) - treat as stale
        if 0 <= age < 3600:
            _LOG.warning('Aggregation already running for route=%s (lock age %.0fs), skipping', route, age)
            return False
        _LOG.warning('Stale lock file found for route=%s (age %.0fs), removing and continuing', route, age)
        lock_file.unlink(missing_ok=True)

    lock_file.touch()
    started_at = datetime.utcnow()
    _LOG.info('MNID aggregation job started for route=%s at %s', route, started_at.strftime('%Y-%m-%d %H:%M:%S'))

    try:
        from mnid.aggregation.engine import run_aggregation
        from mnid.aggregation.store  import invalidate_cache

        success = run_aggregation(viz_dir=viz_dir, output_dir=output_dir, grains=grains, data_source=data_source)

        if success:
            invalidate_cache(route)
            _LOG.info('Aggregation job complete for route=%s, in-memory cache refreshed', route)
            return True
        else:
            msg = 'run_aggregation() returned False (no data or no indicators found)'
            _LOG.warning('%s', msg)
            _write_meta_error(output_dir, msg)
            return False

    except Exception as exc:
        msg = f'{type(exc).__name__}: {exc}'
        _LOG.exception('Aggregation job failed for route=%s: %s', route, msg)
        _write_meta_error(output_dir, msg)
        return False

    finally:
        lock_file.unlink(missing_ok=True)


def get_last_run_status(output_dir: str | None = None) -> dict:
    """
    Return the last run status from meta.json.

    Useful for health-check endpoints or dashboard status banners.
    Keys: generated_at, elapsed_sec, rows, indicators, data_source,
          last_run_status ('ok'|'error'), last_error (on failure only).
    """
    out = Path(output_dir or str(_PROJECT_ROOT / 'data' / 'mnid_aggregates'))
    meta_path = out / 'meta.json'
    if not meta_path.exists():
        return {'last_run_status': 'never_run'}
    try:
        with open(meta_path, encoding='utf-8') as f:
            return json.load(f)
    except Exception as exc:
        return {'last_run_status': 'unreadable', 'error': str(exc)}


def log_to_file(log_dir: str | None = None) -> None:
    """Wire aggregation log output to a dedicated file (called from start_scheduler.py)."""
    target = Path(log_dir or str(_PROJECT_ROOT / 'logs'))
    target.mkdir(parents=True, exist_ok=True)
    log_path = target / 'mnid_aggregation.log'
    fh = logging.FileHandler(str(log_path))
    fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    logging.getLogger('mnid').addHandler(fh)
    _LOG.info('Aggregation log file: %s', log_path)
