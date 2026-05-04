import os
import pandas as pd
import config as cfg
from db_services import DataFetcher
from datetime import datetime
import logging
import json
import duckdb
from functools import lru_cache

logging.basicConfig(level=logging.DEBUG)

QUERY_OBS = cfg.QUERY_OBS
QUERY_PROGRAMS = cfg.QUERY_PROGRAMS
QUERY_CONCEPT_NAMES = cfg.QUERY_CONCEPT_NAMES
QUERY_ENCOUNTER_TYPES = cfg.QUERY_ENCOUNTER_TYPES
QUERY_LOCATIONS = cfg.QUERY_LOCATIONS
QUERY_FACILITIES = cfg.QUERY_FACILITIES
QUERY_DRUGS = cfg.QUERY_DRUGS
QUERY_USERS = cfg.QUERY_USERS
QUERY_ORDER_TYPES = cfg.QUERY_ORDER_TYPES
IS_HARMONIZED_MAHIS = cfg.IS_HARMONIZED_MAHIS

CUSTOM_MNID_MAP_PROGRAM = cfg.CUSTOM_MNID_MAP_PROGRAM
CUSTOM_MNID_MAP_SERVICE_AREA = cfg.CUSTOM_MNID_MAP_SERVICE_AREA
CUSTOM_GENDER_MAP = cfg.CUSTOM_GENDER_MAP

USE_LOCALHOST = cfg.USE_LOCALHOST
DATA_FILE_NAME_ = cfg.DATA_FILE_NAME_
CONCEPTS = getattr(cfg, "CONCEPTS", None)


