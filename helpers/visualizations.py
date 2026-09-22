import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import dash
import operator
from dash import dash_table, html, dcc, callback, Input, Output, State, MATCH, ALL
from dash.exceptions import PreventUpdate
from dash_iconify import DashIconify
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Union, Callable
import json
import ast
import uuid
from io import BytesIO
import base64
import duckdb
from data_storage import DataStorage

pd.options.mode.chained_assignment = None

from config import (PERSON_ID_, ENCOUNTER_ID_, DATE_, CONCEPT_NAME_,DATA_PATH_,FIRST_NAME_, LAST_NAME_,
                    VALUE_DATETIME_, AGE_, GENDER_, HOME_DISTRICT_, TA_, VILLAGE_, IDENTIFIER_,PROGRAM_,
                    DISTRICT_, FACILITY_)


THEME = {
    # Multi-series: dark green → mid greens → warm amber → teal → slate
    "primary":  ["#006401", "#03FAD5", "#8A5A01", "#f59e0b", "#0d9488"],
    # Single-series or color group: progressive green shades
    "greens":   ["#006401", "#1a7a1a", "#2e8f2e", "#43a443", "#57b957", "#80cc80"],
    # Gender/binary split (green + amber)
    "gender":   ["#006401", "#f59e0b", "#0d9488", "#7c3aed", "#dc2626"],
    # Single bar / line (no color grouping)
    "single":   "#FFFFFF",
    # Table accent colours
    "table_header":       "#DDEBDD",
    "table_header_text":  "#0F172A",
    "table_row_alt":      "#EEEEEE",
    "table_index_bg":     "#f4f4f4",
    "table_active_bg":    "#ffffff",
    "table_active_border":"#FFFFFF",
    "chart_fill": "#006401",
}

def _prepare_data_for_visualization(df, unique_column, apply_deduplication=True):
    """
    Prepare data for visualization by applying consistent deduplication logic.
    This mirrors the logic used in create_count functions.
    If a new column name is introduced e.g. for generation of composite key, the system is required to create the column
    """
    data = df
    if isinstance(unique_column, str) and unique_column not in data.columns:
        data[unique_column] = data[PERSON_ID_].astype(str) +"_"+ data[DATE_].dt.strftime('%Y-%m-%d')
        return data
    if isinstance(unique_column, list):
        if apply_deduplication and DATE_ in data.columns and all(col in data.columns for col in unique_column):
            data = data.drop_duplicates(subset=[DATE_] + unique_column)
        return data
    else:
        if apply_deduplication and DATE_ in data.columns and unique_column in data.columns:
            data = data.drop_duplicates(subset=[unique_column, DATE_])
            return data

def apply_calculated_fields(df, rules_json):
    df = df
    if not rules_json:
        return df
    rules = json.loads(rules_json) if isinstance(rules_json, str) else rules_json
    for rule in rules:
        col = rule["column"]
        expr = rule["expr"]
        try:
            df[col] = df.eval(expr, engine="python")
        except Exception:
            # Fallback for string / datetime logic
            df[col] = eval(expr, {"df": df, "pd": pd})

    return df

def _apply_replace(df: pd.DataFrame, replace) -> pd.DataFrame:
    """Apply value replacements to a DataFrame from a config dict."""
    if not replace or not isinstance(replace, dict):
        return df
    
    # Check if it's column-specific format
    if all(isinstance(v, dict) for v in replace.values()):
        for col, mapping in replace.items():
            if col in df.columns:
                # Using str.replace() - need to loop through mapping
                for old_val, new_val in mapping.items():
                    df[col] = df[col].str.replace(old_val, new_val, regex=False)
            else:
                df = df.replace(replace)
        return df
    
    return df.replace(replace)

def _normalize_filter_value(val):
    """Normalize filter_value into a proper list or string."""
    if val is None:
        return None

    if isinstance(val, list):
        return val

    if isinstance(val, str):
        stripped = val.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            parsed = None
            try:
                parsed = ast.literal_eval(stripped)
            except (ValueError, SyntaxError):
                try:
                    parsed = json.loads(stripped)
                except (ValueError, json.JSONDecodeError):
                    parsed = None

            if isinstance(parsed, list):
                return parsed
        if "|" in stripped:
            return [v.strip() for v in stripped.split("|")]
    return val


def _apply_filter(data, filter_col, filter_value):

    """
    This function applies advanced filtering rules on a pandas DataFrame,
    supporting both single-column and multi-column filtering, numeric and
    string operators, wildcards, and set-based logic across "person_id".

    1. SINGLE-COLUMN FILTERING (filter_col is a string)
       ------------------------------------------------
       Acceptable filter_value formats:
       - A single string: "Male", "BP"
       - List: ["A", "B"], ['A','B']
       - Pipe-separated string: "A | B | C"
       - Stringified list: "['A','B','C']"
       - Wildcards: "*BP", "%Sugar"  → performs substring contains
       - Operator expressions:
            =data_value
            !=data_value
            >data_value
            <data_value
            >=data_value
            <=data_value
       - Logical AND intersection (using "&&"):
            "A && B && C"
         Meaning:
            Person must satisfy ALL conditions.
         Mechanism:
            For each expression, filter separately → get person_id set
            → then intersect all sets → return only rows belonging to that intersection.

       Filtering logic on strings:
       - If starts with "*" or "%", uses case-insensitive .str.contains()
       - If contains operators, applies numeric or lexicographical comparisons
       - If list or multi-data_value, uses .isin()

    2. MULTI-COLUMN FILTERING (filter_col is a list)
       ------------------------------------------------
       Two cases:
       a) Length >= 2:
            - filter_value MUST be a list of the same length
            - Each pair (col[i], data_value[i]) is applied independently
            - AND logic across all pairs
       b) Length == 1:
            - Treated like single-column filtering above

    3. LIST FILTERING
       ------------------------------------------------
       If filter_value is a list (after normalization):
           → df[df[col].isin(values)]

    4. WILDCARD FILTERING
       ------------------------------------------------
       "*BP", "%Systolic"
            → interpreted as substring search in column values

    5. OPERATOR FILTERING
       ------------------------------------------------
       Valid operators:
            =  !=  >  <  >=  <=
       Behavior:
            - Attempts numeric conversion where possible
            - Falls back to string comparison if conversion fails

    6. AND INTERSECTION LOGIC USING "&&"
       ------------------------------------------------
       Example:
           filter_value = "Diabetes && Hypertension && Male"
           filter_col = "diagnosis"

       Steps:
           - Split into ["Diabetes", "Hypertension", "Male"]
           - Apply each filter condition independently
           - Collect person_id sets for each
           - Return intersection of all sets
           - Equivalent to requiring ALL conditions to be true

    7. DEFAULT BEHAVIOR
       ------------------------------------------------
       Any unmatched case defaults to simple equality:
           df[df[col] == filter_value]

    This engine supports complex rule-based filtering with recursion,
    multi-condition merging, and fully supports HMIS/clinical datasets
    where "person_id" represents the unique patient key.
    """

    if filter_col is None or filter_value is None:
        return data

    df = data

    # Normalize: list, pipe-separated, stringified list...
    filter_value = _normalize_filter_value(filter_value)
    filter_col = _normalize_filter_value(filter_col)

    if isinstance(filter_col, list):
        if len(filter_col) >= 1:
            # if not isinstance(filter_value, list) or len(filter_value) != len(filter_col):
            #     raise ValueError("Multi-column filters require filter_value list same length as filter_col.")
            if isinstance(filter_value, list):
                sets = []
                for col, val in zip(filter_col, filter_value):
                    base = data
                    if isinstance(val, str) and val.startswith("!="):
                        val = val[2:].strip()
                        excluded_ids = set(
                                    base.loc[base[col] == val, "person_id"].astype(str)
                                )
                        ids = set(base["person_id"].astype(str)) - excluded_ids
                    else:
                        temp = _apply_filter(base, col, val)
                        ids = set(temp["person_id"].astype(str))
        
                    sets.append(ids)

                final_persons = set.intersection(*sets) if sets else set()
                df = df[df["person_id"].astype(str).isin(final_persons)]
                return df

        filter_col = filter_col[0]  # reduce to single column

    if isinstance(filter_value, str) and "&&" in filter_value:
        conditions = [c.strip() for c in filter_value.split("&&") if c.strip()]

        if not conditions:
            return df

        person_sets = []
        for cond in conditions:
            filtered = _apply_filter(df, filter_col, cond)  # recursively apply each condition
            persons = set(filtered["person_id"].astype(str).tolist())
            person_sets.append(persons)

        # Intersection of all sets
        common_persons = set.intersection(*person_sets) if person_sets else set()

        return df[df["person_id"].astype(str).isin(common_persons)]

    if isinstance(filter_value, list):
        return df[df[filter_col].isin(filter_value)]


    if isinstance(filter_value, str):

        # 1. Wildcard / contains
        if filter_value.startswith("*") or filter_value.startswith("%"):
            needle = filter_value[1:]
            return df[df[filter_col].astype(str).str.contains(needle, case=False, na=False)]

        # 2. Operator parsing
        match = re.match(r'^(>=|<=|!=|=|>|<)?\s*(.*)$', filter_value.strip())
        if match:
            operator, value_str = match.groups()
            operator = operator or "="
            value_str = value_str.strip()

            # Try numeric conversion
            if value_str in ["_"]:
                data_value = ""
            else:
                try:
                    if "." in value_str:
                        data_value = float(value_str)
                    else:
                        data_value = int(value_str)
                except:
                    data_value = value_str


            if operator == "=":
                return df[df[filter_col] == data_value]
            if operator == "!=":
                return df[df[filter_col] != data_value]
            if operator == ">":
                return df[df[filter_col] > data_value]
            if operator == "<":
                return df[df[filter_col] < data_value]
            if operator == ">=":
                return df[df[filter_col] >= data_value]
            if operator == "<=":
                return df[df[filter_col] <= data_value]

        # 3. Simple equality
        return df[df[filter_col] == filter_value]

    return df[df[filter_col] == filter_value]

def _apply_filter_mask(df, filter_col, filter_value):
    if filter_col not in df.columns:
        return pd.Series(False, index=df.index)
    if isinstance(filter_value, list):
        return df[filter_col].isin(filter_value)
    if isinstance(filter_value, str):
        #Wildcard / contains
        if filter_value.startswith("*") or filter_value.startswith("%"):
            needle = filter_value[1:]
            return (
                df[filter_col]
                .astype(str)
                .str.contains(needle, case=False, na=False)
            )
        #Operator parsing
        match = re.match(r'^(>=|<=|!=|=|>|<)?\s*(.*)$', filter_value.strip())
        if match:
            operator, value_str = match.groups()
            operator = operator or "="
            value_str = value_str.strip()
            #Empty placeholder
            if value_str == "_":
                data_value = ""
            else:
                # Numeric conversion
                try:
                    if "." in value_str:
                        data_value = float(value_str)
                    else:
                        data_value = int(value_str)
                except:
                    data_value = value_str
            series = df[filter_col]
            if operator == "=":
                return series == data_value
            if operator == "!=":
                return series != data_value
            if operator == ">":
                return series > data_value
            if operator == "<":
                return series < data_value
            if operator == ">=":
                return series >= data_value
            if operator == "<=":
                return series <= data_value

        return df[filter_col] == filter_value
    return df[filter_col] == filter_value

def build_filter_query(cols, vals,data_path, unique_column, isSet, start_date, end_date, query_filter:str=None):
    """
    Build a SQL WHERE clause based on filter type.
    Supports single filters and paired list filters with AND conditions.
    
    Args:
        cols (str or list): Column name(s)
        vals (str, list, or list of lists): Filter data_value(s)
        unique_column (str/list): Column to select from
    
    Returns:
        str: SQL SELECT query
    """
    def parse_value(val_str):
        """Parse a single data_value for operators, wildcards, or numeric types."""
        val_str = str(val_str).strip()
        
        # Special case: "_" means IS NULL
        if val_str == "_":
            return "IS", None
        
        # Handle wildcard/LIKE patterns
        if val_str.startswith(("*", "%")):
            return "LIKE", f"%{val_str[1:]}%"
        
        # Handle operators (>=, <=, !=, =, >, <)
        if match := re.match(r'^(>=|<=|!=|=|>|<)?\s*(.*)$', val_str):
            operator, value_str = match.groups()
            operator = operator or "="
            value_str = value_str.strip()
            
            if value_str == "_":
                if operator == "=":
                    return "IS", None
                elif operator =="!=":
                    return "IS NOT", None
                return "IS", None
            elif value_str.replace(".", "", 1).isdigit():
                data_value = float(value_str) if "." in value_str else int(value_str)
            else:
                data_value = value_str
            
            return operator, data_value
        
        return "=", val_str
    
    def build_single_condition(col, val):
        """Build a single WHERE condition."""
        # Handle list values for IN clause
        if isinstance(val, list):
            clause_list = []
            for item in val:
                operator, data_value = parse_value(item)
                if data_value == None:
                    data_value = 'NULL'
                clause_list.append(f"{col} {operator} '{data_value}'")
            clause = " OR ".join(clause_list)
            return f"({clause})"
        if col == "defaulter_period":
            return (f"concept_name = 'Drug end date' "
                    + f"GROUP BY {unique_column}, CAST({DATE_} AS DATE)"
                    + f"HAVING MAX(CAST({VALUE_DATETIME_} AS TIMESTAMP)) < ('{end_date}'::DATE - INTERVAL {val} DAY)")
        if col == "days_before_visit_date":
            return f"{DATE_} >= ('{start_date}'::DATE - INTERVAL {int(val)} DAY) AND {DATE_} <= ('{end_date}'::DATE - INTERVAL 0 DAY)"
        operator, data_value = parse_value(val)
        if data_value == None:
            data_value = 'NULL'
            return f"{col} {operator} {data_value}"
        if operator == "LIKE":
            return f"{col} LIKE '{data_value}'"
        if (isinstance(data_value, int) or isinstance(data_value, float)):
            return f"{col} {operator} {data_value}"
        else:
            return f"{col} {operator} '{data_value}'"
    
    # Handle paired lists
    if isinstance(cols, list):
        conditions = [
            build_single_condition(col, val) 
            for col, val in zip(cols, vals)
        ]
        where_clause = " AND ".join(conditions)
        return f"SELECT DISTINCT {unique_column} FROM '{data_path}' WHERE {query_filter} AND {where_clause}"
    where_clause = build_single_condition(cols, vals)
    if isinstance(unique_column, list):
        unique_column_str = ", ".join(unique_column)
    else:        unique_column_str = unique_column
    if isSet:
        return f"SELECT DISTINCT {unique_column_str} FROM '{data_path}' WHERE {query_filter} AND {where_clause}"
    return f"{where_clause}"

