import pandas as pd
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

from config import PERSON_ID_, ENCOUNTER_ID_, DATE_

"""
MAIN USE CASE OF THIS FILE IS TO PROVIDE VISUALIZATION FUNCTIONS FOR PATIENT DATA

"""

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
            =value
            !=value
            >value
            <value
            >=value
            <=value
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
       - If list or multi-value, uses .isin()

    2. MULTI-COLUMN FILTERING (filter_col is a list)
       ------------------------------------------------
       Two cases:
       a) Length >= 2:
            - filter_value MUST be a list of the same length
            - Each pair (col[i], value[i]) is applied independently
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

    df = data.copy()

    # Normalize: list, pipe-separated, stringified list...
    filter_value = _normalize_filter_value(filter_value)

    if isinstance(filter_col, list):

        if len(filter_col) >= 2:
            if not isinstance(filter_value, list) or len(filter_value) != len(filter_col):
                raise ValueError("Multi-column filters require filter_value list same length as filter_col.")

            for col, val in zip(filter_col, filter_value):
                df = _apply_filter(df, col, val)
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
                value = ""
            else:
                try:
                    if "." in value_str:
                        value = float(value_str)
                    else:
                        value = int(value_str)
                except:
                    value = value_str


            if operator == "=":
                return df[df[filter_col] == value]
            if operator == "!=":
                return df[df[filter_col] != value]
            if operator == ">":
                return df[df[filter_col] > value]
            if operator == "<":
                return df[df[filter_col] < value]
            if operator == ">=":
                return df[df[filter_col] >= value]
            if operator == "<=":
                return df[df[filter_col] <= value]

        # 3. Simple equality
        return df[df[filter_col] == filter_value]

    return df[df[filter_col] == filter_value]


def create_count(df,aggregation='count', unique_column=PERSON_ID_, filter_col1=None, filter_value1=None, filter_col2=None, filter_value2=None, 
                 filter_col3=None, filter_value3=None, filter_col4=None, filter_value4=None,
                 filter_col5=None, filter_value5=None, filter_col6=None, filter_value6=None, 
                 filter_col7=None, filter_value7=None, filter_col8=None, filter_value8=None,
                 filter_col9=None, filter_value9=None, filter_col10=None, filter_value10=None):
    data = df
    
    # Apply all filters using the helper function
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)
    data = _apply_filter(data, filter_col4, filter_value4)
    data = _apply_filter(data, filter_col5, filter_value5)
    data = _apply_filter(data, filter_col6, filter_value6)
    data = _apply_filter(data, filter_col7, filter_value7)
    data = _apply_filter(data, filter_col8, filter_value8)
    data = _apply_filter(data, filter_col9, filter_value9)
    data = _apply_filter(data, filter_col10, filter_value10)
    
    # Remove duplicates based on unique_column and DATE_
    unique_visits = data.drop_duplicates(subset=[unique_column, DATE_])
    # unique_visits = data
    # Handle different aggregation types
    if aggregation == 'count':
        return len(unique_visits[unique_column].dropna())
    elif aggregation == 'nunique':
        return unique_visits[unique_column].nunique()
    elif aggregation == 'list':
        return unique_visits[unique_column].dropna().unique().tolist()
    elif aggregation in ['sum', 'mean', 'min', 'max', 'std', 'var']:
        # For numeric aggregations
        return unique_visits[unique_column].agg(aggregation)
    else:
        # Default to count
        # unique_visits.to_csv("debug_summary.csv", index=False)
        return len(unique_visits[unique_column].dropna())

def create_count_sets(
    df,
    unique_column=PERSON_ID_,
    filter_col1=None, filter_value1=None,
    filter_col2=None, filter_value2=None,
    filter_col3=None, filter_value3=None,
    filter_col4=None, filter_value4=None,
    filter_col5=None, filter_value5=None,
    filter_col6=None, filter_value6=None,
    filter_col7=None, filter_value7=None,
    filter_col8=None, filter_value8=None,
    filter_col9=None, filter_value9=None,
    filter_col10=None, filter_value10=None
):

    data = df.copy()

    filter_cols = [
        filter_col1, filter_col2, filter_col3, filter_col4, filter_col5,
        filter_col6, filter_col7, filter_col8, filter_col9, filter_col10
    ]

    filter_vals = [
        filter_value1, filter_value2, filter_value3, filter_value4, filter_value5,
        filter_value6, filter_value7, filter_value8, filter_value9, filter_value10
    ]

    if not isinstance(filter_value1, list) or len(filter_value1) <= 1:

        data = _apply_filter(data, filter_col1, filter_value1)
        data = _apply_filter(data, filter_col2, filter_value2)
        data = _apply_filter(data, filter_col3, filter_value3)
        data = _apply_filter(data, filter_col4, filter_value4)
        data = _apply_filter(data, filter_col5, filter_value5)
        data = _apply_filter(data, filter_col6, filter_value6)
        data = _apply_filter(data, filter_col7, filter_value7)
        data = _apply_filter(data, filter_col8, filter_value8)
        data = _apply_filter(data, filter_col9, filter_value9)
        data = _apply_filter(data, filter_col10, filter_value10)

        unique_visits = data.drop_duplicates(subset=[unique_column, DATE_])
        return len(unique_visits)

    if not isinstance(filter_value2, list):
        raise ValueError(
            "filter_value2 must be a list when filter_value1 is a list"
        )

    if len(filter_value1) != len(filter_value2):
        raise ValueError(
            "filter_value1 and filter_value2 must have equal lengths"
        )

    set_length = len(filter_value1)

    # Validate remaining list filters
    for v in filter_vals[2:]:
        if isinstance(v, list) and len(v) != set_length:
            raise ValueError(
                "All list filter values must have equal lengths"
            )

    sets = []

    for i in range(set_length):

        df_f = data.copy()

        for col, val in zip(filter_cols, filter_vals):

            if col is None or val is None:
                continue

            if isinstance(val, list):

                # list filters participate in set construction
                df_f = _apply_filter(df_f, col, val[i])

        ids = set(
            df_f[[unique_column, DATE_]]
            .drop_duplicates()
            .apply(tuple, axis=1)
        )

        sets.append(ids)

    # intersection
    final_set = sets[0]
    for s in sets[1:]:
        final_set = final_set.intersection(s)


    remaining_df = data[
        data[[unique_column, DATE_]]
        .apply(tuple, axis=1)
        .isin(final_set)
    ]

    for col, val in zip(filter_cols, filter_vals):

        if col is None or val is None:
            continue

        if not isinstance(val, list):
            remaining_df = _apply_filter(remaining_df, col, val)

    unique_visits = remaining_df.drop_duplicates(subset=[unique_column, DATE_])

    return len(unique_visits)

