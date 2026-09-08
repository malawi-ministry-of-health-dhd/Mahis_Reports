"""
Fully self-contained DuckDB-targeted OpenMRS fetcher.

Deliberately does not import anything from db_services.py or data_storage.py — the MySQL/SSH
connection handling and day-by-day batch-pagination logic are inlined here so db_services.py
and data_storage.py can be retired independently without breaking this file.

fetch_incremental() re-pulls a trailing lookback window (instead of only rows added since the
last max date) so that rows edited in OpenMRS after their original fetch get picked up again
and reconciled via upsert in DataStorageDuckDB.
"""
import os
import logging
import warnings
from datetime import datetime, timedelta
from typing import Optional

import duckdb
import pandas as pd
import pymysql
from sshtunnel import SSHTunnelForwarder

from config import (BATCH_SIZE, DB_CONFIG, SSH_CONFIG, USE_LOCALHOST, START_DATE,
                     LOAD_FRESH_DATA, DUCKDB_TABLE_NAME, DUCKDB_LOOKBACK_DAYS)

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataFetcherDuckDB:
    def __init__(self, use_localhost=USE_LOCALHOST, ssh_config=SSH_CONFIG,
                 db_config=DB_CONFIG, start_date=START_DATE,
                 load_fresh_data=LOAD_FRESH_DATA, batch_size=BATCH_SIZE,
                 batch_folder="data/duckdb_batches",
                 duckdb_path=None, duckdb_table=DUCKDB_TABLE_NAME):
        self.use_localhost = use_localhost
        self.load_fresh_data = load_fresh_data
        self.ssh_config = ssh_config
        self.db_config = db_config
        self.batch_size = batch_size
        self.batch_folder = batch_folder
        self.start_date = start_date
        # Used only to look up the last max date when load_fresh_data=False — queries the
        # persisted DuckDB table directly, so there's no dependency on parquet output.
        self.duckdb_path = duckdb_path
        self.duckdb_table = duckdb_table
        self.path = os.path.dirname(os.path.realpath(__file__))
        os.makedirs(os.path.join(self.path, batch_folder), exist_ok=True)

    def _build_tunnel_kwargs(self) -> dict:
        """Build SSHTunnelForwarder keyword arguments from ssh_config.
        Handles two mutually exclusive auth modes:
          - password auth: ssh_config contains 'ssh_password'
          - key-file auth: ssh_config contains 'ssh_pkey'
        """
        cfg = self.ssh_config
        kwargs = {
            'ssh_username':         cfg.get('ssh_user', 'ubuntu'),
            'remote_bind_address':  tuple(cfg['remote_bind_address']),
        }
        ssh_port = cfg.get('ssh_port', 22)

        if cfg.get('ssh_password'):
            kwargs['ssh_password'] = cfg['ssh_password']
        elif cfg.get('ssh_pkey'):
            pkey_path = cfg['ssh_pkey']
            if not os.path.isabs(pkey_path) and not pkey_path.startswith('ssh/'):
                pkey_path = os.path.join('ssh', pkey_path)
            kwargs['ssh_pkey'] = pkey_path

        return (cfg['ssh_host'], ssh_port), kwargs

    def _get_db_connection(self, tunnel=None) -> pymysql.Connection:
        """Establish database connection with SSL support if configured."""
        try:
            if not self.use_localhost and tunnel:
                conn = pymysql.connect(
                    host=self.db_config.get('host', 'localhost'),
                    port=tunnel.local_bind_port,
                    user=self.db_config['user'],
                    password=self.db_config['password'],
                    database=self.db_config['database'],
                    connect_timeout=60,
                    read_timeout=3600,
                )
            elif not self.use_localhost and 'ssl' in self.db_config:
                conn = pymysql.connect(
                    host=self.db_config['host'],
                    port=self.db_config.get('port', 3306),
                    user=self.db_config['user'],
                    password=self.db_config['password'],
                    database=self.db_config['database'],
                    ssl=self.db_config['ssl'],
                    connect_timeout=60,
                    read_timeout=3600,
                )
            else:
                conn = pymysql.connect(
                    host=self.db_config.get('host', 'localhost'),
                    port=self.db_config.get('port', 3306),
                    user=self.db_config['user'],
                    password=self.db_config['password'],
                    database=self.db_config['database'],
                    connect_timeout=30,
                    read_timeout=1800,
                )
            logger.info("Database connection established successfully")
            return conn
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def _get_max_date_from_duckdb(self, date_column: str) -> Optional[datetime]:
        """DuckDB-native equivalent of 'find where we last left off' — queries the persisted
        table directly instead of parquet files, so this has no dependency on data_storage.py
        or on parquet output existing at all."""
        if not self.duckdb_path or not os.path.exists(self.duckdb_path):
            return self.start_date
        try:
            con = duckdb.connect(self.duckdb_path, read_only=True)
            try:
                table_exists = con.sql(
                    "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
                    params=[self.duckdb_table],
                ).fetchone()[0] > 0
                if not table_exists:
                    return self.start_date
                result = con.execute(
                    f"SELECT MAX({date_column}) AS max_date FROM {self.duckdb_table}"
                ).df()
            finally:
                con.close()
            if not result.empty and not result["max_date"].isna().iloc[0]:
                max_date = pd.to_datetime(result["max_date"].iloc[0])
                logger.info(f"Found existing data up to {max_date}")
                return max_date
        except Exception as e:
            logger.warning(f"Could not read max date from {self.duckdb_path}: {e}")
        return self.start_date

    def _load_batches_from_files(self, batch_paths: list) -> pd.DataFrame:
        """Load and concatenate all batch files into a single dataframe."""
        if not batch_paths:
            logger.info("No batch files to load")
            return pd.DataFrame()

        logger.info(f"Loading {len(batch_paths)} batch files into memory...")
        batches = []
        try:
            for batch_path in batch_paths:
                if os.path.exists(batch_path):
                    df = pd.read_parquet(batch_path, engine='pyarrow')
                    batches.append(df)
                    logger.debug(f"Loaded batch: {os.path.basename(batch_path)} ({len(df)} rows)")
                else:
                    logger.warning(f"Batch file not found: {batch_path}")

            if batches:
                final_df = pd.concat(batches, ignore_index=True)
                logger.info(f"Concatenated {len(batches)} batches ({len(final_df)} total rows)")
                return final_df
            logger.info("No valid batch files found")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error loading batches from files: {e}")
            raise

    def fetch_data(self, query_template: str, date_column: str = 'Date',
                    id_column: str = 'encounter_id') -> pd.DataFrame:
        logger.info("Fetching Started...")

        if not self.load_fresh_data:
            max_date = self._get_max_date_from_duckdb(date_column)
            start_date = max_date if isinstance(max_date, datetime) else pd.to_datetime(max_date)
        else:
            start_date = self.start_date if isinstance(self.start_date, datetime) else pd.to_datetime(self.start_date)
            logger.info(f"Forced fresh load. Starting from {start_date}")

        batch_paths = []
        try:
            if self.use_localhost:
                conn = self._get_db_connection()
                batch_paths = self._fetch_in_batches(conn, query_template, date_column, id_column, start_date)
                conn.close()
            elif self.ssh_config:
                _tunnel_host, _tunnel_kwargs = self._build_tunnel_kwargs()
                with SSHTunnelForwarder(_tunnel_host, **_tunnel_kwargs) as tunnel:
                    logger.info(f"SSH tunnel established on port {tunnel.local_bind_port}")
                    conn = self._get_db_connection(tunnel)
                    batch_paths = self._fetch_in_batches(conn, query_template, date_column, id_column, start_date)
                    conn.close()
            else:
                conn = self._get_db_connection()
                batch_paths = self._fetch_in_batches(conn, query_template, date_column, id_column, start_date)
                conn.close()

            if batch_paths:
                logger.info(f"Merging {len(batch_paths)} batch files...")
                final_df = self._load_batches_from_files(batch_paths)
                if not final_df.empty:
                    final_df.drop_duplicates(inplace=True)
                    logger.info(f"Final dataframe contains {len(final_df)} rows after deduplication")
                self.cleanup_batches()
                return final_df
            logger.info("No new data fetched")
            self.cleanup_batches()
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error in fetch_data: {e}")
            raise

    def _fetch_in_batches(self, conn: pymysql.Connection, query_template: str,
                           date_column: str, id_column: str, start_date: datetime) -> list:
        """Fetch data in batches and save each batch as parquet file without storing in RAM."""
        batch_paths = []
        current_date = start_date
        today = datetime.now()

        while current_date.date() <= today.date():
            logger.info(f"Processing date: {current_date.strftime('%Y-%m-%d')}")

            date_str = current_date.strftime('%Y-%m-%d')
            date_start_midnight = current_date.strftime('%Y-%m-%d 00:00:00')
            date_end_midnight = current_date.strftime('%Y-%m-%d 23:59:59')
            has_more_data = True
            batch_count = 0
            last_id_for_date = 0

            while has_more_data:
                date_filter = (f"AND {date_column} >= '{date_start_midnight}' "
                                f"AND {date_column} <= '{date_end_midnight}' "
                                f"AND e.{id_column} > {last_id_for_date}")
                query = query_template.format(date_filter=date_filter)
                full_query = f"{query} ORDER BY e.{id_column} LIMIT {self.batch_size}"

                try:
                    batch_df = pd.read_sql(full_query, conn)

                    if batch_df.empty:
                        has_more_data = False
                        logger.info(f"Completed {date_str} - {batch_count} batches fetched")
                    else:
                        last_id_for_date = batch_df[id_column].max()
                        batch_size = len(batch_df)

                        batch_filename = f"batch_{date_str}_b{batch_count:04d}_{batch_size}.parquet"
                        batch_path = os.path.join(self.path, self.batch_folder, batch_filename)
                        batch_df.to_parquet(batch_path, index=False, engine='pyarrow')

                        logger.info(f"Saved batch {batch_count} for {date_str}: {batch_path} ({batch_size} rows)")
                        batch_paths.append(batch_path)
                        batch_count += 1
                        del batch_df

                except Exception as e:
                    logger.error(f"Error fetching batch for {date_str}: {e}")
                    import traceback
                    traceback.print_exc()
                    has_more_data = False

            current_date += timedelta(days=1)

        return batch_paths

    def fetch_single_table(self, table_name: str, query: str) -> pd.DataFrame:
        """Fetch a small lookup/dimension table (programs, concepts, encounter types, etc.)
        in a single query — no pagination, these are small reference tables."""
        try:
            if self.use_localhost:
                conn = self._get_db_connection()
                df = pd.read_sql(query, conn)
                conn.close()
            elif self.ssh_config:
                _tunnel_host, _tunnel_kwargs = self._build_tunnel_kwargs()
                with SSHTunnelForwarder(_tunnel_host, **_tunnel_kwargs) as tunnel:
                    conn = self._get_db_connection(tunnel)
                    df = pd.read_sql(query, conn)
                    conn.close()
            else:
                conn = self._get_db_connection()
                df = pd.read_sql(query, conn)
                conn.close()
            logger.info(f"Fetched {table_name} ({len(df)} rows)")
            return df
        except Exception as e:
            logger.error(f"Error fetching single table {table_name}: {e}")
            raise

    def cleanup_batches(self):
        """Clean up all batch parquet files after successful merge."""
        batch_dir = os.path.join(self.path, self.batch_folder)
        if not os.path.exists(batch_dir):
            return
        try:
            for filename in os.listdir(batch_dir):
                if filename.startswith('batch_') and filename.endswith('.parquet'):
                    os.remove(os.path.join(batch_dir, filename))
            logger.info(f"Cleaned up batch files from {batch_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up batches: {e}")

    def fetch_incremental(self, query_template, date_column="Date", id_column="encounter_id",
                           lookback_days=None):
        """Fetch rows from `lookback_days` ago through today, regardless of what's already
        stored, so edits made in OpenMRS after the original fetch get picked up again and
        reconciled via upsert in DataStorageDuckDB."""
        lookback_days = DUCKDB_LOOKBACK_DAYS if lookback_days is None else lookback_days
        lookback_start = datetime.now() - timedelta(days=lookback_days)
        configured_start = pd.to_datetime(self.start_date)
        effective_start = max(lookback_start, configured_start)

        original_load_fresh_data, original_start_date = self.load_fresh_data, self.start_date
        self.load_fresh_data = True
        self.start_date = effective_start
        try:
            return self.fetch_data(query_template=query_template, date_column=date_column,
                                    id_column=id_column)
        finally:
            self.load_fresh_data, self.start_date = original_load_fresh_data, original_start_date
