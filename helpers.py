import dash
from dash import html, dcc
import pandas as pd
from visualizations import (create_column_chart, 
                          create_count,
                          create_pie_chart,
                          create_line_chart,
                          create_age_gender_histogram,
                          create_horizontal_bar_chart,
                          create_pivot_table,create_crosstab_table, create_line_list)
from datetime import datetime
from config import (actual_keys_in_data, 
                    FIRST_NAME_, LAST_NAME_,
                    DATA_FILE_NAME_, 
                    DATE_, PERSON_ID_, ENCOUNTER_ID_,
                    FACILITY_, AGE_GROUP_, AGE_,
                    GENDER_, ENCOUNTER_, PROGRAM_,
                    NEW_REVISIT_, 
                    HOME_DISTRICT_, 
                    TA_, 
                    VILLAGE_, 
                    FACILITY_CODE_,
                    OBS_VALUE_CODED_,
                    CONCEPT_NAME_,
                    VALUE_,
                    VALUE_NUMERIC_,
                    DRUG_NAME_,
                    VALUE_NAME_)

def build_metrics_section(filtered, counts_config):
    """Build metric cards from counts configuration"""
    metrics = []
    
    for count_config in counts_config:
        metric = html.Div(
            html.Div([
                html.H2(
                    create_count_from_config(filtered, count_config["filters"]), 
                    className="metric-value"
                ),
                html.H4(count_config["name"], className="metric-title"),
            ], className="card")
        )
        metrics.append(metric) 
    
    return metrics

def parse_filter_value(filter_val):
        """Convert string representation of list to actual list if needed"""
        if filter_val is None:
            return None
        if isinstance(filter_val, list):
            return filter_val
        if isinstance(filter_val, str) and filter_val.startswith('[') and filter_val.endswith(']'):
            try:
                # Remove brackets and split by comma, then strip quotes and whitespace
                items = filter_val[1:-1].split(',')
                return [item.strip().strip("'\"") for item in items if item.strip()]
            except:
                return filter_val
        return filter_val

def create_count_from_config(df, filters):
    """Create count based on JSON filter configuration"""

    unique_col = filters.get("unique", "")

    # Extract variables and values
    variables = [
        filters.get("variable1", ""),
        filters.get("variable2", ""),
        filters.get("variable3", ""),
        filters.get("variable4", ""),
        filters.get("variable5", ""),
        filters.get("variable6", ""),
        filters.get("variable7", ""),
        filters.get("variable8", ""),
        filters.get("variable9", ""),
        filters.get("variable10", "")
    ]

    values = [
        parse_filter_value(filters.get("value1", "")),
        parse_filter_value(filters.get("value2", "")),
        parse_filter_value(filters.get("value3", "")),
        parse_filter_value(filters.get("value4", "")),
        parse_filter_value(filters.get("value5", "")),
        parse_filter_value(filters.get("value6", "")),
        parse_filter_value(filters.get("value7", "")),
        parse_filter_value(filters.get("value8", "")),
        parse_filter_value(filters.get("value9", "")),
        parse_filter_value(filters.get("value10", ""))
    ]
    active_filters = []
    for var, val in zip(variables, values):
        if var and val:
            active_filters.append((var, val))
    if not active_filters:
        return create_count(df, unique_col)
    
    

    # if active_filters[0][0] != filters.get("variable1"):
    #     return create_count(df, unique_col)  # failsafe
    args = []
    for var, val in active_filters:
        args.extend([var, val])
    return create_count(df, unique_col, *args)

def build_charts_section(filtered, data_opd, delta_days, sections_config):
    """Build chart sections from JSON configuration"""
    sections = []
    
    for section_config in sections_config:
        section = html.Div([
            html.H2(section_config["section_name"], style={'textAlign': 'left', 'color': 'black'}),
            build_section_items(filtered, data_opd, delta_days, section_config["items"])
        ])
        sections.append(section)
    
    return html.Div(sections)

def build_section_items(filtered, data_opd, delta_days, items_config):
    """Build individual chart items within a section"""
    items = []
    
    # Group items into pairs for card-container-2
    for i in range(0, len(items_config), 3):
        pair_items = items_config[i:i+3]
        card_container = html.Div(
            className="card-container-3",
            children=[
                build_single_chart(filtered, data_opd, delta_days, item_config)
                for item_config in pair_items
            ]
        )
        items.append(card_container)
    
    return html.Div(items)