def create_count_unique(df, unique_column=PERSON_ID_, filter_col1=None, filter_value1=None, filter_col2=None, filter_value2=None, 
                 filter_col3=None, filter_value3=None, filter_col4=None, filter_value4=None,
                 filter_col5=None, filter_value5=None, filter_col6=None, filter_value6=None):
    data = df
    
    # Apply all filters using the helper function
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)
    data = _apply_filter(data, filter_col4, filter_value4)
    data = _apply_filter(data, filter_col5, filter_value5)
    data = _apply_filter(data, filter_col6, filter_value6) 
    
    return len(data[unique_column].dropna().unique())

def create_sum(df, num_field='ValueN', filter_col1=None, filter_value1=None, filter_col2=None, filter_value2=None, 
                 filter_col3=None, filter_value3=None, filter_col4=None, filter_value4=None,
                 filter_col5=None, filter_value5=None, filter_col6=None, filter_value6=None):
    data = df
    
    # Apply all filters using the helper function
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)
    data = _apply_filter(data, filter_col4, filter_value4)
    data = _apply_filter(data, filter_col5, filter_value5)
    data = _apply_filter(data, filter_col6, filter_value6)
    
    return data[num_field].sum()

def create_sum_sets(df, filter_col1, filter_value1, filter_col2, filter_value2, num_field='ValueN',
                      unique_column=ENCOUNTER_ID_, **extra_filters):
    """
    Sum values for unique IDs that satisfy a paired condition.
    """
    if not (isinstance(filter_value1, list) and isinstance(filter_value2, list)):
        raise ValueError("filter_value1 and filter_value2 must be lists of the same length.")
    if len(filter_value1) != len(filter_value2):
        raise ValueError("filter_value1 and filter_value2 must have the same length.")

    pair_ids = []
    for v1, v2 in zip(filter_value1, filter_value2):
        ids = set(df.loc[(df[filter_col1] == v1) & (df[filter_col2] == v2), unique_column])
        pair_ids.append(ids)

    pair_total = set.intersection(*pair_ids)
    filtered = df[df[unique_column].isin(pair_total)]

    # Apply extra filters if provided
    for i in range(3, 7):
        col = extra_filters.get(f'filter_col{i}')
        val = extra_filters.get(f'filter_value{i}')
        if col is not None and val is not None:
            filtered = _apply_filter(filtered, col, val)

    return filtered[num_field].sum()

def _prepare_data_for_visualization(df, unique_column, apply_deduplication=True):
    """
    Prepare data for visualization by applying consistent deduplication logic.
    This mirrors the logic used in create_count functions.
    """
    data = df.copy()
    
    if isinstance(unique_column, list):
        if apply_deduplication and DATE_ in data.columns and all(col in data.columns for col in unique_column):
            data = data.drop_duplicates(subset=[DATE_] + unique_column)
        return data
    else:
        if apply_deduplication and DATE_ in data.columns and unique_column in data.columns:
            data = data.drop_duplicates(subset=[unique_column, DATE_])
        return data

