# start_scheduler.py
import subprocess
import threading
import schedule
import time
import os
from datetime import datetime


def run_data_storage():
    """Run the data_storage.py script and log output."""
    try:
        log_file = "/app/logs/data_update.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(log_file, "a") as f:
            f.write(f"\n{'='*50}\n")
            f.write(f"Starting data update at {timestamp}\n")
            f.write(f"{'='*50}\n")

        result = subprocess.run(
            ["python", "/app/data_storage.py"],
            capture_output=True,
            text=True
        )

        with open(log_file, "a") as f:
            f.write(f"Exit code: {result.returncode}\n")
            if result.stdout:
                f.write(f"STDOUT:\n{result.stdout}\n")
            if result.stderr:
                f.write(f"STDERR:\n{result.stderr}\n")
            f.write(f"\nData update completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        print(f"Data update completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        error_msg = f"Error running data_storage.py: {str(e)}"
        print(error_msg)
        with open("/app/logs/data_update_error.log", "a") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {error_msg}\n")


def _configured_routes():
    """Every route declared in configurations.json (falls back to 'default')."""
    import json
    try:
        with open('/app/configurations.json') as f:
            configs = json.load(f)
        routes = [c.get('data_path') for c in configs if c.get('data_path')]
        return routes or ['default']
    except Exception:
        return ['default']


def _run_mnid_aggregation():
    """Run the MNID pre-aggregation pipeline for every configured route, in a background thread."""
    def _job():
        from mnid.aggregation.scheduler import run_aggregation_job, log_to_file
        log_to_file('/app/logs')
        for route in _configured_routes():
            try:
                run_aggregation_job(route=route)
            except Exception as exc:
                print(f"MNID aggregation error (route={route}): {exc}")

    t = threading.Thread(target=_job, daemon=True)
    t.start()


def _run_dhis2_publish():
    """Refresh the DHIS2 -> MNID aggregate (data/mnid_aggregates/dhis2), in a background thread.

    Pulls all 52 mapped indicators from the DHIS2 Analytics API and republishes
    indicator_aggregates.parquet -- what MNID reads from when
    config.MNID_DATA_SOURCE = 'dhis2'. Runs on its own weekly schedule (see
    run_scheduler) rather than at every DATA_UPDATE_INTERVAL tick, since it's a
    live API pull (minutes, not seconds) and DHIS2 data doesn't change that often.
    See mnid/dhis2/PUBLISH_GUIDE.md for manual runs and troubleshooting.
    """
    def _job():
        import os as _os
        from datetime import datetime as _datetime
        log_file = "/app/logs/dhis2_publish.log"
        timestamp = _datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _os.environ['MNH_DHIS2_START_PERIOD'] = _os.getenv('MNH_DHIS2_START_PERIOD', '202501')
        _os.environ['MNH_DHIS2_END_PERIOD'] = _datetime.now().strftime('%Y%m')
        try:
            from mnid.dhis2.mnid_publish import publish_mnid_aggregate
            result = publish_mnid_aggregate()
            with open(log_file, "a") as f:
                f.write(f"[{timestamp}] DHIS2 publish OK: {result}\n")
            print(f"DHIS2 publish complete at {timestamp}: {result}")
        except Exception as exc:
            with open(log_file, "a") as f:
                f.write(f"[{timestamp}] DHIS2 publish FAILED: {exc}\n")
            print(f"DHIS2 publish error: {exc}")

    t = threading.Thread(target=_job, daemon=True)
    t.start()


def run_scheduler():
    """Run the scheduler in a separate thread."""
    interval = int(os.getenv('DATA_UPDATE_INTERVAL', '30'))
    agg_interval_hours = int(os.getenv('MNID_AGGREGATION_INTERVAL_HOURS', '6'))
    dhis2_publish_days = int(os.getenv('MNID_DHIS2_PUBLISH_INTERVAL_DAYS', '7'))
    dhis2_publish_time = os.getenv('MNID_DHIS2_PUBLISH_TIME', '03:00')

    print(f"Scheduler started. Data will be updated every {interval} minutes.")
    print(f"MNID aggregation scheduled every {agg_interval_hours} hours.")
    print(f"DHIS2 publish scheduled every {dhis2_publish_days} days at {dhis2_publish_time}.")

    schedule.every(interval).minutes.do(run_data_storage)

    # Independent overnight aggregation — runs even if data_storage didn't fire
    schedule.every(agg_interval_hours).hours.do(_run_mnid_aggregation)

    # Weekly DHIS2 -> MNID aggregate refresh (data/mnid_aggregates/dhis2)
    schedule.every(dhis2_publish_days).days.at(dhis2_publish_time).do(_run_dhis2_publish)

    if os.getenv('INITIAL_DATA_LOAD', 'true').lower() == 'true':
        print("Running initial data load...")
        run_data_storage()
        _run_mnid_aggregation()

    while True:
        schedule.run_pending()
        time.sleep(60)


def start_dash_app():
    """Start the Dash application."""
    print("Starting Dash application...")

    subprocess.run([
        "python", "-m", "gunicorn",
        "--workers", "4",
        "--bind", "0.0.0.0:8050",
        "wsgi:server"
    ])


if __name__ == "__main__":
    os.makedirs("/app/logs", exist_ok=True)
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    start_dash_app()