def build_single_chart(filtered, data_opd, delta_days, item_config,user_role=None, style = "card-2", theme_name=None):
    """Build a single chart based on configuration"""
    chart_type = item_config["type"]
    filters = item_config["filters"]
    
    if chart_type == "Line":
        figure = create_line_chart_from_config(data_opd, delta_days, filters)
    elif chart_type == "Pie":
        figure = create_pie_chart_from_config(filtered, filters)
    elif chart_type == "Column":
        figure = create_column_chart_from_config(filtered, filters)
    elif chart_type == "Bar":
        figure = create_bar_chart_from_config(filtered, filters)
    elif chart_type == "Histogram":
        figure = create_histogram_from_config(filtered, filters)
    elif chart_type == "PivotTable":
        figure = create_pivot_table_from_config(filtered, filters)
    elif chart_type == "CrossTab":
        figure = create_crosstab_from_config(filtered, filters)
    elif chart_type == "LineList":
        figure = create_linelist_from_config(filtered, item_config, user_role)
    else:
        # Default empty figure for unknown chart types
        figure = create_empty_figure()
    figure = apply_figure_theme(figure, chart_type, theme_name)
    if chart_type in ["Line","Pie","Column","Bar","Histogram","PivotTable"]:
        return dcc.Graph(
            id=item_config["filters"]["unique"],
            figure=figure,
            className=style
        )
    else:
        return figure


def apply_figure_theme(figure, chart_type, theme_name=None):
    if theme_name != "premium_mch" or not hasattr(figure, "update_layout"):
        return figure

    palette = ["#1976d2", "#22a7b8", "#79c9d5", "#ffb347", "#7f8ea3", "#2f6d8d"]
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        colorway=palette,
        font=dict(family="Segoe UI, Tahoma, sans-serif", color="#16354f", size=13),
        margin=dict(l=28, r=18, t=58, b=28),
        title=dict(
            x=0.02,
            xanchor="left",
            font=dict(size=18, family="Segoe UI, Tahoma, sans-serif", color="#12344d"),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            bgcolor="rgba(255,255,255,0.7)",
            bordercolor="#dde8ee",
            borderwidth=1,
        ),
    )

    if hasattr(figure, "update_xaxes"):
        figure.update_xaxes(
            showgrid=False,
            linecolor="#d8e4ea",
            tickfont=dict(color="#537086"),
            title_font=dict(color="#12344d"),
        )
    if hasattr(figure, "update_yaxes"):
        figure.update_yaxes(
            gridcolor="#e8f0f4",
            zeroline=False,
            tickfont=dict(color="#537086"),
            title_font=dict(color="#12344d"),
        )

    if chart_type in ["Column", "Bar", "Histogram"]:
        figure.update_traces(
            marker_line_color="#ffffff",
            marker_line_width=1.5,
            selector=lambda trace: getattr(trace, "type", None) in ["bar", "histogram"],
        )
    elif chart_type == "Line":
        figure.update_traces(
            line=dict(width=3),
            marker=dict(size=8, line=dict(width=2, color="#ffffff")),
            selector=lambda trace: getattr(trace, "type", None) == "scatter",
        )
    elif chart_type == "Pie":
        figure.update_traces(
            hole=0.58,
            marker=dict(line=dict(color="#ffffff", width=2)),
            textfont=dict(color="#16354f", family="Segoe UI, Tahoma, sans-serif"),
        )
    elif chart_type == "PivotTable":
        figure.update_traces(
            header=dict(fill_color="#0f6b9a", font=dict(color="#ffffff", size=12)),
            cells=dict(fill_color="#ffffff", font=dict(color="#16354f", size=11)),
            selector=dict(type="table"),
        )

    return figure


def create_line_chart_from_config(data_opd, delta_days, filters):
    """
    Create line chart from JSON configuration
    Configs
                "measure": "chart",
                "unique": "any",
                "duration_default": "7days",
                "date_col": "Date",
                "y_col": "encounter_id",
                "title":"Daily OPD Attendance - Last 7 Days",
                "x_title": "Date",
                "y_title": "Number of Patients",
                "unique_column":"person_id",
                "legend_title":"Legend",
                "color":"",
                "filter_col1": "",
                "filter_val1": "",
                "filter_col2": "",
                "filter_val2": "",
                "filter_col3": "",
                "filter_val3": ""
    """
    date_filter = str(datetime.now() - pd.Timedelta(days=delta_days))
    filtered_data = data_opd[data_opd['Date'] >= date_filter]
    
    # keys = list(filters.keys())[3:]
    date_col       = filters.get('date_col')
    y_col          = filters.get('y_col')
    title          = filters.get('title')
    x_title        = filters.get('x_title')
    y_title        = filters.get('y_title')
    unique_column  = filters.get('unique_column')
    legend_title   = filters.get('legend_title') or None
    color          = filters.get('color') or None
    filter_col1    = filters.get('filter_col1') or None
    filter_val1    = parse_filter_value(filters.get('filter_val1'))
    filter_col2    = filters.get('filter_col2') or None
    filter_val2    = parse_filter_value(filters.get('filter_val2'))
    filter_col3    = filters.get('filter_col3') or None
    filter_val3    = parse_filter_value(filters.get('filter_val3'))
    aggregation   = filters.get('measure') or 'count'

    return create_line_chart(filtered_data, date_col, y_col, title, x_title, y_title, unique_column, legend_title, color, filter_col1, filter_val1, filter_col2, filter_val2, filter_col3, filter_val3,aggregation)

