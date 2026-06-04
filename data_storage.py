import os
import pandas as pd
import config as cfg
from db_services import DataFetcher
from datetime import datetime
import logging
import json
import re
import duckdb
import pyarrow.parquet as pq
import pyarrow as pa
import warnings
import sys
warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.DEBUG)

QUERY_OBS_OLD = cfg.QUERY_OBS_OLD
QUERY_OBS_HARMONIZED = cfg.QUERY_OBS_HARMONIZED
QUERY_PROGRAMS = cfg.QUERY_PROGRAMS
QUERY_CONCEPT_NAMES = cfg.QUERY_CONCEPT_NAMES
QUERY_ENCOUNTER_TYPES = cfg.QUERY_ENCOUNTER_TYPES
QUERY_LOCATIONS = cfg.QUERY_LOCATIONS
QUERY_FACILITIES = cfg.QUERY_FACILITIES
QUERY_DRUGS = cfg.QUERY_DRUGS
QUERY_USERS = cfg.QUERY_USERS
QUERY_USER_PROGRAMS = cfg.QUERY_USER_PROGRAMS
# QUERY_BIDS = cfg.BIDS
QUERY_ORDER_TYPES = cfg.QUERY_ORDER_TYPES
IS_HARMONIZED_MAHIS = cfg.IS_HARMONIZED_MAHIS
CUSTOM_GENDER_MAP = cfg.CUSTOM_GENDER_MAP
# ASSESSMENT_MAP = cfg.AESSESSMENT_TYPE
# COLS_TO_DROP = cfg.NONE_ESSENTIAL_COLUMNS

CUSTOM_MNID_MAP_PROGRAM = cfg.CUSTOM_MNID_MAP_PROGRAM
CUSTOM_MNID_MAP_SERVICE_AREA = cfg.CUSTOM_MNID_MAP_SERVICE_AREA
CUSTOM_GENDER_MAP = cfg.CUSTOM_GENDER_MAP

USE_LOCALHOST = cfg.USE_LOCALHOST
DATA_PATH_ = cfg.DATA_PATH_
CONCEPTS = getattr(cfg, "CONCEPTS", None)
KEYS_IN_DATA = cfg.actual_keys_in_data


