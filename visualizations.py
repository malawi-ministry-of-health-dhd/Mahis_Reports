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

from config import PERSON_ID_, ENCOUNTER_ID_, DATE_

"""
MAIN USE CASE OF THIS FILE IS TO PROVIDE VISUALIZATION FUNCTIONS FOR PATIENT DATA

"""

def _apply_filter(data, filter_col, filter_value):
    """
    Apply filtering with full support for:
    
    - Single-column filters:
        filter_col="col", filter_value=">10"
        filter_col="col", filter_value=["Male", "!=Female", ">20"]

    - Multi-column paired filters:
        filter_col=["concept_name", "Value"],
        filter_value=["Systolic BP", ">140"]

    Rules:
    - If filter_col is list → filter_value MUST be list of same length.
      AND logic applied across column-value pairs.
      
    - If filter_col is str and filter_value is list → apply AND logic on same column.
    
    - Operators supported: =, != , < , <= , > , >=
    """

    if filter_col is None or filter_value is None:
        return data
    
    if "|" in filter_value:
        filter_value = [x.strip() for x in filter_value.split("|")]

    df = data.copy()

    if isinstance(filter_col, list):

        if not isinstance(filter_value, list):
            raise ValueError("If filter_col is list, filter_value must also be list.")

        if len(filter_col) != len(filter_value):
            raise ValueError("filter_col and filter_value lists must match in length.")

        # Apply each (column, value) pair using AND logic
        for col, val in zip(filter_col, filter_value):
            df = _apply_filter(df, col, val)

        return df

    if isinstance(filter_value, list):
        return df[df[filter_col].isin(filter_value)]

    if isinstance(filter_value, str):
        match = re.match(r'^([=!<>]*=?)(.*)$', filter_value.strip())
        if match:
            operator, value_str = match.groups()
            operator = operator.strip()
            value_str = value_str.strip()

            valid_ops = ["=", "!=", "<", "<=", ">", ">="]

            if operator in valid_ops:
                try:
                    if "." in value_str:
                        value = float(value_str)
                    else:
                        value = int(value_str)
                except:
                    value = value_str

                # Apply operator logic
                if operator == "=":
                    return df[df[filter_col] == value]
                elif operator == "!=":
                    # should also filter out corresponding persons
                    persons = df[df[filter_col] == value][PERSON_ID_].to_list()
                    return df[~df[PERSON_ID_].isin(persons)]
                elif operator == "<":
                    return df[df[filter_col] < value]
                elif operator == "<=":
                    return df[df[filter_col] <= value]
                elif operator == ">":
                    return df[df[filter_col] > value]
                elif operator == ">=":
                    return df[df[filter_col] >= value]
        return df[df[filter_col] == filter_value]

    return df[df[filter_col] == filter_value]