def create_pie_chart_from_config(filtered, filters):
    """
    Create pie chart from JSON configuration
    Configs:
                "measure": "chart",
                "unique": "any",
                "duration_default": "any",
                "names_col": "new_revisit",
                "values_col": "encounter_id",
                "title":"Patient Visit Type",
                "unique_column": "person_id",
                "filter_col1": "",
                "filter_val1": "",
                "filter_col2": "",
                "filter_val2": "",
                "filter_col3": "",
                "filter_val3": "",
                "colormap": {
                                "New": "#292D79",
                                "Revisit": "#FE1AD0"
                            }
                }
    """

    names_col       = filters.get('names_col')
    values_col      = filters.get('values_col')
    title           = filters.get('title')
    unique_column   = filters.get('unique_column')
    filter_col1    = filters.get('filter_col1') or None
    filter_val1    = parse_filter_value(filters.get('filter_val1'))
    filter_col2    = filters.get('filter_col2') or None
    filter_val2    = parse_filter_value(filters.get('filter_val2'))
    filter_col3    = filters.get('filter_col3') or None
    filter_val3    = parse_filter_value(filters.get('filter_val3'))
    colormap        = filters.get('colormap') or None
    aggregation   = filters.get('measure') or 'count'
    
    return create_pie_chart(filtered, names_col, values_col, title, unique_column, filter_col1, filter_val1, filter_col2, filter_val2, filter_col3, filter_val3, colormap, aggregation)

def create_column_chart_from_config(filtered, filters):
    """
    Create column chart from JSON configuration
    Config:
                "measure": "chart",
                "unique": "any",
                "duration_default": "any",
                "x_col": "Program",
                "y_col": "encounter_id",
                "title":"Enrollment Type",
                "x_title": "Program",
                "y_title": "Number of Patients",
                "unique_column":"person_id",
                "legend_title":"Legend",
                "color":"",
                "filter_col1": "",
                "filter_val1": "",
                "filter_col2": "",
                "filter_val2": "",
                "filter_col3": "",
                "filter_val3": ""
    """
    
    x_col          = filters.get('x_col')
    y_col          = filters.get('y_col')
    title          = filters.get('title')
    x_title        = filters.get('x_title')
    y_title        = filters.get('y_title')
    unique_column  = filters.get('unique_column')
    legend_title   = filters.get('legend_title') or None
    color          = filters.get('color') or None
    filter_col1    = filters.get('filter_col1') or None
    filter_val1    = parse_filter_value(filters.get('filter_val1'))
    filter_col2    = filters.get('filter_col2') or None
    filter_val2    = parse_filter_value(filters.get('filter_val2'))
    filter_col3    = filters.get('filter_col3') or None
    filter_val3    = parse_filter_value(filters.get('filter_val3'))
    aggregation   = filters.get('measure') or 'count'

    return create_column_chart(filtered, x_col, y_col, title, x_title, y_title, unique_column, legend_title, color, filter_col1, filter_val1, filter_col2, filter_val2, filter_col3, filter_val3, aggregation)

def create_bar_chart_from_config(filtered, filters):
    """
    Create column chart from JSON configuration
    Config: 
                "measure": "chart",
                "unique": "any",
                "duration_default": "any",
                "label_col": "DrugName",
                "value_col": "Program",
                "title": "Medications dispensed",
                "x_title": "",
                "y_title": "",
                "top_n":10,
                "filter_col1": "Encounter",
                "filter_val1": "DISPENSING",
                "filter_col2": "",
                "filter_val2": "",
                "filter_col3": "",
                "filter_val3": ""
    """
    label_col     = filters.get("label_col")
    value_col     = filters.get("value_col")
    title         = filters.get("title")
    x_title       = filters.get("x_title")
    y_title       = filters.get("y_title")
    top_n         = filters.get("top_n") or 10
    filter_col1    = filters.get('filter_col1') or None
    filter_val1    = parse_filter_value(filters.get('filter_val1'))
    filter_col2    = filters.get('filter_col2') or None
    filter_val2    = parse_filter_value(filters.get('filter_val2'))
    filter_col3    = filters.get('filter_col3') or None
    filter_val3    = parse_filter_value(filters.get('filter_val3'))
    aggregation   = filters.get('measure') or 'count'

    return create_horizontal_bar_chart(
        filtered, label_col, value_col, title, x_title, y_title, top_n,
        filter_col1, filter_val1, filter_col2, filter_val2, filter_col3, filter_val3, aggregation
    )

