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

QERY = cfg.QERY
USE_LOCALHOST = cfg.USE_LOCALHOST
DATA_FILE_NAME_ = cfg.DATA_FILE_NAME_
CONCEPTS = getattr(cfg, "CONCEPTS", None)


class DataStorage:
    def __init__(self, query=QERY, data_dir="data", filename=DATA_FILE_NAME_):
        self.query = query
        self.script_dir = os.path.dirname(os.path.realpath(__file__))
        os.chdir(self.script_dir)
        logging.debug(f"Working directory set to: {os.getcwd()}")
        self.data_dir = os.path.join(self.script_dir, data_dir)
        os.makedirs(self.data_dir, exist_ok=True)
        self.filepath = os.path.join(self.data_dir, filename)
        self.dropdown_filepath = os.path.join(self.data_dir, 'dcc_dropdown_json', 'dropdowns.json')

    def fetch_and_save(self):
        """Fetch fresh data from DB and save to Parquet."""
        fetcher = DataFetcher(use_localhost=USE_LOCALHOST)
        df = fetcher.fetch_data(
            self.query,
            filename=self.filepath,
            date_column='Date',
            batch_size=10000,
        )
        if df is not None and not df.empty:
            df.to_parquet(self.filepath, index=False)
            logging.info(f"Data saved to {self.filepath} (Parquet format)")
        else:
            logging.warning("No data fetched from database.")

    @staticmethod
    def query_duckdb(sql: str) -> pd.DataFrame:
        """
        Cached DuckDB query.
        Cache key is the SQL string itself.
        """
        logging.debug("DuckDB cache miss")
        return duckdb.query(sql).df()

    def load_data(self):
        """Load data from Parquet and clean it."""
        if not os.path.exists(self.filepath):
            logging.error("Parquet file not found, fetching fresh data...")
            self.fetch_and_save()

        df = pd.read_parquet(self.filepath)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df[df['Date'] <= datetime.now()]
        # logging.info(f"Data loaded successfully from {self.filepath}")
        return df
    def save_dcc_dropdown_json(self):
        if not os.path.exists(self.dropdown_filepath):
            logging.error("Parquet file not found, fetching fresh data...")
            self.fetch_and_save()
        df = pd.read_parquet(self.filepath)
        dropdown_json = {"programs":sorted(df.Program.dropna().unique().tolist()),
                         "encounters":sorted(df.Encounter.dropna().unique().tolist()),
                         "concepts":sorted(df.concept_name.dropna().unique().tolist()),
                         "concept_answers":sorted(df.obs_value_coded.dropna().unique().tolist()),
                         "gender":sorted(df.Gender.dropna().unique().tolist()),
                         "age_group":sorted(df.Age_Group.dropna().unique().tolist()),
                         "DrugName":sorted(df.DrugName.dropna().unique().tolist())
                         }
        with open(self.dropdown_filepath, 'w') as r:
            json.dump(dropdown_json, r, indent=2)
    def preview_data(self, col_index="Date", tail=10):
        """Print sample data for quick inspection."""
        df = self.load_data()
        print(df[col_index].tail(tail))
        print(f"Total records: {len(df)}")
        return df
    def fetch_and_save_single_table(self):
        """Fetch fresh data from DB and save to CSV."""
        fetcher = DataFetcher(use_localhost=USE_LOCALHOST)
        df = fetcher.fetch_single_table(
            single_table_query=self.query,
            single_table_name=self.filepath
        )
        if df is not None and not df.empty:
            df.to_csv(self.filepath, index=False)
            logging.info(f"Data saved to {self.filepath} (csv format)")
        else:
            logging.warning("No data fetched from database.")

if __name__ == "__main__":
    storage = DataStorage(query=QERY)
    storage.fetch_and_save()
    storage.preview_data()
    storage.save_dcc_dropdown_json()

    users = DataStorage(query="SELECT u.uuid as user_id, ur.role as role FROM users u JOIN user_role ur ON u.user_id = ur.user_id", 
                        filename="users_data.csv")
    users.fetch_and_save_single_table()

    if CONCEPTS:
        concepts = DataStorage(query=CONCEPTS, filename="concepts_data.csv")
        concepts.fetch_and_save_single_table()
