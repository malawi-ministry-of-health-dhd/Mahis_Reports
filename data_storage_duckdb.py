import os
import re
import json
import duckdb
import pandas as pd
import config as cfg
from db_services_duckdb import DataFetcherDuckDB

CONFIGURATIONS_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "configurations.json")

# Every existing DataStorage.query_duckdb call site embeds the route straight into the SQL
# text — e.g. f"SELECT ... FROM '{data_path}'" where data_path is often built per-request
# from a URL param (f"data/{route}/parquet"), not passed as a separate argument. A data_dir
# *parameter* can never track that; these two patterns detect it the same way
# data_storage.py's _expand_dir_paths does, so query_duckdb stays a true drop-in replacement.
_FROM_READ_PARQUET_RE = re.compile(r"FROM\s+read_parquet\(\s*(['\"])(.+?)\1[^()]*\)", re.IGNORECASE)
_FROM_QUOTED_PATH_RE = re.compile(r"FROM\s+(['\"])(.+?)\1", re.IGNORECASE)
_ROUTE_IN_PATH_RE = re.compile(r"data/([^/'\"]+)/parquet")


def _extract_route_and_rewrite(sql):
    """Find a data/<route>/parquet reference embedded in the SQL (bare quoted directory or a
    read_parquet(...) call) and rewrite that FROM clause to reference the persisted table
    instead. Returns (route, rewritten_sql), or (None, sql) unchanged if no such reference is
    found (e.g. the caller already wrote table-native SQL)."""
    for pattern in (_FROM_READ_PARQUET_RE, _FROM_QUOTED_PATH_RE):
        match = pattern.search(sql)
        if not match:
            continue
        route_match = _ROUTE_IN_PATH_RE.search(match.group(2))
        if not route_match:
            continue
        rewritten, _n = pattern.subn(f"FROM {cfg.DUCKDB_TABLE_NAME}", sql)
        return route_match.group(1), rewritten
    return None, sql


def _normalize_route(value):
    """Accept either a bare route name ('mahisuat') or a full path ('data/mahisuat') and
    return the bare route name."""
    value = value.strip("/")
    if value.startswith("data/"):
        value = value[len("data/"):]
    return value


def load_or_create_configurations():
    """Same configurations.json used by data_storage.py's __main__ — shared data, not code.
    Creates a single default entry (mirroring data_storage.py's fallback) if the file doesn't
    exist yet."""
    if os.path.exists(CONFIGURATIONS_PATH):
        with open(CONFIGURATIONS_PATH) as f:
            configurations = json.load(f)
        # JSON serialises tuples as arrays; restore remote_bind_address to a tuple
        for item in configurations:
            ssh = item.get("ssh_config")
            if isinstance(ssh, dict) and isinstance(ssh.get("remote_bind_address"), list):
                ssh["remote_bind_address"] = tuple(ssh["remote_bind_address"])
        return configurations

    configurations = [{
        "uuid": "uuid_default",
        "name": "Default Configuration",
        "use_localhost": cfg.USE_LOCALHOST,
        "start_date": cfg.START_DATE,
        "load_fresh_data": cfg.LOAD_FRESH_DATA,
        "data_path": "default",
        "base_query": cfg.NEW_HARMONIZED_QUERY,
        "pause_data_source": False,
        "batch_size": cfg.BATCH_SIZE,
        "db_config": cfg.DB_CONFIG,
        "ssh_config": None if cfg.USE_LOCALHOST else cfg.SSH_CONFIG,
    }]
    with open(CONFIGURATIONS_PATH, 'w') as f:
        json.dump(configurations, f, indent=2)
    return configurations


# (csv filename without extension, query, dict key column, dict value column)
_SINGLE_TABLE_SPECS = [
    ("programs_data",        cfg.QUERY_PROGRAMS,        "program_id",       "name"),
    ("concept_names_data",   cfg.QUERY_CONCEPT_NAMES,   "concept_id",       "name"),
    ("encounter_types_data", cfg.QUERY_ENCOUNTER_TYPES, "encounter_type_id", "name"),
    ("locations_data",       cfg.QUERY_LOCATIONS,       "location_id",      "name"),
    ("drugs_data",           cfg.QUERY_DRUGS,           "drug_id",          "name"),
    ("order_types_data",     cfg.QUERY_ORDER_TYPES,     "order_type_id",    "name"),
    ("users_data",           cfg.QUERY_USERS,           "user_id",          "User"),
    ("user_programs_data",   cfg.QUERY_USER_PROGRAMS,   None,               None),  # fetched for parity; unused by harmonize (matches data_storage.py)
]
if not cfg.IS_HARMONIZED_MAHIS:
    _SINGLE_TABLE_SPECS.insert(4, ("facilities_data", cfg.QUERY_FACILITIES, "code", "name"))