def create_count(query_fiter,data_path, aggregation='count', unique_column=PERSON_ID_, *filters,
                  start_date=None, end_date=None, group_by=None, custom_sql=None):

    isSet = False
    unique_column = _normalize_filter_value(unique_column)
    if isinstance(unique_column, list):
        unique_column = ", ".join(unique_column)
    else: unique_column = unique_column

    if filters:
        filter_cols = [item for item in filters[:-2][::2] if item is not None]
        filter_vals = [item for item in filters[:-2][1::2] if item is not None]
        start_date = filters[-2] if len(filters) % 2 == 0 else start_date
        end_date = filters[-1] if len(filters) % 2 == 0 else end_date
    else:
        filter_cols = []
        filter_vals = []

    queries = []
    for col, val in zip(filter_cols, filter_vals):
        col,val = _normalize_filter_value(col), _normalize_filter_value(val)
        query = build_filter_query(col, val,data_path, unique_column, isSet, start_date, end_date)
        queries.append(query)

    if custom_sql:
        custom_sql = custom_sql.replace("data", data_path)
        # Full escape hatch: the JSON author owns the entire query from here,
        # built on top of the same query_fiter every other count uses.
        joined_query =  f"{custom_sql} AND {query_fiter}"
    elif group_by:
        # Adds the group_by column to the select/group-by so the query stays
        # correct per-group, without changing what gets returned below --
        # unique_column is still a plain column in the result (it's part of
        # the GROUP BY key), Value is just along for the ride, unused here.
        where_clause = query_fiter + ((" AND " + " AND ".join(queries)) if queries else "")
        joined_query = (
            f"SELECT {unique_column}, {DATE_}::DATE, {group_by}, COUNT(*) AS Value"
            f" FROM '{data_path}' WHERE {where_clause}"
            f" GROUP BY {unique_column}, {DATE_}::DATE, {group_by}"
        )
    else:
        joined_query =f"SELECT DISTINCT {unique_column}, {DATE_}::DATE FROM '{data_path}' WHERE {query_fiter} AND "  + " AND ".join(queries)
        if not queries:
            joined_query = f"SELECT DISTINCT {unique_column}, {DATE_}::DATE FROM '{data_path}' WHERE {query_fiter}"
    if aggregation == "time_diff_mins":
        joined_query = (joined_query.replace(unique_column, 
                                            f"({unique_column}), DATEDIFF('minute', MIN({DATE_}), MAX({DATE_})) AS patient_session_minutes")
                                            + f" GROUP BY {unique_column}, CAST({DATE_} AS DATE)")
    
    result = DataStorage.query_duckdb(joined_query)
    unique_patients = result[unique_column].unique().tolist()
    if aggregation == 'count':
        return len(result), unique_patients
    elif aggregation == 'nunique':
        return len(result[unique_column].unique().tolist()), unique_patients
    elif aggregation == 'list':
        return result[unique_column].dropna().unique().tolist(), unique_patients
    elif aggregation == 'time_diff_mins':
        if result.empty:
            return 0, unique_patients
        result = result[result["patient_session_minutes"]<=120] #120 minutes is the threshold for a single patient session, we want to exclude outliers that may be caused by data quality issues
        return int(result["patient_session_minutes"].agg('mean')), unique_patients
    elif aggregation in ['sum', 'mean', 'min', 'max', 'std', 'var']:
        return int(result[unique_column].agg(aggregation)), unique_patients
    else:
        return len(result.drop_duplicates()), unique_patients

def create_count_sets(
    query_fiter,data_path,aggregation='count',
    unique_column=PERSON_ID_,
    *filters,
    start_date=None,
    end_date=None,
    same_day=False,
    group_by=None,
    custom_sql=None,
):
    isSet = True
    unique_column = _normalize_filter_value(unique_column)
    if isinstance(unique_column, list):
        unique_column = ", ".join(unique_column)
    else: unique_column = unique_column

    # Scalar ID column: strip any ", Date::DATE" suffix and SQL casts (e.g. "person_id, Date::DATE" → "person_id")
    pid_col = unique_column.split(",")[0].split("::")[0].strip()

    if custom_sql:
        # Full escape hatch, same convention as create_count: the JSON author
        # owns the entire query from here, built on the same query_fiter.
        joined_query = query_fiter + custom_sql
        result = DataStorage.query_duckdb(joined_query)
        unique_patients = result[unique_column].unique().tolist()
        return result[pid_col].nunique(), unique_patients

    set_filters = []
    non_set_filters = []
    for i in range(0, len(filters)-2, 2):
        col = filters[i]
        val = filters[i + 1]
        if not col:
            continue
        col_norm = _normalize_filter_value(col)
        val_norm = _normalize_filter_value(val)
        if isinstance(col_norm, list):
            set_filters.append((col_norm, val_norm))
        else:
            non_set_filters.append((col, val))

    start_date = filters[-2] if len(filters) % 2 == 0 else start_date
    end_date = filters[-1] if len(filters) % 2 == 0 else end_date

    queries = []
    cols_list = []
    vals_list = []
    for cols, vals in set_filters:
        if len(cols) != len(vals):
            raise ValueError("For multi-column filters, filter_value must be a list of the same length as filter_col.")
        cols_list = []
        vals_list = []
        for col, val in zip(cols, vals):
            cols_list.append(col)
            vals_list.append(val)
        query = build_filter_query(cols_list, vals_list,data_path, unique_column, isSet, start_date, end_date, query_fiter)
        queries.append(query)

    for cols, vals in non_set_filters:
        query = build_filter_query(cols, vals,data_path, unique_column, isSet, start_date, end_date, query_fiter)
        queries.append(query)

    if same_day:
        # All conditions must be met on the same date row — original INTERSECT behaviour.
        intersection_query = " INTERSECT ".join(queries)
        result = DataStorage.query_duckdb(intersection_query)
        return result[pid_col].nunique(), unique_patients

    # Default: conditions may live on different rows / different dates.
    in_clauses = [
        f"{pid_col} IN (SELECT DISTINCT {pid_col} FROM '{data_path}' WHERE {q.split('WHERE ', 1)[1]})"
        for q in queries
    ]
    where_full = query_fiter + ((" AND " + " AND ".join(in_clauses)) if in_clauses else "")
    if group_by:
        # Same principle as create_count: adds the column to select/group-by
        # without changing what's returned -- pid_col stays a plain column
        # in the result (it's part of the GROUP BY key), Value is unused here.
        final_query = (
            f"SELECT {pid_col}, {group_by}, COUNT(*) AS Value"
            f" FROM '{data_path}' WHERE {where_full}"
            f" GROUP BY {pid_col}, {group_by}"
        )
    else:
        final_query = f"SELECT DISTINCT {pid_col} FROM '{data_path}' WHERE {where_full}"
    # print("Create countset", final_query, "\n\n")
    result = DataStorage.query_duckdb(final_query)
    unique_patients = result[unique_column].unique().tolist()
    return result[pid_col].nunique(), unique_patients

def create_sum(query_fiter,data_path, unique_column=PERSON_ID_, num_field='ValueN', *filters, start_date=None, end_date=None):

    isSet = False

    if filters:
        filter_cols = [item for item in filters[:-2][::2] if item is not None]
        filter_vals = [item for item in filters[:-2][1::2] if item is not None]
        start_date = filters[-2] if len(filters) % 2 == 0 else start_date
        end_date = filters[-1] if len(filters) % 2 == 0 else end_date
    else:
        filter_cols = []
        filter_vals = []
    queries = []
    for col, val in zip(filter_cols, filter_vals):
        query = build_filter_query(col, val,data_path, [unique_column,num_field], isSet, start_date, end_date)
        queries.append(query)
    joined_query =f"SELECT DISTINCT {unique_column}, {num_field} FROM '{data_path}' WHERE {query_fiter} AND "  + " AND ".join(queries)
    if not queries:
        joined_query =f"SELECT DISTINCT {unique_column}, {num_field} FROM '{data_path}' WHERE {query_fiter}"  
    
    # print("create sum", joined_query)
    result = DataStorage.query_duckdb(joined_query)
    unique_patients = result[unique_column].unique().tolist()
    return result[num_field].sum(), unique_patients


def _build_column_figure(query_fiter,data_path, x_col, y_col, title, x_title, y_title,
                        unique_column=PERSON_ID_, legend_title=None,
                        color=None, filter_col1=None, filter_value1=None,
                        filter_col2=None, filter_value2=None,
                        filter_col3=None, filter_value3=None, aggregation='count',
                        custom_fields=None, height=400, responsive=True,
                        show_values=True, sort_by_value=True, max_categories=None):
    """
    Create a modern, responsive column chart using Plotly Express with legend support.
    Aggregation is pushed entirely into SQL: only the grouped summary rows
    are returned to Python, keeping RAM usage minimal.
    
    Parameters:
    - height: Chart height in pixels (default: 400)
    - responsive: Make chart responsive to container width (default: True)
    - show_values: Show data values on bars (default: True)
    - sort_by_value: Sort bars by value descending (default: True)
    - max_categories: Limit number of categories shown (default: None = all)
    """
    isSet = False
    filter_pairs = [
        (filter_col1, filter_value1),
        (filter_col2, filter_value2),
        (filter_col3, filter_value3),
    ]
    conditions = []
    for col, val in filter_pairs:
        if col is not None and val is not None:
            col = _normalize_filter_value(col)
            if isinstance(col, list):
                col = col[0]
            val = _normalize_filter_value(val)
            conditions.append(build_filter_query(col, val,data_path, unique_column, isSet, None, None))
 
    where_clause = query_fiter + ((" AND " + " AND ".join(conditions)) if conditions else "")
 
    # Map aggregation name → SQL aggregate expression on y_col.
    if aggregation in ('count', 'nunique'):
        agg_expr = f"COUNT(DISTINCT {y_col})"
    elif aggregation == 'sum':
        agg_expr = f"SUM({y_col})"
    elif aggregation == 'mean':
        agg_expr = f"AVG({y_col})"
    elif aggregation == 'median':
        agg_expr = f"MEDIAN({y_col})"
    elif aggregation == 'min':
        agg_expr = f"MIN({y_col})"
    elif aggregation == 'max':
        agg_expr = f"MAX({y_col})"
    else:
        agg_expr = f"{aggregation}({y_col})"
 
    if color:
        # SELECT x_col, color, AGG(y_col) … GROUP BY x_col, color
        joined_query = (
            f"SELECT {x_col}, {color} as Color, {agg_expr} AS data_value"
            f" FROM '{data_path}'"
            f" WHERE {where_clause}"
            f" GROUP BY {x_col}, {color}"
        )
        summary = DataStorage.query_duckdb(joined_query)
        summary = apply_calculated_fields(summary, custom_fields)

        # Apply category limit if specified
        if max_categories and len(summary[x_col].unique()) > max_categories:
            top_categories = summary.groupby(x_col)['data_value'].sum().nlargest(max_categories).index
            summary = summary[summary[x_col].isin(top_categories)]

        summary['label'] = summary['data_value'].apply(
            lambda x: f'{int(x):,}' if x == int(x) else f'{x:,.1f}'
        ) if show_values else ''

        fig = px.bar(
            summary,
            x=x_col,
            y='data_value',
            color="Color",
            title=None,  # Title added in layout
            text='label' if show_values else None,
            color_discrete_sequence=THEME["primary"],
            barmode='group',
            template='plotly_white'
        )
    else:
        # SELECT x_col, AGG(y_col) … GROUP BY x_col
        order_clause = "ORDER BY data_value DESC" if sort_by_value else ""
        joined_query = (
            f"SELECT {x_col}, {agg_expr} AS data_value"
            f" FROM '{data_path}'"
            f" WHERE {where_clause}"
            f" GROUP BY {x_col}"
            f" {order_clause}"
        )
        summary = DataStorage.query_duckdb(joined_query)
        summary = apply_calculated_fields(summary, custom_fields)
        
        # Apply category limit if specified
        if max_categories and len(summary) > max_categories:
            if sort_by_value:
                summary = summary.head(max_categories)
            else:
                summary = summary.iloc[:max_categories]
        
        summary['label'] = summary['data_value'].apply(
            lambda x: f'{int(x):,}' if x == int(x) else f'{x:,.1f}'
        ) if show_values else ''
 
        # Modern gradient color for single-color bars
        fig = px.bar(
            summary,
            x=x_col,
            y='data_value',
            title=None,
            text='label' if show_values else None,
            template='plotly_white'
        )
        
        # Apply theme single-color
        fig.update_traces(
            marker_color=THEME["chart_fill"],
            marker_line_color="#004a01",
            marker_line_width=1,
            opacity=0.85
        )

    # Modern layout configuration with responsive settings
    layout_config = {
        'title': dict(
            text=f'<b>{title}</b>',
            x=0.5,
            xanchor='center',
            font=dict(size=18, color='#2c3e50', family='Arial, sans-serif'),
            y=0.95
        ),
        'xaxis_title': dict(
            text=x_title,
            font=dict(size=13, color='#34495e', family='Arial, sans-serif'),
            standoff=10
        ),
        'yaxis_title': dict(
            text=y_title,
            font=dict(size=13, color='#34495e', family='Arial, sans-serif'),
            standoff=10
        ),
        'template': 'plotly_white',
        'legend_title': dict(
            text=legend_title if legend_title else color,
            font=dict(size=12, color='#2c3e50')
        ),
        'plot_bgcolor': '#ffffff',
        'paper_bgcolor': '#ffffff',
        'margin': dict(l=50, r=30, t=80, b=50, pad=4),
        'height': height,
        'hovermode': 'x unified',
        'font': dict(family='Arial, sans-serif', size=12, color='#2c3e50'),
        
        # Make chart responsive to container width
        'autosize': responsive,
        'width': None if responsive else 800,  # None = auto, or set fixed width
    }
    
    fig.update_layout(**layout_config)
    
    # Modern axes styling
    fig.update_xaxes(
        showgrid=True,
        gridwidth=0.5,
        gridcolor='#e8ecef',
        showline=True,
        linewidth=1,
        linecolor='#cbd5e0',
        tickangle=-45 if len(summary) > 5 else 0,
        tickfont=dict(size=11, color='#4a5568'),
        title_standoff=10
    )
    
    fig.update_yaxes(
        showgrid=True,
        gridwidth=0.5,
        gridcolor='#e8ecef',
        showline=True,
        linewidth=1,
        linecolor='#cbd5e0',
        zeroline=True,
        zerolinewidth=1,
        zerolinecolor='#e2e8f0',
        tickfont=dict(size=11, color='#4a5568'),
        tickformat=',.0f',
        title_standoff=10
    )
    
    # Modern bar styling
    fig.update_traces(
        textposition='outside',
        textfont=dict(size=11, color='#2c3e50', family='Arial, sans-serif'),
        hovertemplate="<b>%{x}</b><br>" +
                      f"<b>{y_title}:</b> %{{y:,.0f}}<br>" +
                      "<extra></extra>",
        marker=dict(
            pattern_shape='',
            cornerradius=4  # Rounded corners for modern look
        )
    )
    
    # Add optional grid lines and improve readability
    if responsive:
        # Configure for responsive behavior
        fig.update_layout(
            autosize=True,
            bargap=0.15,  # Gap between bars
            bargroupgap=0.05  # Gap between bar groups
        )
    
    # Add subtle background pattern or border (optional)
    fig.update_layout(
        shapes=[
            dict(
                type='rect',
                xref='paper', yref='paper',
                x0=0, y0=0, x1=1, y1=1,
                line=dict(width=1, color='#e2e8f0'),
                fillcolor='rgba(0,0,0,0)'
            )
        ]
    )
    
    return fig


