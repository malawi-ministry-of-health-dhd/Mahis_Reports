import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import dash
import operator
from dash import dash_table, html
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Union, Callable
import json
import ast
from io import BytesIO
import base64
import duckdb
from data_storage import DataStorage

pd.options.mode.chained_assignment = None

from config import PERSON_ID_, ENCOUNTER_ID_, DATE_, CONCEPT_NAME_,DATA_FILE_NAME_


THEME = {
    # Multi-series: dark green → mid greens → warm amber → teal → slate
    "primary":  ["#006401", "#2e8b2e", "#57b957", "#f59e0b", "#0d9488"],
    # Single-series or color group: progressive green shades
    "greens":   ["#006401", "#1a7a1a", "#2e8f2e", "#43a443", "#57b957", "#80cc80"],
    # Gender/binary split (green + amber)
    "gender":   ["#006401", "#f59e0b", "#0d9488", "#7c3aed", "#dc2626"],
    # Single bar / line (no color grouping)
    "single":   "#006401",
    # Table accent colours
    "table_header":       "#525E52",
    "table_header_text":  "#ffffff",
    "table_row_alt":      "#f2f9f2",
    "table_index_bg":     "#e8f5e8",
    "table_active_bg":    "#d4edda",
    "table_active_border":"#006401",
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
            # Try eval first (numeric expressions)
            df[col] = df.eval(expr, engine="python")
        except Exception:
            # Fallback for string / datetime logic
            df[col] = eval(expr, {"df": df, "pd": pd})

    return df


def _normalize_filter_value(val):
    """Normalize filter_value into a proper list or string."""
    if val is None:
        return None

    # Convert pipe-delimited ("A | B")
    if isinstance(val, str) and "|" in val:
        return [v.strip() for v in val.split("|")]

    # Convert stringified lists ("['A','B']")
    if isinstance(val, str) and val.strip().startswith("[") and val.strip().endswith("]"):
        try:
            parsed = ast.literal_eval(val)
            if isinstance(parsed, list):
                return parsed
        except:
            pass  # fall back to string

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

def build_filter_query(cols, vals, unique_column, isSet, start_date, end_date, query_filter:str=None):
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
        # Handle wildcard/LIKE patterns
        if val_str.startswith(("*", "%")):
            return "LIKE", f"%{val_str[1:]}%"
        # Handle operators (>=, <=, !=, =, >, <)
        if match := re.match(r'^(>=|<=|!=|=|>|<)?\s*(.*)$', val_str):
            operator, value_str = match.groups()
            operator = operator or "="
            value_str = value_str.strip()
            
            # Parse data_value
            data_value = "" if value_str == "_" else (
                float(value_str) if "." in value_str else int(value_str)
            ) if value_str.replace(".", "", 1).isdigit() else value_str
            
            return operator, data_value
        return "=", val_str
    
    def build_single_condition(col, val):
        """Build a single WHERE condition."""
        # Handle list values for IN clause
        if isinstance(val, list):
            placeholders = ", ".join([f"'{v}'" for v in val])
            return f"{col} IN ({placeholders})"
        if col == "defaulter_period":
            return f"concept_name = 'Appointment date' AND (NOW() - CAST(value_datetime AS TIMESTAMP)) > INTERVAL {val} DAY"
        if col == "days_before_visit_date":
            return f"{DATE_} >= ('{start_date}'::DATE - INTERVAL {int(val)} DAY) AND {DATE_} <= ('{start_date}'::DATE - INTERVAL 1 DAY)"
        operator, data_value = parse_value(val)
        if operator == "LIKE":
            return f"{col} LIKE '{data_value}'"
        return f"{col} {operator} '{data_value}'"
    
    # Handle paired lists
    if isinstance(cols, list):
        conditions = [
            build_single_condition(col, val) 
            for col, val in zip(cols, vals)
        ]
        where_clause = " AND ".join(conditions)
        return f"SELECT DISTINCT {unique_column} FROM '{DATA_FILE_NAME_}' WHERE {query_filter} AND {where_clause}"
    where_clause = build_single_condition(cols, vals)
    if isinstance(unique_column, list):
        unique_column_str = ", ".join(unique_column)
    else:        unique_column_str = unique_column
    if isSet:
        return f"SELECT DISTINCT {unique_column_str} FROM '{DATA_FILE_NAME_}' WHERE {query_filter} AND {where_clause}"
    return f"{where_clause}"

def create_count(query_fiter, aggregation='count', unique_column=PERSON_ID_, *filters, start_date=None, end_date=None):

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
        col,val = _normalize_filter_value(col), _normalize_filter_value(val)
        query = build_filter_query(col, val, unique_column, isSet, start_date, end_date)
        queries.append(query)

    joined_query =f"SELECT DISTINCT {unique_column} FROM '{DATA_FILE_NAME_}' WHERE {query_fiter} AND "  + " AND ".join(queries)
    if not queries:
        joined_query = f"SELECT DISTINCT {unique_column} FROM '{DATA_FILE_NAME_}' WHERE {query_fiter}"
    if aggregation == "time_diff_mins":
        joined_query = (joined_query.replace(unique_column, 
                                            f"({unique_column}), DATEDIFF('minute', MIN({DATE_}), MAX({DATE_})) AS patient_session_minutes")
                                            + f" GROUP BY {unique_column}")
    result = DataStorage.query_duckdb(joined_query)
    if aggregation == 'count':
        return len(result[unique_column].dropna().unique())
    elif aggregation == 'nunique':
        return len(result[unique_column].dropna().unique())
    elif aggregation == 'list':
        return result[unique_column].dropna().unique().tolist()
    elif aggregation == 'time_diff_mins':
        if result.empty:
            return 0
        result = result[result["patient_session_minutes"]<=120] #120 minutes is the threshold for a single patient session, we want to exclude outliers that may be caused by data quality issues
        return int(result["patient_session_minutes"].agg('mean'))
    elif aggregation in ['sum', 'mean', 'min', 'max', 'std', 'var']:
        return int(result[unique_column].agg(aggregation))
    else:
        return len(result[unique_column].dropna().unique())

def create_count_sets(
    query_fiter,aggregation='count',
    unique_column=PERSON_ID_,
    *filters,
    start_date=None,
    end_date=None
):
    isSet = True

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
        query = build_filter_query(cols_list, vals_list, unique_column, isSet, start_date, end_date, query_fiter)
        queries.append(query)

    for cols, vals in non_set_filters:
        query = build_filter_query(cols, vals, unique_column, isSet, start_date, end_date, query_fiter)
        queries.append(query)

    intersection_query = " INTERSECT ".join(queries)
    print(intersection_query)
    result = DataStorage.query_duckdb(intersection_query)
    return result[unique_column].nunique()

def create_sum(query_fiter, unique_column=PERSON_ID_, num_field='ValueN', *filters, start_date=None, end_date=None):

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
        query = build_filter_query(col, val, [unique_column,num_field], isSet, start_date, end_date)
        queries.append(query)
    joined_query =f"SELECT {unique_column}, {num_field} FROM '{DATA_FILE_NAME_}' WHERE {query_fiter} AND "  + " AND ".join(queries)
    if not queries:
        joined_query =f"SELECT {unique_column}, {num_field} FROM '{DATA_FILE_NAME_}' WHERE {query_fiter}"  
    result = DataStorage.query_duckdb(joined_query)
    return result[num_field].sum()


def create_column_chart(query_fiter, x_col, y_col, title, x_title, y_title,
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
            conditions.append(build_filter_query(col, val, unique_column, isSet, None, None))
 
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
            f" FROM '{DATA_FILE_NAME_}'"
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
            barmode='group'
        )
    else:
        # SELECT x_col, AGG(y_col) … GROUP BY x_col
        order_clause = "ORDER BY data_value DESC" if sort_by_value else ""
        joined_query = (
            f"SELECT {x_col}, {agg_expr} AS data_value"
            f" FROM '{DATA_FILE_NAME_}'"
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
            text='label' if show_values else None
        )
        
        # Apply theme single-color
        fig.update_traces(
            marker_color=THEME["single"],
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

def create_time_line_chart(query_fiter, date_col, y_col, title, x_title, 
                      y_title, unique_column=PERSON_ID_, 
                      legend_title=None, color=None, filter_col1=None, 
                      filter_value1=None, filter_col2=None, 
                      filter_value2=None, filter_col3=None, 
                      filter_value3=None, aggregation='count', 
                      custom_fields=None, height=400, responsive=True,
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
            conditions.append(build_filter_query(col, val, unique_column, isSet, None, None))
 
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
        agg_expr = f"{aggregation}({y_col})"
    
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
            f" FROM '{DATA_FILE_NAME_}'"
            f" WHERE {where_clause}"
            f" GROUP BY {date_expr}, {color}"
            f" ORDER BY date_trunc"
        )
    else:
        joined_query = (
            f"SELECT {date_expr} AS date_trunc, {agg_expr} AS metric_value"
            f" FROM '{DATA_FILE_NAME_}'"
            f" WHERE {where_clause}"
            f" GROUP BY {date_expr}"
            f" ORDER BY date_trunc"
        )

    summary = DataStorage.query_duckdb(joined_query)
    summary = apply_calculated_fields(summary, custom_fields)
    summary = summary.rename(columns={'metric_value': 'count'})

    # Create figure
    if color:
        fig = px.line(
            summary,
            x='date_trunc',
            y='count',
            color=color,
            color_discrete_sequence=THEME["primary"],
            title=None  # Title added in layout
        )
    else:
        fig = px.line(
            summary,
            x='date_trunc',
            y='count',
            color_discrete_sequence=[THEME["single"]],
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
            text=legend_title if legend_title else (color if color else ""),
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
    query_fiter,
    title,
    chart_mode='pie',           # 'pie' | 'line'
    date_col=DATE_,
    unique_column=PERSON_ID_,
    filter_col1=None, filter_value1=None,
    filter_col2=None, filter_value2=None,
    filter_col3=None, filter_value3=None,
    custom_fields=None,
    height=400,
    hole_size=0.45,
):
    """
    Classify patients in the filtered window as 'New' or 'Returning'.

    'New'       = the person_id has no record anywhere in the dataset before
                  the earliest date found in the current filtered window.
    'Returning' = the person_id has at least one earlier record.

    Uses a CTE so only two DuckDB passes are needed:
      1. Find prior patients (Date < range start, no scope filter needed).
      2. LEFT JOIN against the filtered window, count distinct person_ids.
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
            conditions.append(build_filter_query(col, val, unique_column, isSet, None, None))

    where_clause = query_fiter + ((" AND " + " AND ".join(conditions)) if conditions else "")

    # ── CTE: find patients with any record before the current range start ─────
    prior_cte = f"""
        WITH range_start AS (
            SELECT MIN({date_col}) AS min_date
            FROM '{DATA_FILE_NAME_}'
            WHERE {where_clause}
        ),
        prior_patients AS (
            SELECT DISTINCT {unique_column}
            FROM '{DATA_FILE_NAME_}', range_start
            WHERE {date_col} < range_start.min_date
        )
    """

    if chart_mode == 'line':
        sql = prior_cte + f"""
        SELECT
            CAST(f.{date_col} AS DATE)                                       AS date_trunc,
            CASE WHEN p.{unique_column} IS NOT NULL THEN 'Returning'
                 ELSE 'New' END                                               AS patient_type,
            COUNT(DISTINCT f.{unique_column})                                 AS metric_value
        FROM '{DATA_FILE_NAME_}' f
        LEFT JOIN prior_patients p ON f.{unique_column} = p.{unique_column}
        WHERE {where_clause}
        GROUP BY date_trunc, patient_type
        ORDER BY date_trunc
        """
        df = DataStorage.query_duckdb(sql)
        df = apply_calculated_fields(df, custom_fields)
        if df.empty:
            return go.Figure().update_layout(title=dict(text=f'<b>{title}</b>', x=0.5),
                                             height=height, paper_bgcolor='#ffffff')

        fig = px.line(
            df, x='date_trunc', y='metric_value', color='patient_type',
            color_discrete_map={'New': THEME['primary'][0], 'Returning': THEME['primary'][3]},
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
        sql = prior_cte + f"""
        SELECT
            CASE WHEN p.{unique_column} IS NOT NULL THEN 'Returning'
                 ELSE 'New' END                       AS patient_type,
            COUNT(DISTINCT f.{unique_column})          AS metric_value
        FROM '{DATA_FILE_NAME_}' f
        LEFT JOIN prior_patients p ON f.{unique_column} = p.{unique_column}
        WHERE {where_clause}
        GROUP BY patient_type
        """
        df = DataStorage.query_duckdb(sql)
        df = apply_calculated_fields(df, custom_fields)
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


def create_pie_chart(query_fiter, names_col, values_col, title,
                     unique_column=PERSON_ID_, filter_col1=None,
                     filter_value1=None, filter_col2=None,
                     filter_value2=None, filter_col3=None,
                     filter_value3=None, colormap=None, aggregation='count',
                     custom_fields=None, height=400, responsive=True,
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
            conditions.append(build_filter_query(col, val, unique_column, isSet, None, None))

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
        f" FROM '{DATA_FILE_NAME_}'"
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

    # Collapse tail slices into "Other"
    if max_slices and len(df_summary) > max_slices:
        top = df_summary.head(max_slices - 1)
        other_val = df_summary.iloc[max_slices - 1:]['data_value'].sum()
        other_row = pd.DataFrame({names_col: ['Other'], 'data_value': [other_val]})
        df_summary = pd.concat([top, other_row], ignore_index=True)

    color_sequence = (
        list(colormap.values()) if colormap
        else THEME["gender"]
    )

    fig = px.pie(
        df_summary,
        names=names_col,
        values='data_value',
        hole=hole_size,
        color_discrete_sequence=color_sequence,
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
 
def create_pivot_table(query_fiter, index_col, columns_col, values_col, title, unique_column='PERSON_ID_', aggfunc='sum',
                     filter_col1=None, filter_value1=None,
                     filter_col2=None, filter_value2=None,
                     filter_col3=None, filter_value3=None,
                     aggregation='count',
                     rename={}, replace={}, custom_fields=None,
                     page_size=5, current_page=0):
    """
    Create a pivot table with native pagination and sortable column headers.
    Returns a Dash html.Div containing a dash_table.DataTable.
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
            conditions.append(build_filter_query(col, val, unique_column, isSet, None, None))

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
        f" FROM '{DATA_FILE_NAME_}'"
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

    pivot = pivot.rename(columns=rename).replace(replace)
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
                    "color": THEME["table_header"],
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

    return table
 
def create_crosstab_table(
    query_fiter,
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
    rename={}, replace={}, custom_fields=None
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
            conditions.append(build_filter_query(col, val, unique_column, isSet, None, None))

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
            f" FROM '{DATA_FILE_NAME_}'"
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
        joined_query = (
            f"SELECT {select_cols}"
            f" FROM '{DATA_FILE_NAME_}'"
            f" WHERE {where_clause}"
        )
        data = DataStorage.query_duckdb(joined_query)
        data = apply_calculated_fields(data, custom_fields)
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
            normalize=norm if ct_aggfunc != 'first' else False
        )

    ct = ct.reset_index()
    ct = ct.rename(columns=rename).replace(replace)

    dash_columns = []
    for col in ct.columns:
        if isinstance(col, tuple):
            dash_columns.append({
                "name": [str(c) for c in col],
                "id": "|".join([str(c) for c in col])
            })
        else:
            dash_columns.append({
                "name": [str(col)],
                "id": str(col)
            })

    ct_flat = ct.copy()
    ct_flat.columns = [
        "|".join(str(c) for c in col) if isinstance(col, tuple) else str(col)
        for col in ct.columns
    ]

    data_records = ct_flat.to_dict("records")

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
                    "color": THEME["table_header"],
                },
            ),
            html.Div(
                dash_table.DataTable(
                    id="crosstab-table",
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
                        "fontSize": "13px",
                        "height": "42px",
                        "lineHeight": "42px",
                        "whiteSpace": "normal",
                        "borderBottom": "2px solid #004a01",
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

    return table
 
def create_age_gender_histogram(
    query_fiter, age_col, gender_col, title, xtitle, ytitle, bin_size,
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
            conditions.append(build_filter_query(col, val, PERSON_ID_, isSet, None, None))

    where_clause = query_fiter + ((" AND " + " AND ".join(conditions)) if conditions else "")
    null_guard   = f"{age_col} IS NOT NULL AND {gender_col} IS NOT NULL"

    range_query = (
        f"SELECT MIN(CAST({age_col} AS INTEGER)) AS min_age,"
        f"       MAX(CAST({age_col} AS INTEGER)) AS max_age"
        f" FROM ("
        f"   SELECT {age_col} FROM '{DATA_FILE_NAME_}'"
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
        f" FROM '{DATA_FILE_NAME_}'"
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
        category_orders={"age_bin": labels}
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
    query_fiter, label_col, value_col, title, x_title, y_title, top_n=10,
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
            conditions.append(build_filter_query(col, val, PERSON_ID_, isSet, None, None))

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

    joined_query = (
        f"SELECT {label_col}, {agg_expr} AS data_value"
        f" FROM '{DATA_FILE_NAME_}'"
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
        color=color if color else None,
        color_discrete_sequence=THEME["primary"],
        orientation='h',
        title=None
    )

    if not color:
        fig.update_traces(
            marker_color=THEME["single"],
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
    'min': 'min',
    'max': 'max',
    'sum': 'sum',
    'mean': 'mean',
    'count': 'count',
    'join': agg_join
}

def create_line_list(
    title: str,
    df: pd.DataFrame,
    unique_col: Union[str, List[str]] = PERSON_ID_,
    rename: Optional[dict] = None,
    cols_order: Optional[List[str]] = None,
    merge_methods: Optional[List[str]] = None,
    message = None,
    custom_fields=None,
    **kwargs
) -> pd.DataFrame:
    """
    Creates a line list by aggregating data with consistent deduplication.
    Supports group-specific renaming via group{i}_rename parameter.
    """
    ops = {
        "==": operator.eq, "!=": operator.ne, ">": operator.gt, "<": operator.lt,
        ">=": operator.ge, "<=": operator.le
    }
    DEFAULT_MERGE = 'inner'
    
    unique_col_list = [unique_col] if isinstance(unique_col, str) else unique_col
    if not unique_col_list:
        raise ValueError("unique_col must specify at least one column.")
    
    df_base = df
    df_base = apply_calculated_fields(df_base, custom_fields)
    
    group_dfs = []
    
    for i in range(1, 31): #rows extended to 30
        group_cols = kwargs.get(f"group_cols{i}", []) or []
        group_filters = kwargs.get(f"group{i}_filters", {}) or {}
        group_aggr = kwargs.get(f"group{i}_aggr", {}) or {}
        group_rename_map = kwargs.get(f"group{i}_rename", {}) or {}
        
        if not group_cols:
            continue
        
        aggr_cols_needed = list(group_aggr.keys())
        all_required_cols = list(set(group_cols + unique_col_list + aggr_cols_needed))
        # print(all_required_cols)
        
        df_group_filtered = df_base
        filter_mask = pd.Series(True, index=df_group_filtered.index)
        
        for col, raw_val in group_filters.items():
            if col not in df_group_filtered.columns:
                print(f"Warning: Filter column '{col}' for group {i} not found. Skipping filter.")
                continue
            val = str(raw_val).strip()
            current_filter = None
            if val.startswith(("in:", "!in:")):
                is_in = val.startswith("in:")
                prefix_len = 3 if is_in else 4
                items = [x.strip() for x in val[prefix_len:].split(",")]
                current_filter = df_group_filtered[col].isin(items) if is_in else ~df_group_filtered[col].isin(items)
            else:
                applied = False
                for symbol, func in ops.items():
                    if val.startswith(symbol):
                        comp_val = val[len(symbol):].strip()
                        try:
                            comp_val = float(comp_val)
                        except ValueError:
                            pass 
                        current_filter = func(df_group_filtered[col], comp_val)
                        applied = True
                        break
                if not applied:
                    current_filter = (df_group_filtered[col] == raw_val)
            if current_filter is not None:
                filter_mask = filter_mask & current_filter
        
        df_group_filtered = df_group_filtered[filter_mask]
        
        if df_group_filtered.empty:
            continue
        
        missing_output_cols = [c for c in all_required_cols if c not in df_group_filtered.columns]
        if missing_output_cols:
            print(f"Warning: Group {i} skipped. Required columns not found: {missing_output_cols}")
            continue
        
        # Apply deduplication by unique_col and DATE_
        if DATE_ in df_group_filtered.columns:
            df_group_filtered = df_group_filtered.drop_duplicates(subset=unique_col_list + [DATE_])
        
        df_group = df_group_filtered[all_required_cols]
        
        count_col_name = f'unique_count_{i}'

        # Calculate unique count per group
        try:
            if not df_group.empty and len(df_group) > 0:
                df_group[count_col_name] = (
                    df_group.groupby(group_cols)[unique_col_list].transform("nunique").sum(axis=1)
                )
            else:
                df_group[count_col_name] = 0
        except Exception as e:
            print(f"Warning: Could not calculate unique count for group {i}: {e}")
            df_group[count_col_name] = 0
        
        # Build aggregation dictionary
        agg_dict = {
            col: AGG_MAP.get(method.lower(), 'first')
            for col, method in group_aggr.items()
        }
        
        aggr_columns = list(set(agg_dict.keys()))
        
        for col in group_cols + unique_col_list:
            if col not in aggr_columns:
                agg_dict[col] = 'first' 
        
        agg_dict[count_col_name] = 'first'
        
        df_group = (
            df_group.groupby(unique_col_list, dropna=False, as_index=False)
            .agg(agg_dict)
            .reset_index(drop=True)
        )
        
        # APPLY GROUP-SPECIFIC RENAME BEFORE APPENDING
        if group_rename_map:
            df_group = df_group.rename(columns=group_rename_map)
            # print(f"Applied rename for group {i}: {group_rename_map}")
        
        # Remove any duplicate columns that might have been created
        df_group = df_group.loc[:, ~df_group.columns.duplicated()]

        # print(group_filters, df_group)
        
        group_dfs.append(df_group)
    
    if not group_dfs:
        return html.Div(f"No data available for {title}")
    
    merge_methods_list = merge_methods or []
    final_df = group_dfs[0]
    
    for idx, right_df in enumerate(group_dfs[1:]):
        try:
            merge_how = merge_methods_list[idx] if idx < len(merge_methods_list) else DEFAULT_MERGE
            
            # Before merging, ensure unique_col_list columns exist in both dataframes
            # If group rename changed the unique_col names, we need to handle that
            merge_on = unique_col_list
            for col in unique_col_list:
                if col not in final_df.columns:
                    print(f"Warning: Unique column '{col}' not found in left DataFrame after group {idx+1}")
                if col not in right_df.columns:
                    print(f"Warning: Unique column '{col}' not found in right DataFrame for group {idx+2}")
            
            final_df = pd.merge(
                final_df, 
                right_df, 
                on=merge_on,
                how=merge_how,
                suffixes=('', f'_dup_{idx+2}')  # Avoid duplicate column names
            )
        except ValueError as e:
            print(f"Error during merge between group {idx+1} and group {idx+2} using method '{merge_how}'. Details: {e}")
            raise
    # Remove any duplicate columns created during merge
    final_df = final_df.loc[:, ~final_df.columns.duplicated()]
    
    # Apply main rename (only for columns that haven't been renamed yet)
    if rename:
        # Only rename columns that exist in the DataFrame
        rename_dict = {k: v for k, v in rename.items() if k in final_df.columns}
        if rename_dict:
            final_df = final_df.rename(columns=rename_dict)
            # print(f"Applied main rename: {rename_dict}")
    
    # Apply column ordering
    if cols_order and isinstance(cols_order, list):
        # Only keep columns that exist in the final DataFrame
        ordered_cols = [col for col in cols_order if col in final_df.columns]
        final_df = final_df[ordered_cols]
    elif isinstance(cols_order, str):
        raise ValueError("cols_order must be a list.")
    
    final_df = final_df.fillna('')
    
    if not final_df.empty and final_df.columns[0] in final_df.columns:
        final_df = final_df.sort_values(by=final_df.columns[0])
    
    table = html.Div([
        html.H3(title, style={"textAlign": "center"}),
        html.P(message, style={"textAlign": "center", "color": "red"}) if message else None,
        dash_table.DataTable(
            id="linelist-table",
            columns=[{"name": col, "id": col} for col in final_df.columns],
            data=final_df.to_dict('records'),
            merge_duplicate_headers=False,
            style_header={
                "backgroundColor": "rgb(70,70,70)",
                "color": "white",
                "fontWeight": "bold",
                "textAlign": "left",
                "fontSize": "13px",
            },
            style_cell={
                "padding": "6px",
                "textAlign": "left",
                "fontSize": "12px",
                "whiteSpace": "normal",
                "height": "auto",
            },
            style_table={"overflowX": "scroll"},
            page_size=20,
        )
    ])
    
    return table

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

# def create_heatmap(df, x_col, y_col, values_col, title, x_title, y_title,
#                    unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
#                    filter_col2=None, filter_value2=None, aggregation='count'):
#     """
#     Create a heatmap for correlation or density visualization.
#     Useful for: Time-of-day vs day-of-week patterns, diagnosis by age group, etc.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     # Create pivot for heatmap
#     pivot_data = data.pivot_table(
#         index=y_col, 
#         columns=x_col, 
#         values=values_col,
#         aggfunc=aggregation,
#         fill_value=0
#     )
    
#     fig = px.imshow(
#         pivot_data,
#         title=title,
#         labels=dict(x=x_title, y=y_title, color="Count"),
#         aspect="auto",
#         color_continuous_scale="Viridis"
#     )
    
#     fig.update_layout(
#         xaxis_title=x_title,
#         yaxis_title=y_title,
#         template="plotly_white"
#     )
    
#     return fig

# def create_stacked_area_chart(df, date_col, y_col, color_col, title, x_title, y_title,
#                               unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
#                               filter_col2=None, filter_value2=None, aggregation='count'):
#     """
#     Create a stacked area chart for cumulative trends over time.
#     Useful for: Program enrollment over time, disease burden trends, etc.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     # Ensure date column is datetime
#     data[date_col] = pd.to_datetime(data[date_col])
    
#     # Group by date and color column
#     summary = data.groupby([date_col, color_col])[y_col].agg(aggregation).reset_index()
    
#     fig = px.area(
#         summary,
#         x=date_col,
#         y=y_col,
#         color=color_col,
#         title=title,
#         line_group=color_col,
#         color_discrete_sequence=px.colors.qualitative.Dark2
#     )
    
#     fig.update_layout(
#         xaxis_title=x_title,
#         yaxis_title=y_title,
#         template="plotly_white",
#         hovermode='x unified'
#     )
    
#     return fig

# def create_box_plot(df, x_col, y_col, title, x_title, y_title,
#                     unique_column=PERSON_ID_, color=None,
#                     filter_col1=None, filter_value1=None,
#                     filter_col2=None, filter_value2=None):
#     """
#     Create a box plot showing distribution of numerical values.
#     Useful for: Age distribution by diagnosis, lab data_value ranges, etc.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     fig = px.box(
#         data,
#         x=x_col,
#         y=y_col,
#         color=color,
#         title=title,
#         color_discrete_sequence=px.colors.qualitative.Dark2,
#         points="outliers"  # Show only outliers as points
#     )
    
#     fig.update_layout(
#         xaxis_title=x_title,
#         yaxis_title=y_title,
#         template="plotly_white",
#         boxmode='group' if color else 'overlay'
#     )
    
#     # Add mean markers
#     means = data.groupby(x_col)[y_col].mean().reset_index()
#     fig.add_scatter(
#         x=means[x_col],
#         y=means[y_col],
#         mode='markers',
#         marker=dict(symbol='diamond', size=10, color='red'),
#         name='Mean'
#     )
    
#     return fig

# def create_scatter_plot(df, x_col, y_col, title, x_title, y_title,
#                         color=None, size=None, trendline=True,
#                         unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
#                         filter_col2=None, filter_value2=None):
#     """
#     Create a scatter plot with optional trend line.
#     Useful for: Age vs BP correlation, weight vs height, etc.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     # Deduplicate
#     data = _prepare_data_for_visualization(data, unique_column)
    
#     fig = px.scatter(
#         data,
#         x=x_col,
#         y=y_col,
#         color=color,
#         size=size,
#         title=title,
#         trendline="ols" if trendline else None,
#         color_discrete_sequence=px.colors.qualitative.Dark2
#     )
    
#     if trendline:
#         # Customize trendline
#         fig.update_traces(
#             line=dict(dash='dash', width=2),
#             selector=dict(mode='lines')
#         )
    
#     fig.update_layout(
#         xaxis_title=x_title,
#         yaxis_title=y_title,
#         template="plotly_white"
#     )
    
#     return fig

# def create_gauge_chart(data_value, title, min_val=0, max_val=100, 
#                        threshold_ranges=None, threshold_colors=None):
#     """
#     Create a gauge chart for single metric visualization.
#     Useful for: Bed occupancy, vaccination coverage, target achievement, etc.
#     """
#     if threshold_ranges is None:
#         threshold_ranges = [(0, 50), (50, 80), (80, 100)]
#         threshold_colors = ["red", "yellow", "green"]
    
#     fig = go.Figure(go.Indicator(
#         mode="gauge+number+delta",
#         data_value=data_value,
#         title={'text': title},
#         delta={'reference': max_val * 0.8},  # 80% target
#         gauge={
#             'axis': {'range': [min_val, max_val]},
#             'bar': {'color': "darkblue"},
#             'steps': [
#                 {'range': threshold_ranges[i], 'color': threshold_colors[i]}
#                 for i in range(len(threshold_ranges))
#             ],
#             'threshold': {
#                 'line': {'color': "red", 'width': 4},
#                 'thickness': 0.75,
#                 'data_value': max_val * 0.9  # 90% warning
#             }
#         }
#     ))
    
#     fig.update_layout(
#         height=300,
#         margin=dict(l=50, r=50, t=50, b=50)
#     )
    
#     return fig

# def create_treemap(df, path_cols, values_col, title,
#                    unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
#                    filter_col2=None, filter_value2=None):
#     """
#     Create a treemap for hierarchical data visualization.
#     Useful for: Program breakdown by location, diagnosis categories, etc.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     # Deduplicate
#     data = _prepare_data_for_visualization(data, unique_column)
    
#     # Aggregate values
#     summary = data.groupby(path_cols)[values_col].nunique().reset_index()
    
#     fig = px.treemap(
#         summary,
#         path=path_cols,
#         values=values_col,
#         title=title,
#         color=values_col,
#         color_continuous_scale='Blues'
#     )
    
#     fig.update_layout(
#         template="plotly_white"
#     )
    
#     fig.update_traces(
#         hovertemplate="<b>%{label}</b><br>Count: %{data_value}<br>Parent: %{parent}"
#     )
    
#     return fig

# def create_sunburst_chart(df, path_cols, values_col, title,
#                           unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
#                           filter_col2=None, filter_value2=None):
#     """
#     Create a sunburst chart for radial hierarchical visualization.
#     Useful for: Multi-level program enrollment, diagnosis categories, etc.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     # Deduplicate
#     data = _prepare_data_for_visualization(data, unique_column)
    
#     # Aggregate values
#     summary = data.groupby(path_cols)[values_col].nunique().reset_index()
    
#     fig = px.sunburst(
#         summary,
#         path=path_cols,
#         values=values_col,
#         title=title,
#         color=values_col,
#         color_continuous_scale='RdBu'
#     )
    
#     fig.update_layout(
#         template="plotly_white"
#     )
    
#     return fig

# def create_funnel_chart(df, stages_col, values_col, title,
#                         unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
#                         filter_col2=None, filter_value2=None):
#     """
#     Create a funnel chart for tracking progression through stages.
#     Useful for: Patient journey (Screening → Diagnosis → Treatment → Outcome)
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     # Calculate counts per stage
#     funnel_data = data.groupby(stages_col)[values_col].nunique().reset_index()
#     funnel_data = funnel_data.sort_values(by=values_col, ascending=False)
    
#     fig = go.Figure(go.Funnel(
#         y=funnel_data[stages_col],
#         x=funnel_data[values_col],
#         textinfo="data_value+percent previous+percent total",
#         marker=dict(color=["#006401", "#2E8B57", "#3CB371", "#90EE90"]),
#         connector=dict(line=dict(color="royalblue", dash="dot", width=3))
#     ))
    
#     fig.update_layout(
#         title=title,
#         template="plotly_white"
#     )
    
#     return fig

# def create_radar_chart(df, categories_col, values_col, group_col, title,
#                        unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
#                        filter_col2=None, filter_value2=None):
#     """
#     Create a radar chart for comparing multiple dimensions.
#     Useful for: Program performance metrics, patient health indicators, etc.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     # Aggregate by group and category
#     summary = data.groupby([group_col, categories_col])[values_col].mean().reset_index()
    
#     fig = go.Figure()
    
#     for group in summary[group_col].unique():
#         group_data = summary[summary[group_col] == group]
#         fig.add_trace(go.Scatterpolar(
#             r=group_data[values_col],
#             theta=group_data[categories_col],
#             fill='toself',
#             name=group
#         ))
    
#     fig.update_layout(
#         title=title,
#         polar=dict(radialaxis=dict(visible=True, range=[0, summary[values_col].max()])),
#         template="plotly_white",
#         showlegend=True
#     )
    
#     return fig

# def create_waterfall_chart(df, stages_col, values_col, title,
#                           unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
#                           filter_col2=None, filter_value2=None):
#     """
#     Create a waterfall chart showing cumulative effect of sequential steps.
#     Useful for: Patient attrition, stock management, financial tracking.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     # Calculate stage-wise values
#     stage_values = data.groupby(stages_col)[values_col].sum().reset_index()
    
#     fig = go.Figure(go.Waterfall(
#         name=title,
#         orientation="v",
#         measure=["relative"] * len(stage_values),
#         x=stage_values[stages_col],
#         y=stage_values[values_col],
#         textposition="outside",
#         text=stage_values[values_col],
#         connector={"line": {"color": "rgb(63, 63, 63)"}},
#     ))
    
#     fig.update_layout(
#         title=title,
#         template="plotly_white",
#         showlegend=False
#     )
    
#     return fig

# def create_bubble_chart(df, x_col, y_col, size_col, color_col, title,
#                        x_title, y_title, unique_column=PERSON_ID_,
#                        filter_col1=None, filter_value1=None,
#                        filter_col2=None, filter_value2=None):
#     """
#     Create a bubble chart with three dimensions of data.
#     Useful for: Program comparison (enrollment, outcomes, cost), etc.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     # Deduplicate and aggregate
#     summary = data.groupby([color_col, x_col, y_col])[size_col].nunique().reset_index()
    
#     fig = px.scatter(
#         summary,
#         x=x_col,
#         y=y_col,
#         size=size_col,
#         color=color_col,
#         title=title,
#         hover_name=color_col,
#         size_max=60,
#         color_discrete_sequence=px.colors.qualitative.Dark2
#     )
    
#     fig.update_layout(
#         xaxis_title=x_title,
#         yaxis_title=y_title,
#         template="plotly_white"
#     )
    
#     return fig

# def create_timeline_chart(df, task_col, start_col, end_col, color_col, title,
#                           unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
#                           filter_col2=None, filter_value2=None):
#     """
#     Create a Gantt chart for timeline visualization.
#     Useful for: Patient stay duration, treatment timelines, etc.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     # Ensure dates are datetime
#     data[start_col] = pd.to_datetime(data[start_col])
#     data[end_col] = pd.to_datetime(data[end_col])
    
#     fig = px.timeline(
#         data,
#         x_start=start_col,
#         x_end=end_col,
#         y=task_col,
#         color=color_col,
#         title=title,
#         color_discrete_sequence=px.colors.qualitative.Dark2
#     )
    
#     fig.update_layout(
#         xaxis_title="Timeline",
#         yaxis_title="Task/Patient",
#         template="plotly_white"
#     )
    
#     return fig

# def create_3d_scatter(df, x_col, y_col, z_col, color_col, title,
#                       unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
#                       filter_col2=None, filter_value2=None):
#     """
#     Create a 3D scatter plot for multidimensional analysis.
#     Useful for: Age, BP, BMI correlation; lab data_value clusters, etc.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     # Deduplicate
#     data = _prepare_data_for_visualization(data, unique_column)
    
#     fig = px.scatter_3d(
#         data,
#         x=x_col,
#         y=y_col,
#         z=z_col,
#         color=color_col,
#         title=title,
#         opacity=0.7,
#         color_discrete_sequence=px.colors.qualitative.Dark2
#     )
    
#     fig.update_layout(
#         scene=dict(
#             xaxis_title=x_col,
#             yaxis_title=y_col,
#             zaxis_title=z_col
#         ),
#         template="plotly_white"
#     )
    
#     return fig

# def create_violin_plot(df, x_col, y_col, title, x_title, y_title,
#                        color=None, box=True, points=False,
#                        unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
#                        filter_col2=None, filter_value2=None):
#     """
#     Create a violin plot showing distribution density.
#     Useful for: Comparing distributions across categories.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     fig = px.violin(
#         data,
#         x=x_col,
#         y=y_col,
#         color=color,
#         box=box,
#         points=points,
#         title=title,
#         color_discrete_sequence=px.colors.qualitative.Dark2,
#         violinmode='group' if color else 'overlay'
#     )
    
#     fig.update_layout(
#         xaxis_title=x_title,
#         yaxis_title=y_title,
#         template="plotly_white"
#     )
    
#     return fig

# def create_choropleth_map(df, location_col, values_col, title,
#                           locations_dict=None, unique_column=PERSON_ID_,
#                           filter_col1=None, filter_value1=None,
#                           filter_col2=None, filter_value2=None):
#     """
#     Create a choropleth map for geographic data visualization.
#     Useful for: Disease prevalence by region, facility coverage, etc.
#     """
#     data = df
    
#     # Apply filters
#     data = _apply_filter(data, filter_col1, filter_value1)
#     data = _apply_filter(data, filter_col2, filter_value2)
    
#     # Aggregate by location
#     summary = data.groupby(location_col)[values_col].nunique().reset_index()
    
#     # If no custom locations dict, assume coordinates are in data
#     if locations_dict and 'lat' in locations_dict and 'lon' in locations_dict:
#         # Use scatter mapbox for point data
#         fig = px.scatter_mapbox(
#             summary,
#             lat=locations_dict['lat'],
#             lon=locations_dict['lon'],
#             size=values_col,
#             color=values_col,
#             hover_name=location_col,
#             title=title,
#             mapbox_style="carto-positron",
#             zoom=8,
#             color_continuous_scale="Viridis"
#         )
#     else:
#         # Use density mapbox for heatmap
#         fig = px.density_mapbox(
#             summary,
#             lat=locations_dict.get('lat') if locations_dict else None,
#             lon=locations_dict.get('lon') if locations_dict else None,
#             z=values_col,
#             radius=20,
#             title=title,
#             mapbox_style="carto-positron",
#             zoom=8
#         )
    
#     fig.update_layout(
#         template="plotly_white"
#     )
    
#     return fig

# def create_bullet_chart(actual, target, title, ranges=None, 
#                         range_colors=None, measure_name="Current"):
#     """
#     Create a bullet chart for performance against targets.
#     Useful for: KPIs, program targets, etc.
#     """
#     if ranges is None:
#         ranges = [target * 0.7, target * 0.9, target]
#         range_colors = ["red", "yellow", "green"]
    
#     fig = go.Figure(go.Indicator(
#         mode="number+gauge+delta",
#         data_value=actual,
#         delta={'reference': target},
#         title={'text': title},
#         gauge={
#             'shape': "bullet",
#             'axis': {'range': [0, target * 1.2]},
#             'bar': {'color': "darkblue"},
#             'steps': [
#                 {'range': [0, ranges[0]], 'color': range_colors[0]},
#                 {'range': [ranges[0], ranges[1]], 'color': range_colors[1]},
#                 {'range': [ranges[1], ranges[2]], 'color': range_colors[2]}
#             ],
#             'threshold': {
#                 'line': {'color': "red", 'width': 2},
#                 'thickness': 0.75,
#                 'data_value': target
#             }
#         }
#     ))
    
#     fig.update_layout(
#         height=200,
#         margin=dict(l=50, r=50, t=50, b=50)
#     )
    
#     return fig

# # def create_count(df, aggregation='count', unique_column=PERSON_ID_, *filters):
# #     data = df

# #     filter_cols = [item for item in filters[::2] if item is not None]
# #     filter_vals = [item for item in filters[1::2] if item is not None]
# #      #for defaulters
# #     data["DateValue"] = pd.to_datetime(data[DATE_]).dt.date
# #     data['datetime'] = data[DATE_]

# #     # Apply all filters using the helper function
# #     for col, val in zip(filter_cols, filter_vals):
# #         if col == "defaulter_period":
# #             continue
# #         else:
# #             data = _apply_filter(data, col, val)
    
    
# #     # Remove duplicates based on unique_column and DATE_
# #     unique_visits = _prepare_data_for_visualization(data, unique_column)
    
# #     # Handle different aggregation types
# #     if aggregation == 'count':
# #         return len(unique_visits[unique_column].dropna())
# #     elif aggregation == 'nunique':
# #         return len(unique_visits.drop_duplicates(subset=unique_column))
# #     elif aggregation == 'list':
# #         return unique_visits[unique_column].dropna().unique().tolist()
# #     elif aggregation == 'time_diff_mins':
# #         # Calculate time difference between min and max datetime for each patient
# #         # Note: This assumes there's a 'DATETIME' column in your dataframe
# #         if 'datetime' not in unique_visits.columns:
# #             raise ValueError("datetime column is required for time_diff aggregation")
# #         patient_times = data.groupby([unique_column, DATE_])['datetime'].agg(['min', 'max'])
# #         patient_times['time_diff'] = (patient_times['max'] - patient_times['min']).dt.total_seconds() / (60)
# #         patient_times = patient_times[patient_times['time_diff'] < 120]
# #         mean_val = patient_times['time_diff'].mean()
# #         if pd.isna(mean_val):
# #             return 0
# #         return int(mean_val)
# #     elif aggregation == 'time_diff_hour':
# #         if 'datetime' not in unique_visits.columns:
# #             raise ValueError("datetime column is required for time_diff aggregation")
# #         patient_times = data.groupby([unique_column, DATE_])['datetime'].agg(['min', 'max'])
# #         patient_times['time_diff'] = (patient_times['max'] - patient_times['min']).dt.total_seconds() / (60 * 60)
# #         patient_times = patient_times[patient_times['time_diff'] < 2]
# #         mean_val = patient_times['time_diff'].mean()
# #         if pd.isna(mean_val):
# #             return 0
# #         return int(mean_val)
# #     elif aggregation == 'defaulter_count':
# #         unique_visits['defaulter_period'] = unique_visits[CONCEPT_NAME_]
# #         # lets maintain individuals who passed through filters
# #         filtered_ids = set(unique_visits[unique_column].dropna().unique())
# #         df = df[df[unique_column].isin(filtered_ids)]
# #         df["start_date"] = pd.to_datetime(df["start_date"],errors='coerce')
# #         df['value_datetime'] = pd.to_datetime(df['value_datetime'],errors='coerce')
# #         df = df.dropna(subset=[DATE_, 'value_datetime'])
# #         df_defaulted_ids = []
# #         for col,val in zip(filter_cols, filter_vals):
# #             try:
# #                 if col == "defaulter_period":
# #                     default = df[df[col].isin(["Appointment date","Next scheduled visit","Return visit date"])]\
# #                         .sort_values(by=[PERSON_ID_,DATE_]) #restart the filter
# #                     default['Duration_to_visit'] = (
# #                                     default['start_date'] - default["value_datetime"]
# #                                 ).dt.days
# #                     # print(default[["Program","concept_name","value_datetime","Duration_to_visit","start_date"]])
# #                     default = default[default['Duration_to_visit']> val]
# #                     ids = default[PERSON_ID_].unique().tolist()
# #                     df_defaulted_ids.extend(ids)
# #             except Exception as e:
# #                 print(e)
# #                 df_defaulted_ids = []
# #         return len(df_defaulted_ids)

# #     elif aggregation in ['sum', 'mean', 'min', 'max', 'std', 'var']:
# #         return int(unique_visits[unique_column].agg(aggregation))
# #     else:
# #         return len(unique_visits[unique_column].dropna())