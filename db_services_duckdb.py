import os
import logging
import warnings
from datetime import datetime, timedelta

import duckdb
import pandas as pd
import pymysql
from sshtunnel import SSHTunnelForwarder

from config import BATCH_SIZE, DB_CONFIG, SSH_CONFIG, USE_LOCALHOST, START_DATE, DUCKDB_LOOKBACK_DAYS

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataFetcherDuckDB:
    def __init__(self, use_localhost=USE_LOCALHOST, ssh_config=SSH_CONFIG,
                 db_config=DB_CONFIG, start_date=START_DATE, batch_size=BATCH_SIZE,
                 batch_folder="data/duckdb_batches", duckdb_path=None):
        self.use_localhost = use_localhost
        self.ssh_config = ssh_config
        self.db_config = db_config
        self.batch_size = batch_size
        self.batch_folder = batch_folder
        self.start_date = start_date
        # Target .duckdb file for fetch_tables() — only required by callers that use it.
        self.path = os.path.dirname(os.path.realpath(__file__))
        self.duckdb_path = duckdb_path
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

    def fetch_bulk(self, query_template: str, date_column: str = 'Date', id_column: str = 'encounter_id',
                    start_date=None, end_date=None, on_batch=None):
        """Fetch data across the whole [start_date, end_date] range, paginating continuously by
        id_column (batches are "up to batch_size rows past the last id seen", not chunked by
        calendar day). Used for both routine incremental fetches (via fetch_incremental) and
        full historical (re)loads — the caller always says exactly which start_date (and
        optionally end_date) to (re)load from; this never touches self.start_date.

        If on_batch is given, each batch is streamed straight to it as soon as it's fetched
        and this returns the total row count instead of a DataFrame.
        """
        if start_date is None:
            raise ValueError("fetch_bulk() requires an explicit start_date")
        start_date = start_date if isinstance(start_date, datetime) else pd.to_datetime(start_date)
        end_date = (end_date if isinstance(end_date, datetime) else pd.to_datetime(end_date)) if end_date else datetime.now()

        try:
            if self.use_localhost:
                conn = self._get_db_connection()
                batch_paths, total_rows = self._fetch_bulk_batches(conn, query_template, date_column, id_column, start_date, end_date, on_batch=on_batch)
                conn.close()
            elif self.ssh_config:
                _tunnel_host, _tunnel_kwargs = self._build_tunnel_kwargs()
                with SSHTunnelForwarder(_tunnel_host, **_tunnel_kwargs) as tunnel:
                    logger.info(f"SSH tunnel established on port {tunnel.local_bind_port}")
                    conn = self._get_db_connection(tunnel)
                    batch_paths, total_rows = self._fetch_bulk_batches(conn, query_template, date_column, id_column, start_date, end_date, on_batch=on_batch)
                    conn.close()
            else:
                conn = self._get_db_connection()
                batch_paths, total_rows = self._fetch_bulk_batches(conn, query_template, date_column, id_column, start_date, end_date, on_batch=on_batch)
                conn.close()

            if on_batch is not None:
                logger.info(f"Streamed {total_rows} rows across batches")
                return total_rows

            if batch_paths:
                logger.info(f"Merging {len(batch_paths)} batch files...")
                final_df = self._load_batches_from_files(batch_paths)
                if not final_df.empty:
                    final_df.drop_duplicates(inplace=True)
                    logger.info(f"Final dataframe contains {len(final_df)} rows after deduplication")
                self.cleanup_batches()
                return final_df
            logger.info("No data fetched for the given range")
            self.cleanup_batches()
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error in fetch_bulk: {e}")
            raise

    def _fetch_bulk_batches(self, conn: pymysql.Connection, query_template: str,
                             date_column: str, id_column: str,
                             start_date: datetime, end_date: datetime, on_batch=None):
        """The continuous (non-day-chunked) pagination loop backing fetch_bulk(). Returns
        (batch_paths, total_rows) — batch_paths stays empty when streaming via on_batch."""
        range_start = start_date.strftime('%Y-%m-%d 00:00:00')
        range_end = end_date.strftime('%Y-%m-%d 23:59:59')
        logger.info(f"Bulk fetch: {range_start} through {range_end}")

        batch_paths = []
        total_rows = 0
        has_more_data = True
        last_id = 0
        batch_count = 0

        while has_more_data:
            date_filter = (f"AND {date_column} >= '{range_start}' "
                            f"AND {date_column} <= '{range_end}' "
                            f"AND e.{id_column} > {last_id}")
            if "{batch_size}" in query_template:
                full_query = query_template.format(date_filter=date_filter, batch_size=self.batch_size)
            else:
                query = query_template.format(date_filter=date_filter)
                full_query = f"{query} ORDER BY e.{id_column} LIMIT {self.batch_size}"

            try:
                batch_df = pd.read_sql(full_query, conn)
                batch_df = batch_df.drop_duplicates(subset='obs_id')

                if batch_df.empty:
                    has_more_data = False
                    logger.info(f"Bulk fetch complete — {batch_count} batches fetched")
                else:
                    last_id = batch_df[id_column].max()
                    batch_size = len(batch_df)
                    total_rows += batch_size

                    if on_batch is not None:
                        logger.info(f"Streaming bulk batch {batch_count} ({batch_size} rows, last_id={last_id})...")
                        on_batch(batch_df)
                    else:
                        batch_filename = f"bulk_b{batch_count:05d}_{batch_size}.parquet"
                        batch_path = os.path.join(self.path, self.batch_folder, batch_filename)
                        batch_df.to_parquet(batch_path, index=False, engine='pyarrow')
                        logger.info(f"Saved bulk batch {batch_count}: {batch_path} ({batch_size} rows, last_id={last_id})")
                        batch_paths.append(batch_path)
                    batch_count += 1
                    del batch_df

            except Exception as e:
                logger.error(f"Error fetching bulk batch {batch_count}: {e}")
                import traceback
                traceback.print_exc()
                has_more_data = False

        return batch_paths, total_rows

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

    def fetch_tables(self, query: str, table_name: str, unique_index: str, last_id) -> int:
        if not self.duckdb_path:
            raise ValueError("fetch_tables() requires self.duckdb_path to be set")
        os.makedirs(os.path.dirname(self.duckdb_path), exist_ok=True)
        con = duckdb.connect(self.duckdb_path)
        try:
            table_exists = con.sql(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
                params=[table_name],
            ).fetchone()[0] > 0

            if table_exists:
                result = con.execute(f"SELECT MAX({unique_index}) FROM {table_name}").fetchone()
                if result and result[0] is not None:
                    last_id = result[0]

            full_query = query.format(last_id=last_id)

            if self.use_localhost:
                conn = self._get_db_connection()
                df = pd.read_sql(full_query, conn)
                conn.close()
            elif self.ssh_config:
                _tunnel_host, _tunnel_kwargs = self._build_tunnel_kwargs()
                with SSHTunnelForwarder(_tunnel_host, **_tunnel_kwargs) as tunnel:
                    conn = self._get_db_connection(tunnel)
                    df = pd.read_sql(full_query, conn)
                    conn.close()
            else:
                conn = self._get_db_connection()
                df = pd.read_sql(full_query, conn)
                conn.close()

            if df.empty:
                logger.info(f"fetch_tables: no new rows for {table_name}")
                return 0
            df = df.drop_duplicates(subset=unique_index)
            con.register("incoming_df", df)
            if not table_exists:
                con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM incoming_df")
                con.execute(f"CREATE UNIQUE INDEX idx_{table_name}_key ON {table_name} ({unique_index})")
            else:
                con.execute(f"""
                    INSERT INTO {table_name}
                    SELECT * FROM incoming_df
                    ON CONFLICT ({unique_index}) DO NOTHING
                """)
            logger.info(f"fetch_tables: inserted {len(df)} rows into {table_name}")
            return len(df)
        except Exception as e:
            logger.error(f"Error in fetch_tables for {table_name}: {e}")
            raise
        finally:
            con.close()

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
                           lookback_days=None, on_batch=None):
        """Fetch rows from `lookback_days` ago through today, regardless of what's already
        stored, so edits made in OpenMRS after the original fetch get picked up again and
        reconciled via upsert in DataStorageDuckDB. Paginates continuously by id_column (see
        fetch_bulk) rather than chunking by calendar day."""
        lookback_days = DUCKDB_LOOKBACK_DAYS if lookback_days is None else lookback_days
        lookback_start = datetime.now() - timedelta(days=lookback_days)
        configured_start = pd.to_datetime(self.start_date)
        effective_start = max(lookback_start, configured_start)
        return self.fetch_bulk(query_template, date_column=date_column, id_column=id_column,
                                start_date=effective_start, on_batch=on_batch)