# Datetime columns produced by NEW_HARMONIZED_QUERY that come from LEFT JOINs (visit, obs,
# orders) and so can be entirely NULL within any one small batch. pandas then infers those
# columns as dtype 'object' (all-None) rather than datetime64, which DuckDB in turn registers
# as INTEGER on first CREATE TABLE — a later batch with real timestamps then fails to
# insert/upsert with "Conversion Error: Unimplemented type for cast (TIMESTAMP_NS -> INTEGER)".
# Coercing explicitly keeps the dtype (and therefore the DuckDB column type) consistent across
# batches regardless of which batch happens to create the table.
_DATETIME_COLUMNS = ["date_started", "date_stopped", "birthdate", "Date", "obs_datetime", "value_datetime"]


class DataStorage:
    def __init__(self, data_dir=cfg.DATA_PATH_, db_config=cfg.DB_CONFIG, ssh_config=cfg.SSH_CONFIG,
                 load_fresh_data=cfg.LOAD_FRESH_DATA, use_localhost=cfg.USE_LOCALHOST,
                 batch_size=cfg.BATCH_SIZE, start_date=cfg.START_DATE,
                 table_name=cfg.DUCKDB_TABLE_NAME, key_columns=None):
        self.script_dir = os.path.dirname(os.path.realpath(__file__))
        self.duckdb_dir = os.path.join(self.script_dir, data_dir, cfg.DUCKDB_DIR_NAME)
        self.tables_dir = os.path.join(self.duckdb_dir, "single_tables")
        os.makedirs(self.duckdb_dir, exist_ok=True)
        os.makedirs(self.tables_dir, exist_ok=True)
        self.db_path = os.path.join(self.duckdb_dir, cfg.DUCKDB_FILE_NAME)

        self.table_name = table_name
        self.key_columns = key_columns or cfg.DUCKDB_KEY_COLUMNS
        self.db_config = db_config
        self.ssh_config = ssh_config
        self.load_fresh_data = load_fresh_data
        self.use_localhost = use_localhost
        self.batch_size = batch_size
        self.start_date = start_date

    @classmethod
    def from_config_entry(cls, entry):
        """Build an instance from one configurations.json entry."""
        return cls(
            data_dir=f"data/{entry.get('data_path')}",
            db_config=entry.get("db_config"),
            ssh_config=entry.get("ssh_config"),
            load_fresh_data=entry.get("load_fresh_data", True),
            use_localhost=entry.get("use_localhost", True),
            batch_size=entry.get("batch_size", 1000),
            start_date=entry.get("start_date", "2026-01-01"),
        )

    def _make_fetcher(self):
        return DataFetcherDuckDB(
            use_localhost=self.use_localhost, ssh_config=self.ssh_config, db_config=self.db_config,
            start_date=self.start_date, load_fresh_data=self.load_fresh_data,
            batch_size=self.batch_size, batch_folder=os.path.join(self.duckdb_dir, "_tmp_batches"),
            duckdb_path=self.db_path, duckdb_table=self.table_name,
        )

    def fetch_single_tables(self, fetcher=None):
        """Fetch each lookup/dimension table fresh and save it as CSV under
        data/<route>/duckdb/single_tables/ — separate from data_storage.py's own
        data/<route>/single_tables/, so the two pipelines never interfere with each other.
        Returns {csv_name: DataFrame}."""
        fetcher = fetcher or self._make_fetcher()
        tables = {}
        for csv_name, query, *_ in _SINGLE_TABLE_SPECS:
            df = fetcher.fetch_single_table(csv_name, query)
            df.to_csv(os.path.join(self.tables_dir, f"{csv_name}.csv"), index=False)
            tables[csv_name] = df
        return tables

    def _load_single_tables_from_csv(self):
        """Read back whatever single tables are on disk (from the most recent
        fetch_single_tables() call, this run or a previous one)."""
        tables = {}
        for csv_name, *_ in _SINGLE_TABLE_SPECS:
            path = os.path.join(self.tables_dir, f"{csv_name}.csv")
            if os.path.exists(path):
                tables[csv_name] = pd.read_csv(path)
        return tables

    def harmonize(self, df: pd.DataFrame, tables: dict) -> pd.DataFrame:
        """Map raw OpenMRS IDs to names, using pandas .map() against the small lookup tables
        already fetched to CSV — the same approach data_storage.py uses. For this shape (a
        large transactional batch joined against small dimension tables that fit comfortably
        in memory), vectorized dict lookups are as fast as or faster than a SQL join's
        round-trip/plan overhead, and they make it straightforward to preserve the exact same
        value-resolution order as data_storage.py (see the note on Service_Area below).

        NOTE: replicates data_storage.py's existing order exactly, including one quirk worth
        flagging — Service_Area is computed from the *raw* Encounter id (Encounter isn't
        mapped to its name until the line after), so CUSTOM_MNID_MAP_SERVICE_AREA (keyed by
        encounter type *names* like "ANC VISIT") never actually matches anything there and it
        silently falls back to Program every time. Kept as-is for parity with data_storage.py
        rather than silently changed — flag it if that's not intended and I'll fix both.
        """
        if df is None or df.empty:
            return df

        df = df.copy()

        def dict_from(csv_name, key_col, val_col):
            t = tables.get(csv_name)
            if t is None or key_col not in t.columns or val_col not in t.columns:
                return {}
            return t.set_index(key_col)[val_col].to_dict()

        programs_dict        = dict_from("programs_data", "program_id", "name")
        concepts_dict         = dict_from("concept_names_data", "concept_id", "name")
        encounter_types_dict  = dict_from("encounter_types_data", "encounter_type_id", "name")
        drugs_name_dict       = dict_from("drugs_data", "drug_id", "name")
        drugs_unit_dict       = dict_from("drugs_data", "drug_id", "units")
        order_type_dict       = dict_from("order_types_data", "order_type_id", "name")
        username_dict         = dict_from("users_data", "user_id", "User")

        locations_t = tables.get("locations_data")
        facilities_t = tables.get("facilities_data")
        if facilities_t is not None:
            facilities_t = facilities_t.copy()
            facilities_t["code"] = facilities_t["code"].astype(str)
            facilities_dict = facilities_t.set_index("code")["name"].to_dict()
            facility_districts_dict = facilities_t.set_index("code")["district"].to_dict()
        elif locations_t is not None:
            locations_t = locations_t.copy()
            locations_t["location_id"] = locations_t["location_id"].astype(str)
            facilities_dict = locations_t.set_index("location_id")["name"].to_dict()
            facility_districts_dict = locations_t.set_index("location_id")["county_district"].to_dict()
        else:
            facilities_dict = {}
            facility_districts_dict = {}

        df["Gender"] = df["Gender"].map(cfg.CUSTOM_GENDER_MAP).fillna(df["Gender"])
        df["Program"] = df["Program"].map(programs_dict)
        df["Source_Program"] = df["Program"]
        df["Reporting_Program"] = df["Source_Program"].map(cfg.CUSTOM_MNID_MAP_PROGRAM).fillna(df["Source_Program"])
        df["Service_Area"] = (df["Encounter"].map(cfg.CUSTOM_MNID_MAP_SERVICE_AREA)
                               .map({"NEONATAL PROGRAM": "NEONATAL"}).fillna(df["Program"]))
        df["new_revisit"] = ""
        df["concept_name"] = df["concept_name"].map(concepts_dict)
        df["obs_value_coded"] = df["obs_value_coded"].map(concepts_dict)
        df["Encounter"] = df["Encounter"].map(encounter_types_dict)
        df["DrugUnits"] = df["DrugName"].map(drugs_unit_dict)
        df["DrugName"] = df["DrugName"].map(drugs_name_dict)
        df["User"] = df["creator"].map(username_dict)
        df["Facility_CODE"] = df["location_id"]
        df["Facility"] = df["Facility_CODE"].map(facilities_dict)
        df["District"] = df["Facility_CODE"].map(facility_districts_dict)
        df["Order_Type"] = df["Order_Type"].map(order_type_dict)
        df["Order_Name"] = df["Order_Name"].map(concepts_dict)
        return df.reset_index(drop=True)

    def upsert_dataframe(self, df: pd.DataFrame) -> int:
        """Insert new rows, overwrite rows that already exist (matched by key_columns).
        Returns the number of incoming rows processed."""
        if df is None or df.empty:
            return 0

        for col in _DATETIME_COLUMNS:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        if "obs_id" in self.key_columns and "obs_id" in df.columns and "encounter_id" in df.columns:
            # obs is LEFT JOINed — an encounter with no obs rows yields obs_id = NULL. A UNIQUE
            # index/ON CONFLICT never treats two NULLs as equal, so that encounter would be
            # re-inserted as a new row every time it's re-fetched instead of upserted in place.
            # Fill with a deterministic, non-null, non-colliding stand-in (obs_id is always a
            # positive OpenMRS id) so repeated fetches of the same no-obs encounter collide.
            df["obs_id"] = df["obs_id"].fillna(-df["encounter_id"])

        con = duckdb.connect(self.db_path)
        try:
            con.register("incoming_df", df)
            table_exists = con.sql(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
                params=[self.table_name],
            ).fetchone()[0] > 0

            if not table_exists:
                con.execute(f"CREATE TABLE {self.table_name} AS SELECT * FROM incoming_df")
                key_clause = ", ".join(self.key_columns)
                con.execute(
                    f"CREATE UNIQUE INDEX idx_{self.table_name}_key ON {self.table_name} ({key_clause})"
                )
                return len(df)

            # Self-heal tables created before the coercion above existed: an all-NULL datetime
            # column got stuck as INTEGER at CREATE TABLE time (see _DATETIME_COLUMNS), which
            # only ever holds if every existing value in it is NULL — a real timestamp would
            # have hit this exact conversion error on insert and never made it in. Safe to
            # widen back to TIMESTAMP before inserting real values now.
            existing_types = dict(con.execute(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = ?",
                [self.table_name],
            ).fetchall())
            cols_to_fix = [c for c in _DATETIME_COLUMNS
                           if c in df.columns and existing_types.get(c, "").upper() == "INTEGER"]
            if cols_to_fix:
                # DuckDB refuses ALTER COLUMN TYPE while the unique index depends on the table
                # — drop and recreate it around the type fix.
                con.execute(f"DROP INDEX IF EXISTS idx_{self.table_name}_key")
                for col in cols_to_fix:
                    con.execute(f'ALTER TABLE {self.table_name} ALTER COLUMN "{col}" TYPE TIMESTAMP')
                key_clause = ", ".join(self.key_columns)
                con.execute(
                    f"CREATE UNIQUE INDEX idx_{self.table_name}_key ON {self.table_name} ({key_clause})"
                )

            key_clause = ", ".join(self.key_columns)
            update_cols = [c for c in df.columns if c not in self.key_columns]
            set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
            con.execute(f"""
                INSERT INTO {self.table_name}
                SELECT * FROM incoming_df
                ON CONFLICT ({key_clause}) DO UPDATE SET {set_clause}
            """)
            return len(df)
        finally:
            con.close()

    def _make_batch_processor(self, tables):
        """Returns an on_batch callback that harmonizes and upserts each fetched batch
        immediately, plus a 0-element list used as a mutable counter of rows upserted so far
        (fetch_incremental/fetch_bulk stream batches straight to this instead of buffering the
        whole result set in RAM before harmonizing/upserting it in one shot)."""
        total_upserted = [0]

        def _process_batch(batch_df):
            harmonized_df = self.harmonize(batch_df, tables)
            total_upserted[0] += self.upsert_dataframe(harmonized_df)

        return _process_batch, total_upserted

    def fetch_and_upsert(self, base_query=None, date_column="encounter_datetime", id_column="encounter_id",
                          lookback_days=None, refresh_single_tables=True) -> int:
        """Full pipeline for this route: fetch single tables (unless told not to), then stream
        the trailing lookback window of transactional data — each batch is harmonized against
        the single tables and upserted as soon as it's fetched, rather than accumulating every
        batch in RAM before a single harmonize+upsert at the end. Returns the number of rows
        upserted (0 if nothing new/changed)."""
        base_query = base_query or cfg.NEW_HARMONIZED_QUERY
        if "obs_id" not in base_query:
            print("WARNING: base_query has no obs_id column — falling back to "
                  "config.NEW_HARMONIZED_QUERY so the upsert key stays valid.")
            base_query = cfg.NEW_HARMONIZED_QUERY

        fetcher = self._make_fetcher()

        if refresh_single_tables:
            tables = self.fetch_single_tables(fetcher)
        else:
            tables = self._load_single_tables_from_csv()

        on_batch, total_upserted = self._make_batch_processor(tables)
        fetcher.fetch_incremental(base_query, date_column=date_column, id_column=id_column,
                                   lookback_days=lookback_days, on_batch=on_batch)
        return total_upserted[0]

    def reload_historical(self, start_date, end_date=None, base_query=None,
                           date_column="encounter_datetime", id_column="encounter_id",
                           refresh_single_tables=True) -> int:
        """Bulk (re)load history from start_date through end_date (default: today), paginating
        straight through by id_column instead of day-by-day — for a full or partial historical
        backfill/reload, not routine updates (use fetch_and_upsert for that). Always explicit
        about which range to (re)load; never runs on its own. Streams each batch through
        harmonize+upsert immediately, same as fetch_and_upsert. Returns the number of rows
        upserted."""
        base_query = base_query or cfg.NEW_HARMONIZED_QUERY
        if "obs_id" not in base_query:
            print("WARNING: base_query has no obs_id column — falling back to "
                  "config.NEW_HARMONIZED_QUERY so the upsert key stays valid.")
            base_query = cfg.NEW_HARMONIZED_QUERY

        fetcher = self._make_fetcher()

        if refresh_single_tables:
            tables = self.fetch_single_tables(fetcher)
        else:
            tables = self._load_single_tables_from_csv()

        on_batch, total_upserted = self._make_batch_processor(tables)
        fetcher.fetch_bulk(base_query, date_column=date_column, id_column=id_column,
                            start_date=start_date, end_date=end_date, on_batch=on_batch)
        return total_upserted[0]

    @staticmethod
    def query_duckdb(sql: str, data_dir: str = None) -> pd.DataFrame:
        """True drop-in for DataStorage.query_duckdb(sql) — same signature, same return type,
        and now the same calling convention too: the route is detected directly from the SQL
        text (see _extract_route_and_rewrite), matching how every existing call site already
        embeds data/<route>/parquet in the query string. `data_dir` is only a fallback for the
        rare query that doesn't reference a route at all, and cfg.DATA_PATH_ is read fresh here
        (not baked into the signature at import time), so it reflects whatever it's currently
        set to."""
        route, rewritten_sql = _extract_route_and_rewrite(sql)
        if route is None:
            route = _normalize_route(data_dir or cfg.DATA_PATH_)
        if route == 'mahis':
            print("Data Dir is",route, rewritten_sql)
        script_dir = os.path.dirname(os.path.realpath(__file__))
        db_path = os.path.join(script_dir, "data", route, cfg.DUCKDB_DIR_NAME, cfg.DUCKDB_FILE_NAME)
        con = duckdb.connect(db_path, read_only=True)
        try:
            return con.execute(rewritten_sql).df()
        finally:
            con.close()


