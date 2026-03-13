<!-- USING PY DASH FOR THE BUSINESS INTELLIGENCE -->
# MaHIS Dash Plotly
### This serves as an analytical platform for the MaHIS system. It utilizes the plotly web visualization power to produce dashboards and reports for the ministry of health.


## Installation steps - Bash
1. Execute install.sh. This will install ubuntu and python dependencies
    ```bash
    chmod +x install.sh
    ./install.sh
    ```
2. update database settings in config.py
    ```text
    <!-- Example -->
    cp config.example.py config.py
    nano config.py
    ```
    By default, config.py is set to pull data from the START_DATE and USE_LOCALHOST = True (will use DB_CONFIG and SSH_CONFIG).

    Test pulling the data using below
    ```text
    <!-- Example -->
    source venv/bin/activate
    python3 data_storage.py
    ```

3. Be sure to add data_storage.py to crontab or taskscheduler as per install.sh or
    ```text
    <!-- Example -->
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