def create_column_chart(df, x_col, y_col, title, x_title, y_title,
                        unique_column=PERSON_ID_, legend_title=None,
                        color=None, filter_col1=None, filter_value1=None,
                        filter_col2=None, filter_value2=None,
                        filter_col3=None, filter_value3=None, aggregation='count'):
    """
    Create a column chart using Plotly Express with legend support.
    """
    data = df
    
    # Apply filters using the helper function
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)
    
    # Apply consistent deduplication
    data = _prepare_data_for_visualization(data, unique_column)
    
    # if data.empty:
    #     return go.Figure().update_layout(title=f"No data available for {title}")
    
    if color:
        # Group by both x_col and color column
        if aggregation == 'count':
            summary = data.groupby([x_col, color])[y_col].nunique().reset_index()
        elif aggregation == 'nunique':
            summary = data.groupby([x_col, color])[y_col].nunique().reset_index()
        else:
            summary = data.groupby([x_col, color])[y_col].agg(aggregation).reset_index()
        
        summary.columns = [x_col, color, 'value']
        summary['label'] = summary['value'].astype(str)
        
        fig = px.bar(
            summary, 
            x=x_col, 
            y='value', 
            color=color,
            title=title, 
            text='label',
            color_discrete_sequence=px.colors.qualitative.Dark2,
            barmode='group'
        )
    else:
        # Group only by x_col
        if aggregation == 'count':
            summary = data.groupby(x_col)[y_col].count().reset_index()
            # data.to_csv("debug_summary.csv", index=False)
        elif aggregation == 'nunique':
            summary = data.groupby(x_col)[y_col].nunique().reset_index()
        else:
            summary = data.groupby(x_col)[y_col].agg(aggregation).reset_index()
        
        summary.columns = [x_col, 'value']
        summary = summary.sort_values(by='value', ascending=False)
        summary['label'] = summary['value'].astype(str)
        
        fig = px.bar(summary, x=x_col, y='value', title=title, text='label')
        fig.update_traces(marker_color="#006401")
    
    fig.update_layout(
        xaxis_title=x_title,
        yaxis_title=y_title,
        template="plotly_white",
        legend_title=legend_title if legend_title else color,
    )
    
    fig.update_traces(
        textposition='auto',
        hovertemplate="<b>X-Axis:</b> %{x}<br>" +
                      "<b>Count:</b> %{y}<br>" 
    )
    
    return fig

def create_line_chart(df, date_col, y_col, title, x_title, 
                      y_title, unique_column=PERSON_ID_, 
                      legend_title=None, color=None, filter_col1=None, 
                      filter_value1=None, filter_col2=None, 
                      filter_value2=None, filter_col3=None, 
                      filter_value3=None, aggregation='count'):
    """
    Create a time series chart using Plotly Express.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)
    
    # Apply consistent deduplication
    data = _prepare_data_for_visualization(data, unique_column)
    
    # if data.empty:
    #     return go.Figure().update_layout(title=f"{title}")
    
    # Ensure date column is in datetime format
    if not pd.api.types.is_datetime64_any_dtype(data[date_col]):
        try:
            data[date_col] = pd.to_datetime(data[date_col], errors='coerce')
        except Exception as e:
            raise ValueError(f"Error converting {date_col} to datetime: {e}")
    
    data = data.copy()
    data['date_only'] = pd.to_datetime(data[date_col]).dt.date
    
    if color:
        if aggregation == 'count':
            summary = data.groupby(['date_only', color])[y_col].nunique().reset_index(name='count')
        else:
            summary = data.groupby(['date_only', color])[y_col].agg(aggregation).reset_index(name='count')
    else:
        if aggregation == 'count':
            summary = data.groupby('date_only')[y_col].nunique().reset_index(name='count')
        else:
            summary = data.groupby('date_only')[y_col].agg(aggregation).reset_index(name='count')
    
    summary = summary.sort_values('date_only')
    
    fig = px.line(
        summary,
        x='date_only',
        y='count',
        color=color if color else None,
        color_discrete_sequence=px.colors.qualitative.Dark2,
        title=title,
        markers=True,
        text='count'
    )
    
    fig.update_traces(
        mode='lines+markers+text',
        textposition='top center',
        hovertemplate="<b>Date:</b> %{x|%b %d}<br>" +
                     "<b>Count:</b> %{y}<br>"
    )
    
    if not summary.empty:
        avg_val = summary['count'].mean()
        fig.add_hline(
            y=avg_val,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Average = {avg_val:.0f}",
            annotation_position="top right"
        )
    
    fig.update_layout(
        yaxis=dict(title=y_title),
        xaxis=dict(title=x_title),
        legend_title=legend_title if legend_title else (color if color else ""),
        template="plotly_white"
    )
    
    return fig

def create_pie_chart(df, names_col, values_col, title, 
                     unique_column=PERSON_ID_, filter_col1=None, 
                     filter_value1=None, filter_col2=None, 
                     filter_value2=None, filter_col3=None, 
                     filter_value3=None, colormap=None, aggregation='count'):
    """
    Create a pie chart using Plotly Express.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)
    
    # Apply consistent deduplication
    data = _prepare_data_for_visualization(data, unique_column)
    
    # if data.empty:
    #     return go.Figure().update_layout(title=f"No data available for {title}")
    
    if aggregation == 'count':
        df_summary = data.groupby(names_col)[values_col].nunique().reset_index()
    elif aggregation == 'nunique':
        df_summary = data.groupby(names_col)[values_col].nunique().reset_index()
    else:
        df_summary = data.groupby(names_col)[values_col].agg(aggregation).reset_index()
    
    df_summary.columns = [names_col, 'value']
    
    # Filter out zero values
    df_summary = df_summary[df_summary['value'] > 0]
    
    if df_summary.empty:
        return go.Figure().update_layout(title=f"No data available for {title}")
    
    fig = px.pie(
        df_summary, 
        names=names_col, 
        values='value', 
        title=title, 
        hole=0.5, 
        color_discrete_sequence=px.colors.qualitative.Dark2 if colormap is None else None
    )
    colormap = {}
    
    if colormap:
        colors = [colormap.get(cat, px.colors.qualitative.Dark2[i % len(px.colors.qualitative.Dark2)]) 
                  for i, cat in enumerate(df_summary[names_col])]
        fig.update_traces(marker=dict(colors=colors))
    
    fig.update_traces(
        textposition='inside', 
        textinfo='percent+label',
        hovertemplate="<b>Category:</b> %{label}<br>" +
                      "<b>Value:</b> %{value}<br>" +
                      "<b>Percent:</b> %{percent}<br>" 
    )
    
    return fig