def run_all_configured_sources(uuid=None):
    """Mirrors data_storage.py's __main__ loop: read (or create) configurations.json, run the
    full fetch+harmonize+upsert pipeline for every entry that isn't paused — or, if `uuid` is
    given, just the one entry matching it (still skipped if that entry is itself paused, same
    as data_storage.py's --uuid behavior)."""
    entries = load_or_create_configurations()
    if uuid:
        entries = [e for e in entries if e.get("uuid") == uuid]
        if not entries:
            print(f"No data source found with uuid={uuid}")

    for entry in entries:
        if entry.get("pause_data_source"):
            continue
        try:
            store = DataStorage.from_config_entry(entry)
            rows = store.fetch_and_upsert(base_query=entry.get("base_query"))
            print(f"[{entry.get('name', entry.get('uuid'))}] upserted {rows} rows into {store.db_path}")
        except Exception as e:
            print(f"[{entry.get('name', entry.get('uuid'))}] error: {e}")


if __name__ == "__main__":
    import argparse
    _parser = argparse.ArgumentParser(description="Fetch/harmonize/upsert OpenMRS data into DuckDB.")
    _parser.add_argument("--uuid", default=None,
                          help="Only run the configurations.json entry with this uuid, instead of all of them.")
    _args = _parser.parse_args()
    # `python data_storage_duckdb.py` — path is testable at data/default/duckdb
    # (cfg.DATA_PATH_ defaults to "data/default").
    run_all_configured_sources(uuid=_args.uuid)