def create_histogram_from_config(filtered, filters):
    """
    Create column chart from JSON configuration
    Config: 
                "measure": "chart",
                "unique": "any",
                "duration_default": "any",
                "age_col": "Age",
                "gender_col": "Gender",
                "title":"Age Gender Disaggregation",
                "x_title": "Program",
                "y_title": "Number of Patients",
                "bin_size": 5,
                "filter_col1": "",
                "filter_val1": "",
                "filter_col2": "",
                "filter_val2": "",
                "filter_col3": "",
                "filter_val3": ""
    """
    age_col       = filters.get("age_col")
    gender_col    = filters.get("gender_col")
    title         = filters.get("title")
    bin_size      = filters.get("bin_size") or 5
    x_title       = filters.get("x_title")
    y_title       = filters.get("y_title")
    filter_col1    = filters.get('filter_col1') or None
    filter_val1    = parse_filter_value(filters.get('filter_val1'))
    filter_col2    = filters.get('filter_col2') or None
    filter_val2    = parse_filter_value(filters.get('filter_val2'))
    filter_col3    = filters.get('filter_col3') or None
    filter_val3    = parse_filter_value(filters.get('filter_val3'))
    aggregation   = filters.get('measure') or 'count'

    # print(f"my bin size {filtered}")

    return create_age_gender_histogram(
        filtered, age_col, gender_col, title, x_title, y_title, bin_size,
        filter_col1, filter_val1, filter_col2, filter_val2, filter_col3, filter_val3,aggregation
    )

def create_pivot_table_from_config(filtered, filters):
    """
    Create pivot table from JSON configuration
    Config:     "measure": "chart",
                "unique": "any",
                "duration_default": "any",
                "index_col1": "DrugName",
                "columns": "Program",
                "values_col":"ValueN",
                "title": "Medications dispensed",
                "unique_column":"person_id",
                "aggfunc":"sum",
                "filter_col1": "Encounter",
                "filter_val1": "DISPENSING",
                "filter_col2": "",
                "filter_val2": "",
                "filter_col3": "",
                "filter_val3": "",
                "x_title": "",
                "y_title": ""
    """
    index_col    = filters.get("index_col1")
    columns       = filters.get("columns")
    values_co    = filters.get("values_col")
    title         = filters.get('title')
    unique_column = filters.get('unique_column')
    aggfunc       = filters.get("aggfunc") or "sum"
    filter_col1    = filters.get('filter_col1') or None
    filter_val1    = parse_filter_value(filters.get('filter_val1'))
    filter_col2    = filters.get('filter_col2') or None
    filter_val2    = parse_filter_value(filters.get('filter_val2'))
    filter_col3    = filters.get('filter_col3') or None
    filter_val3    = parse_filter_value(filters.get('filter_val3'))
    aggregation   = filters.get('measure') or 'count'
    rename        = filters.get("rename") or {}
    replace       = filters.get("replace") or {}

    return create_pivot_table(
        filtered, index_col, columns, values_co, title, unique_column, aggfunc,
        filter_col1, filter_val1, filter_col2, filter_val2, filter_col3, filter_val3, aggregation, rename, replace
    )