def create_pivot_table(df, index_col, columns_col, values_col, title, unique_column=PERSON_ID_, aggfunc='sum',
                     filter_col1=None, filter_value1=None, 
                     filter_col2=None, filter_value2=None,
                     filter_col3=None, filter_value3=None,
                     aggregation='count',
                     rename={}, replace={}):
    """
    Create a pivot table from the DataFrame.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)
    
    # Apply consistent deduplication
    data = _prepare_data_for_visualization(data, unique_column)

    
    # Determine the actual aggregation function
    if aggfunc == 'concat':
        actual_aggfunc = lambda x: ', '.join(sorted(set(str(v) for v in x if str(v) != '')))
        value_format = None
    elif aggfunc == 'count':
        # For count, use nunique on the values_col
        actual_aggfunc = 'nunique'
        value_format = ",.0f"
    else:
        actual_aggfunc = aggfunc
        value_format = ",.0f"
    
    # Build pivot
    pivot = data.pivot_table(
        index=index_col,
        columns=columns_col,
        values=values_col,
        aggfunc=actual_aggfunc,
        fill_value=0
    ).reset_index()
    
    num_index_cols = len(index_col) if isinstance(index_col, (list, tuple)) else 1
    
    align_list = (['left'] * num_index_cols) + (['center'] * (len(pivot.columns) - num_index_cols))
    
    if value_format is None:
        format_list = [None] * len(pivot.columns)
    else:
        format_list = ([None] * num_index_cols) + ([value_format] * (len(pivot.columns) - num_index_cols))
    
    pivot = pivot.rename(columns=rename).replace(replace)
    
    fig = go.Figure(data=[go.Table(
        header=dict(
            values=["<b>" + str(col) + "</b>" for col in pivot.columns],
            fill_color='grey',
            align=align_list,
            font=dict(size=12, color='white')
        ),
        cells=dict(
            values=[pivot[col] for col in pivot.columns],
            fill_color='white',
            align=align_list,
            height=30,
            format=format_list,
            font=dict(size=11, color='darkslategray')
        )
    )])
    
    row_height = 30
    extra_space = 100
    dynamic_height = row_height * len(pivot) + extra_space
    
    layout_updates = {
        'title': dict(
            text='<b>' + title + '</b>',
            x=0.5,
            xanchor='center',
            font=dict(size=18, color='black'),
        ),
        'margin': dict(l=20, r=20, b=20, t=90),
        'height': dynamic_height + 40
    }
    
    fig.update_layout(**layout_updates)
    return fig

def create_crosstab_table(
    df,
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
    rename={}, replace={}
):
    """
    Create a crosstab table with multilayer column headers using Dash DataTable.
    """

    data = df.copy()

    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)

    # Deduplicate by person + date
    if DATE_ in data.columns:
        data = data.drop_duplicates(subset=[unique_column, DATE_])

    # Helper: support multi-axis for crosstab
    def _axis_arg(arg):
        if isinstance(arg, (list, tuple)):
            return [data[c] for c in arg]
        return data[arg]

    index_arg = _axis_arg(index_col)
    columns_arg = _axis_arg(columns_col)

    # Handle normalization
    norm = False
    if normalize is True:
        norm = 'all'
    elif normalize in ('all', 'index', 'columns'):
        norm = normalize

    # Build the crosstab
    if values_col is None:
        ct = pd.crosstab(index=index_arg, columns=columns_arg, normalize=norm)
    else:
        if aggfunc == 'concat':
            ct = pd.crosstab(
                index=index_arg,
                columns=columns_arg,
                values=data[values_col],
                aggfunc=lambda x: ', '.join(sorted(set(str(v) for v in x if pd.notna(v) and v != '')))
            )
        else:
            ct = pd.crosstab(
                index=index_arg,
                columns=columns_arg,
                values=data[values_col],
                aggfunc=aggfunc,
                normalize=norm
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

    # Format options
    percent_format = "{:.1%}"
    int_format = "{:,.0f}"

    # Data formatting
    data_records = ct_flat.to_dict("records")


    table = html.Div(
        [
            html.H4(
                title,
                style={
                    "textAlign": "center",
                    "marginBottom": "15px",
                    "marginTop": "10px",
                },
            ),
            html.Div(
                dash_table.DataTable(
                    id="crosstab-table",
                    columns=dash_columns,
                    data=data_records,
                    merge_duplicate_headers=True,

                    style_header={
                        "backgroundColor": "rgb(120,120,120)",
                        "color": "white",
                        "fontWeight": "bold",
                        "textAlign": "center",
                        "fontSize": "16px",
                        "height": "40px",
                        "lineHeight": "40px",
                        "whiteSpace": "normal",
                    },

                    style_cell={
                        "padding": "6px",
                        "textAlign": "center",
                        "fontSize": "14px",
                        "whiteSpace": "normal",
                    },

                    style_table={
                        "overflowX": "auto",
                        "marginTop": "10px",
                    },

                    page_size=20,
                )
            ),
        ],
        style={"width": "100%"},
    )

    return table

# LINELISTS
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
    'join': agg_join # join strings
}

def create_line_list(
    title: str,
    df: pd.DataFrame,
    unique_col: Union[str, List[str]] = PERSON_ID_,
    rename: Optional[dict] = None,
    cols_order: Optional[List[str]] = None,
    merge_methods: Optional[List[str]] = None,
    message = None,
    **kwargs
) -> pd.DataFrame:
    """
    Creates a line list by aggregating data with consistent deduplication.
    """
    ops = {
        "==": operator.eq, "!=": operator.ne, ">": operator.gt, "<": operator.lt,
        ">=": operator.ge, "<=": operator.le
    }
    DEFAULT_MERGE = 'inner'
    
    unique_col_list = [unique_col] if isinstance(unique_col, str) else unique_col
    if not unique_col_list:
        raise ValueError("unique_col must specify at least one column.")
    
    df_base = df.copy()
    
    group_dfs = []
    
    for i in range(1, 11):
        group_cols = kwargs.get(f"group_cols{i}", []) or []
        group_filters = kwargs.get(f"group{i}_filters", {}) or {}
        group_aggr = kwargs.get(f"group{i}_aggr", {}) or {} 
        
        if not group_cols:
            continue
            
        aggr_cols_needed = list(group_aggr.keys())
        all_required_cols = list(set(group_cols + unique_col_list + aggr_cols_needed))
        
        df_group_filtered = df_base.copy()
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
        
        df_group_filtered = df_group_filtered[filter_mask].copy()
        
        if df_group_filtered.empty:
            continue
        
        missing_output_cols = [c for c in all_required_cols if c not in df_group_filtered.columns]
        if missing_output_cols:
            print(f"Warning: Group {i} skipped. Required columns not found: {missing_output_cols}")
            continue
        
        # Apply deduplication by unique_col and DATE_
        if DATE_ in df_group_filtered.columns:
            df_group_filtered = df_group_filtered.drop_duplicates(subset=unique_col_list + [DATE_])
        
        df_group = df_group_filtered[all_required_cols].copy()
        
        count_col_name = f'unique_count_{i}'
        
        # Calculate unique count per group
        df_group[count_col_name] = (
            df_group.groupby(group_cols)[unique_col_list].transform("nunique").sum(axis=1)
        )
        
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
        
        group_dfs.append(df_group)
    
    if not group_dfs:
        return html.Div(f"No data available for {title}")
    
    merge_methods_list = merge_methods or []
    final_df = group_dfs[0]
    
    for idx, right_df in enumerate(group_dfs[1:]):
        try:
            merge_how = merge_methods_list[idx] if idx < len(merge_methods_list) else DEFAULT_MERGE
            final_df = pd.merge(
                final_df, 
                right_df, 
                on=unique_col_list,
                how=merge_how
            )
        except ValueError as e:
            print(f"Error during merge between group {idx+1} and group {idx+2} using method '{merge_how}'. Details: {e}")
            raise
    
    if cols_order and isinstance(cols_order, list):
        final_df = final_df[[c for c in cols_order if c in final_df.columns]]
    elif isinstance(cols_order, str):
        raise ValueError("cols_order must be a list.")
    
    if rename:
        final_df = final_df.rename(columns=rename)
    
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

def create_age_gender_histogram(
    df, age_col, gender_col, title, xtitle, ytitle, bin_size,
    filter_col1=None, filter_value1=None,
    filter_col2=None, filter_value2=None,
    filter_col3=None, filter_value3=None,
    aggregation='count'
):
    """
    Create an age–gender histogram with labeled bins and data labels.
    """
    data = df.copy()
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)
    
    # Apply consistent deduplication
    data = _prepare_data_for_visualization(data, PERSON_ID_)
    
    # if data.empty:
    #     return go.Figure().update_layout(title=f"No data available for {title}")
    
    # Remove any rows with missing age or gender
    data = data.dropna(subset=[age_col, gender_col])
    
    if data.empty:
        return go.Figure().update_layout(title=f"{title}")
    
    min_age = int(data[age_col].min())
    max_age = int(data[age_col].max())
    
    # Create bins
    bin_size = int(bin_size)
    bins = list(range(min_age, max_age + bin_size, bin_size))
    
    labels = [
        f"{bins[i]}-{bins[i+1]-1}" if i < len(bins)-2 else f"{bins[i]}+"
        for i in range(len(bins) - 1)
    ]
    
    data = data.copy()
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
        title=title,
        text_auto=True,
        color_discrete_sequence=px.colors.qualitative.Dark2,
        category_orders={"age_bin": labels}
    )
    
    fig.update_layout(
        xaxis_title=xtitle,
        yaxis_title=ytitle,
        bargap=0.15
    )
    
    fig.update_traces(
        textposition="outside",
        cliponaxis=False
    )
    
    return fig

def create_horizontal_bar_chart(df, label_col, value_col, title, x_title, y_title, top_n=10,
                                 filter_col1=None, filter_value1=None, filter_col2=None, filter_value2=None,
                                 filter_col3=None, filter_value3=None, aggregation='count'):
    """
    Create a horizontal bar chart showing the top N items by value.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)
    
    # Apply consistent deduplication
    data = _prepare_data_for_visualization(data, PERSON_ID_)
    
    # if data.empty:
    #     return go.Figure().update_layout(title=f"No data available for {title}")
    
    if aggregation == 'count':
        df_grouped = data.groupby(label_col)[value_col].nunique().reset_index()
    elif aggregation == 'nunique':
        df_grouped = data.groupby(label_col)[value_col].nunique().reset_index()
    else:
        df_grouped = data.groupby(label_col)[value_col].agg(aggregation).reset_index()
    
    df_grouped.columns = [label_col, 'value']
    df_grouped = df_grouped[df_grouped['value'] > 0]
    df_top = df_grouped.sort_values(by='value', ascending=False).head(int(top_n))
    
    if df_top.empty:
        return go.Figure().update_layout(title=f"No data available for {title}")
    
    fig = px.bar(
        df_top,
        x='value',
        y=label_col,
        text='value',
        orientation='h',
        title=title
    )
    
    fig.update_traces(
        textposition='auto',
        texttemplate='%{text}',
        marker_color='steelblue'
    )
    
    fig.update_layout(
        xaxis_title=x_title,
        yaxis_title=y_title,
        yaxis=dict(autorange='reversed')
    )
    
    return fig

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
            value=flow_data[value_col]
        )
    )])
    
    fig.update_layout(
        title=title,
        font_size=12,
        template="plotly_white"
    )
    
    return fig