def create_column_chart(df, x_col, y_col, title, x_title, y_title,
                        unique_column=PERSON_ID_, legend_title=None,
                        color=None, filter_col1=None, filter_value1=None,
                        filter_col2=None, filter_value2=None,
                        filter_col3=None, filter_value3=None,aggregation='count'):
    """
    Create a column chart using Plotly Express with legend support.
    Labels will display both count and percentage, e.g. "10 (25.1%)".
    """
    data = df
    
    # Apply filters using the new helper function
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)

    
    # data = data.drop_duplicates(subset=[unique_column, DATE_])

    if color:
        # Group by both x_col and color column
        summary = data.groupby([x_col, color])[y_col].nunique().reset_index()
        total = summary[y_col].sum()
        # summary["label"] = summary[y_col].astype(str) + "(" + (summary[y_col]/total*100).round(1).astype(str) + "%)"
        summary['label'] = summary[y_col].astype(str)
        
        fig = px.bar(
            summary, 
            x=x_col, 
            y=y_col, 
            color=color,
            title=title, 
            text="label",
            color_discrete_sequence=px.colors.qualitative.Dark2,
            barmode='group'
        )
    else:
        # Group only by x_col
        summary = data.groupby(x_col)[y_col].agg(aggregation).reset_index()
        summary = summary.sort_values(by=y_col, ascending=False)
        total = summary[y_col].sum()
        # summary["label"] = summary[y_col].astype(str) + "(" + (summary[y_col]/total*100).round(1).astype(str) + "%)"
        summary['label'] = summary[y_col].astype(str)
        fig = px.bar(summary, x=x_col, y=y_col, title=title, text="label")
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
    
    # Apply filters using the new helper function
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)

    # data = data.drop_duplicates(subset=[unique_column, DATE_])

    # Ensure date column is in datetime format
    if not pd.api.types.is_datetime64_any_dtype(data[date_col]):
        try:
            data[date_col] = pd.to_datetime(data[date_col], errors='coerce')
        except Exception as e:
            raise ValueError(f"Error converting {date_col} to datetime: {e}")

    data = data.copy()
    data[date_col] = pd.to_datetime(data[date_col]).dt.date

    if color:
        summary = data.groupby([date_col, color])[y_col].agg(aggregation).reset_index(name='count')
    else:
        summary = data.groupby(date_col)[y_col].agg(aggregation).reset_index(name='count')

    fig = px.line(
        summary,
        x=date_col,
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
        xaxis=dict(title=x_title, tickformat='%b %d'),
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
    
    # Apply filters using the new helper function
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)
    
    # data = data.drop_duplicates(subset=[unique_column, DATE_])
    
    df_summary = data.groupby(names_col)[values_col].agg(aggregation).reset_index()
    df_summary.columns = [names_col, values_col]

    colormap = {}

    fig = px.pie(df_summary, 
                 names=names_col, 
                 values=values_col, 
                 title=title, hole=0.5, 
                 color_discrete_map=px.colors.qualitative.Dark2 if colormap is None else colormap
                 )
    
    if colormap:
        categories = df_summary[names_col].tolist()
        colors = [colormap.get(cat, None) for cat in categories]
        fig.update_traces(marker=dict(colors=colors))
    
    fig.update_traces(textposition='inside', 
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
    # Rename columns and replace content (explicit columns=)
    
    # Apply filters using the new helper function
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)

    data = data.drop_duplicates(subset=[unique_column, DATE_])

    # Build pivot
    if aggfunc == 'concat':
        pivot = data.pivot_table(
            index=index_col,
            columns=columns_col,
            values=values_col,
            aggfunc=lambda x: ', '.join(sorted(set(str(v) for v in x if str(v) != ''))),
        ).reset_index()
        value_format = None  # strings → no numeric formatting
    else:
        pivot = data.pivot_table(
            index=index_col,
            columns=columns_col,
            values=values_col,
            aggfunc=aggfunc
        ).reset_index()
        value_format = ",.0f"  # numeric formatting for value columns

    num_index_cols = len(index_col) if isinstance(index_col, (list, tuple)) else 1

    align_list = (['left'] * num_index_cols) + (['center'] * (len(pivot.columns) - num_index_cols))

    if value_format is None:
        format_list = [None] * len(pivot.columns)
    else:
        format_list = ([None] * num_index_cols) + ([value_format] * (len(pivot.columns) - num_index_cols))

    pivot = pivot.rename(columns=rename).replace(replace)
    fig = go.Figure(data=[go.Table(
        header=dict(
            values=["<b>" + col + "</b>" for col in pivot.columns],
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
    Helps defragment the data from openmrs, and reagregate to a Line List
    For each group N:
      - Apply only groupN_filters to the full base dataframe (for filter flexibility).
      - Create df_groupN = group_colsN + [unique_col] + unique_count_N from the filtered data,
        applying custom aggregations defined in groupN_aggr.
    Then merge all df_groupN on unique_col using a specified sequence of join methods.
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
                 print(f"Warning: Filter column '{col}' for group {i} not found in dataframe. Skipping filter.")
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

        df_group = df_group_filtered[all_required_cols].copy()
        
        count_col_name = f'unique_count_{i}'


        df_group[count_col_name] = (
            df_group.groupby(group_cols)[unique_col_list].transform("nunique").sum(axis=1)
        )
        
        # Initiator
        agg_dict = {
            col: AGG_MAP.get(method.lower(), 'first') # Default to 'first' if method is unknown
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
        # print(df_group)
        group_dfs.append(df_group)

    if not group_dfs:
        return pd.DataFrame()

    merge_methods_list = merge_methods or []
    final_df = group_dfs[0]

    for idx, right_df in enumerate(group_dfs[1:]):
        
        try:
            merge_how = merge_methods_list[idx]
        except IndexError:
            merge_how = DEFAULT_MERGE
            
        try:
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
    # sort the final_df by col1
    final_df = final_df.sort_values(by=final_df.columns[0])

    table = html.Div([
        html.H3(title, style={"textAlign":"center"}),
        html.P(message, style={"textAlign":"center", "color":"red"}),
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

    df_unique = data.drop_duplicates(subset=[PERSON_ID_, DATE_])

    if df_unique.empty:
        return go.Figure()

    min_age = int(df_unique[age_col].min())
    max_age = int(df_unique[age_col].max())

    bins = list(range(min_age, max_age + int(bin_size), int(bin_size)))

    labels = [
        f"({bins[i]}–{bins[i+1]})"
        for i in range(len(bins) - 1)
    ]
    df_unique = df_unique.copy()
    df_unique["age_bin"] = pd.cut(
        df_unique[age_col],
        bins=bins,
        labels=labels,
        include_lowest=True,
        right=True
    ).copy()

    fig = px.histogram(
        df_unique,
        x="age_bin",
        color=gender_col,
        barmode="group",
        title=title,
        text_auto=True,
        color_discrete_sequence=px.colors.qualitative.Dark2
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
    
    # Apply filters using the new helper function
    data = _apply_filter(data, filter_col1, filter_value1)
    data = _apply_filter(data, filter_col2, filter_value2)
    data = _apply_filter(data, filter_col3, filter_value3)

    df_unique = data.drop_duplicates(subset=[PERSON_ID_, DATE_])

    df_grouped = df_unique.groupby(label_col)[value_col].agg(aggregation).reset_index()
    df_top = df_grouped.sort_values(by=value_col, ascending=False).head(int(top_n))

    fig = px.bar(df_top,
                 x=value_col,
                 y=label_col,
                 text=value_col,
                 orientation='h',
                 title=title)
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


def create_metric_heatmap(
    df,
    title,
    metrics,
    date_col=DATE_,
    unique_column=PERSON_ID_,
    month_format="%b %Y",
    mode="month_metric",
    category_col="Facility",
):
    """Build a performance heatmap across metric/month or facility/metric dimensions."""
    data = df.copy()
    if data.empty:
        return go.Figure()

    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data = data.dropna(subset=[date_col]).copy()
    data["metric_month"] = data[date_col].dt.to_period("M").dt.to_timestamp()

    rows = []
    for metric in metrics:
        metric_df = data.copy()
        for filter_col, filter_value in metric.get("filters", []):
            metric_df = _apply_filter(metric_df, filter_col, filter_value)

        if metric_df.empty:
            continue

        target = metric.get("target", 80)
        if mode == "facility_metric":
            summary = (
                metric_df.drop_duplicates(subset=[unique_column, date_col])
                .groupby(category_col)[unique_column]
                .nunique()
                .reset_index(name="count")
            )
            summary["progress"] = summary["count"].apply(lambda value: round((value / target) * 100) if target else 0)
            summary["metric"] = metric["label"]
            summary["text"] = summary.apply(
                lambda row: f"{int(row['count'])} ({int(row['progress'])}%)",
                axis=1,
            )
            rows.append(summary[[category_col, "metric", "progress", "text"]])
        else:
            summary = (
                metric_df.drop_duplicates(subset=[unique_column, date_col])
                .groupby("metric_month")[unique_column]
                .nunique()
                .reset_index(name="count")
            )
            summary["progress"] = summary["count"].apply(lambda value: round((value / target) * 100) if target else 0)
            summary["metric"] = metric["label"]
            summary["month_label"] = summary["metric_month"].dt.strftime(month_format)
            summary["text"] = summary.apply(
                lambda row: f"{int(row['count'])} ({int(row['progress'])}%)",
                axis=1,
            )
            rows.append(summary[["month_label", "metric", "progress", "text"]])

    if not rows:
        return go.Figure()

    final_df = pd.concat(rows, ignore_index=True)
    if mode == "facility_metric":
        matrix = final_df.pivot(index=category_col, columns="metric", values="progress").fillna(0)
        text_matrix = final_df.pivot(index=category_col, columns="metric", values="text").fillna("")
        x_values = matrix.columns.tolist()
        y_values = matrix.index.tolist()
        hovertemplate = "<b>%{y}</b><br>Indicator: %{x}<br>Achievement: %{z}%<extra></extra>"
        xaxis_title = "Indicator"
        yaxis_title = category_col
    else:
        month_order = list(dict.fromkeys(final_df["month_label"].tolist()))
        metric_order = [metric["label"] for metric in metrics if metric["label"] in final_df["metric"].unique()]
        matrix = final_df.pivot(index="metric", columns="month_label", values="progress").reindex(index=metric_order, columns=month_order).fillna(0)
        text_matrix = final_df.pivot(index="metric", columns="month_label", values="text").reindex(index=metric_order, columns=month_order).fillna("")
        x_values = matrix.columns.tolist()
        y_values = matrix.index.tolist()
        hovertemplate = "<b>%{y}</b><br>Month: %{x}<br>Achievement: %{z}%<extra></extra>"
        xaxis_title = "Month"
        yaxis_title = "Indicator"

    heatmap = go.Figure(
        data=go.Heatmap(
            x=x_values,
            y=y_values,
            z=matrix.values,
            text=text_matrix.values,
            texttemplate="%{text}",
            textfont={"size": 10},
            colorscale=[
                [0.0, "#D2222D"],
                [0.49, "#FFBF00"],
                [0.5, "#FFBF00"],
                [1.0, "#238823"],
            ],
            zmin=0,
            zmax=max(100, float(final_df["progress"].max())),
            colorbar={"title": "Target %"},
            hovertemplate=hovertemplate,
        )
    )
    heatmap.update_layout(
        title=title,
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        template="plotly_white",
    )
    return heatmap

def create_count(df, unique_column=PERSON_ID_, filter_col1=None, filter_value1=None, filter_col2=None, filter_value2=None, 
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
    
    unique_visits = data.drop_duplicates(subset=[unique_column, DATE_])

    return len(unique_visits[unique_column].dropna().unique())

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