def create_crosstab_from_config(filtered, filters):
    """
    Create crosstab table from JSON configuration.

    Example config:
        {
            "measure": "crosstab",
            "title": "Diagnosis × Gender × Age Group",
            "unique_column": "person_id",
            "index_col1": "DIAGNOSIS",                # rows
            "columns": ["Gender", "Age_Group"],       # columns (can be string or list)
            "values_col": null,                       # None → raw counts; or a field to aggregate
            "aggfunc": "count",                       # 'count', 'sum', 'nunique', 'mean', 'concat'
            "normalize": null,                        # null | true | "all" | "index" | "columns"
            "rename": {"obs_value_coded": "DIAGNOSIS"},
            "replace": {"Under Five": "Under5", "Over Five": "Over5"},

            "filter_col1": "concept_name",
            "filter_val1": "Primary diagnosis",
            "filter_col2": null,
            "filter_val2": null,
            "filter_col3": null,
            "filter_val3": null
        }
    """
    # Helper to parse index/columns if they arrive as comma-separated strings
    def _as_list_or_str(v):
        if isinstance(v, str) and ',' in v:
            return [s.strip() for s in v.split(',') if s.strip()]
        return v

    index_col     = _as_list_or_str(filters.get("index_col1") or filters.get("index"))
    columns_col   = _as_list_or_str(filters.get("columns") or filters.get("columns_col"))
    values_col    = filters.get("values_col") or None
    title         = filters.get("title")
    unique_column = filters.get("unique_column") or "person_id"
    aggfunc       = filters.get("aggfunc") or ("count" if values_col is None else "count")
    normalize     = filters.get("normalize")  # None | True | 'all' | 'index' | 'columns'

    # Filters (up to three)
    filter_col1   = filters.get("filter_col1") or None
    filter_val1   = parse_filter_value(filters.get("filter_val1"))
    filter_col2   = filters.get("filter_col2") or None
    filter_val2   = parse_filter_value(filters.get("filter_val2"))
    filter_col3   = filters.get("filter_col3") or None
    filter_val3   = parse_filter_value(filters.get("filter_val3"))

    # Optional rename/replace
    rename        = filters.get("rename") or {}
    replace       = filters.get("replace") or {}

    return create_crosstab_table(
        df=filtered,
        index_col=index_col,
        columns_col=columns_col,
        title=title,
        values_col=values_col,
        aggfunc=aggfunc,
        normalize=normalize,
        unique_column=unique_column,
        filter_col1=filter_col1, filter_value1=filter_val1,
        filter_col2=filter_col2, filter_value2=filter_val2,
        filter_col3=filter_col3, filter_value3=filter_val3,
        rename=rename, replace=replace
    )

def create_linelist_from_config(filtered, filters,user_role=None, **kwargs):
    """
    Convert JSON config into arguments for create_line_list().
    Accepts dynamic group_cols, group_filters, group_aggr, merge methods, rename, cols_order etc.
    """

    def _as_list_or_str(v):
        if isinstance(v, str) and '|' in v:
            return [s.strip() for s in v.split('|') if s.strip()]
        return v

    unique_col     = _as_list_or_str(filters.get("unique_col") or filters.get("unique"))
    cols_order     = _as_list_or_str(filters.get("cols_order") or [])
    merge_methods  = _as_list_or_str(filters.get("merge_methods") or [])
    rename         = filters.get("rename") or {}
    title          = filters.get("report_name")
    authorized_user= filters.get("authorized_user") or "Any"
    message= filters.get("message") or None

    if message:
        message = message + str(authorized_user)

    if authorized_user != "Any":
        if isinstance(authorized_user, list):
            if user_role not in authorized_user:
                if FIRST_NAME_ in filtered.columns:
                    filtered[FIRST_NAME_] = 'fname_xxxx'
                if LAST_NAME_ in filtered.columns:
                    filtered[LAST_NAME_] = 'lname_xxxx'
        elif isinstance(authorized_user, str):
            if user_role != authorized_user:
                if FIRST_NAME_ in filtered.columns:
                    filtered[FIRST_NAME_] = 'fname_xxxx'
                if LAST_NAME_ in filtered.columns:
                    filtered[LAST_NAME_] = 'lname_xxxx'

    group_kwargs = {}

    for i in range(1, 10 + 1):
        # group_colsN
        c = filters.get(f"group_cols{i}")
        if c:
            group_kwargs[f"group_cols{i}"] = c
        # groupN_filters
        gf = filters.get(f"group{i}_filters")
        if gf:
            group_kwargs[f"group{i}_filters"] = gf
        # groupN_aggr
        ga = filters.get(f"group{i}_aggr") or filters.get(f"group{i}_aggregations")
        if ga:
            group_kwargs[f"group{i}_aggr"] = ga
    # Merge any extra **kwargs the user passes
    group_kwargs.update(kwargs)

    return create_line_list(
        df=filtered,
        unique_col=unique_col,
        cols_order=cols_order,
        title=title,
        message = message,
        merge_methods=merge_methods,
        rename=rename,
        **group_kwargs
    )

def create_empty_figure():
    """Create empty figure for unsupported chart types"""
    return {
        'data': [],
        'layout': {
            'title': 'Chart configuration not supported',
            'xaxis': {'visible': False},
            'yaxis': {'visible': False}
        }
    }