def create_heatmap(df, x_col, y_col, values_col, title, x_title, y_title,
                   unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
                   filter_col2=None, filter_value2=None, aggregation='count'):
    """
    Create a heatmap for correlation or density visualization.
    Useful for: Time-of-day vs day-of-week patterns, diagnosis by age group, etc.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Create pivot for heatmap
    pivot_data = data.pivot_table(
        index=y_col, 
        columns=x_col, 
        values=values_col,
        aggfunc=aggregation,
        fill_value=0
    )
    
    fig = px.imshow(
        pivot_data,
        title=title,
        labels=dict(x=x_title, y=y_title, color="Count"),
        aspect="auto",
        color_continuous_scale="Viridis"
    )
    
    fig.update_layout(
        xaxis_title=x_title,
        yaxis_title=y_title,
        template="plotly_white"
    )
    
    return fig

def create_stacked_area_chart(df, date_col, y_col, color_col, title, x_title, y_title,
                              unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
                              filter_col2=None, filter_value2=None, aggregation='count'):
    """
    Create a stacked area chart for cumulative trends over time.
    Useful for: Program enrollment over time, disease burden trends, etc.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Ensure date column is datetime
    data[date_col] = pd.to_datetime(data[date_col])
    
    # Group by date and color column
    summary = data.groupby([date_col, color_col])[y_col].agg(aggregation).reset_index()
    
    fig = px.area(
        summary,
        x=date_col,
        y=y_col,
        color=color_col,
        title=title,
        line_group=color_col,
        color_discrete_sequence=px.colors.qualitative.Dark2
    )
    
    fig.update_layout(
        xaxis_title=x_title,
        yaxis_title=y_title,
        template="plotly_white",
        hovermode='x unified'
    )
    
    return fig