def _normalize_filter_headers(filter_headers):
    """filter_headers can be a single {"column": ..., "default": ...} dict or
    a list of them; normalize to a list of valid entries (skip anything
    without a "column")."""
    if not filter_headers:
        return []
    headers = filter_headers if isinstance(filter_headers, list) else [filter_headers]
    return [h for h in headers if isinstance(h, dict) and h.get("column")]


def _column_filter_where(column_value_pairs):
    """Build 'AND'-joined 'col = value' conditions for the truthy pairs."""
    parts = []
    for col, val in column_value_pairs:
        if col and val:
            escaped = str(val).replace("'", "''")
            parts.append(f"{col} = '{escaped}'")
    return " AND ".join(parts)


def create_column_chart(query_fiter, data_path, x_col, y_col, title, x_title, y_title,
                        unique_column=PERSON_ID_, legend_title=None,
                        color=None, filter_col1=None, filter_value1=None,
                        filter_col2=None, filter_value2=None,
                        filter_col3=None, filter_value3=None, aggregation='count',
                        custom_fields=None, height=400, responsive=True,
                        show_values=True, sort_by_value=True, max_categories=None,
                        filter_headers=None):
    """
    Column chart, optionally with header dropdown filters (filter_headers),
    following the same design as create_crosstab_table's index/columns
    filters. Each header is {"column": ..., "default": ...}: "default"
    pre-filters the chart to that value; with no default, the dropdown still
    lets the user pick any value from that column but nothing is filtered up
    front. With no filter_headers at all, this returns a plain figure exactly
    as before -- no wrapper, no filter UI.
    """
    headers = _normalize_filter_headers(filter_headers)
    rest_args = (data_path, x_col, y_col, title, x_title, y_title,
                 unique_column, legend_title, color, filter_col1, filter_value1,
                 filter_col2, filter_value2, filter_col3, filter_value3, aggregation,
                 custom_fields, height, responsive, show_values, sort_by_value, max_categories)

    if not headers:
        return _build_column_figure(query_fiter, *rest_args)

    default_where = _column_filter_where([(h["column"], h.get("default")) for h in headers])
    initial_query_fiter = f"{query_fiter} AND {default_where}" if default_where else query_fiter
    initial_figure = _build_column_figure(initial_query_fiter, *rest_args)

    dropdown_specs = []
    for h in headers:
        col = h["column"]
        try:
            opts_df = DataStorage.query_duckdb(
                f"SELECT DISTINCT {col} FROM '{data_path}' WHERE {query_fiter} AND {col} IS NOT NULL ORDER BY {col}"
            )
            options = opts_df[col].dropna().astype(str).tolist() if not opts_df.empty else []
        except Exception:
            options = []
        dropdown_specs.append({"column": col, "default": h.get("default"), "options": options})

    uid = uuid.uuid4().hex[:8]

    filter_controls = [
        dcc.Dropdown(
            id={"type": "column-chart-filter", "index": uid, "col": spec["column"]},
            options=[{"label": v, "value": v} for v in spec["options"]],
            value=spec["default"] or None,
            placeholder=f"Filter {spec['column']}",
            clearable=True,
            style={"width": "170px", "fontSize": "12px"},
        )
        for spec in dropdown_specs
    ]

    return html.Div([
        html.Div(
            [
                html.H4(title, style={
                    "margin": "0", "fontFamily": "Arial, sans-serif", "fontSize": "16px",
                    "fontWeight": "bold", "color": "#2c3e50",
                }),
                html.Div(filter_controls, style={
                    "display": "flex", "gap": "8px", "alignItems": "center",
                    "justifyContent": "flex-end", "flexWrap": "wrap",
                }),
            ],
            style={
                "display": "flex", "justifyContent": "space-between", "alignItems": "center",
                "flexWrap": "wrap", "gap": "8px", "marginBottom": "8px",
            },
        ),
        dcc.Store(id={"type": "column-chart-store", "index": uid}, data={
            "query_fiter": query_fiter, "data_path": data_path, "x_col": x_col, "y_col": y_col,
            "title": title, "x_title": x_title, "y_title": y_title, "unique_column": unique_column,
            "legend_title": legend_title, "color": color,
            "filter_col1": filter_col1, "filter_value1": filter_value1,
            "filter_col2": filter_col2, "filter_value2": filter_value2,
            "filter_col3": filter_col3, "filter_value3": filter_value3,
            "aggregation": aggregation, "custom_fields": custom_fields,
            "height": height, "responsive": responsive, "show_values": show_values,
            "sort_by_value": sort_by_value, "max_categories": max_categories,
        }),
        dcc.Graph(id={"type": "column-chart-graph", "index": uid}, figure=initial_figure),
    ], className="card-2")


@callback(
    Output({"type": "column-chart-graph", "index": MATCH}, "figure"),
    Input({"type": "column-chart-filter", "index": MATCH, "col": ALL}, "value"),
    State({"type": "column-chart-filter", "index": MATCH, "col": ALL}, "id"),
    State({"type": "column-chart-store", "index": MATCH}, "data"),
    prevent_initial_call=True,
)
def _filter_column_chart(values, ids, store_data):
    """Re-run the column chart's SQL with the dropdown-selected column=value
    filters applied, mirroring create_crosstab_table's filter design."""
    if not store_data:
        return dash.no_update

    extra_where = _column_filter_where([(id_dict.get("col"), val) for val, id_dict in zip(values, ids)])
    base_where = store_data["query_fiter"]
    effective_where = f"{base_where} AND {extra_where}" if extra_where else base_where

    return _build_column_figure(
        effective_where, store_data["data_path"], store_data["x_col"], store_data["y_col"],
        store_data["title"], store_data["x_title"], store_data["y_title"],
        store_data["unique_column"], store_data["legend_title"], store_data["color"],
        store_data["filter_col1"], store_data["filter_value1"],
        store_data["filter_col2"], store_data["filter_value2"],
        store_data["filter_col3"], store_data["filter_value3"],
        store_data["aggregation"], store_data["custom_fields"],
        store_data["height"], store_data["responsive"], store_data["show_values"],
        store_data["sort_by_value"], store_data["max_categories"],
    )


def create_time_line_chart(query_fiter,data_path, date_col, y_col, title, x_title,
                      y_title, unique_column=PERSON_ID_, 
                      legend_title=None, color=None, filter_col1=None, 
                      filter_value1=None, filter_col2=None, 
                      filter_value2=None, filter_col3=None, 
                      filter_value3=None, aggregation='count', 
                      custom_fields=None,group_by=None, 
                      *args, height=400, responsive=True,
                      show_avg_line=True, show_trend_line=False,
                      date_granularity='day', smooth_lines=False,
                      show_annotations=True, forecast_periods=0):
    """
    Create a modern, responsive time series chart using Plotly Express.
    Aggregation is pushed into SQL so only summary rows are returned to Python.
    
    Parameters:
    - height: Chart height in pixels (default: 400)
    - responsive: Make chart responsive to container width (default: True)
    - show_avg_line: Show average reference line (default: True)
    - show_trend_line: Show trend line (default: False)
    - date_granularity: 'day', 'week', 'month', 'quarter', 'year' (default: 'day')
    - smooth_lines: Use smooth curves instead of straight lines (default: False)
    - show_annotations: Show key point annotations (default: True)
    - forecast_periods: Number of periods to forecast (default: 0)
    """
    isSet = False
    filter_pairs = [
        (filter_col1, filter_value1),
        (filter_col2, filter_value2),
        (filter_col3, filter_value3),
    ]
    conditions = []
    for col, val in filter_pairs:
        if col is not None and val is not None:
            col = _normalize_filter_value(col)
            if isinstance(col, list):
                col = col[0]
            val = _normalize_filter_value(val)
            conditions.append(build_filter_query(col, val,data_path, unique_column, isSet, None, None))
 
    where_clause = query_fiter + ((" AND " + " AND ".join(conditions)) if conditions else "")
 
    # Map aggregation to SQL
    if aggregation in ('count', 'nunique'):
        agg_expr = f"COUNT(DISTINCT {y_col})"
    elif aggregation == 'sum':
        agg_expr = f"SUM({y_col})"
    elif aggregation == 'mean':
        agg_expr = f"AVG({y_col})"
    elif aggregation == 'median':
        agg_expr = f"MEDIAN({y_col})"
    elif aggregation == 'min':
        agg_expr = f"MIN({y_col})"
    elif aggregation == 'max':
        agg_expr = f"MAX({y_col})"
    else:
        agg_expr = f"COUNT(DISTINCT {y_col})"
    
    # Date granularity formatting
    date_format_map = {
        'day': f"CAST({date_col} AS DATE)",
        'week': f"DATE_TRUNC('week', {date_col})",
        'month': f"DATE_TRUNC('month', {date_col})",
        'quarter': f"DATE_TRUNC('quarter', {date_col})",
        'year': f"DATE_TRUNC('year', {date_col})"
    }
    date_expr = date_format_map.get(date_granularity, f"CAST({date_col} AS DATE)")
    
    if color:
        joined_query = (
            f"SELECT {date_expr} AS date_trunc, {color}, {agg_expr} AS metric_value"
            f" FROM '{data_path}'"
            f" WHERE {where_clause}"
            f" GROUP BY {date_expr}, {color}"
            f" ORDER BY date_trunc"
        )
    elif group_by:
        sub_query = (
                f"SELECT {date_expr} AS date_trunc, {group_by}, {agg_expr} AS metric_value"
                f" FROM '{data_path}'"
                f" WHERE {where_clause}"
                f" GROUP BY {date_expr}, {group_by}"
                f" ORDER BY date_trunc"
            )
        joined_query = f"""
                        SELECT
                            date_trunc,
                            SUM(metric_value) AS metric_value
                        FROM (
                                {sub_query}
                            )
                        GROUP BY date_trunc
                        ORDER BY date_trunc
                    """
    else:
        joined_query = (
            f"SELECT {date_expr} AS date_trunc, {agg_expr} AS metric_value"
            f" FROM '{data_path}'"
            f" WHERE {where_clause}"
            f" GROUP BY {date_expr}"
            f" ORDER BY date_trunc"
        )
    # if aggregation is calculated, use queries from the calculated
    if aggregation == "calculated":
        queries = []
        for index, items in enumerate(args[:-1]):
            if items:
                query = (
                        f"SELECT {date_expr} AS date_trunc, {agg_expr} AS query{index+1}"
                        f" FROM '{data_path}'"
                        f" {items}" #items will need a where clause
                        f" AND {query_fiter}"
                        f" GROUP BY {date_expr}"
                        f" ORDER BY date_trunc"
                    )
            else:
                query = (
                    f"SELECT {date_expr} AS date_trunc, {agg_expr} AS query{index+1}"
                    f" FROM '{data_path}'"
                    f" WHERE {query_fiter}"
                    f" GROUP BY {date_expr}"
                    f" ORDER BY date_trunc"
                )
            queries.append(query)
        if len(queries) > 1:
            subqueries = []
            coalesce_parts = []
            
            for i, query in enumerate(queries, start=1):
                subqueries.append(f"({query}) q{i}")
                coalesce_parts.append(f"COALESCE(q{i}.query{i}, 0) AS query{i}")
            date_coalesce_parts = [f"q{i}.date_trunc" for i in range(1, len(queries) + 1)]
            select_clause = f"SELECT COALESCE({', '.join(date_coalesce_parts)}) AS date_trunc, {', '.join(coalesce_parts)}"
            join_clause = subqueries[0]
            for i in range(2, len(queries) + 1):
                join_clause += f" FULL OUTER JOIN ({queries[i-1]}) q{i} ON q{i-1}.date_trunc = q{i}.date_trunc"
            joined_query = f"{select_clause} FROM {join_clause} ORDER BY date_trunc"  
        else:
            joined_query = queries[0]
        # print("Line Chart",query_fiter, joined_query) 

    summary = DataStorage.query_duckdb(joined_query)
    summary = apply_calculated_fields(summary, custom_fields)
    summary = summary.rename(columns={'metric_value': 'count'})

    # Create figure
    # group_by shapes the SQL the same way color does (one row per
    # date_trunc x category, not one row per date) whenever color itself
    # isn't set -- the figure has to split into one line per category the
    # same way, or plotly just connects every category's point at each date
    # in row order, drawing one distorted zigzag "line" instead of several.
    series_col = color
    if series_col:
        fig = px.line(
            summary,
            x='date_trunc',
            y='count',
            color=series_col,
            color_discrete_sequence=THEME["primary"],
            template='plotly_white',
            title=None  # Title added in layout
        )
    else:
        fig = px.line(
            summary,
            x='date_trunc',
            y='count',
            color_discrete_sequence=[THEME["chart_fill"]],
            template='plotly_white',
            title=None
        )
    
    # Line styling
    line_mode = 'lines+markers' if len(summary) < 50 else 'lines'
    
    fig.update_traces(
        mode='lines+markers' if smooth_lines else line_mode,
        line=dict(
            width=2.5 if not smooth_lines else 3,
            shape='spline' if smooth_lines else 'linear',
            smoothing=1.3 if smooth_lines else 0
        ),
        marker=dict(
            size=6,
            symbol='circle',
            line=dict(width=1, color='white')
        ),
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>" +
                      f"<b>{y_title}:</b> %{{y:,.0f}}<br>" +
                      "<extra></extra>"
    )
    
    # Add key point annotations
    if show_annotations and not summary.empty:
        try:
            summary = summary.sort_values('date_trunc').reset_index(drop=True)
            
            # Identify key points
            idx_start = 0
            idx_end = len(summary) - 1
            idx_max = summary['count'].idxmax() if summary['count'].notna().any() else None
            idx_min = summary['count'].idxmin() if summary['count'].notna().any() else None
            
            key_indices = {idx_start, idx_end}
            if idx_max is not None:
                key_indices.add(idx_max)
            if idx_min is not None:
                key_indices.add(idx_min)
            
            key_points = summary.loc[list(key_indices)]
            
            # Add markers for key points
            fig.add_scatter(
                x=key_points['date_trunc'],
                y=key_points['count'],
                mode='markers+text',
                text=key_points['count'].apply(lambda x: f'{int(x):,}' if x == int(x) else f'{x:,.1f}'),
                textposition='top center',
                marker=dict(size=12, color='#e74c3c', symbol='diamond', 
                           line=dict(width=2, color='white')),
                showlegend=False,
                name='Key Points',
                textfont=dict(size=10, color='#e74c3c', family='Arial, sans-serif'),
                hovertemplate="<b>Key Point:</b> %{x|%Y-%m-%d}<br>" +
                              f"<b>{y_title}:</b> %{{y:,.0f}}<extra></extra>"
            )
        except Exception:
            pass
    
    # Add average line
    if show_avg_line and not summary.empty:
        avg_val = summary['count'].mean()
        fig.add_hline(
            y=avg_val,
            line_dash="dash",
            line_color="#0b7903",
            line_width=1.5,
            opacity=0.7,
            annotation_text=f"Average: {avg_val:,.0f}",
            annotation_position="bottom right",
            annotation_font_size=11,
            annotation_font_color="#e74c3c"
        )
    
    # Add trend line (simple linear regression)
    if show_trend_line and len(summary) > 1:
        from scipy import stats
        x_numeric = range(len(summary))
        slope, intercept, r_value, p_value, std_err = stats.linregress(x_numeric, summary['count'])
        trend_values = [intercept + slope * i for i in x_numeric]
        
        fig.add_scatter(
            x=summary['date_trunc'],
            y=trend_values,
            mode='lines',
            line=dict(width=2, color='#f39c12', dash='dot'),
            name='Trend Line',
            opacity=0.8,
            hovertemplate=f"<b>Trend:</b> %{{y:,.0f}}<extra></extra>"
        )
    
    # Add simple forecast
    if forecast_periods > 0 and len(summary) > 2:
        from scipy import stats
        x_numeric = range(len(summary))
        slope, intercept, r_value, p_value, std_err = stats.linregress(x_numeric, summary['count'])
        
        last_date = summary['date_trunc'].iloc[-1]
        date_range = pd.date_range(start=last_date, periods=forecast_periods + 1, freq='D')[1:]
        
        forecast_values = [intercept + slope * (len(summary) + i) for i in range(forecast_periods)]
        
        fig.add_scatter(
            x=date_range,
            y=forecast_values,
            mode='lines+markers',
            line=dict(width=2, color='#0b7903', dash='dash'),
            marker=dict(size=6, symbol='diamond'),
            name='Forecast',
            opacity=0.7,
            hovertemplate="<b>Forecast:</b> %{x|%Y-%m-%d}<br>" +
                          f"<b>{y_title}:</b> %{{y:,.0f}}<extra></extra>"
        )
    
    # Modern layout configuration
    layout_config = {
        'title': dict(
            text=f'<b>{title}</b>',
            x=0.5,
            xanchor='center',
            font=dict(size=18, color='#2c3e50', family='Arial, sans-serif'),
            y=0.95
        ),
        'xaxis_title': dict(
            text=x_title,
            font=dict(size=13, color='#34495e', family='Arial, sans-serif'),
            standoff=10
        ),
        'yaxis_title': dict(
            text=y_title,
            font=dict(size=13, color='#34495e', family='Arial, sans-serif'),
            standoff=10
        ),
        'template': 'plotly_white',
        'legend_title': dict(
            text=legend_title if legend_title else (series_col if series_col else ""),
            font=dict(size=12, color='#2c3e50')
        ),
        'legend': dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor='#e2e8f0',
            borderwidth=1
        ),
        'plot_bgcolor': '#ffffff',
        'paper_bgcolor': '#ffffff',
        'margin': dict(l=60, r=40, t=80, b=50, pad=4),
        'height': height,
        'hovermode': 'x unified',
        'font': dict(family='Arial, sans-serif', size=12, color='#2c3e50'),
        'autosize': responsive,
        'width': None if responsive else 900,
    }
    
    fig.update_layout(**layout_config)
    
    # Modern axes styling
    fig.update_xaxes(
        title_standoff=10,
        showgrid=True,
        gridwidth=0.5,
        gridcolor='#e8ecef',
        showline=True,
        linewidth=1,
        linecolor='#cbd5e0',
        tickangle=-45 if len(summary) > 10 else 0,
        tickfont=dict(size=11, color='#4a5568'),
        tickformat='%b %d, %Y' if date_granularity == 'day' else '%b %Y',
        rangeslider=dict(visible=False),  # Can be enabled if needed
        rangeselector=dict(
            buttons=list([
                dict(count=7, label="1w", step="day", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(count=3, label="3m", step="month", stepmode="backward"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                dict(step="all", label="All")
            ]),
            bgcolor='white',
            bordercolor='#cbd5e0',
            borderwidth=1,
            font=dict(size=10, color='#2c3e50')
        ) if len(summary) > 30 else None
    )
    
    fig.update_yaxes(
        title_standoff=10,
        showgrid=True,
        gridwidth=0.5,
        gridcolor='#e8ecef',
        showline=True,
        linewidth=1,
        linecolor='#cbd5e0',
        zeroline=True,
        zerolinewidth=1,
        zerolinecolor='#e2e8f0',
        tickfont=dict(size=11, color='#4a5568'),
        tickformat=',.0f'
    )
    
    # Add range slider for long time series
    if len(summary) > 60:
        fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.05))
    
    # Add fill below line for single series
    if not color and len(summary) > 0:
        fig.update_traces(
            fill='tozeroy',
            fillcolor='rgba(44, 62, 80, 0.1)',
            selector=dict(mode='lines+markers')
        )
    
    return fig