class DataStorage:
    def __init__ (self, 
                  query=QUERY_OBS_HARMONIZED,
                  data_dir=DATA_PATH_, db_config=cfg.DB_CONFIG, ssh_config=cfg.SSH_CONFIG,
                  load_fresh_data=cfg.LOAD_FRESH_DATA, use_localhost=USE_LOCALHOST,
                  batch_size=cfg.BATCH_SIZE, start_date=cfg.START_DATE):
        self.query = query
        self.script_dir = os.path.dirname(os.path.realpath(__file__))
        os.chdir(self.script_dir)
        logging.debug(f"Working directory set to: {os.getcwd()}")
        self.data_dir = os.path.join(self.script_dir, data_dir)
        self.tables_dir = os.path.join(self.script_dir, data_dir, "single_tables")
        self.parquet_path = os.path.join(self.script_dir, data_dir, "parquet")
        self.dropdown_path = os.path.join(self.script_dir, data_dir, "dcc_dropdown_json")
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.tables_dir), exist_ok=True)
        os.makedirs(os.path.join(self.parquet_path), exist_ok=True)
        os.makedirs(os.path.join(self.dropdown_path), exist_ok=True)

        self.use_localhost = use_localhost
        self.load_fresh_data = load_fresh_data
        self.ssh_config = ssh_config
        self.db_config = db_config
        self.batch_size = batch_size
        self.start_date = start_date

        self.dropdown_filepath = os.path.join(self.data_dir, self.dropdown_path, 'dropdowns.json')
        self.facillities_dropdown_filepath = os.path.join(self.data_dir, self.dropdown_path, 'facilities_dropdowns.json')

    def fetch_transactional_data(self, date_column, incremental_id_column):
        """Fetch fresh data from DB and save to Parquet."""
        logging.info("Fetching Transactional Tables.")
        fetcher = DataFetcher(use_localhost=self.use_localhost, ssh_config=self.ssh_config, 
                 db_config=self.db_config, db_config_local=self.db_config,start_date=self.start_date, 
                 load_fresh_data=self.load_fresh_data, single_tables_folder=self.tables_dir,
                 batch_size=self.batch_size)

        df = fetcher.fetch_data(
            query_template = self.query,
            parquet_output=self.parquet_path,
            date_column=date_column,
            id_column=incremental_id_column
        )
        # load single tables
        programs = pd.read_csv(os.path.join(self.script_dir, self.tables_dir, "programs_data.csv"))
        programs_dict = programs.set_index('program_id')['name'].to_dict()

        concepts = pd.read_csv(os.path.join(self.script_dir,self.tables_dir, "concept_names_data.csv"))
        concepts_dict = concepts.set_index('concept_id')['name'].to_dict()

        encounter_types = pd.read_csv(os.path.join(self.script_dir,self.tables_dir, "encounter_types_data.csv"))
        encounter_types_dict = encounter_types.set_index('encounter_type_id')['name'].to_dict()

        locations = pd.read_csv(os.path.join(self.script_dir,self.tables_dir, "locations_data.csv"))
        locations_dict = (locations[(locations['county_district'].notna())&(locations['name'].notna())]
                          .groupby('county_district')['name'].apply(list).to_dict())
    
        # check if facilities or locations can be used to map facility names, if not create empty dicts and log a warning
        facilities_path = os.path.join(self.script_dir,self.tables_dir, "facilities_data.csv")
        if not os.path.exists(facilities_path):
            logging.warning(f"Facilities data file not found at {facilities_path}. Skipping facilities data loading.")
            locations['location_id'] = locations['location_id'].astype(str)
            facilities_dict = locations.set_index('location_id')['name'].to_dict()
            facility_districts_dict = locations.set_index('location_id')['county_district'].to_dict()
        else:
            facilities = pd.read_csv(os.path.join(self.script_dir,self.tables_dir, "facilities_data.csv"))
            facilities['code'] = facilities['code'].astype(str)
            facilities_dict = facilities.set_index('code')['name'].to_dict()
            facility_districts_dict = facilities.set_index('code')['district'].to_dict()

        drugs = pd.read_csv(os.path.join(self.script_dir,self.tables_dir, "drugs_data.csv"))
        drugs_name_dict = drugs.set_index('drug_id')['name'].to_dict()
        drugs_unit_dict = drugs.set_index('drug_id')['units'].to_dict()

        order_types = pd.read_csv(os.path.join(self.script_dir,self.tables_dir, "order_types_data.csv"))
        order_type_dict = order_types.set_index('order_type_id')['name'].to_dict()


        users = pd.read_csv(os.path.join(self.script_dir,self.tables_dir, "users_data.csv"))
        username_dict = users.set_index('user_id')['User'].to_dict()

        user_programs = pd.read_csv(os.path.join(self.script_dir,self.tables_dir, "user_programs.csv"))
        # username_dict = user_programs.set_index('user_id')['User'].to_dict()
        # user_location_dict = users.set_index('user_id')['location_id'].to_dict()

        # merge single tables with main df
        if not df.empty:
            df['Gender'] = df['Gender'].map(CUSTOM_GENDER_MAP).fillna(df['Gender'])
            df['Program'] = df['Program'].map(programs_dict)
            df['Source_Program'] = df['Program']
            df['Reporting_Program'] = df['Source_Program'].map(CUSTOM_MNID_MAP_PROGRAM).fillna(df['Source_Program'])
            df['Service_Area'] = df['Encounter'].map(CUSTOM_MNID_MAP_SERVICE_AREA).map({"NEONATAL PROGRAM": "NEONATAL"}).fillna(df['Program'])
            df['new_revisit'] = ""
            df['concept_name'] = df['concept_name'].map(concepts_dict)
            df['obs_value_coded'] = df['obs_value_coded'].map(concepts_dict)
            df['Encounter'] = df['Encounter'].map(encounter_types_dict)
            df['DrugUnits'] = df['DrugName'].map(drugs_unit_dict)
            df['DrugName'] = df['DrugName'].map(drugs_name_dict)
            df['User'] = df['creator'].map(username_dict)
            df['Facility_CODE'] = df['location_id']
            df['Facility'] = df['Facility_CODE'].map(facilities_dict)
            df['District'] = df['Facility_CODE'].map(facility_districts_dict)
            df['Order_Type'] = df['Order_Type'].map(order_type_dict)
            df['Order_Name'] = df['Order_Name'].map(concepts_dict)
            # df["Assessment_Type"] = df['Encounter'].map(ASSESSMENT_MAP).fillna(df['Encounter'])
            df = df.reset_index(drop=True)
            print(len(df))
            # df = df.drop(columns=COLS_TO_DROP)
        try:
            if df is not None and not df.empty:
                # Partition into monthly parquet files under the configured directory.
                if date_column in df.columns:
                    df[date_column] = pd.to_datetime(df[date_column], errors='coerce')
                elif 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                    date_column = 'Date'
                else:
                    raise ValueError("No valid date column found for monthly parquet partitioning.")

                df['month_key'] = df[date_column].dt.strftime('%Y%m')
                for month, month_df in df.groupby('month_key'):
                    month_file = os.path.join(self.parquet_path, f"data_{month}.parquet")
                    if os.path.exists(month_file):
                        existing_df = pd.read_parquet(month_file, engine='pyarrow')
                        for col in existing_df.columns:
                            if col not in month_df.columns:
                                month_df[col] = None
                        for col in month_df.columns:
                            if col not in existing_df.columns:
                                existing_df[col] = None
                        month_df = month_df[existing_df.columns]
                        month_df = pd.concat([existing_df, month_df], ignore_index=True)
                        month_df = month_df.drop_duplicates()
                    month_df.to_parquet(month_file, index=False, engine='pyarrow')
                df = df.drop(columns=['month_key'])
                # df = pd.concat([existing_df, df])
                # df = df.drop_duplicates()
                # df.to_parquet(self.filepath, index=False, engine='pyarrow')
                
                print(self.parquet_path)
                print("exists:", os.path.exists(self.parquet_path))
                print("size:", os.path.getsize(self.parquet_path))

                DataStorage.invalidate_query_cache()
                logging.info(f"Data saved to {self.parquet_path} (Parquet format)")

                timestamp_file = os.path.join(self.data_dir,'TimeStamp.csv')
                os.makedirs(os.path.dirname(timestamp_file), exist_ok=True)
                pd.DataFrame({'saving_time': [datetime.now().strftime("%d/%m/%Y, %H:%M:%S")]}).to_csv(timestamp_file, index=False)

                dropdown_json = {"programs":sorted(user_programs.name.dropna().unique().tolist()),
                            "encounters":sorted(encounter_types.name.dropna().unique().tolist()),
                            "concepts":sorted(df.concept_name.dropna().unique().tolist()),
                            "concept_answers":sorted(df.obs_value_coded.dropna().unique().tolist()),
                            "gender":sorted(df.Gender.dropna().unique().tolist()),
                            #  "age_group":sorted(df.Age_Group.dropna().unique().tolist()),
                            "DrugName":sorted(drugs.name.dropna().unique().tolist()),
                            }
                with open(self.dropdown_filepath, 'w') as r:
                    json.dump(dropdown_json, r, indent=2)
                with open(self.facillities_dropdown_filepath, 'w') as f:
                    json.dump(locations_dict, f, indent=2)
                
            else:
                logging.warning("No data fetched from database.")
        except Exception as e:
            logging.error(f"Error merging data: {e}")
            raise

    # Structure: { sql_str: {"mtime_sig": str, "result": pd.DataFrame} }
    _query_cache: dict = {}
    _CACHE_MAXSIZE: int = 32

    @staticmethod
    def _parquet_mtime_signature(sql: str) -> str:
        import glob as _glob
        # Catch explicit *.parquet paths already in the SQL
        paths = re.findall(r"['\"]([^'\"]+\.parquet[^'\"]*)['\"]", sql, re.IGNORECASE)
        # Also catch bare directory paths that will be expanded to globs
        dir_paths = re.findall(r"['\"]([^'\"]+)['\"]", sql, re.IGNORECASE)

        files: list = []
        for p in paths:
            files.extend(_glob.glob(p))
        for d in dir_paths:
            if os.path.isdir(d):
                files.extend(_glob.glob(os.path.join(d, "*.parquet")))

        files = sorted(set(files))
        sig_parts = []
        for f in files:
            try:
                st = os.stat(f)
                sig_parts.append(f"{f}:{st.st_mtime}:{st.st_size}")
            except OSError:
                pass
        return "|".join(sig_parts) if sig_parts else "no_files"

    @staticmethod
    def _expand_dir_paths(sql: str) -> str:
        """Replace bare directory paths in FROM clauses with read_parquet globs."""
        def replace_dir_path(match):
            quote = match.group(1)
            path = match.group(2)
            if os.path.isdir(path) and not path.endswith('*'):
                pattern = os.path.join(path, '*.parquet')
                return f"FROM read_parquet({quote}{pattern}{quote}, union_by_name=True)"
            return match.group(0)
        return re.sub(r"FROM\s+(['\"])(.+?)\1", replace_dir_path, sql, flags=re.IGNORECASE)

    @staticmethod
    def query_duckdb(sql: str) -> pd.DataFrame:
        cache = DataStorage._query_cache
        mtime_sig = DataStorage._parquet_mtime_signature(sql)

        cached = cache.get(sql)
        if cached is not None and cached["mtime_sig"] == mtime_sig:
            logging.debug("DuckDB cache hit")
            return cached["result"].copy()

        logging.debug("DuckDB cache miss — executing query")
        expanded_sql = DataStorage._expand_dir_paths(sql)
        conn = duckdb.connect()
        try:
            result = conn.execute(expanded_sql).df()
        finally:
            conn.close()

        # Evict the oldest entry when the cache is full (simple FIFO)
        if len(cache) >= DataStorage._CACHE_MAXSIZE and sql not in cache:
            oldest_key = next(iter(cache))
            del cache[oldest_key]

        cache[sql] = {"mtime_sig": mtime_sig, "result": result}
        return result.copy()

    @staticmethod
    def invalidate_query_cache():
        """Clear the entire in-process query cache (called after new data is written)."""
        DataStorage._query_cache.clear()
        logging.debug("Query cache invalidated")

    @staticmethod
    def _cached_query(sql: str) -> pd.DataFrame:
        """Backward-compatibility alias — delegates to query_duckdb."""
        return DataStorage.query_duckdb(sql)

    def fetch_and_save_single_table(self, table_name, format="csv"):
        """Fetch fresh data from DB and save to CSV."""
        fetcher = DataFetcher(use_localhost=USE_LOCALHOST)
        return fetcher.fetch_single_table(
            query=self.query,
            table_name=table_name,
            output_folder=self.tables_dir,
            output_format=format
        )