def create_box_plot(df, x_col, y_col, title, x_title, y_title,
                    unique_column=PERSON_ID_, color=None,
                    filter_col1=None, filter_value1=None,
                    filter_col2=None, filter_value2=None):
    """
    Create a box plot showing distribution of numerical values.
    Useful for: Age distribution by diagnosis, lab value ranges, etc.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    fig = px.box(
        data,
        x=x_col,
        y=y_col,
        color=color,
        title=title,
        color_discrete_sequence=px.colors.qualitative.Dark2,
        points="outliers"  # Show only outliers as points
    )
    
    fig.update_layout(
        xaxis_title=x_title,
        yaxis_title=y_title,
        template="plotly_white",
        boxmode='group' if color else 'overlay'
    )
    
    # Add mean markers
    means = data.groupby(x_col)[y_col].mean().reset_index()
    fig.add_scatter(
        x=means[x_col],
        y=means[y_col],
        mode='markers',
        marker=dict(symbol='diamond', size=10, color='red'),
        name='Mean'
    )
    
    return fig

def create_scatter_plot(df, x_col, y_col, title, x_title, y_title,
                        color=None, size=None, trendline=True,
                        unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
                        filter_col2=None, filter_value2=None):
    """
    Create a scatter plot with optional trend line.
    Useful for: Age vs BP correlation, weight vs height, etc.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Deduplicate
    data = data.drop_duplicates(subset=[unique_column, DATE_])
    
    fig = px.scatter(
        data,
        x=x_col,
        y=y_col,
        color=color,
        size=size,
        title=title,
        trendline="ols" if trendline else None,
        color_discrete_sequence=px.colors.qualitative.Dark2
    )
    
    if trendline:
        # Customize trendline
        fig.update_traces(
            line=dict(dash='dash', width=2),
            selector=dict(mode='lines')
        )
    
    fig.update_layout(
        xaxis_title=x_title,
        yaxis_title=y_title,
        template="plotly_white"
    )
    
    return fig

