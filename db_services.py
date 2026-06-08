import pandas as pd
import os
from datetime import datetime, timedelta
import pymysql
from sshtunnel import SSHTunnelForwarder
import logging
import duckdb
import glob
from typing import Optional, Dict, Any, Generator
import warnings
warnings.filterwarnings("ignore")
from config import (BATCH_SIZE, DB_CONFIG, SSH_CONFIG, USE_LOCALHOST,
                    DB_CONFIG_LOCAL, START_DATE, LOAD_FRESH_DATA,DATA_PATH_)
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if LOAD_FRESH_DATA:
    # drop file latest_data_opd.parquet if exists in data folder
    file_path = os.path.join(os.getcwd(), DATA_PATH_)
    if os.path.exists(file_path):
        os.rename(file_path, f"{file_path}_backup")
        logger.info("Removed existing data file for fresh load.")

class DataFetcher:
    def __init__(self, use_localhost=USE_LOCALHOST, ssh_config=SSH_CONFIG, 
                 db_config=DB_CONFIG, db_config_local=DB_CONFIG_LOCAL,start_date=START_DATE, 
                 load_fresh_data=LOAD_FRESH_DATA, single_tables_folder="data/single_tables",
                 batch_size=BATCH_SIZE, batch_folder="data/batches"):
        self.use_localhost = use_localhost
        self.load_fresh_data = load_fresh_data
        self.ssh_config = ssh_config
        self.db_config = db_config
        self.db_config_local = db_config_local
        self.batch_size = batch_size
        self.batch_folder = batch_folder
        self.single_tables_folder = single_tables_folder
        self.start_date = start_date
        self.path = os.path.dirname(os.path.realpath(__file__))
        # Ensure batch folder exists
        os.makedirs(os.path.join(self.path, batch_folder), exist_ok=True)
    
    def _build_tunnel_kwargs(self) -> dict:
        """
        Build SSHTunnelForwarder keyword arguments from ssh_config.
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
            # Prepend the ssh/ directory if only a filename is given
            if not os.path.isabs(pkey_path) and not pkey_path.startswith('ssh/'):
                pkey_path = os.path.join('ssh', pkey_path)
            kwargs['ssh_pkey'] = pkey_path

        return (cfg['ssh_host'], ssh_port), kwargs

    def _get_db_connection(self, tunnel=None) -> pymysql.Connection:
        """
        Establish database connection with SSL support if configured
        Returns:
            pymysql.Connection: Database connection object
        """
        try:
            if not self.use_localhost and tunnel:
                # Remote connection through SSH tunnel
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
                # Direct connection with SSL
                conn = pymysql.connect(
                    host=self.db_config['host'],
                    port=self.db_config.get('port', 3306),
                    user=self.db_config['user'],
                    password=self.db_config['password'],
                    database=self.db_config['database'],
                    ssl=self.db_config['ssl'],  # SSL configuration dict
                    connect_timeout=60,
                    read_timeout=3600,
                )
            else:
                # Local connection (no SSL)
                conn = pymysql.connect(
                    host=self.db_config_local.get('host', 'localhost'),
                    port=self.db_config_local.get('port', 3306),
                    user=self.db_config_local['user'],
                    password=self.db_config_local['password'],
                    database=self.db_config_local['database'],
                    connect_timeout=30,
                    read_timeout=1800,
                )
            logger.info("Database connection established successfully")
            return conn
            
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def _get_max_date_from_parquet(self, parquet_file_path: str, date_column: str) -> Optional[datetime]:
        
        full_path = os.path.join(self.path, parquet_file_path)
        parquet_files = glob.glob(os.path.join(full_path, "*.parquet"))
        if not parquet_files:
            return self.start_date
        try:
            logger.info(f"Getting max from parquet using DuckDB")
            conn = duckdb.connect()
            file_list = "', '".join(parquet_files)
            query = f"SELECT MAX(Date) AS max_date FROM read_parquet(['{file_list}'], union_by_name=True)"
            result = conn.execute(query).df()
            conn.close()
            
            if not result.empty and not result['max_date'].isna().iloc[0]:
                max_date = pd.to_datetime(result['max_date'].iloc[0])
                logger.info(f"Found existing data up to {max_date}")
                return max_date
        except Exception as e:
            logger.warning(f"Could not read existing parquet file: {e}")
        
        return None
    
    def _load_batches_from_files(self, batch_paths: list) -> pd.DataFrame:
        """
        Load and concatenate all batch files into a single dataframe
        
        Args:
            batch_paths: List of batch file paths
            
        Returns:
            pd.DataFrame: Concatenated dataframe from all batches
        """
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
            else:
                logger.info("No valid batch files found")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"Error loading batches from files: {e}")
            raise
    
    def fetch_data(self, query_template: str, parquet_output: str, 
                   date_column: str = 'Date', 
                   id_column: str = 'encounter_id',
                   start_date: Optional[datetime] = None) -> pd.DataFrame:
        logging.info("Fetching Started...")

        # Determine start date
        if not self.load_fresh_data:
            max_date = self._get_max_date_from_parquet(parquet_output, date_column)
            start_date = max_date if isinstance(max_date, datetime) else pd.to_datetime(max_date)
        else:
            # convert start_date to datetime if it's a string
            start_date = self.start_date if isinstance(self.start_date, datetime) else pd.to_datetime(self.start_date)
            logger.info(f"Forced fresh load. Starting from {start_date}")
        
        
        # Collect all batch file paths (not dataframes)
        batch_paths = []
        
        try:
            # Get database connection and fetch batches
            if self.use_localhost:
                conn = self._get_db_connection()
                batch_paths = self._fetch_in_batches(conn, query_template, date_column, 
                                                     id_column, start_date)
                conn.close()
            elif self.ssh_config:
                _tunnel_host, _tunnel_kwargs = self._build_tunnel_kwargs()
                with SSHTunnelForwarder(_tunnel_host, **_tunnel_kwargs) as tunnel:
                    logger.info(f"SSH tunnel established on port {tunnel.local_bind_port}")
                    conn = self._get_db_connection(tunnel)
                    batch_paths = self._fetch_in_batches(conn, query_template, date_column,
                                                        id_column, start_date)
                    conn.close()
            else:
                conn = self._get_db_connection()
                batch_paths = self._fetch_in_batches(conn, query_template, date_column,
                                                    id_column, start_date)
                conn.close()
            
            # Load all batches from disk and merge into final dataframe
            if batch_paths:
                logger.info(f"Merging {len(batch_paths)} batch files...")
                final_df = self._load_batches_from_files(batch_paths)
                
                if not final_df.empty:
                    print("Final data before duplication =", len(final_df))
                    final_df.drop_duplicates(inplace=True)
                    logger.info(f"Final dataframe contains {len(final_df)} rows after deduplication")
                
                # Clean up batch files after successful merge
                self.cleanup_batches()
                return final_df
            else:
                logger.info("No new data fetched")
                self.cleanup_batches()
                return pd.DataFrame()  # Return empty DataFrame if no data fetched
                
        except Exception as e:
            logger.error(f"Error in fetch_data: {e}")
            raise
    
    def _fetch_in_batches(self, conn: pymysql.Connection, query_template: str,
                          date_column: str, id_column: str, start_date: datetime) -> list:
        """
        Fetch data in batches and save each batch as parquet file without storing in RAM
        
        Args:
            conn: Database connection
            query_template: SQL query template
            date_column: Date column name
            id_column: ID column name for pagination
            start_date: Start date for fetching
            
        Returns:
            list: List of saved batch file paths (not dataframes)
        """
        batch_paths = []  # Store only file paths, not dataframes
        current_date = start_date
        today = datetime.now()

        # print(current_date, type(today))
        
        while current_date.date() <= today.date():
            logger.info(f"Processing date: {current_date.strftime('%Y-%m-%d')}")
            
            date_str = current_date.strftime('%Y-%m-%d')
            date_start_midnight = current_date.strftime('%Y-%m-%d 00:00:00')
            date_end_midnight = current_date.strftime('%Y-%m-%d 23:59:59')
            has_more_data = True
            batch_count = 0
            last_id_for_date = 0
            
            while has_more_data:
                # Fetch batches for the current date only (midnight to 23:59:59)
                # Use encounter_id pagination to ensure no duplicates across batches
                date_filter = f"AND {date_column} >= '{date_start_midnight}' AND {date_column} <= '{date_end_midnight}' AND e.{id_column} > {last_id_for_date}"
                query = query_template.format(date_filter=date_filter)
                full_query = f"{query} ORDER BY e.{id_column} LIMIT {self.batch_size}"

                
                try:
                    batch_df = pd.read_sql(full_query, conn)
                    
                    if batch_df.empty:
                        has_more_data = False
                        logger.info(f"Completed {date_str} - {batch_count} batches fetched")
                    else:
                        # Update last_id_for_date to continue pagination within this date
                        last_id_for_date = batch_df[id_column].max()
                        batch_size = len(batch_df)
                        
                        # Save batch as parquet file
                        batch_filename = f"batch_{date_str}_b{batch_count:04d}_{batch_size}.parquet"
                        batch_path = os.path.join(self.path, self.batch_folder, batch_filename)
                        batch_df.to_parquet(batch_path, index=False, engine='pyarrow')
                        
                        logger.info(f"Saved batch {batch_count} for {date_str}: {batch_path} ({batch_size} rows)")
                        
                        # Store only the file path, not the dataframe
                        batch_paths.append(batch_path)
                        batch_count += 1
                        
                        # Explicitly delete the dataframe to free memory immediately
                        del batch_df
                        
                except Exception as e:
                    logger.error(f"Error fetching batch for {date_str}: {e}")
                    import traceback
                    traceback.print_exc()
                    has_more_data = False
            
            # Move to next day
            current_date += timedelta(days=1)
        
        return batch_paths  # Return list of file paths only
    
    def fetch_single_table(self, table_name: str, query: str,output_folder, output_format: str = 'csv') -> pd.DataFrame:
        """
        Fetch data from single table and save as CSV
        
        Args:
            table_name: Name of the output file (without extension)
            query: SQL query to execute
            output_format: Output format ('csv' or 'parquet')
            
        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Get database connection
            if self.use_localhost:
                conn = self._get_db_connection()
                df = pd.read_sql(query, conn)
                conn.close()
            elif self.ssh_config:
                _tunnel_host, _tunnel_kwargs = self._build_tunnel_kwargs()
                with SSHTunnelForwarder(_tunnel_host, **_tunnel_kwargs) as tunnel:
                    logger.info(f"SSH tunnel established on port {tunnel.local_bind_port}")
                    conn = self._get_db_connection(tunnel)
                    df = pd.read_sql(query, conn)
                    conn.close()
            else:
                conn = self._get_db_connection()
                df = pd.read_sql(query, conn)
                conn.close()
            
            # Save to file
            output_path = os.path.join(output_folder, f"{table_name}.{output_format}")
            # os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
            
            if output_format == 'csv':
                df.to_csv(output_path, index=False)
            elif output_format == 'parquet':
                df.to_parquet(output_path, index=False, engine='pyarrow')
            else:
                raise ValueError(f"Unsupported output format: {output_format}")
            
            logger.info(f"Saved {table_name} to {output_path} ({len(df)} rows)")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching single table {table_name}: {e}")
            raise
    
    def cleanup_batches(self):
        """
        Clean up all batch parquet files after successful merge
        """
        batch_dir = os.path.join(self.path, self.batch_folder)
        if not os.path.exists(batch_dir):
            return
        
        try:
            for filename in os.listdir(batch_dir):
                if filename.startswith('batch_') and filename.endswith('.parquet'):
                    file_path = os.path.join(batch_dir, filename)
                    os.remove(file_path)
                    logger.debug(f"Removed batch file: {filename}")
            logger.info(f"Cleaned up batch files from {batch_dir}")
        except Exception as e:
            logger.warning(f"Error cleaning up batch files: {e}")