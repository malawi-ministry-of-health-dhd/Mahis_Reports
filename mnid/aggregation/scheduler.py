"""
Overnight aggregation job.

Triggered two ways:
  1. Daily at 02:00 via APScheduler in start_scheduler.py
  2. After data_storage.py refreshes the parquet (call run_aggregation_job directly)

Data source is always determined by config.py:
  USE_DEMO_DATA = True  → reads from demo_parquet/
  USE_DEMO_DATA = False → reads from data/parquet/

The job writes indicator_aggregates.parquet + meta.json and then invalidates
the in-memory store cache so the next dashboard request picks up fresh data.

Sustainability design:
  - A lock file (mnid_aggregates/.agg_running) prevents concurrent runs.
  - meta.json is always written, even on failure, so the dashboard can show
    last-run status and whether it succeeded.
  - Log output is written to logs/mnid_aggregation.log when log_to_file() is
    called from start_scheduler.py.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

_LOG = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOCK_FILE = _PROJECT_ROOT / 'data' / 'mnid_aggregates' / '.agg_running'


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
) -> bool:
    """
    Entry point called by the scheduler (and directly after data refresh).

    Returns True on success, False on failure or if another run is in progress.
    """
    root       = _PROJECT_ROOT
    viz_dir    = viz_dir    or str(root / 'data' / 'visualizations')
    output_dir = output_dir or str(root / 'data' / 'mnid_aggregates')
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # ── Concurrency guard ────────────────────────────────────────────────
    if _LOCK_FILE.exists():
        age = datetime.utcnow().timestamp() - _LOCK_FILE.stat().st_mtime
        if age < 3600:           # stale after 1 hour
            _LOG.warning('Aggregation already running (lock age %.0fs) — skipping', age)
            return False
        _LOG.warning('Stale lock file found (%.0f min old) — removing and continuing', age / 60)
        _LOCK_FILE.unlink(missing_ok=True)

    _LOCK_FILE.touch()
    started_at = datetime.utcnow()
    _LOG.info('MNID aggregation job started at %s', started_at.strftime('%Y-%m-%d %H:%M:%S'))

    try:
        from mnid.aggregation.engine import run_aggregation
        from mnid.aggregation.store  import invalidate_cache

        success = run_aggregation(viz_dir=viz_dir, output_dir=output_dir)

        if success:
            invalidate_cache()
            _LOG.info('Aggregation job complete — in-memory cache refreshed')
            return True
        else:
            msg = 'run_aggregation() returned False (no data or no indicators found)'
            _LOG.warning('%s', msg)
            _write_meta_error(output_dir, msg)
            return False

    except Exception as exc:
        msg = f'{type(exc).__name__}: {exc}'
        _LOG.exception('Aggregation job failed: %s', msg)
        _write_meta_error(output_dir, msg)
        return False

    finally:
        _LOCK_FILE.unlink(missing_ok=True)


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
