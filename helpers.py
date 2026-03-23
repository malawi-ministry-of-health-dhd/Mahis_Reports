import dash
from dash import html, dcc
import pandas as pd
from visualizations import (create_column_chart, 
                          create_count,
                          create_pie_chart,
                          create_line_chart,
                          create_age_gender_histogram,
                          create_horizontal_bar_chart,
                          create_pivot_table,create_crosstab_table, create_line_list,
                          create_metric_heatmap)
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
    """Build a single chart based on configuration."""
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
    elif chart_type == "Heatmap":
        figure = create_heatmap_from_config(filtered, filters)
    elif chart_type == "CrossTab":
        figure = create_crosstab_from_config(filtered, filters)
    elif chart_type == "LineList":
        figure = create_linelist_from_config(filtered, item_config, user_role)
    else:
        # Default empty figure for unknown chart types
        figure = create_empty_figure()
    figure = apply_figure_theme(figure, chart_type, theme_name, chart_name=item_config.get("name", ""))
    if chart_type in ["Line","Pie","Column","Bar","Histogram","PivotTable","Heatmap"]:
        graph_style = {"width": "100%"}
        if style == "mnid-graph":
            if chart_type == "Line":
                graph_style["height"] = "320px"
            elif chart_type == "Heatmap":
                graph_style["height"] = "360px"
            elif chart_type in ["Bar", "Column", "Histogram", "PivotTable"]:
                graph_style["height"] = "280px"
            else:
                graph_style["height"] = "240px"
        else:
            graph_style["height"] = "100%"

        return dcc.Graph(
            id=item_config.get("id", f"chart-{chart_type.lower()}"),
            figure=figure,
            className=style,
            style=graph_style,
            config={
                "displaylogo": False,
                "responsive": True,
                "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
            },
        )
    else:
        return figure