def create_new_returning_chart(
    query_fiter, data_path,
    title,
    chart_mode='pie',
    date_col=DATE_,
    unique_column=PERSON_ID_,
    filter_col1=None, filter_value1=None,
    filter_col2=None, filter_value2=None,
    filter_col3=None, filter_value3=None,
    custom_fields=None,
    height=400,
    hole_size=0.45,
    group_by=None,
):
    """
    Classify patients in the filtered window as 'New' or 'Returning'.

    'New'       = patient's first ever visit falls within the filtered window
    'Returning' = patient has at least one visit BEFORE the filtered window
    """
    isSet = False
    filter_pairs = [
        (filter_col1, filter_value1),
        (filter_col2, filter_value2),
        (filter_col3, filter_value3),
    ]
    conditions = []
    for col, val in filter_pairs:
        if col is not None and val is not None:
            col = _normalize_filter_value(col)
            if isinstance(col, list):
                col = col[0]
            val = _normalize_filter_value(val)
            conditions.append(build_filter_query(col, val, data_path, unique_column, isSet, None, None))

    where_clause = query_fiter + ((" AND " + " AND ".join(conditions)) if conditions else "")

    # ── CTE: Find first visit date for each patient ──────────────────────────
    # This finds the absolute first visit date for each patient across ALL data
    first_visits_cte = f"""
        WITH first_visits AS (
            SELECT DISTINCT {unique_column}, MIN({date_col}) AS first_visit_date
            FROM '{data_path}'
            GROUP BY {unique_column}
        )
    """

    if chart_mode == 'line':
        group_by_select = f", {group_by}" if group_by else ""
        group_by_groupby = f", {group_by}" if group_by else ""
        
        sql = first_visits_cte + f"""
        SELECT
            CAST(f.{date_col} AS DATE)                                       AS date_trunc,
            CASE WHEN f.{date_col} = fv.first_visit_date THEN 'New'
                 ELSE 'Returning' END                                         AS patient_type{group_by_select},
            COUNT(DISTINCT f.{unique_column})                                 AS metric_value
        FROM '{data_path}' f
        INNER JOIN first_visits fv ON f.{unique_column} = fv.{unique_column}
        WHERE {where_clause}
        GROUP BY date_trunc, patient_type{group_by_groupby}
        ORDER BY date_trunc
        """
        
        df = DataStorage.query_duckdb(sql)
        df = apply_calculated_fields(df, custom_fields)
        
        if group_by and not df.empty:
            df = df.groupby(['date_trunc', 'patient_type'], as_index=False)['metric_value'].sum()
            
        if df.empty:
            return go.Figure().update_layout(title=dict(text=f'<b>{title}</b>', x=0.5),
                                             height=height, paper_bgcolor='#ffffff')

        fig = px.line(
            df, x='date_trunc', y='metric_value', color='patient_type',
            color_discrete_map={'New': THEME['primary'][0], 'Returning': THEME['primary'][3]},
            template='plotly_white',
            title=None,
        )
        fig.update_traces(
            mode='lines+markers',
            line=dict(width=2.5),
            marker=dict(size=5, symbol='circle', line=dict(width=1, color='white')),
        )
        fig.update_layout(
            title=dict(text=f'<b>{title}</b>', x=0.5, xanchor='center',
                       font=dict(size=16, color='#2c3e50', family='Arial, sans-serif')),
            xaxis=dict(title='Date', showgrid=False, linecolor='#dee2e6', tickangle=-30),
            yaxis=dict(title='Patients', gridcolor='#f0f0f0', zeroline=False),
            legend=dict(title='Patient Type', orientation='h', y=1.05, x=0),
            height=height, paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
            margin=dict(l=50, r=30, t=70, b=60),
        )

    else:  # pie / donut
        group_by_select = f", {group_by}" if group_by else ""
        group_by_groupby = f", {group_by}" if group_by else ""
        
        sql = first_visits_cte + f"""
        SELECT
            CASE WHEN f.{date_col} = fv.first_visit_date THEN 'New'
                 ELSE 'Returning' END                                         AS patient_type{group_by_select},
            COUNT(DISTINCT f.{unique_column})                                 AS metric_value
        FROM '{data_path}' f
        INNER JOIN first_visits fv ON f.{unique_column} = fv.{unique_column}
        WHERE {where_clause}
        GROUP BY patient_type{group_by_groupby}
        """
        
        df = DataStorage.query_duckdb(sql)
        df = apply_calculated_fields(df, custom_fields)
        
        if group_by and not df.empty:
            df = df.groupby(['patient_type'], as_index=False)['metric_value'].sum()
            
        if df.empty:
            return go.Figure().update_layout(title=dict(text=f'<b>{title}</b>', x=0.5),
                                             height=height, paper_bgcolor='#ffffff')

        total = df['metric_value'].sum()
        df['pct'] = (df['metric_value'] / total * 100).round(1).astype(str) + '%'

        fig = px.pie(
            df, names='patient_type', values='metric_value',
            hole=hole_size,
            color='patient_type',
            color_discrete_map={'New': THEME['primary'][0], 'Returning': THEME['primary'][3]},
            template='plotly_white',
            title=None,
        )
        fig.update_traces(
            textposition='outside',
            textinfo='label+percent',
            textfont=dict(size=12, color='#2c3e50'),
            marker=dict(line=dict(color='white', width=2)),
            pull=[0.04] * len(df),
        )
        # Centre annotation
        new_row = df[df['patient_type'] == 'New']
        if not new_row.empty:
            new_pct = round(new_row['metric_value'].iloc[0] / total * 100, 1)
            fig.add_annotation(
                text=f"<b>{new_pct}%</b><br>New",
                x=0.5, y=0.5, font=dict(size=13, color=THEME['primary'][0]),
                showarrow=False,
            )
        fig.update_layout(
            title=dict(text=f'<b>{title}</b>', x=0.5, xanchor='center',
                       font=dict(size=16, color='#2c3e50', family='Arial, sans-serif')),
            legend=dict(orientation='h', y=-0.15, x=0.5, xanchor='center'),
            height=height, paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
            margin=dict(l=30, r=30, t=70, b=60),
        )

    return fig


_WINDOW_RE = re.compile(
    r"(?P<col>\w+)\s*>=\s*'(?P<start>[^']+)'::TIMESTAMP\s+AND\s+(?P=col)\s*<=\s*'(?P<end>[^']+)'::TIMESTAMP"
)


def widen_query_window(query_filter, lookback_days):
    """Rewrites a "<col> >= '<start>'::TIMESTAMP AND <col> <= '<end>'::TIMESTAMP"
    window -- e.g. pages/home.py's network_query/filtered_query_data_range,
    which looks like "Date >= '2026-08-31 00:00:00'::TIMESTAMP AND Date <=
    '2026-09-07 23:59:59'::TIMESTAMP" plus scope conditions -- to instead
    span exactly `lookback_days` trailing days ending at the SAME end date.
    Any trailing conditions after the date bounds (facility/programme/etc
    scope) are left untouched. Returns query_filter unchanged if that shape
    isn't found, so callers can pass any WHERE-clause string safely.
    """
    match = _WINDOW_RE.search(query_filter)
    if not match:
        return query_filter
    col = match.group("col")
    end_str = match.group("end")
    end_dt = pd.to_datetime(end_str)
    new_start = end_dt.normalize() - pd.Timedelta(days=lookback_days - 1)
    new_clause = f"{col} >= '{new_start}'::TIMESTAMP AND {col} <= '{end_str}'::TIMESTAMP"
    return query_filter[:match.start()] + new_clause + query_filter[match.end():]


def compute_entity_daily_counts(query_filter, data_path, entity_col=FACILITY_, group_by_col=PROGRAM_, unique_col=PERSON_ID_):
    """One row per (entity, Date) with COUNT(DISTINCT unique_col) records,
    grouped through group_by_col first then summed back down (same
    group_by convention used elsewhere in this app, e.g. the "All
    Attendance" KPI's own group_by="Program"): an entity touching more than
    one group_by_col value on the same day is counted once per value, so
    totals can exceed the true distinct-count. Generic over
    entity_col/group_by_col/unique_col so the same function backs facility,
    programme, or user-level heatmaps/attention checks alike -- the
    returned entity column is always named "entity".
    """
    sub_sql = (
        f"SELECT {entity_col} AS entity, CAST({DATE_} AS DATE) AS d, {group_by_col}, "
        f"COUNT(DISTINCT {unique_col}) AS n "
        f"FROM '{data_path}' WHERE {query_filter} "
        f"GROUP BY {entity_col}, CAST({DATE_} AS DATE), {group_by_col}"
    )
    sql = (
        f"SELECT entity, d, SUM(n) AS n FROM ({sub_sql}) "
        f"GROUP BY entity, d ORDER BY entity, d"
    )
    try:
        df = DataStorage.query_duckdb(sql)
    except Exception:
        df = pd.DataFrame(columns=["entity", "d", "n"])
    return df


def compute_segment_drop(query_filter, data_path, entity_col=FACILITY_, group_by_col=PROGRAM_,
                          unique_col=PERSON_ID_, lookback_days=14, segment_days=7, drop_threshold=0.25):
    """Entities whose average daily count over the most recent `segment_days`
    (segment B, "last N days") fell by at least `drop_threshold` compared to
    their average over the `segment_days` immediately before that (segment
    A), across a trailing `lookback_days` window widened from query_filter's
    own end date via widen_query_window. Generic over
    entity_col/group_by_col/unique_col -- the same detector backs facility,
    programme, or user-level attention checks/heatmaps alike. Returns
    (count, pct_of_total, flagged_entities, daily_counts_df) -- daily_counts_df
    is the raw per-entity-per-day data over the widened window, reusable by
    a heatmap that needs the same window without re-querying.
    """
    widened_filter = widen_query_window(query_filter, lookback_days)
    df = compute_entity_daily_counts(
        widened_filter, data_path, entity_col=entity_col, group_by_col=group_by_col, unique_col=unique_col,
    )
    if df.empty:
        return 0, 0.0, [], df

    df = df.copy()
    df["d"] = pd.to_datetime(df["d"])
    total_entities = df["entity"].nunique()

    max_date = df["d"].max()
    segment_b_start = max_date - pd.Timedelta(days=segment_days - 1)
    segment_a_end = segment_b_start - pd.Timedelta(days=1)
    segment_a_start = segment_a_end - pd.Timedelta(days=segment_days - 1)

    flagged = []
    for entity, sub in df.groupby("entity"):
        seg_a = sub[(sub["d"] >= segment_a_start) & (sub["d"] <= segment_a_end)]["n"]
        seg_b = sub[(sub["d"] >= segment_b_start) & (sub["d"] <= max_date)]["n"]
        if seg_a.empty or seg_b.empty:
            continue
        avg_a = seg_a.mean()
        avg_b = seg_b.mean()
        if avg_a > 0 and avg_b <= avg_a * (1 - drop_threshold):
            flagged.append(entity)

    count = len(flagged)
    pct = (count / total_entities * 100) if total_entities else 0.0
    return count, pct, flagged, df