class DataStorage:
    def __init__ (self, 
                  query=QUERY_OBS,
                  data_dir="data",
                  tables_dir = "data/single_tables", 
                  filename=DATA_FILE_NAME_):
        self.query = query
        self.script_dir = os.path.dirname(os.path.realpath(__file__))
        os.chdir(self.script_dir)
        logging.debug(f"Working directory set to: {os.getcwd()}")
        self.data_dir = os.path.join(self.script_dir, data_dir)
        self.tables_dir = os.path.join(self.script_dir, tables_dir)
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.script_dir, tables_dir), exist_ok=True)
        self.filepath = os.path.join(self.data_dir, filename)
        self.dropdown_filepath = os.path.join(self.data_dir, 'dcc_dropdown_json', 'dropdowns.json')

    def fetch_transactional_data(self, date_column, incremental_id_column):
        """Fetch fresh data from DB and save to Parquet."""
        fetcher = DataFetcher(use_localhost=USE_LOCALHOST)
        if os.path.exists(self.filepath):
            existing_df = pd.read_parquet(self.filepath)
        else:
            existing_df = pd.DataFrame()

        df = fetcher.fetch_data(
            query_template = self.query,
            parquet_output=self.filepath,
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
    
        # check if facilities or locations can be used to map facility names, if not create empty dicts and log a warning
        facilities_path = os.path.join(self.script_dir,self.tables_dir, "facilities_data.csv")
        if not os.path.exists(facilities_path):
            logging.warning(f"Facilities data file not found at {facilities_path}. Skipping facilities data loading.")
            facilities_dict = locations.set_index('location_id')['name'].to_dict()
            facility_districts_dict = locations.set_index('city_village')['name'].to_dict()
        else:
            facilities = pd.read_csv(os.path.join(self.script_dir,self.tables_dir, "facilities_data.csv"))
            facilities_dict = facilities.set_index('code')['name'].to_dict()
            facility_districts_dict = facilities.set_index('code')['district'].to_dict()

        drugs = pd.read_csv(os.path.join(self.script_dir,self.tables_dir, "drugs_data.csv"))
        drugs_name_dict = drugs.set_index('drug_id')['name'].to_dict()
        drugs_unit_dict = drugs.set_index('drug_id')['units'].to_dict()

        order_types = pd.read_csv(os.path.join(self.script_dir,self.tables_dir, "order_types_data.csv"))
        order_type_dict = order_types.set_index('order_type_id')['name'].to_dict()


        users = pd.read_csv(os.path.join(self.script_dir,self.tables_dir, "users_data.csv"))
        username_dict = users.set_index('user_id')['User'].to_dict()
        user_location_dict = users.set_index('user_id')['location_id'].to_dict()

        # merge single tables with main df
        if not df.empty:
            df['Gender'] = df['Gender'].map(CUSTOM_GENDER_MAP).fillna(df['Gender'])
            df['Program'] = df['Program'].map(programs_dict)
            df['Source_Program'] = df['Program']
            df['new_revisit'] = ""
            df['Reporting_Program'] = df['Source_Program'].map(CUSTOM_MNID_MAP_PROGRAM).fillna(df['Source_Program'])
            df['Service_Area'] = df['Encounter'].map(CUSTOM_MNID_MAP_SERVICE_AREA).map({"NEONATAL PROGRAM": "NEONATAL"}).fillna(df['Program'])
            df['concept_name'] = df['concept_name'].map(concepts_dict)
            df['obs_value_coded'] = df['obs_value_coded'].map(concepts_dict)
            df['Encounter'] = df['Encounter'].map(encounter_types_dict)
            df['DrugUnits'] = df['DrugName'].map(drugs_unit_dict)
            df['DrugName'] = df['DrugName'].map(drugs_name_dict)
            df['User'] = df['creator'].map(username_dict)
            df['Facility_CODE'] = df['creator'].map(user_location_dict)
            df['Facility'] = df['Facility_CODE'].map(facilities_dict)
            df['District'] = df['Facility_CODE'].map(facility_districts_dict)
            df['Order_Type'] = df['Order_Type'].map(order_type_dict)
            df['Order_Name'] = df['Order_Name'].map(concepts_dict)

        if df is not None and not df.empty:
            
            # combine with existing parquet
            df = pd.concat([existing_df, df])
            df.to_parquet(self.filepath, index=False, engine='pyarrow')
            
            print(self.filepath)
            print("exists:", os.path.exists(self.filepath))
            print("size:", os.path.getsize(self.filepath))

            with open(self.filepath, "rb") as f:
                print("start:", f.read(4))
                f.seek(-4, 2)
                print("end:", f.read(4))

            DataStorage.invalidate_query_cache()
            logging.info(f"Data saved to {self.filepath} (Parquet format)")

            timestamp_file = os.path.join(self.data_dir,'TimeStamp.csv')
            os.makedirs(os.path.dirname(timestamp_file), exist_ok=True)
            pd.DataFrame({'saving_time': [datetime.now().strftime("%d/%m/%Y, %H:%M:%S")]}).to_csv(timestamp_file, index=False)

            dropdown_json = {"programs":sorted(programs.name.dropna().unique().tolist()),
                         "encounters":sorted(encounter_types.name.dropna().unique().tolist()),
                         "concepts":sorted(df.concept_name.dropna().unique().tolist()),
                         "concept_answers":sorted(df.obs_value_coded.dropna().unique().tolist()),
                         "gender":sorted(df.Gender.dropna().unique().tolist()),
                        #  "age_group":sorted(df.Age_Group.dropna().unique().tolist()),
                         "DrugName":sorted(drugs.name.dropna().unique().tolist())
                         }
            with open(self.dropdown_filepath, 'w') as r:
                json.dump(dropdown_json, r, indent=2)
        else:
            logging.warning("No data fetched from database.")

    @staticmethod
    def query_duckdb(sql: str) -> pd.DataFrame:
        return DataStorage._cached_query(sql).copy()

    @staticmethod
    @lru_cache(maxsize=32)
    def _cached_query(sql: str) -> pd.DataFrame:
        logging.debug("DuckDB cache miss")
        return duckdb.query(sql).df()

    @staticmethod
    def invalidate_query_cache():
        DataStorage._cached_query.cache_clear()
        try:
            from pages.home import _mnid_full_data_cache, _mnid_disk_cache, clear_dashboard_state_cache
            from mnid.app import clear_runtime_caches
            _mnid_full_data_cache.clear()
            _mnid_disk_cache.clear()
            clear_dashboard_state_cache()
            clear_runtime_caches()
        except Exception:
            pass

    def fetch_and_save_single_table(self, table_name, format="csv"):
        """Fetch fresh data from DB and save to CSV."""
        fetcher = DataFetcher(use_localhost=USE_LOCALHOST)
        return fetcher.fetch_single_table(
            query=self.query,
            table_name=table_name,
            output_format=format
        )


if __name__ == "__main__":

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

    storage = DataStorage(query=QUERY_OBS, filename=DATA_FILE_NAME_)
    storage.fetch_transactional_data(date_column="encounter_datetime", incremental_id_column="encounter_id")


    if CONCEPTS:
        concepts = DataStorage(query=CONCEPTS)
        concepts.fetch_and_save_single_table(table_name="concepts_data")
