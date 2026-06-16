<!-- USING PY DASH FOR THE BUSINESS INTELLIGENCE -->
# MaHIS Dash Plotly
### This serves as an analytical platform for the MaHIS system. It utilizes the plotly web visualization power to produce dashboards and reports for the ministry of health.


## Installation steps - Bash
1. Update database settings in config.py
    ```text
    <!-- Example -->
    cp config.example.py config.py
    nano config.py
    ```
    By default, config.py is set to pull data from the START_DATE and USE_LOCALHOST = True (False will use DB_CONFIG and SSH_CONFIG).


2. Execute install.sh. This will install ubuntu and python dependencies
    ```bash
    chmod +x install.sh
    ./install.sh
    ```
    Test pulling the data using below
    ```text
    <!-- Example -->
    source venv/bin/activate
    python3 data_storage.py
    ```

3. Be sure to add data_storage.py to crontab or taskscheduler as per install.sh or
    ```text
    <!-- Example -->
    crontab -e
    */10 * * * * /home/$(whoami)/Mahis_Reports/venv/bin/python3 /home/$(whoami)/Mahis_Reports/data_storage.py >> /home/$(whoami)/Mahis_Reports/log.txt 2>&1
    ```

4. Start gunicorn in development or production by running start_dev or start_prod
    ```bash
    chmod +x start_dev.sh
    ./start_dev.sh
    ```

    ```bash
    chmod +x start_prod.sh
    ./start_prod.sh
    ```

5. Kill process (kills production. For dev use CTRL + C)
    ```bash
    chmod +x stop.sh
    ./stop.sh

End


## Installation steps - Traditional
***
1. **Install Python 3.11 (recommended) or later**
    ```bash
    sudo apt-get update
    sudo apt-get install -y python3
    ```

2. **Install pip**
    ```bash
    sudo apt-get install -y python3-pip
    ```

3. **Install dependencies**
    ```bash
    <!-- VENV -->
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    export DASH_APP_DIR=/var/www/dash_plotly_mahis
    ```

4. **Update configuration**  
   Edit the `config.py` file to point to your database.  
   (The config includes the SQL query required to pull data and store it to a CSV in `/data/`.)

    NOTE: if config includes ssh files, create a directory in the parent folder /ssh and add the files. The config.py should include the file name.


    ```bash
    mv config.example.py config.py
    ```
    Use sample of the config.example

5. **Load data**
    ```bash
    python3 data_storage.py
    ```
6. **Add data_storage.py to crontab to run every time (30 minutes as default)

    ```text
    */30 * * * * /path-to-directory/data_storage.py >> /path-to-monitor-logs/logfile.log 2>&1
    ```

7. **Run the app (development mode)**
    ```bash
    python3 app.py
    ```
    Default port: [http://localhost:8050](http://localhost:8050)

8. **Run in production with Gunicorn**
    ```bash
    nohup python3 -m gunicorn --workers 4 --bind 0.0.0.0:8050 wsgi:server > gunicorn.log 2>&1 &
    ```
    To stop:
    ```bash
    pkill -9 gunicorn
    ```
    To deactivate venv:
    ```bash
    deactivate
    ```
---

## MNID Dashboard

The MNID (Maternal and Neonatal Indicator Dashboard) is a modular Dash dashboard for monitoring maternal and child health indicators across facilities and districts in Malawi.

### Module structure

```
mnid/
  app.py              — main renderer, callbacks, layout assembly
  layout.py           — hero cards, alert banner, KPI row, sidebar
  chart_helpers.py    — shared chart/figure helpers, moving averages
  coverage.py         — coverage charts, comparative analysis section
  indicators.py       — indicator config resolution, category ordering
  heatmap.py          — facility/district performance heatmaps
  data_utils.py       — dataframe prep, serialization, lightweight session store
  constants.py        — colours, facility maps, palette constants
  aggregation/
    engine.py         — overnight pre-aggregation pipeline
    store.py          — aggregate loader and query helpers
    scheduler.py      — job wrapper called by start_scheduler.py
```

### Pre-aggregation service

The dashboard pre-computes indicator coverage (`numerator`, `denominator`, `pct`) for every combination of **facility × indicator × period** (daily / weekly / monthly) and writes the result to `data/mnid_aggregates/indicator_aggregates.parquet`.

Dashboard callbacks query this parquet instead of scanning 1.7M+ raw rows on every period change — making period selection near-instant.

**How it runs**

| Trigger | When | How |
|---|---|---|
| App startup (dev & prod) | Once, if parquet is missing | Background thread auto-fires inside `mnid/app.py` on first import |
| After every `data_storage.py` run | Every data refresh cycle | Background thread called from `start_scheduler.py` → `_run_mnid_aggregation()` |
| Overnight schedule | Daily at **02:00** | APScheduler job in `start_scheduler.py` |
| Manual / one-off | On demand | See command below |

**In production**, the scheduler handles everything: `start_scheduler.py` runs `data_storage.py` on its interval, then fires the aggregation in a background thread after each successful data pull. The 02:00 daily job is a safety net in case the data refresh cycle was skipped.

**In development** (running `python app.py` directly without the scheduler), the aggregation fires automatically in a background thread the first time `mnid/app.py` is imported — i.e. on app startup. You will see the following in your terminal when it completes:

```
INFO mnid.app Aggregate parquet not found — building in background...
INFO mnid.app Startup aggregation complete.
```

The first page load after a fresh install may still feel slow while the background job runs (30 seconds to a few minutes depending on data volume). Once the parquet is written, all subsequent loads use the fast path.

**Manual trigger**

Run this any time you want to force a rebuild — after changing indicator configs, after a large data import, or to verify the pipeline works:

```bash
python -c "from mnid.aggregation.scheduler import run_aggregation_job; run_aggregation_job()"
```

This runs synchronously in your terminal, prints progress to the log, and writes two files on success:

```
data/mnid_aggregates/
  indicator_aggregates.parquet   — pre-computed coverage per facility × indicator × period
  meta.json                      — build timestamp, row count, elapsed time, status