def compute_facilities_requiring_attention(query_filter, data_path, lookback_days=14, segment_days=7, drop_threshold=0.25):
    """Facility-specific convenience wrapper around compute_segment_drop --
    see that function for the detection rule. Returns (count, pct_of_total,
    flagged_facility_names).
    """
    count, pct, flagged, _df = compute_segment_drop(
        query_filter, data_path, entity_col=FACILITY_, group_by_col=PROGRAM_, unique_col=PERSON_ID_,
        lookback_days=lookback_days, segment_days=segment_days, drop_threshold=drop_threshold,
    )
    return count, pct, flagged


_HEATMAP_BAND_COLORS = ["#DC2626", "#F87171", "#FFC107", "#86EFAC", "#16A34A"]


def create_entity_heatmap(query_filter, data_path, title="Performance Heatmap", entity_label="Facility",
                          entity_col=FACILITY_, group_by_col=PROGRAM_, unique_col=PERSON_ID_,
                          lookback_days=14, segment_days=7, drop_threshold=0.25,
                          only_declining=True, page_size=5, dom_id=None):
    """Entity (rows) x Date (columns) performance table -- red for low
    activity (worst case), green for high activity (good case), banded into
    5 colour steps across the table's own min/max. Paginated (page_size
    rows per page) since this is a table, not a plot -- white borders
    between cells via style_cell. When only_declining, rows are limited to
    whatever compute_segment_drop flags as having dropped by drop_threshold
    or more. Generic over entity_col/group_by_col/unique_col so the same
    builder backs facility, programme, or user-level heatmaps alike.
    Returns an html.Div wrapping a dash_table.DataTable; dom_id is set on
    that outer Div (not the table itself) so it can be used as a scroll-to
    target.
    """
    if only_declining:
        _count, _pct, flagged, df = compute_segment_drop(
            query_filter, data_path, entity_col=entity_col, group_by_col=group_by_col, unique_col=unique_col,
            lookback_days=lookback_days, segment_days=segment_days, drop_threshold=drop_threshold,
        )
        if not flagged:
            return html.Div(
                [
                    html.H4(title, style={"textAlign": "center"}),
                    html.Div(f"No {entity_label}(s) currently show a drop of {drop_threshold * 100:.0f}% or more."),
                ],
                id=dom_id,
            )
        df = df[df["entity"].isin(flagged)]
    else:
        widened_filter = widen_query_window(query_filter, lookback_days)
        df = compute_entity_daily_counts(
            widened_filter, data_path, entity_col=entity_col, group_by_col=group_by_col, unique_col=unique_col,
        )
        if df.empty:
            return html.Div(
                [html.H4(title, style={"textAlign": "center"}), html.Div(f"No {entity_label.lower()} activity in scope.")],
                id=dom_id,
            )

    pivot = df.pivot_table(index="entity", columns="d", values="n", fill_value=0).sort_index()
    date_cols = [pd.Timestamp(c).strftime("%Y-%m-%d") for c in pivot.columns]
    pivot.columns = date_cols
    table_df = pivot.reset_index().rename(columns={"entity": entity_label})

    vmin = float(pivot.values.min())
    vmax = float(pivot.values.max())
    span = (vmax - vmin) or 1.0
    n_bands = len(_HEATMAP_BAND_COLORS)

    style_data_conditional = []
    for col in date_cols:
        for i, color in enumerate(_HEATMAP_BAND_COLORS):
            lo = vmin + span * i / n_bands
            hi = vmin + span * (i + 1) / n_bands
            condition = f"{{{col}}} >= {lo}" if i == n_bands - 1 else f"{{{col}}} >= {lo} && {{{col}}} < {hi}"
            style_data_conditional.append({
                "if": {"filter_query": condition, "column_id": col},
                "backgroundColor": color,
                "color": "#ffffff" if i < 2 else "#0F172A",
            })

    return html.Div(
        [
            html.H4(title, style={"textAlign": "center"}),
            dash_table.DataTable(
                columns=[{"name": entity_label, "id": entity_label}] + [{"name": c, "id": c} for c in date_cols],
                data=table_df.to_dict("records"),
                page_size=page_size,
                page_action="native",
                sort_action="native",
                style_cell={
                    "border": "1px solid white", "textAlign": "center",
                    "fontSize": "12px", "padding": "6px",
                },
                style_header={"border": "1px solid white", "backgroundColor": "#f8f9fa", "fontWeight": "bold"},
                style_data_conditional=style_data_conditional,
            ),
        ],
        id=dom_id,
    )


def create_pie_chart(query_fiter,data_path, names_col, values_col, title,
                     unique_column=PERSON_ID_, filter_col1=None,
                     filter_value1=None, filter_col2=None,
                     filter_value2=None, filter_col3=None,
                     filter_value3=None, colormap=None, aggregation='count',
                     custom_fields=None,rename = {}, replace={}, height=400, responsive=True,
                     hole_size=0.5, show_legend=True, legend_title=None,
                     sort_by_value=True, max_slices=None):
    """
    Create a modern, responsive donut/pie chart using Plotly Express.
    Aggregation is pushed into SQL: only the grouped summary rows
    are returned to Python, keeping RAM usage minimal.

    Parameters:
    - height: Chart height in pixels (default: 400)
    - responsive: Make chart responsive to container width (default: True)
    - hole_size: Donut hole ratio 0–1; 0 = full pie (default: 0.5)
    - show_legend: Show the external legend (default: True)
    - legend_title: Override legend header text (default: names_col)
    - sort_by_value: Sort slices largest-first (default: True)
    - max_slices: Collapse tail slices into "Other" (default: None = all)
    """
    isSet = False
    filter_pairs = [
        (filter_col1, filter_value1),
        (filter_col2, filter_value2),
        (filter_col3, filter_value3),
    ]
    conditions = []
    for col, val in filter_pairs:
        if col is not None and val is not None:
            col = _normalize_filter_value(col)
            if isinstance(col, list):
                col = col[0]
            val = _normalize_filter_value(val)
            conditions.append(build_filter_query(col, val,data_path, unique_column, isSet, None, None))

    where_clause = query_fiter + ((" AND " + " AND ".join(conditions)) if conditions else "")

    if aggregation in ('count', 'nunique'):
        agg_expr = f"COUNT(DISTINCT {values_col})"
    elif aggregation == 'sum':
        agg_expr = f"SUM({values_col})"
    elif aggregation == 'mean':
        agg_expr = f"AVG({values_col})"
    elif aggregation == 'median':
        agg_expr = f"MEDIAN({values_col})"
    elif aggregation == 'min':
        agg_expr = f"MIN({values_col})"
    elif aggregation == 'max':
        agg_expr = f"MAX({values_col})"
    else:
        agg_expr = f"{aggregation}({values_col})"

    order_clause = "ORDER BY data_value DESC" if sort_by_value else ""
    joined_query = (
        f"SELECT {names_col}, {agg_expr} AS data_value"
        f" FROM '{data_path}'"
        f" WHERE {where_clause}"
        f" GROUP BY {names_col}"
        f" HAVING data_value > 0"
        f" {order_clause}"
    )
    df_summary = DataStorage.query_duckdb(joined_query)
    df_summary = apply_calculated_fields(df_summary, custom_fields)

    if df_summary.empty:
        return go.Figure().update_layout(
            title=dict(
                text=f'<b>No data available for {title}</b>',
                x=0.5, xanchor='center',
                font=dict(size=18, color='#2c3e50', family='Arial, sans-serif')
            ),
            paper_bgcolor='#ffffff',
            height=height
        )
    # apply replace and rename
    df_summary = _apply_replace(df_summary.rename(columns=rename), replace)

    # Collapse tail slices into "Other"
    if max_slices and len(df_summary) > max_slices:
        top = df_summary.head(max_slices - 1)
        other_val = df_summary.iloc[max_slices - 1:]['data_value'].sum()
        other_row = pd.DataFrame({names_col: ['Other'], 'data_value': [other_val]})
        df_summary = pd.concat([top, other_row], ignore_index=True)

    color_sequence = (
        list(colormap.values()) if isinstance(colormap, dict)
        else THEME["gender"]
    )

    fig = px.pie(
        df_summary,
        names=names_col,
        values='data_value',
        hole=hole_size,
        color_discrete_sequence=color_sequence,
        template='plotly_white',
        title=None  # Title added in layout below
    )

    # Modern trace styling
    fig.update_traces(
        textposition='inside',
        textinfo='percent+label',
        textfont=dict(size=11, color='white', family='Arial, sans-serif'),
        hovertemplate=(
            "<b>%{label}</b><br>"
            "<b>Value:</b> %{value:,.0f}<br>"
            "<b>Share:</b> %{percent}<br>"
            "<extra></extra>"
        ),
        marker=dict(
            line=dict(color='#ffffff', width=2)   # clean white gap between slices
        ),
        pull=[0.03] + [0] * (len(df_summary) - 1)  # slight pull on the largest slice
    )

    # Shared modern layout (mirrors column/timeline)
    fig.update_layout(
        title=dict(
            text=f'<b>{title}</b>',
            x=0.5,
            xanchor='center',
            font=dict(size=18, color='#2c3e50', family='Arial, sans-serif'),
            y=0.97
        ),
        template='plotly_white',
        plot_bgcolor='#ffffff',
        paper_bgcolor='#ffffff',
        margin=dict(l=30, r=30, t=80, b=30, pad=4),
        height=height,
        autosize=responsive,
        width=None if responsive else 800,
        font=dict(family='Arial, sans-serif', size=12, color='#2c3e50'),
        showlegend=show_legend,
        legend=dict(
            title=dict(
                text=legend_title if legend_title else names_col,
                font=dict(size=12, color='#2c3e50')
            ),
            orientation='v',
            yanchor='middle',
            y=0.5,
            xanchor='left',
            x=1.02,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor='#e2e8f0',
            borderwidth=1,
            font=dict(size=11, color='#4a5568')
        ),
        # Subtle outer border (same as column chart)
        shapes=[
            dict(
                type='rect',
                xref='paper', yref='paper',
                x0=0, y0=0, x1=1, y1=1,
                line=dict(width=1, color='#e2e8f0'),
                fillcolor='rgba(0,0,0,0)'
            )
        ]
    )

    return fig
 
def create_pivot_table(query_fiter, data_path, index_col, columns_col, values_col, title, 
                       unique_column='PERSON_ID_', aggfunc='sum',
                       filter_col1=None, filter_value1=None,
                       filter_col2=None, filter_value2=None,
                       filter_col3=None, filter_value3=None,
                       aggregation='count',
                       rename={}, replace={}, custom_fields=None,
                       page_size=5,row_totals=False, current_page=0,
                       ): 
    """
    Create a pivot table with native pagination and sortable column headers.
    Returns a Dash html.Div containing a dash_table.DataTable.
    
    Parameters:
    -----------
    row_totals : bool, default=False
        If True, adds a 'Row Total' column to the pivot table showing sum of numeric values across columns
    """
    isSet = False
    filter_pairs = [
        (filter_col1, filter_value1),
        (filter_col2, filter_value2),
        (filter_col3, filter_value3),
    ]
    conditions = []
    for col, val in filter_pairs:
        if col is not None and val is not None:
            col = _normalize_filter_value(col)
            if isinstance(col, list):
                col = col[0]
            val = _normalize_filter_value(val)
            conditions.append(build_filter_query(col, val, data_path, unique_column, isSet, None, None))

    where_clause = query_fiter + ((" AND " + " AND ".join(conditions)) if conditions else "")

    index_cols = list(index_col) if isinstance(index_col, (list, tuple)) else [index_col]
    columns_cols = [columns_col] if (columns_col and columns_col != "") else []
    group_cols = index_cols + columns_cols
    group_sql = ", ".join(group_cols)

    if aggfunc == 'concat':
        agg_expr = f"STRING_AGG(DISTINCT CAST({values_col} AS VARCHAR), ', ' ORDER BY CAST({values_col} AS VARCHAR))"
    elif aggfunc == 'count':
        agg_expr = f"COUNT({values_col})"
    elif aggfunc == 'sum':
        agg_expr = f"SUM({values_col})"
    elif aggfunc == 'mean':
        agg_expr = f"AVG({values_col})"
    elif aggfunc == 'min':
        agg_expr = f"MIN({values_col})"
    elif aggfunc == 'max':
        agg_expr = f"MAX({values_col})"
    else:
        agg_expr = f"COUNT(DISTINCT {values_col})"

    joined_query = (
        f"SELECT {group_sql}, {agg_expr} AS __value__"
        f" FROM '{data_path}'"
        f" WHERE {where_clause}"
        f" GROUP BY {group_sql}"
    )
    data = DataStorage.query_duckdb(joined_query)
    data = apply_calculated_fields(data, custom_fields)
    data = data.rename(columns={"__value__": values_col})

    pivot = data.pivot_table(
        index=index_col,
        columns=columns_col if columns_col != "" else None,
        values=values_col,
        aggfunc='first',
        fill_value=0 if aggfunc != 'concat' else ""
    ).reset_index()

    pivot = _apply_replace(pivot.rename(columns=rename), replace)
    
    if row_totals:
        index_cols_list = index_col if isinstance(index_col, list) else [index_col]
        
        numeric_cols = [c for c in pivot.columns if c not in index_cols_list and 
                       pd.api.types.is_numeric_dtype(pivot[c])]
        
        if numeric_cols:
            pivot['Row Total'] = pivot[numeric_cols].sum(axis=1)
            # other_cols = [c for c in pivot.columns if c not in index_cols_list + ['Row Total']]
            # pivot = pivot[index_cols_list + ['Row Total'] + other_cols]
    
    pivot.columns = [str(c) for c in pivot.columns]

    num_index_cols = len(index_cols)
    index_col_ids = [str(c) for c in pivot.columns[:num_index_cols]]

    dash_columns = [{"name": col, "id": col} for col in pivot.columns]
    data_records = pivot.to_dict("records")

    style_data_conditional = [
        {"if": {"row_index": "odd"}, "backgroundColor": THEME["table_row_alt"]},
        {"if": {"state": "active"}, "backgroundColor": THEME["table_active_bg"], "border": f"1px solid {THEME['table_active_border']}", "color": "#2c3e50"},
    ]
    for col_id in index_col_ids:
        style_data_conditional.append({
            "if": {"column_id": col_id},
            "fontWeight": "bold",
            "backgroundColor": THEME["table_index_bg"],
            "color": "#2c3e50",
            "textAlign": "left",
        })
    
    # --- NEW: Style for Row Total column ---
    if row_totals:
        style_data_conditional.append({
            "if": {"column_id": "Row Total"},
            "fontWeight": "bold",
            "backgroundColor": "#f8f9fa",
            "borderLeft": "2px solid #004a01",
            "color": "#004a01",
        })

    table = html.Div(
        [
            html.H4(
                title,
                style={
                    "textAlign": "center",
                    "marginBottom": "16px",
                    "marginTop": "12px",
                    "fontFamily": "Arial, sans-serif",
                    "fontSize": "18px",
                    "fontWeight": "bold",
                    "color": THEME["table_header_text"],
                },
            ),
            html.Div(
                dash_table.DataTable(
                    columns=dash_columns,
                    data=data_records,
                    page_size=page_size,
                    page_action="native",
                    sort_action="native",
                    sort_mode="multi",
                    virtualization=False,
                    style_header={
                        "backgroundColor": THEME["table_header"],
                        "color": THEME["table_header_text"],
                        "fontWeight": "bold",
                        "fontFamily": "Arial, sans-serif",
                        "textAlign": "center",
                        "fontSize": "13px",
                        "height": "42px",
                        "lineHeight": "42px",
                        "whiteSpace": "normal",
                        "borderBottom": "2px solid #004a01",
                        "cursor": "pointer",
                        "textTransform": "uppercase",
                    },
                    style_cell={
                        "padding": "10px 14px",
                        "textAlign": "center",
                        "fontSize": "13px",
                        "fontFamily": "Arial, sans-serif",
                        "color": "#2c3e50",
                        "whiteSpace": "normal",
                        "border": "1px solid #dee2e6",
                        "backgroundColor": "#ffffff",
                    },
                    style_data_conditional=style_data_conditional,
                    style_table={
                        "overflowX": "auto",
                        "marginTop": "8px",
                        "borderRadius": "8px",
                        "border": f"1px solid {THEME['table_active_border']}",
                        "boxShadow": "0 1px 3px rgba(0,100,1,0.10)",
                    },
                )
            ),
        ],
        style={
            "width": "100%",
            "fontFamily": "Arial, sans-serif",
            "backgroundColor": "#ffffff",
            "padding": "8px",
            "borderRadius": "8px",
        },
    )


    return table, pivot