def create_gauge_chart(value, title, min_val=0, max_val=100, 
                       threshold_ranges=None, threshold_colors=None):
    """
    Create a gauge chart for single metric visualization.
    Useful for: Bed occupancy, vaccination coverage, target achievement, etc.
    """
    if threshold_ranges is None:
        threshold_ranges = [(0, 50), (50, 80), (80, 100)]
        threshold_colors = ["red", "yellow", "green"]
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value,
        title={'text': title},
        delta={'reference': max_val * 0.8},  # 80% target
        gauge={
            'axis': {'range': [min_val, max_val]},
            'bar': {'color': "darkblue"},
            'steps': [
                {'range': threshold_ranges[i], 'color': threshold_colors[i]}
                for i in range(len(threshold_ranges))
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': max_val * 0.9  # 90% warning
            }
        }
    ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=50, r=50, t=50, b=50)
    )
    
    return fig

def create_treemap(df, path_cols, values_col, title,
                   unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
                   filter_col2=None, filter_value2=None):
    """
    Create a treemap for hierarchical data visualization.
    Useful for: Program breakdown by location, diagnosis categories, etc.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Deduplicate
    data = data.drop_duplicates(subset=[unique_column, DATE_])
    
    # Aggregate values
    summary = data.groupby(path_cols)[values_col].nunique().reset_index()
    
    fig = px.treemap(
        summary,
        path=path_cols,
        values=values_col,
        title=title,
        color=values_col,
        color_continuous_scale='Blues'
    )
    
    fig.update_layout(
        template="plotly_white"
    )
    
    fig.update_traces(
        hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Parent: %{parent}"
    )
    
    return fig

def create_sunburst_chart(df, path_cols, values_col, title,
                          unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
                          filter_col2=None, filter_value2=None):
    """
    Create a sunburst chart for radial hierarchical visualization.
    Useful for: Multi-level program enrollment, diagnosis categories, etc.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Deduplicate
    data = data.drop_duplicates(subset=[unique_column, DATE_])
    
    # Aggregate values
    summary = data.groupby(path_cols)[values_col].nunique().reset_index()
    
    fig = px.sunburst(
        summary,
        path=path_cols,
        values=values_col,
        title=title,
        color=values_col,
        color_continuous_scale='RdBu'
    )
    
    fig.update_layout(
        template="plotly_white"
    )
    
    return fig

def create_funnel_chart(df, stages_col, values_col, title,
                        unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
                        filter_col2=None, filter_value2=None):
    """
    Create a funnel chart for tracking progression through stages.
    Useful for: Patient journey (Screening → Diagnosis → Treatment → Outcome)
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Calculate counts per stage
    funnel_data = data.groupby(stages_col)[values_col].nunique().reset_index()
    funnel_data = funnel_data.sort_values(by=values_col, ascending=False)
    
    fig = go.Figure(go.Funnel(
        y=funnel_data[stages_col],
        x=funnel_data[values_col],
        textinfo="value+percent previous+percent total",
        marker=dict(color=["#006401", "#2E8B57", "#3CB371", "#90EE90"]),
        connector=dict(line=dict(color="royalblue", dash="dot", width=3))
    ))
    
    fig.update_layout(
        title=title,
        template="plotly_white"
    )
    
    return fig

def create_radar_chart(df, categories_col, values_col, group_col, title,
                       unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
                       filter_col2=None, filter_value2=None):
    """
    Create a radar chart for comparing multiple dimensions.
    Useful for: Program performance metrics, patient health indicators, etc.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Aggregate by group and category
    summary = data.groupby([group_col, categories_col])[values_col].mean().reset_index()
    
    fig = go.Figure()
    
    for group in summary[group_col].unique():
        group_data = summary[summary[group_col] == group]
        fig.add_trace(go.Scatterpolar(
            r=group_data[values_col],
            theta=group_data[categories_col],
            fill='toself',
            name=group
        ))
    
    fig.update_layout(
        title=title,
        polar=dict(radialaxis=dict(visible=True, range=[0, summary[values_col].max()])),
        template="plotly_white",
        showlegend=True
    )
    
    return fig

def create_waterfall_chart(df, stages_col, values_col, title,
                          unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
                          filter_col2=None, filter_value2=None):
    """
    Create a waterfall chart showing cumulative effect of sequential steps.
    Useful for: Patient attrition, stock management, financial tracking.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Calculate stage-wise values
    stage_values = data.groupby(stages_col)[values_col].sum().reset_index()
    
    fig = go.Figure(go.Waterfall(
        name=title,
        orientation="v",
        measure=["relative"] * len(stage_values),
        x=stage_values[stages_col],
        y=stage_values[values_col],
        textposition="outside",
        text=stage_values[values_col],
        connector={"line": {"color": "rgb(63, 63, 63)"}},
    ))
    
    fig.update_layout(
        title=title,
        template="plotly_white",
        showlegend=False
    )
    
    return fig

def create_bubble_chart(df, x_col, y_col, size_col, color_col, title,
                       x_title, y_title, unique_column=PERSON_ID_,
                       filter_col1=None, filter_value1=None,
                       filter_col2=None, filter_value2=None):
    """
    Create a bubble chart with three dimensions of data.
    Useful for: Program comparison (enrollment, outcomes, cost), etc.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Deduplicate and aggregate
    summary = data.groupby([color_col, x_col, y_col])[size_col].nunique().reset_index()
    
    fig = px.scatter(
        summary,
        x=x_col,
        y=y_col,
        size=size_col,
        color=color_col,
        title=title,
        hover_name=color_col,
        size_max=60,
        color_discrete_sequence=px.colors.qualitative.Dark2
    )
    
    fig.update_layout(
        xaxis_title=x_title,
        yaxis_title=y_title,
        template="plotly_white"
    )
    
    return fig

