"""
Overnight aggregation job.

Called by start_scheduler.py after every data_storage.py run and also
on a daily schedule at 02:00.  After rebuilding the parquet, invalidates
the in-memory store cache so the next dashboard request picks up fresh data.
"""
import logging
import os
from datetime import datetime
from pathlib import Path

_LOG = logging.getLogger(__name__)

# Resolved at import time so the job works regardless of cwd
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_aggregation_job(
    viz_dir: str | None = None,
    output_dir: str | None = None,
) -> None:
    """Entry point called by the scheduler. Runs engine then invalidates cache."""
    root = _PROJECT_ROOT
    viz_dir    = viz_dir    or str(root / 'data' / 'visualizations')
    output_dir = output_dir or str(root / 'data' / 'mnid_aggregates')

    _LOG.info('Overnight MNID aggregation triggered at %s', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    try:
        from mnid.aggregation.engine import run_aggregation
        from mnid.aggregation.store import invalidate_cache

        success = run_aggregation(
            viz_dir=viz_dir,
            output_dir=output_dir,
        )
        if success:
            invalidate_cache()
            _LOG.info('Overnight aggregation completed — cache refreshed')
        else:
            _LOG.warning('Overnight aggregation returned False (check engine logs)')
    except Exception:
        _LOG.exception('Overnight aggregation failed')


def log_to_file(log_dir: str = '/app/logs') -> None:
    """Wire aggregation log output to a dedicated file (called from start_scheduler.py)."""
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(log_dir, 'mnid_aggregation.log'))
    fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.getLogger('mnid').addHandler(fh)