def apply_figure_theme(figure, chart_type, theme_name=None, chart_name=""):
    """Apply a scoped figure theme when the parent dashboard requests one."""
    if theme_name != "premium_mch" or not hasattr(figure, "update_layout"):
        return figure

    chart_name_lower = (chart_name or "").lower()

    def _palette_for_chart():
        if any(term in chart_name_lower for term in ["anc", "coverage", "pocus", "gestational", "hiv testing", "family planning", "breastfeeding", "immunisation", "bcg"]):
            return {
                "primary": "#009AD0",
                "secondary": "#5580F4",
                "accent": "#B666D2",
                "fill": "rgba(0,154,208,0.12)",
                "pie": ["#009AD0", "#5580F4", "#B666D2", "#D88DBC", "#FFD6E8"],
            }
        if any(term in chart_name_lower for term in ["performance", "heatmap", "target", "readiness", "quality"]):
            return {
                "primary": "#238823",
                "secondary": "#FFBF00",
                "accent": "#D2222D",
                "fill": "rgba(35,136,35,0.12)",
                "pie": ["#238823", "#FFBF00", "#D2222D", "#009AD0", "#B666D2"],
            }
        if any(term in chart_name_lower for term in ["mortality", "death", "pph", "complication", "hemorrhage"]):
            return {
                "primary": "#D2222D",
                "secondary": "#FF6B73",
                "accent": "#FFD6E8",
                "fill": "rgba(210,34,45,0.12)",
                "pie": ["#D2222D", "#FFBF00", "#238823", "#009AD0", "#B666D2"],
            }
        if any(term in chart_name_lower for term in ["neonatal", "newborn", "baby", "resuscitation", "kmc", "cpap"]):
            return {
                "primary": "#009AD0",
                "secondary": "#7FD6FF",
                "accent": "#5580F4",
                "fill": "rgba(0,154,208,0.12)",
                "pie": ["#009AD0", "#7FD6FF", "#5580F4", "#B666D2", "#D88DBC"],
            }
        if any(term in chart_name_lower for term in ["staff", "facility", "cadre", "referral"]):
            return {
                "primary": "#5580F4",
                "secondary": "#A285D1",
                "accent": "#D88DBC",
                "fill": "rgba(85,128,244,0.12)",
                "pie": ["#5580F4", "#A285D1", "#D88DBC", "#009AD0", "#7FD6FF"],
            }
        return {
            "primary": "#009AD0",
            "secondary": "#5580F4",
            "accent": "#B666D2",
            "fill": "rgba(85,128,244,0.12)",
            "pie": ["#009AD0", "#5580F4", "#B666D2", "#D88DBC", "#FFD6E8"],
        }

    chart_palette = _palette_for_chart()
    # Palette aligned to the light mockup: warm amber, muted red, clinical blue, and soft neutrals.
    palette = ["#b67a16", "#2f5f8f", "#c85b5a", "#6e8b3d", "#8b8578", "#d3cec2"]
    figure.update_layout(
        template="plotly_white",
        autosize=True,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        colorway=palette,
        font=dict(family="Georgia, 'Times New Roman', serif", color="#3f3c37", size=12),
        margin=dict(l=26, r=18, t=24, b=36),
        title=dict(
            x=0.02,
            xanchor="left",
            font=dict(size=16, family="Georgia, 'Times New Roman', serif", color="#2f2b28"),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
            bgcolor="rgba(255,255,255,0.96)",
            bordercolor="#ece7db",
            borderwidth=0,
            font=dict(color="#5d5a53", size=11),
        ),
        hoverlabel=dict(
            bgcolor="#faf8f2",
            bordercolor="#e5dfd1",
            font=dict(color="#2f2b28", family="Georgia, 'Times New Roman', serif"),
        ),
        transition_duration=220,
    )

    if chart_type == "Line":
        figure.update_layout(height=320)
    elif chart_type in ["Bar", "Column", "Histogram"]:
        figure.update_layout(height=280)
    elif chart_type == "Pie":
        figure.update_layout(height=240)
    elif chart_type == "PivotTable":
        figure.update_layout(height=300)
    elif chart_type == "Heatmap":
        figure.update_layout(height=360)

    if hasattr(figure, "update_xaxes"):
        figure.update_xaxes(
            showgrid=False,
            linecolor="#e7e1d4",
            tickfont=dict(color="#7b756b"),
            title_font=dict(color="#4a463f"),
            automargin=True,
        )
    if hasattr(figure, "update_yaxes"):
        figure.update_yaxes(
            gridcolor="#f1ece2",
            zeroline=False,
            tickfont=dict(color="#7b756b"),
            title_font=dict(color="#4a463f"),
            automargin=True,
        )

    if chart_type in ["Column", "Bar", "Histogram"]:
        figure.update_traces(
            marker_color=chart_palette["primary"],
            marker_line_color="#ffffff",
            marker_line_width=1.2,
            opacity=0.92,
            selector=lambda trace: getattr(trace, "type", None) in ["bar", "histogram"],
        )
    elif chart_type == "Line":
        figure.update_traces(
            line=dict(width=2.2, color=chart_palette["primary"]),
            marker=dict(size=6, line=dict(width=1.5, color="#ffffff"), color=chart_palette["primary"]),
            fillcolor=chart_palette["fill"],
            selector=lambda trace: getattr(trace, "type", None) == "scatter",
        )
    elif chart_type == "Pie":
        pie_palette = chart_palette["pie"]
        figure.update_traces(
            hole=0.54,
            marker=dict(colors=pie_palette, line=dict(color="#ffffff", width=2)),
            textfont=dict(color="#5d5a53", family="Georgia, 'Times New Roman', serif"),
            textposition="outside",
            insidetextorientation="horizontal",
            textinfo="percent",
        )
        figure.update_layout(showlegend=True)
    elif chart_type == "PivotTable":
        figure.update_traces(
            header=dict(fill_color="#2f5f8f", font=dict(color="#ffffff", size=12)),
            cells=dict(fill_color="#ffffff", font=dict(color="#3f3c37", size=11)),
            selector=dict(type="table"),
        )
    elif chart_type == "Heatmap":
        figure.update_layout(
            coloraxis_colorbar=dict(
                outlinewidth=0,
                tickfont=dict(color="#5d5a53", size=11),
                title=dict(font=dict(color="#5d5a53", size=11)),
            )
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


def create_heatmap_from_config(filtered, filters):
    """Create a metric heatmap from JSON configuration."""
    title = filters.get("title") or "Performance Heatmap"
    date_col = filters.get("date_col") or "Date"
    unique_column = filters.get("unique_column") or "person_id"
    month_format = filters.get("month_format") or "%b %Y"
    metrics = filters.get("metrics") or []
    mode = filters.get("mode") or "month_metric"
    category_col = filters.get("category_col") or "Facility"

    return create_metric_heatmap(
        filtered,
        title=title,
        metrics=metrics,
        date_col=date_col,
        unique_column=unique_column,
        month_format=month_format,
        mode=mode,
        category_col=category_col,
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