def create_timeline_chart(df, task_col, start_col, end_col, color_col, title,
                          unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
                          filter_col2=None, filter_value2=None):
    """
    Create a Gantt chart for timeline visualization.
    Useful for: Patient stay duration, treatment timelines, etc.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Ensure dates are datetime
    data[start_col] = pd.to_datetime(data[start_col])
    data[end_col] = pd.to_datetime(data[end_col])
    
    fig = px.timeline(
        data,
        x_start=start_col,
        x_end=end_col,
        y=task_col,
        color=color_col,
        title=title,
        color_discrete_sequence=px.colors.qualitative.Dark2
    )
    
    fig.update_layout(
        xaxis_title="Timeline",
        yaxis_title="Task/Patient",
        template="plotly_white"
    )
    
    return fig

def create_3d_scatter(df, x_col, y_col, z_col, color_col, title,
                      unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
                      filter_col2=None, filter_value2=None):
    """
    Create a 3D scatter plot for multidimensional analysis.
    Useful for: Age, BP, BMI correlation; lab value clusters, etc.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Deduplicate
    data = data.drop_duplicates(subset=[unique_column, DATE_])
    
    fig = px.scatter_3d(
        data,
        x=x_col,
        y=y_col,
        z=z_col,
        color=color_col,
        title=title,
        opacity=0.7,
        color_discrete_sequence=px.colors.qualitative.Dark2
    )
    
    fig.update_layout(
        scene=dict(
            xaxis_title=x_col,
            yaxis_title=y_col,
            zaxis_title=z_col
        ),
        template="plotly_white"
    )
    
    return fig

def create_violin_plot(df, x_col, y_col, title, x_title, y_title,
                       color=None, box=True, points=False,
                       unique_column=PERSON_ID_, filter_col1=None, filter_value1=None,
                       filter_col2=None, filter_value2=None):
    """
    Create a violin plot showing distribution density.
    Useful for: Comparing distributions across categories.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    fig = px.violin(
        data,
        x=x_col,
        y=y_col,
        color=color,
        box=box,
        points=points,
        title=title,
        color_discrete_sequence=px.colors.qualitative.Dark2,
        violinmode='group' if color else 'overlay'
    )
    
    fig.update_layout(
        xaxis_title=x_title,
        yaxis_title=y_title,
        template="plotly_white"
    )
    
    return fig

def create_choropleth_map(df, location_col, values_col, title,
                          locations_dict=None, unique_column=PERSON_ID_,
                          filter_col1=None, filter_value1=None,
                          filter_col2=None, filter_value2=None):
    """
    Create a choropleth map for geographic data visualization.
    Useful for: Disease prevalence by region, facility coverage, etc.
    """
    data = df
    
    # Apply filters
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    
    # Aggregate by location
    summary = data.groupby(location_col)[values_col].nunique().reset_index()
    
    # If no custom locations dict, assume coordinates are in data
    if locations_dict and 'lat' in locations_dict and 'lon' in locations_dict:
        # Use scatter mapbox for point data
        fig = px.scatter_mapbox(
            summary,
            lat=locations_dict['lat'],
            lon=locations_dict['lon'],
            size=values_col,
            color=values_col,
            hover_name=location_col,
            title=title,
            mapbox_style="carto-positron",
            zoom=8,
            color_continuous_scale="Viridis"
        )
    else:
        # Use density mapbox for heatmap
        fig = px.density_mapbox(
            summary,
            lat=locations_dict.get('lat') if locations_dict else None,
            lon=locations_dict.get('lon') if locations_dict else None,
            z=values_col,
            radius=20,
            title=title,
            mapbox_style="carto-positron",
            zoom=8
        )
    
    fig.update_layout(
        template="plotly_white"
    )
    
    return fig

def create_bullet_chart(actual, target, title, ranges=None, 
                        range_colors=None, measure_name="Current"):
    """
    Create a bullet chart for performance against targets.
    Useful for: KPIs, program targets, etc.
    """
    if ranges is None:
        ranges = [target * 0.7, target * 0.9, target]
        range_colors = ["red", "yellow", "green"]
    
    fig = go.Figure(go.Indicator(
        mode="number+gauge+delta",
        value=actual,
        delta={'reference': target},
        title={'text': title},
        gauge={
            'shape': "bullet",
            'axis': {'range': [0, target * 1.2]},
            'bar': {'color': "darkblue"},
            'steps': [
                {'range': [0, ranges[0]], 'color': range_colors[0]},
                {'range': [ranges[0], ranges[1]], 'color': range_colors[1]},
                {'range': [ranges[1], ranges[2]], 'color': range_colors[2]}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 2},
                'thickness': 0.75,
                'value': target
            }
        }
    ))
    
    fig.update_layout(
        height=200,
        margin=dict(l=50, r=50, t=50, b=50)
    )
    
    return fig
