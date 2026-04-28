import pandas as pd
import os
from datetime import datetime, timedelta
import socket
import pymysql
from sshtunnel import SSHTunnelForwarder
import tempfile
import pickle
import logging
import time

from config import DB_CONFIG, SSH_CONFIG, DB_CONFIG_LOCAL, START_DATE, LOAD_FRESH_DATA, DATE_, GENDER_, ENCOUNTER_ID_, DATA_FILE_NAME_

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
    """
    Robust DataFetcher with:
      - per-day batch parquet saving
      - safe read of main parquet (quarantines corrupted file)
      - rebuild main parquet from daily batches
      - recovery state to resume partially finished runs
      - automatic re-attempts when batch save/read fails
    """

    def __init__(self, use_localhost=False, ssh_config=SSH_CONFIG, db_config=DB_CONFIG,
                 max_batch_save_retries=3, batch_retry_delay=2):
        """
        Initialize DataFetcher with connection options

        Args:
            use_localhost: Boolean - True for local DB, False for remote
            ssh_config: SSH configuration for remote connection
            db_config: Database configuration
            max_batch_save_retries: how many times to retry saving/validating a batch parquet
            batch_retry_delay: seconds to wait between retries
        """
        self.use_localhost = use_localhost
        self.ssh_route = ssh_config if not use_localhost else None
        self.db_route = DB_CONFIG_LOCAL if use_localhost else db_config
        self.path = os.path.dirname(os.path.realpath(__file__))
        self.recovery_file = os.path.join(tempfile.gettempdir(), "data_fetch_recovery.pkl")
        self.max_batch_save_retries = max_batch_save_retries
        self.batch_retry_delay = batch_retry_delay

        # ensure data directories exist
        os.makedirs(os.path.join(self.path, "data", "batches"), exist_ok=True)

    def _get_db_connection(self, tunnel=None):
        """Establish database connection with error handling"""
        try:
            if not self.use_localhost:
                # Remote connection with SSH tunnel
                sock = socket.socket()
                sock.settimeout(30)
                sock.connect((self.db_route['host'], tunnel.local_bind_port))
                sock.close()

                conn = pymysql.connect(
                    host=self.db_route['host'],
                    port=tunnel.local_bind_port,
                    user=self.db_route['user'],
                    password=self.db_route['password'],
                    database=self.db_route['database'],
                    connect_timeout=60,
                    read_timeout=3600,
                    ssl={'ssl': {'fake_flag_to_enable_ssl': True}}
                )
            else:
                # Direct local connection
                conn = pymysql.connect(
                    host=self.db_route['host'],
                    port=self.db_route['port'],
                    user=self.db_route['user'],
                    password=self.db_route['password'],
                    database=self.db_route['database'],
                    connect_timeout=30,
                    read_timeout=1800
                )

            logger.info("✅ Database connection established")
            return conn
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise


    # Safe parquet helpers
    def safe_read_parquet(self, filepath):
        """
        Safe parquet reader. If read fails, move the corrupt file aside
        and return an empty DataFrame.
        """
        if not os.path.exists(filepath):
            return pd.DataFrame()

        try:
            return pd.read_parquet(filepath, engine="pyarrow")
        except Exception as e:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            corrupt_path = f"{filepath}.corrupt_{timestamp}"
            try:
                os.rename(filepath, corrupt_path)
                logger.error(f"❌ Parquet read failed and file moved to: {corrupt_path} — {e}")
            except Exception as ex:
                logger.error(f"Failed to rename corrupted parquet: {ex}. Original error: {e}")
            return pd.DataFrame()

    def _batch_file_path(self, current_date):
        """Return absolute path for a day's batch parquet file"""
        batch_dir = os.path.join(self.path, "data", "batches")
        return os.path.join(batch_dir, f"{current_date.strftime('%Y-%m-%d')}.parquet")

    def _save_daily_batch(self, df, current_date):
        """
        Save each day's batch as its own parquet file before merging.
        Includes automatic re-attempts on failure.
        Returns validated_df on success, None on persistent failure.
        """
        if df is None or df.empty:
            logger.debug("No data to save for date %s", current_date)
            return None

        batch_path = self._batch_file_path(current_date)

        attempt = 0
        while attempt < self.max_batch_save_retries:
            try:
                # Save batch file (atomic approach)
                temp_batch = f"{batch_path}.tmp"
                df.to_parquet(temp_batch, index=False, engine="pyarrow")
                os.replace(temp_batch, batch_path)
                logger.info(f"📦 Saved batch file: {batch_path} ({len(df)} rows)")

                # Validate by reading back
                validated_df = pd.read_parquet(batch_path, engine="pyarrow")
                # basic sanity check (non-empty)
                if validated_df is None or validated_df.empty:
                    raise ValueError("Validated batch read returned empty DataFrame")

                return validated_df

            except Exception as e:
                attempt += 1
                logger.error(f"Attempt {attempt}/{self.max_batch_save_retries} failed saving/validating "
                             f"batch {batch_path}: {e}")
                # try to cleanup temp file if exists
                try:
                    if os.path.exists(temp_batch):
                        os.remove(temp_batch)
                except Exception:
                    pass

                if attempt < self.max_batch_save_retries:
                    logger.info(f"Retrying in {self.batch_retry_delay}s...")
                    time.sleep(self.batch_retry_delay)

        # All retries failed: quarantine and return None
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            quarantined = f"{batch_path}.bad_{timestamp}"
            if os.path.exists(batch_path):
                os.replace(batch_path, quarantined)
            logger.error(f"All retries failed. Batch moved to {quarantined}")
        except Exception as ex:
            logger.error(f"Failed to quarantine bad batch file: {ex}")

        return None

    def rebuild_main_file_from_batches(self, main_file):
        """
        Rebuild the main parquet from saved daily batch parquets.
        Returns the rebuilt DataFrame (or empty df on failure).
        """
        batch_dir = os.path.join(self.path, "data", "batches")
        if not os.path.exists(batch_dir):
            logger.error("No batch directory exists to rebuild from.")
            return pd.DataFrame()

        batch_files = [os.path.join(batch_dir, f) for f in os.listdir(batch_dir)
                       if f.endswith(".parquet")]

        if not batch_files:
            logger.error("No batch files available for rebuild.")
            return pd.DataFrame()

        frames = []
        for bf in sorted(batch_files):
            try:
                df = pd.read_parquet(bf, engine="pyarrow")
                if not df.empty:
                    frames.append(df)
                else:
                    logger.warning(f"Skipping empty batch file {bf}")
            except Exception as e:
                logger.warning(f"Failed to load batch file {bf}: {e}")

        if not frames:
            logger.error("All batch files failed to load. Cannot rebuild.")
            return pd.DataFrame()

        final_df = pd.concat(frames, ignore_index=True).drop_duplicates()
        # Atomic write
        temp_main = f"{main_file}.tmp"
        try:
            final_df.to_parquet(temp_main, index=False, engine="pyarrow")
            os.replace(temp_main, main_file)
            logger.info(f"🎉 Main parquet rebuilt successfully from {len(frames)} batch files")
        except Exception as e:
            logger.error(f"Failed to write rebuilt main parquet: {e}")
            try:
                if os.path.exists(temp_main):
                    os.remove(temp_main)
            except Exception:
                pass
            return pd.DataFrame()

        return final_df

    # Recovery helpers
    def _save_recovery_state(self, state):
        """Save recovery state to file"""
        try:
            with open(self.recovery_file, 'wb') as f:
                pickle.dump(state, f)
        except Exception as e:
            logger.warning(f"Failed to save recovery state: {e}")

    def _load_recovery_state(self):
        """Load recovery state if exists"""
        if os.path.exists(self.recovery_file):
            try:
                with open(self.recovery_file, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                logger.warning(f"Failed to load recovery state: {e}")
        return None

    def _clear_recovery_state(self):
        """Clean up recovery file"""
        if os.path.exists(self.recovery_file):
            try:
                os.remove(self.recovery_file)
            except Exception:
                pass

    # Main process flow
    def fetch_data(self, query_template, filename='data/latest_data_opd.parquet',
                   date_column=DATE_, batch_size=5000, force_rebuild=False):
        """
        Robust incremental data fetcher with auto-rebuild capability

        Args:
            query_template: SQL query with {date_filter} placeholder
            filename: Relative path to output parquet file
            date_column: Date column for incremental loading
            batch_size: Number of records per batch
            force_rebuild: If True, will rebuild the file from scratch with default start date
        """
        # Create absolute path
        abs_filename = os.path.join(self.path, filename)
        os.makedirs(os.path.dirname(abs_filename), exist_ok=True)

        try:
            # 1. Determine start date
            file_exists = os.path.exists(abs_filename)
            if force_rebuild or not file_exists or not self._is_existing_file_valid(abs_filename, date_column):
                logger.warning("Starting fresh rebuild (force rebuild or missing/invalid file)")
                start_date = START_DATE  # Default start date for rebuilds
                if file_exists:
                    # safe_read_parquet would have moved corrupt file; ensure removal for fresh rebuild
                    try:
                        os.remove(abs_filename)
                    except Exception:
                        pass
                self._clear_recovery_state()
            else:
                start_date = self._get_last_extraction_date(abs_filename, date_column)
                if start_date is None:
                    # fallback
                    start_date = START_DATE

            # 2. Process in batches with recovery
            if self.use_localhost:
                conn = self._get_db_connection()
                try:
                    final_df = self._process_daily_batches(conn, query_template, abs_filename,
                                                          date_column, batch_size, start_date)
                finally:
                    conn.close()
            elif self.ssh_route and "ssh_password" in self.ssh_route:
                logger.info("Using password for SSH")
                with SSHTunnelForwarder(
                        (self.ssh_route['ssh_host'], 22),
                        ssh_username=self.ssh_route['ssh_user'],
                        ssh_password=self.ssh_route['ssh_password'],
                        remote_bind_address=self.ssh_route['remote_bind_address']
                ) as tunnel:
                    logger.info(f"SSH tunnel established on port {tunnel.local_bind_port}")
                    conn = self._get_db_connection(tunnel)
                    try:
                        final_df = self._process_daily_batches(conn, query_template, abs_filename,
                                                              date_column, batch_size, start_date)
                    finally:
                        conn.close()
            else:
                logger.info("Using private key for SSH")
                with SSHTunnelForwarder(
                        (self.ssh_route['ssh_host'], 22),
                        ssh_username=self.ssh_route['ssh_user'],
                        ssh_private_key=f"ssh/{self.ssh_route['ssh_pkey']}",
                        remote_bind_address=self.ssh_route['remote_bind_address']
                ) as tunnel:
                    logger.info(f"SSH tunnel established on port {tunnel.local_bind_port}")
                    conn = self._get_db_connection(tunnel)
                    try:
                        final_df = self._process_daily_batches(conn, query_template, abs_filename,
                                                              date_column, batch_size, start_date)
                    finally:
                        conn.close()

            return self._finalize_operation(final_df, abs_filename)

        except Exception as e:
            logger.error(f"Data fetch failed: {e}")
            logger.info("Recovery data preserved. Will resume from last batch.")
            raise
    def fetch_single_table(self, single_table_name, single_table_query):
        """
        Robust incremental data fetcher with auto-rebuild capability
        
        Args:
            query_template: SQL query with {date_filter} placeholder
            filename: Relative path to output CSV file
            date_column: Date column for incremental loading
            batch_size: Number of records per batch
            force_rebuild: If True, will rebuild the file from scratch with default start date 2025-01-01
        """
        
        try:
            
            if self.use_localhost:
                conn = self._get_db_connection()
                try:
                    table_df = pd.read_sql(single_table_query, conn)
                    table_df.to_csv(os.path.join(self.path, single_table_name))
                finally:
                    conn.close()
            elif "ssh_password" in self.ssh_route:
                print("Using password for SSH")
                # Remote connection with SSH tunnel using password
                with SSHTunnelForwarder(
                    (self.ssh_route['ssh_host'], 22),
                    ssh_username=self.ssh_route['ssh_user'],
                    ssh_password=self.ssh_route['ssh_password'],
                    remote_bind_address=self.ssh_route['remote_bind_address']
                ) as tunnel:
                    logger.info(f"SSH tunnel established on port {tunnel.local_bind_port}")
                    conn = self._get_db_connection(tunnel)
                    try:
                        table_df = pd.read_sql(single_table_query, conn)
                        table_df.to_csv(os.path.join(self.path, single_table_name))
                    finally:
                        conn.close()
            else:
                print("Using private key for SSH")

                print(f"ssh/{self.ssh_route['ssh_pkey']}")
                # Remote connection with SSH tunnel
                with SSHTunnelForwarder(
                    (self.ssh_route['ssh_host'], 22),
                    ssh_username=self.ssh_route['ssh_user'],
                    ssh_private_key=f"ssh/{self.ssh_route['ssh_pkey']}",
                    # ssh_password=self.ssh_route['ssh_password'],
                    remote_bind_address=self.ssh_route['remote_bind_address']
                ) as tunnel:
                    logger.info(f"SSH tunnel established on port {tunnel.local_bind_port}")
                    conn = self._get_db_connection(tunnel)
                    try:
                        table_df = pd.read_sql(single_table_query, conn)
                        table_df.to_csv(os.path.join(self.path, single_table_name))
                    finally:
                        conn.close()
            
            return table_df
            
        except Exception as e:
            logger.error(f"Data fetch failed: {e}")
            raise
        
    def _process_daily_batches(self, conn, query_template, filename, date_column, batch_size, start_date):
        """Process data day by day with batch processing within each day"""
        recovery_state = self._load_recovery_state()

        # LOAD EXISTING DATA FIRST (using safe reader)
        existing_df = self.safe_read_parquet(filename)
        if existing_df.empty and os.path.exists(os.path.join(self.path, "data", "batches")):
            # try to rebuild from batches if existing read failed/returned empty
            logger.warning("Main parquet empty/corrupt — attempting rebuild from batches...")
            rebuilt = self.rebuild_main_file_from_batches(filename)
            if not rebuilt.empty:
                existing_df = rebuilt

        if recovery_state:
            # if recovery contains partial df, it's only new data not yet merged into main file
            current_date = pd.to_datetime(recovery_state.get('current_date'))
            new_data_df = recovery_state.get('df', pd.DataFrame())
            last_id = recovery_state.get('last_id', 0)
            # ensure new_data_df is DataFrame
            if not isinstance(new_data_df, pd.DataFrame):
                new_data_df = pd.DataFrame(new_data_df)
        else:
            current_date = pd.to_datetime(start_date)
            new_data_df = pd.DataFrame()
            last_id = 0

        # COMBINE EXISTING AND NEW DATA (safe)
        if not existing_df.empty and not new_data_df.empty:
            final_df = pd.concat([existing_df, new_data_df], ignore_index=True).drop_duplicates()
            final_df[DATE_] = pd.to_datetime(final_df[DATE_], format='mixed')
            final_df[GENDER_] = final_df[GENDER_].replace({"M":"Male","F":"Female"})
        elif not existing_df.empty:
            final_df = existing_df.copy()
        elif not new_data_df.empty:
            final_df = new_data_df.copy()
        else:
            final_df = pd.DataFrame()

        today = datetime.now().date()
        # Iterate through each day from start_date to today
        while current_date.date() <= today:
            logger.info(f"Processing date: {current_date.strftime('%Y-%m-%d')}")

            # Process all batches for the current day
            day_new_df = self._process_single_day(conn, query_template, date_column,
                                                 batch_size, current_date, last_id)

            if not day_new_df.empty:
                # 1️⃣ Save daily batch to dedicated file and validate read-back (with retries)
                validated_batch = self._save_daily_batch(day_new_df, current_date)

                # 2️⃣ Only merge validated parquet batch
                if validated_batch is not None:
                    # Append validated batch into final_df
                    if final_df.empty:
                        final_df = validated_batch.copy()
                    else:
                        final_df = pd.concat([final_df, validated_batch], ignore_index=True).drop_duplicates()

                    # Update last processed ID for recovery
                    if ENCOUNTER_ID_ in validated_batch.columns:
                        last_id = validated_batch[ENCOUNTER_ID_].max()

                    # Save intermediate results and recovery state
                    self._save_recovery_state({
                        'current_date': current_date,
                        'last_id': last_id,
                        'df': validated_batch  # Store only new data for recovery
                    })

                    # 3️⃣ Save the COMBINED DATA (existing + new) atomically
                    try:
                        temp_main = f"{filename}.tmp"
                        final_df.to_parquet(temp_main, index=False, engine="pyarrow")
                        os.replace(temp_main, filename)
                    except Exception as e:
                        logger.error(f"Failed to write combined main parquet: {e}")
                        # Attempt to rebuild from batches as fallback
                        logger.info("Attempting rebuild of main parquet from batches as fallback...")
                        rebuilt = self.rebuild_main_file_from_batches(filename)
                        if not rebuilt.empty:
                            final_df = rebuilt
                        else:
                            logger.error("Rebuild failed; keeping current final_df in memory and saving recovery state.")

                    logger.info(f"Completed date {current_date.strftime('%Y-%m-%d')}. Total records: {len(final_df)}")

                else:
                    logger.error(f"❌ Batch for {current_date.strftime('%Y-%m-%d')} skipped due to validation failure.")

            # Move to next day and reset last_id
            current_date += timedelta(days=1)
            last_id = 0
            
        # Cleanup batch files at the end of the run regardless of outcome
            try:
                self._cleanup_batches()
            except Exception as e:
                logger.warning(f"Batch cleanup encountered an error: {e}")
        return final_df

    def _process_single_day(self, conn, query_template, date_column, batch_size, current_date, last_id=0):
        """Process all records for a single day in batches"""
        day_df = pd.DataFrame()
        processed_count = 0

        while True:
            # Build query for current batch
            date_str = current_date.strftime('%Y-%m-%d')
            date_filter = f"AND DATE(e.encounter_datetime) = '{date_str}' AND e.encounter_id > {last_id} "
            query = query_template.format(date_filter=date_filter)
            batch_query = f"{query} ORDER BY encounter_id LIMIT {batch_size}"

            logger.debug(f"Fetching batch for {date_str} from ID {last_id}")
            try:
                # Debug: print the actual query being executed
                batch_df = pd.read_sql(batch_query, conn)
            except Exception as e:
                logger.error(f"SQL read failed for date {date_str}: {e}")
                break

            if batch_df.empty:
                break

            day_df = pd.concat([day_df, batch_df], ignore_index=True)
            processed_count += len(batch_df)

            # Update last ID for next batch
            if not batch_df.empty and ENCOUNTER_ID_ in batch_df.columns:
                last_id = batch_df[ENCOUNTER_ID_].max()

            logger.info(f"Processed {processed_count} records for {date_str}")

        return day_df

    def _finalize_operation(self, final_df, filename):
        """Complete the operation with final checks and cleanup"""
        if not final_df.empty:
            # save final data using atomic write (also attempt to merge with existing safe_read)
            try:
                self._save_final_data(final_df, filename)
                logger.info(f"Data update complete. Total records: {len(final_df)}")
                self._clear_recovery_state()
            except Exception as e:
                logger.error(f"Failed final save: {e}")
                # Try rebuild
                logger.info("Attempting to rebuild main parquet from batches after final save failure...")
                rebuilt = self.rebuild_main_file_from_batches(filename)
                if not rebuilt.empty:
                    logger.info("Rebuild succeeded during finalization.")
                    final_df = rebuilt
                    self._clear_recovery_state()
                else:
                    logger.error("Finalization rebuild failed.")
        else:
            logger.info("No new data found.")

        return final_df

    def _is_existing_file_valid(self, filepath, date_column):
        """Check if existing Parquet file is valid and can be used for incremental update"""
        if not os.path.exists(filepath):
            return False

        try:
            # Read only the date column metadata to verify structure
            columns = pd.read_parquet(filepath, engine="pyarrow", columns=[date_column])
            # Ensure column exists & not empty
            if date_column not in columns.columns:
                return False
            if columns.empty:
                return False
            # quick parse
            pd.to_datetime(columns[date_column].head(1))
            return True
        except Exception as e:
            logger.warning(f"Existing file validation failed: {e}")
            # attempt to quarantine the file
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                corrupt_path = f"{filepath}.corrupt_{timestamp}"
                os.rename(filepath, corrupt_path)
                logger.warning(f"Existing main parquet moved to {corrupt_path} during validation")
            except Exception:
                pass
            return False

    def _get_last_extraction_date(self, file_path, date_column):
        """Safely get the last extraction date from existing Parquet"""
        try:
            df = pd.read_parquet(file_path, columns=[date_column], engine="pyarrow")
            df = df[df[date_column]<=pd.Timestamp.now().normalize()]
            if not df.empty and date_column in df:
                last_date = pd.to_datetime(df[date_column]).max()
                return last_date.strftime('%Y-%m-%d')
        except Exception as e:
            logger.warning(f"Could not read last date from Parquet: {e}")
        return None

    def _save_final_data(self, df, filename):
        """Atomic save operation that preserves existing data (Parquet)"""
        temp_file = f"{filename}.tmp"
        try:
            # Merge with existing safely if exists
            if os.path.exists(filename):
                try:
                    existing_df = self.safe_read_parquet(filename)
                    if not existing_df.empty:
                        df = pd.concat([existing_df, df], ignore_index=True).drop_duplicates()
                except Exception as e:
                    logger.warning(f"Failed to merge with existing file: {e}")

            # Save to temp parquet
            df.to_parquet(temp_file, index=False, engine="pyarrow")

            # Atomic rename
            os.replace(temp_file, filename)

            # Save timestamp
            timestamp_file = os.path.join(self.path, 'data', 'TimeStamp.csv')
            os.makedirs(os.path.dirname(timestamp_file), exist_ok=True)
            pd.DataFrame({'saving_time': [datetime.now().strftime("%d/%m/%Y, %H:%M:%S")]}).to_csv(timestamp_file, index=False)

        except Exception as e:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
            raise
    def _cleanup_batches(self):
        """
        Remove all batch parquet files that were saved during the run.
        This deletes files inside data/batches only—no other folders are touched.
        Deletes:
        - *.parquet
        - *.tmp
        - files containing '.bad_' or '.corrupt_' in filename
        """
        # Explicit expected path for safety
        expected_batch_dir = os.path.join(self.path, "data", "batches")
        batch_dir = expected_batch_dir  # keep naming consistent

        # Safety check: ensure we never try to clean any other path
        if not os.path.exists(batch_dir):
            logger.debug("No batch directory to clean.")
            return

        # Confirm we are operating on the intended directory (extra safety)
        abs_expected = os.path.abspath(expected_batch_dir)
        abs_batch_dir = os.path.abspath(batch_dir)
        if abs_expected != abs_batch_dir:
            logger.error("Batch cleanup path mismatch — aborting cleanup for safety.")
            return

        removed = 0
        for fname in os.listdir(batch_dir):
            fpath = os.path.join(batch_dir, fname)
            try:
                # Only remove files that match the batch-related patterns
                if not os.path.isfile(fpath):
                    continue
                if (fname.endswith(".parquet") or fname.endswith(".tmp") or
                        ".bad_" in fname or ".corrupt_" in fname):
                    os.remove(fpath)
                    removed += 1
                    logger.debug(f"Removed batch file: {fpath}")
            except Exception as e:
                logger.warning(f"Failed to remove batch file {fpath}: {e}")

        logger.info(f"Cleaned up {removed} batch files from {batch_dir}")
