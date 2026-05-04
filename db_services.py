import pandas as pd
import os
from datetime import datetime, timedelta
import pymysql
from sshtunnel import SSHTunnelForwarder
import logging
from typing import Optional, Dict, Any, Generator

from config import (BATCH_SIZE, DB_CONFIG, SSH_CONFIG, USE_LOCALHOST,
                    DB_CONFIG_LOCAL, START_DATE, 
                    LOAD_FRESH_DATA, DATE_, GENDER_, 
                    ENCOUNTER_ID_, DATA_FILE_NAME_)
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if LOAD_FRESH_DATA:
    # drop file latest_data_opd.parquet if exists in data folder
    file_path = os.path.join(os.getcwd(), "data", DATA_FILE_NAME_)
    if os.path.exists(file_path):
        os.rename(file_path, f"{file_path}.backup")
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
        if not os.path.exists(full_path):
            return self.start_date
        try:
            df = pd.read_parquet(full_path, engine='pyarrow')
            if not df.empty and date_column in df.columns:
                max_date = pd.to_datetime(df[date_column]).max()
                logger.info(f"Found existing data up to {max_date}")
                return max_date
        except Exception as e:
            logger.warning(f"Could not read existing parquet file: {e}")
        
        return None
    
    def fetch_data(self, query_template: str, parquet_output: str, 
                   date_column: str = 'Date', 
                   id_column: str = 'encounter_id',
                   start_date: Optional[datetime] = None) -> pd.DataFrame:

        # Determine start date
        if not self.load_fresh_data:
            max_date = self._get_max_date_from_parquet(parquet_output, "Date")
            start_date = max_date if isinstance(max_date, datetime) else pd.to_datetime(max_date)
        else:
            # convert start_date to datetime if it's a string
            start_date = self.start_date if isinstance(self.start_date, datetime) else pd.to_datetime(self.start_date)
            logger.info(f"Forced fresh load. Starting from {start_date}")
        
        
        # Collect all batches
        all_batches = []
        batch_number = 0
        
        try:
            # Get database connection
            if self.use_localhost:
                conn = self._get_db_connection()
                all_batches = self._fetch_in_batches(conn, query_template, date_column, 
                                                     id_column, start_date)
                conn.close()
            elif self.ssh_config:
                with SSHTunnelForwarder(
                    (self.ssh_config['ssh_host'], 22),
                    ssh_username=self.ssh_config['ssh_user'],
                    ssh_password=self.ssh_config.get('ssh_password'),
                    ssh_private_key=f"ssh/{self.ssh_config['ssh_pkey']}",
                    remote_bind_address=self.ssh_config['remote_bind_address']
                ) as tunnel:
                    logger.info(f"SSH tunnel established on port {tunnel.local_bind_port}")
                    conn = self._get_db_connection(tunnel)
                    all_batches = self._fetch_in_batches(conn, query_template, date_column,
                                                        id_column, start_date)
                    conn.close()
            else:
                conn = self._get_db_connection()
                all_batches = self._fetch_in_batches(conn, query_template, date_column,
                                                    id_column, start_date)
                conn.close()
            
            # Merge all batches and save final parquet
            if all_batches:
                final_df = pd.concat(all_batches, ignore_index=True)
                final_df.drop_duplicates(inplace=True)
                self.cleanup_batches()  # Clean up batch files after merging
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
        Fetch data in batches and save each batch as parquet file
        
        Args:
            conn: Database connection
            query_template: SQL query template
            date_column: Date column name
            id_column: ID column name for pagination
            start_date: Start date for fetching
            
        Returns:
            list: List of dataframes for each batch
        """
        batches = []
        last_id = 0
        current_date = start_date
        today = datetime.now()

        print(current_date, type(today))
        
        while current_date.date() <= today.date():
            logger.info(f"Processing date: {current_date.strftime('%Y-%m-%d')}")
            
            date_str = current_date.strftime('%Y-%m-%d')
            has_more_data = True
            batch_count = 0
            
            while has_more_data:
                # Build query with date filter and ID pagination
                date_filter = f"AND DATE({date_column}) = '{date_str}' AND e.{id_column} > {last_id}"
                query = query_template.format(date_filter=date_filter)
                full_query = f"{query} ORDER BY e.{id_column} LIMIT {self.batch_size}"

                # print(full_query)  # Debug: print the full query being executed
                
                try:
                    batch_df = pd.read_sql(full_query, conn)
                    
                    if batch_df.empty:
                        has_more_data = False
                        logger.info(f"Completed {date_str} - {batch_count} batches fetched")
                    else:
                        # Save batch as parquet file
                        batch_filename = f"batch_{date_str}_{len(batch_df)}.parquet"
                        batch_path = os.path.join(self.path, self.batch_folder, batch_filename)
                        batch_df.to_parquet(batch_path, index=False, engine='pyarrow')
                        # batch_df.to_csv(batch_path, index=False)
                        logger.info(f"Saved batch {batch_count} for {date_str}: {batch_path} ({len(batch_df)} rows)")
                        
                        batches.append(batch_df)
                        last_id = batch_df[id_column].max()
                        batch_count += 1
                        # print(last_id)
                        
                except Exception as e:
                    logger.error(f"Error fetching batch for {date_str}: {e}")
                    import traceback
                    traceback.print_exc()
                    has_more_data = False
            
            # Move to next day, reset last_id
            current_date += timedelta(days=1)
            last_id = 0
        
        return batches
    
    def fetch_single_table(self, table_name: str, query: str, output_format: str = 'csv') -> pd.DataFrame:
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
                with SSHTunnelForwarder(
                    (self.ssh_config['ssh_host'], 22),
                    ssh_username=self.ssh_config['ssh_user'],
                    ssh_password=self.ssh_config.get('ssh_password'),
                    ssh_private_key=f"ssh/{self.ssh_config['ssh_pkey']}",
                    remote_bind_address=self.ssh_config['remote_bind_address']
                ) as tunnel:
                    logger.info(f"SSH tunnel established on port {tunnel.local_bind_port}")
                    conn = self._get_db_connection(tunnel)
                    df = pd.read_sql(query, conn)
                    conn.close()
            else:
                conn = self._get_db_connection()
                df = pd.read_sql(query, conn)
                conn.close()
            
            # Save to file
            output_path = os.path.join(self.path, self.single_tables_folder, f"{table_name}.{output_format}")
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
            
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