```

Check `meta.json` to confirm the last run succeeded:

```bash
cat data/mnid_aggregates/meta.json
```

A successful run looks like:
```json
{
  "generated_at": "2025-01-15T02:00:43",
  "elapsed_sec": 87.4,
  "rows": 482310,
  "indicators": 24,
  "data_source": "data/parquet",
  "last_run_status": "ok"
}
```

**When to trigger manually**

- After adding or changing indicator configs in `data/visualizations/*.json`
- After a bulk data import that bypassed the scheduler
- After deleting `data/mnid_aggregates/` to force a clean rebuild
- When `meta.json` shows `"last_run_status": "error"` and you've fixed the underlying cause

**What it replaces**

Before this service, every period-change triggered:
- N × `_cov()` calls on 1.7M raw rows for the KPI/hero section
- A triple-nested entity × indicator × period loop for the comparison charts
- Per-indicator period-by-period row masking for every run chart card

After: all three paths do a single filtered read of the ~500K-row aggregate. The dashboard always falls back to live row-scan computation if the parquet is absent, so no manual step is required before first use.

---

### Modifying data in the pages
To modify data, go to /pages/, select the file to modify and change the filters.

### Calculation functions from visualization.py
1. Create Column Chart ~ create_column_chart()
    Requires to specify dataframe (df), x_col, y_col, title, x_title, y_title, as mandatory fields and filters as optional by specifying "column name" and "value name". It takes upto 6 optional columns and values
2. Create Line Chart ~ create_line_chart()
    Requires to specify dataframe (df), date_col, y_col, title, x_title, y_title, as mandatory fields and filters as optional by specifying "column name" and "value name". It takes upto 6 optional columns and values
3. Create Pie Chart ~ create_pie_chart()
    Requires to specify dataframe (df), names_col, values_col, title, as mandatory fields and filters as optional by specifying "column name" and "value name". It takes upto 6 optional columns and values
4. Create Age Gender Histogram ~ create_age_gender_histogram()
    Requires to specify dataframe (df), age_col, gender_col, title, xtitle, ytitle, bin_size, as mandatory fields and filters as optional by specifying "column name" and "value name". It takes upto 6 optional columns and values
5. Create Bar Chart ~ create_horizontal_bar_chart()
    Requires to specify dataframe (df), label_col, value_col, title, x_title, y_title, top_n=10, as mandatory fields and filters as optional by specifying "column name" and "value name". It takes upto 6 optional columns and values
6. Create Count ~ create_count()
    This is for creating count of rows
    Requires to specify dataframe (df) as mandatory field and filters as optional by specifying "column name" and "value name". It takes upto 6 optional columns and values
6. Create Count Sets ~ create_count_sets()
    This is for creating count of rows whose filter depends on two or more attributes of a person. Example if a person has a diagnosis and an outcome. To filter a diagnosis and an outcome requires set objects and these are converted as such.
    This requires to specify dataframe (df) as mandatory field and define first column and other columns for validation. First two columns are mandatory.
7. Create Count Unique ~ create_count_unique()
    This is for creating count unique people in the openmrs database.
    Requires to specify dataframe (df) as mandatory field and filters as optional by specifying "column name" and "value name". It takes upto 6 optional columns and values
8. Create Sum ~ create_sum()
    This is for summation of numerical fields.
    Requires to specify dataframe (df) and numerical column as mandatory field and filters as optional by specifying "column name" and "value name". It takes upto 6 optional columns and values

## Using DOCKER
1. Prerequisites
    Docker
    Docker Compose

2. clone repo
    ```bash
    git clone <repository-url>
    cd mahis-dash-plotly
    ```

3. copy configurations and update them
    ```bash
    cp config.example.py config.py
    ```

4. start app
    ```bash
    docker-compose up -d
    ```
5. try the application
    ```text
    http://localhost:8050
    ```

6. Monitor
    ```bash
    # View logs
    docker-compose logs -f

    # View specific service logs
    docker-compose logs -f mahis-dash

    # Check service status
    docker-compose ps

    # View container health
    docker-compose exec mahis-dash python -c "import requests; print(requests.get('http://localhost:8050/_health').text)"

    ```

***