def create_time_range_table(
    query_fiter, data_path, index_col, datetime_col, title,
    start_label="Start Time", end_label="End Time",
    unique_column=PERSON_ID_,
    filter_col1=None, filter_value1=None,
    filter_col2=None, filter_value2=None,
    filter_col3=None, filter_value3=None,
    rename={}, replace={}, custom_fields=None,
    page_size=5,
):
    """
    Group by index_col and show the time-of-day (not the date) of the
    earliest and latest datetime_col value in each group -- e.g. "what time
    does each User's first/last recorded activity fall at" (Start Time / End
    Time). MIN/MAX of the same column as two named columns doesn't fit
    create_pivot_table's single values_col + aggfunc + pivot shape, so this
    is its own function; same table look otherwise. Returns (html.Div, DataFrame).
    """
    isSet = False
    filter_pairs = [
        (filter_col1, filter_value1),
        (filter_col2, filter_value2),
        (filter_col3, filter_value3),
    ]
    conditions = []
    for col, val in filter_pairs:
        if col is not None and val is not None:
            col = _normalize_filter_value(col)
            if isinstance(col, list):
                col = col[0]
            val = _normalize_filter_value(val)
            conditions.append(build_filter_query(col, val, data_path, unique_column, isSet, None, None))

    where_clause = query_fiter + ((" AND " + " AND ".join(conditions)) if conditions else "")

    index_cols = list(index_col) if isinstance(index_col, (list, tuple)) else [index_col]
    group_sql = ", ".join(index_cols)

    joined_query = (
        f"SELECT {group_sql}, MIN({datetime_col}) AS __start_dt__, MAX({datetime_col}) AS __end_dt__"
        f" FROM '{data_path}'"
        f" WHERE {where_clause}"
        f" GROUP BY {group_sql}"
    )
    data = DataStorage.query_duckdb(joined_query)
    data = apply_calculated_fields(data, custom_fields)

    data[start_label] = pd.to_datetime(data["__start_dt__"]).dt.strftime('%H:%M:%S')
    data[end_label] = pd.to_datetime(data["__end_dt__"]).dt.strftime('%H:%M:%S')
    data = data.drop(columns=["__start_dt__", "__end_dt__"])

    data = _apply_replace(data.rename(columns=rename), replace)
    data.columns = [str(c) for c in data.columns]

    num_index_cols = len(index_cols)
    index_col_ids = [str(c) for c in data.columns[:num_index_cols]]

    dash_columns = [{"name": col, "id": col} for col in data.columns]
    data_records = data.to_dict("records")

    style_data_conditional = [
        {"if": {"row_index": "odd"}, "backgroundColor": THEME["table_row_alt"]},
        {"if": {"state": "active"}, "backgroundColor": THEME["table_active_bg"], "border": f"1px solid {THEME['table_active_border']}", "color": "#2c3e50"},
    ]
    for col_id in index_col_ids:
        style_data_conditional.append({
            "if": {"column_id": col_id},
            "fontWeight": "bold",
            "backgroundColor": THEME["table_index_bg"],
            "color": "#2c3e50",
            "textAlign": "left",
        })

    table = html.Div(
        [
            html.H4(
                title,
                style={
                    "textAlign": "center",
                    "marginBottom": "16px",
                    "marginTop": "12px",
                    "fontFamily": "Arial, sans-serif",
                    "fontSize": "15px",
                    "fontWeight": "bold"
                },
            ),
            html.Div(
                dash_table.DataTable(
                    columns=dash_columns,
                    data=data_records,
                    page_size=page_size,
                    page_action="native",
                    sort_action="native",
                    sort_mode="multi",
                    style_header={
                        "backgroundColor": THEME["table_header"],
                        "color": THEME["table_header_text"],
                        "fontWeight": "bold",
                        "fontFamily": "Arial, sans-serif",
                        "textAlign": "center",
                        "fontSize": "13px",
                        "height": "22px",
                        "lineHeight": "22px",
                        "whiteSpace": "normal",
                        "borderBottom": "2px solid #ffffff",
                        "cursor": "pointer",
                        "textTransform": "uppercase",
                    },
                    style_cell={
                        "padding": "10px 14px",
                        "textAlign": "center",
                        "fontSize": "13px",
                        "fontFamily": "Arial, sans-serif",
                        "color": "#2c3e50",
                        "whiteSpace": "normal",
                        "border": "1px solid #dee2e6",
                        "backgroundColor": "#ffffff",
                    },
                    style_data_conditional=style_data_conditional,
                    style_table={
                        "overflowX": "auto",
                        "marginTop": "8px",
                        "borderRadius": "8px",
                        "border": f"1px solid {THEME['table_active_border']}",
                        "boxShadow": "0 1px 3px rgba(0,100,1,0.10)",
                    },
                )
            ),
        ],
        style={
            "width": "100%",
            "fontFamily": "Arial, sans-serif",
            "backgroundColor": "#ffffff",
            "padding": "8px",
            "borderRadius": "8px",
        },
    )

    return table, data