if __name__ == "__main__":
    # check if config file exists and load it, if not log an error and exit
    if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), "configurations.json")):
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "configurations.json")) as f:
            global_configurations = json.load(f)
    else:
        global_configurations = [
            {
                "uuid": "uuid_default",
                "name": "Default Configuration",
                "use_localhost": cfg.USE_LOCALHOST,
                "start_date": cfg.START_DATE,
                "load_fresh_data": cfg.LOAD_FRESH_DATA,
                "data_path": "default",
                "base_query": cfg.QUERY_OBS_HARMONIZED,
                "is_harmonized_emr": cfg.IS_HARMONIZED_MAHIS,
                "batch_size": cfg.BATCH_SIZE,
                "db_config": cfg.DB_CONFIG,
                "ssh_config": cfg.SSH_CONFIG, 
                }
        ]
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "configurations.json"), 'w') as f:
            json.dump(global_configurations, f, indent=2)
    sys.exit(0)
    for items in global_configurations:
        BASE_QUERY = items.get("base_query")
        DATA_ROUTE = f"data/{items.get('data_path')}"
        DB_CONFIG = items.get("db_config")
        SSH_CONFIG = items.get("ssh_config")
        USE_LOCALHOST = items.get("use_localhost", True)
        BATCH_SIZE = items.get("batch_size", 1000)
        LOAD_FRESH_DATA = items.get("load_fresh_data", True)
        START_DATE = items.get("start_date", "2026-01-01")

    
        programs = DataStorage(query=QUERY_PROGRAMS)
        programs.fetch_and_save_single_table(table_name="programs_data")

        concepts = DataStorage(query=QUERY_CONCEPT_NAMES)
        concepts.fetch_and_save_single_table(table_name="concept_names_data")

        encounter_types = DataStorage(query=QUERY_ENCOUNTER_TYPES)
        encounter_types.fetch_and_save_single_table(table_name="encounter_types_data")

        locations = DataStorage(query=QUERY_LOCATIONS)
        locations.fetch_and_save_single_table(table_name="locations_data")

        if not IS_HARMONIZED_MAHIS:
            facilities = DataStorage(query=QUERY_FACILITIES)
            facilities.fetch_and_save_single_table(table_name="facilities_data")

        drugs = DataStorage(query=QUERY_DRUGS)
        drugs.fetch_and_save_single_table(table_name="drugs_data")

        order_types = DataStorage(query=QUERY_ORDER_TYPES)
        order_types.fetch_and_save_single_table(table_name="order_types_data")


        users = DataStorage(query=QUERY_USERS)
        users.fetch_and_save_single_table(table_name="users_data")

        user_programs = DataStorage(query=QUERY_USER_PROGRAMS)
        user_programs.fetch_and_save_single_table(table_name="user_programs")

        # bids = DataStorage(query=QUERY_BIDS)
        # bids.fetch_and_save_single_table(table_name="bids")

        transactional = DataStorage(query=BASE_QUERY, data_dir=DATA_PATH_,
                                    db_config=DB_CONFIG, ssh_config=SSH_CONFIG, 
                                    use_localhost=USE_LOCALHOST,batch_size=BATCH_SIZE, 
                                    load_fresh_data=LOAD_FRESH_DATA, start_date=START_DATE)
        transactional.fetch_transactional_data(date_column="encounter_datetime", incremental_id_column="encounter_id")


        # if CONCEPTS:
        #     concepts = DataStorage(query=CONCEPTS)
        #     concepts.fetch_and_save_single_table(table_name="concepts_data")