def create_crosstab_table(
    query_fiter,
    data_path,
    index_col,
    columns_col,
    title,
    values_col=None,
    aggfunc='count',
    normalize=None,
    unique_column=PERSON_ID_,
    filter_col1=None, filter_value1=None,
    filter_col2=None, filter_value2=None,
    filter_col3=None, filter_value3=None,
    rename={}, replace={}, custom_fields=None,
    group_by=None,
):
    """
    Create a crosstab table with multilayer column headers using Dash DataTable.
    Only the columns required for the crosstab are fetched. For concat aggfunc,
    STRING_AGG is pushed into SQL so no Python lambda is needed.
    """
    isSet = False
    filter_pairs = [
        (filter_col1, filter_value1),
        (filter_col2, filter_value2),
        (filter_col3, filter_value3),
    ]
    conditions = []
    for col, val in filter_pairs:
        if col is not None and val is not None:
            col = _normalize_filter_value(col)
            if isinstance(col, list):
                col = col[0]
            val = _normalize_filter_value(val)
            conditions.append(build_filter_query(col, val,data_path, unique_column, isSet, None, None))

    where_clause = query_fiter + ((" AND " + " AND ".join(conditions)) if conditions else "")

    needed = []
    for c in (index_col if isinstance(index_col, (list, tuple)) else [index_col]):
        needed.append(c)
    for c in (columns_col if isinstance(columns_col, (list, tuple)) else [columns_col]):
        needed.append(c)

    if aggfunc == 'concat' and values_col:
        group_cols = list(dict.fromkeys(needed))
        group_sql  = ", ".join(group_cols)
        agg_expr   = (
            f"STRING_AGG(DISTINCT CAST({values_col} AS VARCHAR), ', '"
            f" ORDER BY CAST({values_col} AS VARCHAR))"
        )
        joined_query = (
            f"SELECT {group_sql}, {agg_expr} AS {values_col}"
            f" FROM '{data_path}'"
            f" WHERE {where_clause}"
            f" GROUP BY {group_sql}"
        )
        data = DataStorage.query_duckdb(joined_query)
        data = apply_calculated_fields(data, custom_fields)
        ct_aggfunc = 'first'
    else:
        if values_col:
            needed.append(values_col)
        select_cols = ", ".join(dict.fromkeys(needed))
        if group_by and aggfunc in ('nunique', 'count', 'min', 'max'):
            # Safe to pre-group in SQL only for these aggfuncs -- they only
            # care about distinct combinations, not row counts, so collapsing
            # duplicate rows via GROUP BY (fewer rows sent back from DuckDB)
            # doesn't change what pd.crosstab computes below. Not applied for
            # sum/mean/concat, where collapsing duplicates first would
            # silently change the totals.
            group_cols_full = ", ".join(dict.fromkeys(needed + [group_by]))
            joined_query = (
                f"SELECT {group_cols_full}, COUNT(*) AS Value"
                f" FROM '{data_path}'"
                f" WHERE {where_clause}"
                f" GROUP BY {group_cols_full}"
            )
        else:
            joined_query = (
                f"SELECT {select_cols}"
                f" FROM '{data_path}'"
                f" WHERE {where_clause}"
            )
        data = DataStorage.query_duckdb(joined_query)
        data = apply_calculated_fields(data, custom_fields)
        data = _apply_replace(data.rename(columns=rename), replace)
        ct_aggfunc = aggfunc

    def _axis_arg(arg):
        if isinstance(arg, (list, tuple)):
            return [data[c] for c in arg]
        return data[arg]

    index_arg   = _axis_arg(index_col)
    columns_arg = _axis_arg(columns_col)

    norm = False
    if normalize is True:
        norm = 'all'
    elif normalize in ('all', 'index', 'columns'):
        norm = normalize

    if values_col is None:
        ct = pd.crosstab(index=index_arg, columns=columns_arg, normalize=norm)
    else:
        ct = pd.crosstab(
            index=index_arg,
            columns=columns_arg,
            values=data[values_col],
            aggfunc=ct_aggfunc,
            normalize=norm if ct_aggfunc != 'first' else False,
        )

    # With 2+ column levels, pandas only creates a column for (outer, inner) pairs
    # that actually co-occur in the data — so one outer group (e.g. a Program) can
    # end up with fewer inner sub-columns (e.g. Encounter) than another. Reindex to
    # the full outer x inner grid so every outer group shows the same set of inner
    # sub-columns, which is what lets them merge cleanly under one header cell each.
    if isinstance(ct.columns, pd.MultiIndex) and ct.columns.nlevels >= 2:
        inner_values = ct.columns.get_level_values(-1).unique()
        outer_combos = ct.columns.droplevel(-1).unique()
        outer_tuples = list(outer_combos) if isinstance(outer_combos, pd.MultiIndex) else [(v,) for v in outer_combos]
        full_columns = pd.MultiIndex.from_tuples(
            [outer + (inner,) for outer in outer_tuples for inner in inner_values],
            names=ct.columns.names
        )
        ct = ct.reindex(columns=full_columns)

    ct = ct.fillna(0)
    ct = ct.reset_index()
    # ct = _apply_replace(ct.rename(columns=rename), replace)

    dash_columns = []
    for col in ct.columns:
        if isinstance(col, tuple):
            dash_columns.append({
                "name": [str(c).upper() for c in col],
                "id": "|".join([str(c) for c in col])
            })
        else:
            dash_columns.append({
                "name": [str(col).upper()],
                "id": str(col)
            })

    ct_flat = ct.copy()
    ct_flat.columns = [
        "|".join(str(c) for c in col) if isinstance(col, tuple) else str(col)
        for col in ct.columns
    ]

    data_records = ct_flat.to_dict("records")

    # reset_index() always prepends the index columns first, so the first
    # n_index_levels dash_columns are the row-index axis and the rest are the
    # (possibly 2-level) columns axis — used to build the two filter dropdowns.
    n_index_levels = len(index_col) if isinstance(index_col, (list, tuple)) else 1
    index_dash_columns = dash_columns[:n_index_levels]
    group_dash_columns = dash_columns[n_index_levels:]

    index_filter_options = (
        sorted({str(v) for v in ct_flat[index_dash_columns[0]["id"]].dropna().unique()})
        if index_dash_columns else []
    )
    columns_filter_options = sorted({c["name"][0] for c in group_dash_columns if c["name"][0]})

    # When District and/or Facility are part of the index, clicking a row's
    # index cell can drill straight into the app's own District/Facility
    # filters -- home.py's crosstab-drill-down callback reads this mapping
    # (logical name -> actual flat column id) off the store to know which
    # columns are clickable and what to look up in the clicked row.
    # Compare against "id" (untouched, e.g. "District" or "District|" when
    # padded for a multi-level columns axis), not "name" -- "name" is the
    # cosmetic display label (upper-cased for the header) and isn't reliable
    # to match against.
    index_click_map = {
        col["id"].split("|")[0]: col["id"]
        for col in index_dash_columns
        if col["id"].split("|")[0] in (DISTRICT_, FACILITY_)
    }

    uid = uuid.uuid4().hex[:8]
    table_id = {"type": "crosstab-table", "index": uid}
    store_id = {"type": "crosstab-data-store", "index": uid}
    index_dd_id = {"type": "crosstab-index-filter", "index": uid}
    columns_dd_id = {"type": "crosstab-columns-filter", "index": uid}
    download_btn_id = {"type": "crosstab-download-btn", "index": uid}
    download_id = {"type": "crosstab-download", "index": uid}

    dropdown_style = {"width": "170px", "fontSize": "12px", "textAlign": "left"}
    filter_controls_children = []
    if index_dash_columns:
        filter_controls_children.append(
            dcc.Dropdown(
                id=index_dd_id,
                options=[{"label": v, "value": v} for v in index_filter_options],
                placeholder=f"Filter {index_dash_columns[0]['name'][0]}",
                clearable=True,
                style=dropdown_style,
            )
        )
    if group_dash_columns:
        filter_controls_children.append(
            dcc.Dropdown(
                id=columns_dd_id,
                options=[{"label": v, "value": v} for v in columns_filter_options],
                placeholder=f"Filter {group_dash_columns[0]['name'][0]}",
                clearable=True,
                style=dropdown_style,
            )
        )
    filter_controls_children.append(
        html.Button(
            DashIconify(icon="lucide:download", width=16),
            id=download_btn_id,
            n_clicks=0,
            title="Download as Excel",
            style={
                "padding": "6px 8px",
                "border": "1px solid #d1d5db",
                "borderRadius": "4px",
                "background": "#ffffff",
                "color": "grey",
                "cursor": "pointer",
                "display": "flex",
                "alignItems": "center",
            },
        )
    )

    table = html.Div(
        [
            html.Div(
                [
                    html.H4(
                        title,
                        style={
                            "margin": "0",
                            "fontFamily": "Arial, sans-serif",
                            "fontSize": "15px",
                            "fontWeight": "bold",
                        },
                    ),
                    html.Div(
                        filter_controls_children,
                        style={
                            "display": "flex",
                            "gap": "8px",
                            "alignItems": "center",
                            "justifyContent": "flex-end",
                            "flexWrap": "wrap",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "flexWrap": "wrap",
                    "gap": "8px",
                    "marginBottom": "16px",
                    "marginTop": "12px",
                },
            ),
            dcc.Store(
                id=store_id,
                data={
                    "columns": dash_columns,
                    "records": data_records,
                    "n_index_levels": n_index_levels,
                    "title": title,
                    "index_click_map": index_click_map,
                },
            ),
            dcc.Download(id=download_id),
            html.Div(
                dash_table.DataTable(
                    id=table_id,
                    columns=dash_columns,
                    data=data_records,
                    merge_duplicate_headers=True,
                    page_size=5,

                    style_header={
                        "backgroundColor": THEME["table_header"],
                        "color": THEME["table_header_text"],
                        "fontWeight": "bold",
                        "fontFamily": "Arial, sans-serif",
                        "textAlign": "center",
                        "fontSize": "12px",
                        "height": "15px",
                        "lineHeight": "15px",
                        "whiteSpace": "normal",
                        "borderBottom": "2px solid #ffffff",
                    },

                    style_cell={
                        "padding": "10px 14px",
                        "textAlign": "center",
                        "fontSize": "13px",
                        "fontFamily": "Arial, sans-serif",
                        "color": "#2c3e50",
                        "whiteSpace": "normal",
                        "border": "1px solid #e8ecef",
                        "backgroundColor": "#ffffff",
                    },

                    style_data_conditional=[
                        {
                            "if": {"row_index": "odd"},
                            "backgroundColor": THEME["table_row_alt"],
                        },
                        {
                            "if": {"state": "active"},
                            "backgroundColor": THEME["table_active_bg"],
                            "border": f"1px solid {THEME['table_active_border']}",
                            "color": "#2c3e50",
                        },
                        {
                            "if": {"column_id": dash_columns[0]["id"]},
                            "fontWeight": "bold",
                            "backgroundColor": THEME["table_index_bg"],
                            "color": "#2c3e50",
                        },
                    ] + [
                        {
                            "if": {"column_id": col_id},
                            "cursor": "pointer",
                            "textDecoration": "bold",
                        }
                        for col_id in index_click_map.values()
                    ],

                    style_table={
                        "overflowX": "auto",
                        "marginTop": "8px",
                        "borderRadius": "8px",
                        "border": f"1px solid {THEME['table_active_border']}",
                        "boxShadow": "0 1px 3px rgba(0,100,1,0.10)",
                    },
                )
            ),
        ],
        style={
            "width": "100%",
            "fontFamily": "Arial, sans-serif",
            "backgroundColor": "#ffffff",
            "padding": "8px",
            "borderRadius": "8px",
        },
    )

    return table, ct_flat


@callback(
    Output({"type": "crosstab-table", "index": MATCH}, "data"),
    Output({"type": "crosstab-table", "index": MATCH}, "columns"),
    Input({"type": "crosstab-index-filter", "index": MATCH}, "value"),
    Input({"type": "crosstab-columns-filter", "index": MATCH}, "value"),
    State({"type": "crosstab-data-store", "index": MATCH}, "data"),
    prevent_initial_call=True,
)
def _filter_crosstab_table(index_value, columns_value, store_data):
    """Re-filter a crosstab's displayed rows/columns from its index/columns dropdowns."""
    if not store_data:
        return dash.no_update, dash.no_update

    columns = store_data["columns"]
    records = store_data["records"]
    n_index_levels = store_data["n_index_levels"]
    index_columns = columns[:n_index_levels]
    group_columns = columns[n_index_levels:]

    filtered_columns = list(index_columns)
    filtered_columns += (
        [c for c in group_columns if c["name"][0] == columns_value]
        if columns_value else group_columns
    )

    filtered_records = records
    if index_value and index_columns:
        idx_id = index_columns[0]["id"]
        filtered_records = [r for r in records if str(r.get(idx_id)) == index_value]

    return filtered_records, filtered_columns


@callback(
    Output({"type": "crosstab-download", "index": MATCH}, "data"),
    Input({"type": "crosstab-download-btn", "index": MATCH}, "n_clicks"),
    State({"type": "crosstab-table", "index": MATCH}, "data"),
    State({"type": "crosstab-table", "index": MATCH}, "columns"),
    State({"type": "crosstab-data-store", "index": MATCH}, "data"),
    prevent_initial_call=True,
)
def _download_crosstab_table(n_clicks, data, columns, store_data):
    """Export the currently displayed (possibly filtered) crosstab to Excel,
    rebuilding merged multi-level headers from each column's name levels.

    pandas' to_excel() can't write MultiIndex columns with index=False, so the
    header is written directly via openpyxl instead, merging each header row's
    horizontally-adjacent equal labels the same way the on-screen table does.
    """
    if not data or not columns:
        return dash.no_update

    import openpyxl

    col_ids = [c["id"] for c in columns]
    col_tuples = [tuple(c["name"]) for c in columns]
    max_len = max(len(t) for t in col_tuples)
    col_tuples = [t + ("",) * (max_len - len(t)) for t in col_tuples]

    title = (store_data or {}).get("title") or "crosstab"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = re.sub(r'[\\/*?:\[\]]', '_', str(title))[:31] or "crosstab"

    for level in range(max_len):
        row = level + 1
        col = 1
        while col <= len(col_tuples):
            label = col_tuples[col - 1][level]
            span = 1
            while (
                col + span - 1 < len(col_tuples)
                and all(col_tuples[col + span - 1][l] == col_tuples[col - 1][l] for l in range(level + 1))
            ):
                span += 1
            ws.cell(row=row, column=col, value=label)
            if span > 1:
                ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + span - 1)
            col += span

    data_start_row = max_len + 1
    for r, row_dict in enumerate(data, start=data_start_row):
        for c, col_id in enumerate(col_ids, start=1):
            ws.cell(row=r, column=c, value=row_dict.get(col_id))

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    safe_title = re.sub(r'[^A-Za-z0-9_-]+', '_', str(title)).strip('_') or "crosstab"
    return dcc.send_bytes(buffer.getvalue(), filename=f"{safe_title}.xlsx")


def create_age_gender_histogram(
    query_fiter,data_path, age_col, gender_col, title, xtitle, ytitle, bin_size,
    filter_col1=None, filter_value1=None,
    filter_col2=None, filter_value2=None,
    filter_col3=None, filter_value3=None,
    aggregation='count', custom_fields=None,
    height=400, responsive=True
):
    """
    Create a modern age-gender histogram with labeled bins and data labels.
    A lightweight SQL MIN/MAX query builds the bin boundaries; the main fetch
    selects only age_col and gender_col with NULL filtering pushed into SQL.

    Parameters:
    - height: Chart height in pixels (default: 400)
    - responsive: Make chart responsive to container width (default: True)
    """
    isSet = False
    filter_pairs = [
        (filter_col1, filter_value1),
        (filter_col2, filter_value2),
        (filter_col3, filter_value3),
    ]
    conditions = []
    for col, val in filter_pairs:
        if col is not None and val is not None:
            col = _normalize_filter_value(col)
            if isinstance(col, list):
                col = col[0]
            val = _normalize_filter_value(val)
            conditions.append(build_filter_query(col, val,data_path, PERSON_ID_, isSet, None, None))

    where_clause = query_fiter + ((" AND " + " AND ".join(conditions)) if conditions else "")
    null_guard   = f"{age_col} IS NOT NULL AND {gender_col} IS NOT NULL"

    range_query = (
        f"SELECT MIN(CAST({age_col} AS INTEGER)) AS min_age,"
        f"       MAX(CAST({age_col} AS INTEGER)) AS max_age"
        f" FROM ("
        f"   SELECT {age_col} FROM '{data_path}'"
        f"   WHERE {where_clause} AND {null_guard}"
        f"   QUALIFY ROW_NUMBER() OVER (PARTITION BY {PERSON_ID_} ORDER BY {age_col}) = 1"
        f" )"
    )
    range_df = DataStorage.query_duckdb(range_query)
    if range_df.empty or pd.isna(range_df['min_age'].iloc[0]):
        return go.Figure().update_layout(
            title=dict(
                text=f'<b>{title}</b>',
                x=0.5, xanchor='center',
                font=dict(size=18, color='#2c3e50', family='Arial, sans-serif')
            ),
            paper_bgcolor='#ffffff',
            height=height
        )

    min_age  = int(range_df['min_age'].iloc[0])
    max_age  = int(range_df['max_age'].iloc[0])

    bin_size = int(bin_size)
    bins     = list(range(min_age, max_age + bin_size, bin_size))
    labels   = [
        f"{bins[i]}-{bins[i+1]-1}" if i < len(bins) - 2 else f"{bins[i]}+"
        for i in range(len(bins) - 1)
    ]

    joined_query = (
        f"SELECT {age_col}, {gender_col}"
        f" FROM '{data_path}'"
        f" WHERE {where_clause} AND {null_guard}"
        f" QUALIFY ROW_NUMBER() OVER (PARTITION BY {PERSON_ID_} ORDER BY {age_col}) = 1"
    )
    data = DataStorage.query_duckdb(joined_query)
    data = apply_calculated_fields(data, custom_fields)

    if data.empty:
        return go.Figure().update_layout(
            title=dict(
                text=f'<b>{title}</b>',
                x=0.5, xanchor='center',
                font=dict(size=18, color='#2c3e50', family='Arial, sans-serif')
            ),
            paper_bgcolor='#ffffff',
            height=height
        )

    data["age_bin"] = pd.cut(
        data[age_col],
        bins=bins,
        labels=labels,
        include_lowest=True,
        right=False
    )

    fig = px.histogram(
        data,
        x="age_bin",
        color=gender_col,
        barmode="group",
        title=None,          # Title added in layout
        text_auto=True,
        color_discrete_sequence=THEME["gender"],
        category_orders={"age_bin": labels},
        template='plotly_white'
    )

    # Modern trace styling
    fig.update_traces(
        textposition="outside",
        cliponaxis=False,
        textfont=dict(size=11, color='#2c3e50', family='Arial, sans-serif'),
        marker_line_color='#ffffff',
        marker_line_width=1,
        opacity=0.85,
        hovertemplate="<b>Age group:</b> %{x}<br><b>Count:</b> %{y:,.0f}<extra></extra>"
    )

    # Shared modern layout
    fig.update_layout(
        title=dict(
            text=f'<b>{title}</b>',
            x=0.5,
            xanchor='center',
            font=dict(size=18, color='#2c3e50', family='Arial, sans-serif'),
            y=0.97
        ),
        xaxis_title=dict(
            text=xtitle,
            font=dict(size=13, color='#34495e', family='Arial, sans-serif'),
            standoff=10
        ),
        yaxis_title=dict(
            text=ytitle,
            font=dict(size=13, color='#34495e', family='Arial, sans-serif'),
            standoff=10
        ),
        template='plotly_white',
        plot_bgcolor='#ffffff',
        paper_bgcolor='#ffffff',
        margin=dict(l=50, r=30, t=80, b=50, pad=4),
        height=height,
        hovermode='x unified',
        font=dict(family='Arial, sans-serif', size=12, color='#2c3e50'),
        autosize=responsive,
        width=None if responsive else 800,
        bargap=0.15,
        bargroupgap=0.05,
        legend=dict(
            title=dict(text=gender_col, font=dict(size=12, color='#2c3e50')),
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor='#e2e8f0',
            borderwidth=1,
            font=dict(size=11, color='#4a5568')
        ),
        shapes=[
            dict(
                type='rect',
                xref='paper', yref='paper',
                x0=0, y0=0, x1=1, y1=1,
                line=dict(width=1, color='#e2e8f0'),
                fillcolor='rgba(0,0,0,0)'
            )
        ]
    )

    fig.update_xaxes(
        showgrid=True,
        gridwidth=0.5,
        gridcolor='#e8ecef',
        showline=True,
        linewidth=1,
        linecolor='#cbd5e0',
        tickfont=dict(size=11, color='#4a5568'),
        title_standoff=10
    )

    fig.update_yaxes(
        showgrid=True,
        gridwidth=0.5,
        gridcolor='#e8ecef',
        showline=True,
        linewidth=1,
        linecolor='#cbd5e0',
        zeroline=True,
        zerolinewidth=1,
        zerolinecolor='#e2e8f0',
        tickfont=dict(size=11, color='#4a5568'),
        tickformat=',.0f',
        title_standoff=10
    )

    return fig
 
def create_horizontal_bar_chart(
    query_fiter,data_path, label_col, value_col, title, x_title, y_title, top_n=10,
    filter_col1=None, filter_value1=None,
    filter_col2=None, filter_value2=None,
    filter_col3=None, filter_value3=None,
    aggregation='count', custom_fields=None,
    height=400, responsive=True, show_values=True, color=None
):
    """
    Create a modern horizontal bar chart showing the top N items by value.
    Grouping, zero filtering, ordering and top-N limiting are all pushed into
    SQL so Python only receives the final rows to plot.

    Parameters:
    - height: Chart height in pixels (default: 400)
    - responsive: Make chart responsive to container width (default: True)
    - show_values: Show data labels on bars (default: True)
    - color: Optional column to group bars by color (default: None)
    """
    isSet = False
    filter_pairs = [
        (filter_col1, filter_value1),
        (filter_col2, filter_value2),
        (filter_col3, filter_value3),
    ]
    conditions = []
    for col, val in filter_pairs:
        if col is not None and val is not None:
            col = _normalize_filter_value(col)
            if isinstance(col, list):
                col = col[0]
            val = _normalize_filter_value(val)
            conditions.append(build_filter_query(col, val,data_path, PERSON_ID_, isSet, None, None))

    where_clause = query_fiter + ((" AND " + " AND ".join(conditions)) if conditions else "")

    if aggregation in ('count', 'nunique'):
        agg_expr = f"COUNT(DISTINCT {value_col})"
    elif aggregation == 'sum':
        agg_expr = f"SUM({value_col})"
    elif aggregation == 'mean':
        agg_expr = f"AVG({value_col})"
    elif aggregation == 'median':
        agg_expr = f"MEDIAN({value_col})"
    elif aggregation == 'min':
        agg_expr = f"MIN({value_col})"
    elif aggregation == 'max':
        agg_expr = f"MAX({value_col})"
    else:
        agg_expr = f"{aggregation}({value_col})"

    if color:
        joined_query = (
            f"SELECT {label_col}, {agg_expr} AS data_value, {color}"
            f" FROM '{data_path}'"
            f" WHERE {where_clause}"
            f" GROUP BY {label_col}, {color}"
            f" HAVING data_value > 0"
            f" ORDER BY data_value DESC"
            f" LIMIT {int(top_n)}"
        )
    else:
        joined_query = (
            f"SELECT {label_col}, {agg_expr} AS data_value"
            f" FROM '{data_path}'"
            f" WHERE {where_clause}"
            f" GROUP BY {label_col}"
            f" HAVING data_value > 0"
            f" ORDER BY data_value DESC"
            f" LIMIT {int(top_n)}"
        )
    df_top = DataStorage.query_duckdb(joined_query)
    df_top = apply_calculated_fields(df_top, custom_fields)

    if df_top.empty:
        return go.Figure().update_layout(
            title=dict(
                text=f'<b>No data available for {title}</b>',
                x=0.5, xanchor='center',
                font=dict(size=18, color='#2c3e50', family='Arial, sans-serif')
            ),
            paper_bgcolor='#ffffff',
            height=height
        )

    # Format labels for display
    df_top['label'] = df_top['data_value'].apply(
        lambda x: f'{int(x):,}' if x == int(x) else f'{x:,.1f}'
    ) if show_values else ''

    # Reverse rows so largest bar sits at the top
    df_top = df_top.iloc[::-1].reset_index(drop=True)
    fig = px.bar(
        df_top,
        x='data_value',
        y=label_col,
        text='label' if show_values else None,
        color= color if color else None,
        color_discrete_sequence=THEME["primary"],
        orientation='h',
        template='plotly_white',
        title=None
    )

    if not color:
        fig.update_traces(
            marker_color=THEME["chart_fill"],
            marker_line_color="#004a01",
            marker_line_width=1,
            opacity=0.85,
        )

    # Modern trace styling
    fig.update_traces(
        textposition='outside',
        cliponaxis=False,
        textfont=dict(size=11, color='#2c3e50', family='Arial, sans-serif'),
        hovertemplate=(
            "<b>%{y}</b><br>"
            f"<b>{x_title}:</b> %{{x:,.0f}}<br>"
            "<extra></extra>"
        ),
    )

    # Auto-scale height to number of bars for readability
    computed_height = max(height, len(df_top) * 40 + 120)

    # Shared modern layout
    fig.update_layout(
        title=dict(
            text=f'<b>{title}</b>',
            x=0.5,
            xanchor='center',
            font=dict(size=18, color='#2c3e50', family='Arial, sans-serif'),
            y=0.97
        ),
        xaxis_title=dict(
            text=x_title,
            font=dict(size=13, color='#34495e', family='Arial, sans-serif'),
            standoff=10
        ),
        yaxis_title=dict(
            text=y_title,
            font=dict(size=13, color='#34495e', family='Arial, sans-serif'),
            standoff=10
        ),
        template='plotly_white',
        plot_bgcolor='#ffffff',
        paper_bgcolor='#ffffff',
        margin=dict(l=20, r=80, t=80, b=50, pad=4),  # extra right margin for outside labels
        height=computed_height,
        hovermode='y unified',
        font=dict(family='Arial, sans-serif', size=12, color='#2c3e50'),
        autosize=responsive,
        width=None if responsive else 800,
        bargap=0.2,
        shapes=[
            dict(
                type='rect',
                xref='paper', yref='paper',
                x0=0, y0=0, x1=1, y1=1,
                line=dict(width=1, color='#e2e8f0'),
                fillcolor='rgba(0,0,0,0)'
            )
        ]
    )

    fig.update_xaxes(
        showgrid=True,
        gridwidth=0.5,
        gridcolor='#e8ecef',
        showline=True,
        linewidth=1,
        linecolor='#cbd5e0',
        zeroline=True,
        zerolinewidth=1,
        zerolinecolor='#e2e8f0',
        tickfont=dict(size=11, color='#4a5568'),
        tickformat=',.0f',
        title_standoff=10
    )

    fig.update_yaxes(
        showgrid=False,         # No horizontal grid on a horizontal bar chart
        showline=True,
        linewidth=1,
        linecolor='#cbd5e0',
        tickfont=dict(size=11, color='#4a5568'),
        title_standoff=10,
        autorange=True          # Reversed order already handled by iloc[::-1]
    )

    return fig

def agg_join(series: pd.Series) -> str:
    """Aggregates unique values in a series into a comma-separated string."""
    return ', '.join(series.astype(str).unique())

AGG_MAP: Dict[str, Union[str, Callable]] = {
    'first': 'first',
    'last': 'last',
    'min': 'MIN',
    'max': 'MAX',
    'sum': 'SUM',
    'mean': 'AVG',
    'count': 'COUNT',
    'join': 'STRING_AGG'
}

def create_line_list(
        title: str,
        data_path,
        query_fiter: str,
        unique_col: Union[str, List[str]] = PERSON_ID_,
        rename: Optional[dict] = None,
        cols_order: Optional[List[str]] = None,
        merge_methods: Optional[List[str]] = None,
        message=None,
        custom_fields=None,
        mask_names: bool = False,
        anonymize: bool =False,
        **kwargs):

    # ── helper: strip date filter for cohort (all-time history) queries ──────
    import re as _re
    def _cohort_where(base_where: str) -> str:
        """
        Remove the 'Date BETWEEN ... AND ...' clause from the WHERE string,
        leaving only scope conditions (facility, district, etc.).
        Used by join_cohort so the query covers the full patient history.
        """
        stripped = _re.sub(
            rf"{_re.escape(DATE_)}\s+BETWEEN\s+'[^']+'::[A-Za-z]+\s+AND\s+'[^']+'::[A-Za-z]+"
            rf"(\s+AND\s+)?",
            "",
            base_where,
            flags=_re.IGNORECASE,
        ).strip().lstrip("AND").strip()
        return stripped if stripped else "1=1"

    queries = []
    for i in range(1, 31):
        group_cols = list(kwargs.get(f"group_cols{i}", [])) or []
        group_filters = kwargs.get(f"group{i}_filters", {}) or {}
        group_aggr = kwargs.get(f"group{i}_aggr", {}) or {}
        group_rename_map = kwargs.get(f"group{i}_rename", {}) or {}

        anonymized = []
        group_cols = [item for item in group_cols if item not in anonymized]

        if not group_cols:
            continue

        # Apply rename aliases to group_cols for SELECT clause
        renamed_cols = [
            f"{col} AS {group_rename_map[col]}" if col in group_rename_map else col
            for col in group_cols
        ]
        if DATE_ in renamed_cols:
            renamed_cols = [
                f"CAST({col} AS DATE) AS {DATE_}" if col == DATE_ else col
                for col in renamed_cols
            ]

        where_clause = query_fiter
        if group_filters:
            for col, val in group_filters.items():
                clause = build_filter_query(col, val,data_path, unique_col, False, None, None)
                where_clause += f" AND {clause}"

        if group_aggr:
            # Only cols NOT being aggregated appear as plain SELECT columns and in GROUP BY
            aggr_col_set    = set(group_aggr.keys())
            non_aggr_cols   = [c for c in group_cols if c not in aggr_col_set]
            non_aggr_select = [
                f"STRFTIME(CAST({c} AS DATE), '%Y-%m-%d') AS {c}"
                if c == DATE_ else c
                for c in non_aggr_cols
            ]

            # join_cohort: any column using this func makes the whole group
            # query ignore the date filter so we capture full patient history.
            is_cohort = any(
                (f or "").lower() == "join_cohort"
                for f in group_aggr.values()
            )
            effective_where = _cohort_where(where_clause) if is_cohort else where_clause

            aggr_clauses = []
            for col, func in group_aggr.items():
                alias    = group_rename_map.get(col, col)
                agg_func = (func or "first").lower()
                if agg_func in ("join", "concat", "list", "string_agg", "join_cohort"):
                    # join_cohort is identical to join in the SELECT expression;
                    # the date-filter removal is already handled via effective_where.
                    aggr_clauses.append(
                        f"STRING_AGG(DISTINCT CAST({col} AS VARCHAR), ', '"
                        f" ORDER BY CAST({col} AS VARCHAR)) AS {alias}"
                    )
                elif agg_func == "nunique":
                    aggr_clauses.append(f"COUNT(DISTINCT {col}) AS {alias}")
                elif agg_func in ("first", "any"):
                    aggr_clauses.append(f"ANY_VALUE({col}) AS {alias}")
                elif agg_func == "last":
                    aggr_clauses.append(f"MAX({col}) AS {alias}")
                else:
                    aggr_clauses.append(f"{agg_func.upper()}({col}) AS {alias}")

            # SELECT: unique_col + non-aggregated cols + aggregate expressions
            # GROUP BY: unique_col + non-aggregated cols only (never the aggregated cols)
            select_cols = [unique_col] + non_aggr_select + aggr_clauses
            group_by    = ", ".join([unique_col] + non_aggr_cols)
            query = (
                f"SELECT {', '.join(select_cols)}"
                f" FROM '{data_path}'"
                f" WHERE {effective_where}"
                f" GROUP BY {group_by}"
            )
            
        else:
            query = (
                f"SELECT DISTINCT {unique_col}, {', '.join(renamed_cols)}"
                f" FROM '{data_path}'"
                f" WHERE {where_clause}"
            )
        queries.append(query)

    # Join all subquery results on unique_col using configured merge_methods
    merge_methods_list = list(merge_methods or [])

    if not queries:
        final_df = pd.DataFrame()
    elif len(queries) == 1:
        final_df = DataStorage.query_duckdb(queries[0])
    else:
        # Build a single SQL expression: each subquery joined to the first
        join_type_map = {"inner": "JOIN", "left": "LEFT JOIN",
                         "right": "RIGHT JOIN", "outer": "FULL OUTER JOIN"}
        base  = f"({queries[0]}) t1"
        joins = []
        for idx, q in enumerate(queries[1:], start=2):
            raw_how  = (merge_methods_list[idx - 2]
                        if (idx - 2) < len(merge_methods_list) else "inner")
            sql_join = join_type_map.get(raw_how.lower(), "JOIN")
            joins.append(
                f"{sql_join} ({q}) t{idx}"
                f" ON t1.{unique_col} = t{idx}.{unique_col}"
            )
        final_query = f"SELECT * FROM {base} {' '.join(joins)}"
        # print(final_query)
        final_df    = DataStorage.query_duckdb(final_query)

    # Apply top-level rename (e.g. given_name → First Name)
    if rename and not final_df.empty:
        final_df = final_df.rename(columns={
            k: v for k, v in rename.items() if k in final_df.columns
        })

    # Apply column ordering — use only cols that actually exist after rename
    if cols_order and not final_df.empty:
        cols_order = cols_order.split("|").strip() if isinstance(cols_order, str) else cols_order
        ordered  = [c for c in cols_order if c in final_df.columns]
        final_df = final_df[ordered]

    if not final_df.empty:
        final_df = final_df.sort_values(by=final_df.columns[0])

    # Mask personal name columns for unauthorised users
    if mask_names and not final_df.empty:
        for name_col in (FIRST_NAME_, LAST_NAME_,"First Name", "Last Name"):
            if name_col in final_df.columns:
                final_df[name_col] = "******"

    final_df = final_df.fillna("") if not final_df.empty else final_df
    table = html.Div([
        html.H3(title, style={"textAlign": "center", "color": THEME["table_header_text"],
                               "fontFamily": "Arial, sans-serif"}),
        (html.P(message, style={"textAlign": "center", "color": "red"})
         if message else None),
        dash_table.DataTable(
            id="linelist-table",
            columns=[{"name": col, "id": col} for col in final_df.columns],
            data=final_df.to_dict("records"),
            sort_action="native",
            filter_action="native",
            page_size=10,
            page_action="native",
            style_header={
                "backgroundColor": THEME["table_header"],
                "color":           THEME["table_header_text"],
                "fontWeight":      "bold",
                "textAlign":       "left",
                "fontSize":        "13px",
                "borderBottom":    "2px solid #004a01",
            },
            style_cell={
                "padding":    "8px 10px",
                "textAlign":  "left",
                "fontSize":   "12px",
                "whiteSpace": "normal",
                "height":     "auto",
                "border":     "1px solid #dee2e6",
            },
            style_data_conditional=[
                {"if": {"row_index": "odd"},
                 "backgroundColor": THEME["table_row_alt"]},
                {"if": {"state": "active"},
                 "backgroundColor": THEME["table_active_bg"],
                 "border": "1px solid " + THEME["table_active_border"]},
            ],
            style_table={
                "overflowX":    "auto",
                "borderRadius": "8px",
                "border":       "1px solid " + THEME["table_active_border"],
                "boxShadow":    "0 1px 4px rgba(0,100,1,0.10)",
            },
        ),
    ])

    return table, final_df

def create_line_list_basic_modal(
    unique_column: str,
    data_path: str,
    ids_list: List,
    start_date: List,
    end_date: List
) -> "pd.DataFrame":
    """Return a DataFrame of patient details for the given ID list."""
    if not ids_list:
        return pd.DataFrame()

    # Handle date logic
    if start_date and end_date:
        start_date = f"{start_date[0]} 00:00:00"
        end_date = f"{end_date[0]} 23:59:59"
    else:
        # If lists are empty, use today's date
        today = datetime.now().strftime('%Y-%m-%d')
        start_date = f"{today} 00:00:00"
        end_date = f"{today} 23:59:59"

    ids_quoted = ", ".join(f"'{str(i)}'" for i in ids_list)

    query = f"""
        SELECT DISTINCT
            {unique_column}                     AS "unique_column",
            {PROGRAM_}                          AS "Program",
            {IDENTIFIER_}                       AS "Patient ID",
            {FIRST_NAME_}                       AS "First Name",
            {LAST_NAME_}                        AS "Last Name",
            CAST({AGE_} AS INT)                 AS "Age",
            {GENDER_}                           AS "Gender",
            {HOME_DISTRICT_}                    AS "Home District",
            {TA_}                              AS "Traditional Authority",
            {VILLAGE_}                          AS "Village"
        FROM '{data_path}'
        WHERE {unique_column} IN ({ids_quoted}) AND {DATE_} BETWEEN '{start_date}'::TIMESTAMP and '{end_date}'::TIMESTAMP
        ORDER BY {DATE_}, {LAST_NAME_}, {FIRST_NAME_}
    """

    try:
        result = DataStorage.query_duckdb(query)
        return result.drop_duplicates(subset=['unique_column', PROGRAM_]).drop(columns='unique_column').iloc[:100]
    except Exception:
        return pd.DataFrame()


def create_sankey_diagram(df, source_col, target_col, value_col, title,
                          unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
                          filter_col2=None, filter_value2=None):
    """
    Create a Sankey diagram for flow visualization.
    Useful for: Patient flow between departments, diagnosis to treatment pathways, etc.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Create flow matrix
    flow_data = data.groupby([source_col, target_col])[value_col].nunique().reset_index()
    
    # Get unique labels
    labels = list(set(flow_data[source_col].unique()) | set(flow_data[target_col].unique()))
    label_to_id = {label: i for i, label in enumerate(labels)}
    
    # Create Sankey data
    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=labels,
            color="blue"
        ),
        link=dict(
            source=[label_to_id[src] for src in flow_data[source_col]],
            target=[label_to_id[tgt] for tgt in flow_data[target_col]],
            data_value=flow_data[value_col]
        )
    )])
    
    fig.update_layout(
        title=title,
        font_size=12,
        template="plotly_white"
    )
    
    return fig