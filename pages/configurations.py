import dash
from dash import html, dcc, dash_table, Input, Output, State, callback, ctx, MATCH, ALL
from dash.exceptions import PreventUpdate
import json
import os
import uuid
import pandas as pd
from datetime import datetime
import base64
import io
from helpers.modal_functions import (validate_excel_file, load_reports_data, save_reports_data, 
                        check_existing_report, get_next_report_id, update_or_create_report,load_excel_file,
                        save_excel_file, update_report_metadata, archive_report, load_preview_data,
                        create_count_item,create_chart_item, create_section,create_chart_fields,validate_dashboard_json,
                        upload_dashboard_json,validate_prog_reports_json,upload_prog_reports_json,CHART_TEMPLATES)

dash.register_page(__name__, path="/reports_config", title="Admin Dashboard")


# Load existing dashboards
path = os.getcwd()
dashboards_json_path = os.path.join(path, 'data','visualizations', 'validated_dashboard.json')

def load_dashboards_from_file():
    try:
        with open(dashboards_json_path, 'r') as f:
            data = json.load(f)
            return data if isinstance(data, list) else [data]
    except (FileNotFoundError, json.JSONDecodeError):
        return []
dashboards_data = load_dashboards_from_file()


def build_reports_table(data, page=1, page_size=10):
    # Filter active reports
    active_reports = [item for item in data if item.get("archived", "False") == "False"]
    

    # Pagination calculations
    total = len(active_reports)
    start = (page - 1) * page_size
    end = start + page_size

    paginated_items = active_reports[start:end]

    # Modern styled header
    table_header = html.Thead(
        html.Tr([
            html.Th("#", className="report-table-header", style={"width": "50px"}),
            html.Th("Report Name", style={"text-align":"left"}),
            html.Th("Creator", style={"text-align":"left"}),
            html.Th("Date Updated", style={"text-align":"left"}),
            html.Th("Report Type", style={"text-align":"left"}),
            html.Th("Page Name", style={"text-align":"left"}),
            html.Th("Actions", style={"text-align":"left"}),
        ])
    )

    # Build rows with modern styling
    start_row_number = (page - 1) * page_size + 1
    table_rows = []
    for idx, item in enumerate(paginated_items):
        row_number = start_row_number + idx
        table_rows.append(
            html.Tr(
                className="report-table-row",
                children=[
                    html.Td(row_number, className="report-table-cell", style={"textAlign": "center", "fontWeight": "500"}),
                    html.Td(item.get("report_name"), className="report-table-cell"),
                    html.Td(item.get("creator"), className="report-table-cell"),
                    html.Td(item.get("date_updated"), className="report-table-cell"),
                    html.Td(item.get("kind","dataset"), className="report-table-cell"),
                    html.Td(item.get("page_name"), className="report-table-cell"),
                    html.Td(
                        className="report-table-actions",
                        style={"gap":"5px"},
                        children=[
                            html.Button(
                                "✏️",
                                id={"type": "edit-btn", "index": item.get("report_id")},
                                className="action-btn edit-btn"
                            ),
                            html.Button(
                                "Archive",
                                id={"type": "archive-btn", "index": item.get("report_id")},
                                className="action-btn archive-btn"
                            ),
                            html.Button(
                                "⬇️",
                                id={"type": "download-btn", "index": item.get("report_id")},
                                className="action-btn download-btn"
                            ),
                        ]
                    ),
                ]
            )
        )

    table_body = html.Tbody(table_rows)

    return html.Div(
        className="reports-table-wrapper",
        children=[
            html.Div(
                className="reports-header",
                children=[
                    html.H2("MaHIS DataSet Reports", className="reports-title"),
                    html.P(
                        "These are HMIS dataset reports. To update, click Edit or upload a report template bearing the same page_name (id)",
                        className="reports-description"
                    ),
                ]
            ),

            # Table Output
            html.Table(
                [table_header, table_body],
                className="reports-table"
            ),

            # Pagination controls
            html.Div(
                className="pagination-controls",
                children=[
                    html.Button(
                        "Previous", 
                        id="prev-page", 
                        n_clicks=0,
                        className="pagination-btn"
                    ),
                    html.Button(
                        "Next", 
                        id="next-page", 
                        n_clicks=0,
                        className="pagination-btn"
                    ),
                    html.Span(
                        f"Page {page} / { (total // page_size) + (1 if total % page_size else 0) }",
                        id="page-label",
                        className="pagination-info"
                    ),
                ]
            ),
        ]
    )


def create_editable_table(df, sheet_name):
    """Create an editable Dash DataTable from DataFrame"""
    columns = [{"name": col, "id": col} for col in df.columns]
    
    # Convert DataFrame to dictionary for DataTable
    data = df.to_dict('records')
    
    return html.Div([
        html.H4(f"Sheet: {sheet_name}", style={'marginBottom': '10px'}),
        dash_table.DataTable(
            id={'type': 'editable-table', 'sheet': sheet_name},
            columns=columns,
            data=data,
            editable=True,
            filter_action="native",
            sort_action="native",
            page_action="native",
            page_current=0,
            page_size=10,
            style_table={'overflowX': 'auto'},
            style_cell={
                'minWidth': '100px', 'width': '150px', 'maxWidth': '300px',
                'overflow': 'hidden',
                'textOverflow': 'ellipsis',
            },
            style_header={
                'backgroundColor': 'rgb(230, 230, 230)',
                'fontWeight': 'bold'
            },
        )
    ], style={'marginBottom': '20px'})


def create_preview_table(df):
    """Create a Dash DataTable for preview with filters"""
    columns = [{"name": col, "id": col} for col in df.columns]
    
    # Convert DataFrame to dictionary for DataTable
    data = df.to_dict('records')
    
    return dash_table.DataTable(
        id="preview-data-table-component",
        columns=columns,
        data=data,
        filter_action="native",
        sort_action="native",
        page_action="native",
        page_current=0,
        page_size=50,
        style_table={'overflowX': 'auto'},
        style_cell={
            'minWidth': '100px', 
            'width': '150px', 
            'maxWidth': '300px',
            'overflow': 'hidden',
            'textOverflow': 'ellipsis',
            'textAlign': 'left'
        },
        style_header={
            'backgroundColor': 'rgb(230, 230, 230)',
            'fontWeight': 'bold',
            'textAlign': 'left'
        },
        style_data={
            'whiteSpace': 'normal',
            'height': 'auto',
        },
        css=[{
            'selector': '.dash-spreadsheet td div',
            'rule': '''
                line-height: 15px;
                max-height: 30px; min-height: 30px; height: 30px;
                display: block;
                overflow-y: hidden;
            '''
        }]
    )

instructions = html.Div(
    className="instructions-container",
    children=[
        html.Div(
            className="instructions-steps",
            children=[
                html.Div(
                    className="step-card",
                    children=[
                        html.Div(className="step-number", children="1"),
                        html.Div(className="step-content", children=[
                            html.H3("Update Excel Template"),
                            html.P("Update an excel template as provided on the menu below. Be sure to fill all worksheets", 
                                   className="step-description")
                        ])
                    ]
                ),
                html.Div(
                    className="step-card",
                    children=[
                        html.Div(className="step-number", children="2"),
                        html.Div(className="step-content", children=[
                            html.H3("Upload & Validate"),
                            html.P("Upload the worksheet. Dry run to check if the values are consistent with requirements",
                                   className="step-description")
                        ])
                    ]
                ),
                html.Div(
                    className="step-card",
                    children=[
                        html.Div(className="step-number", children="3"),
                        html.Div(className="step-content", children=[
                            html.H3("Edit or Archive"),
                            html.P("To edit or archive, click on the item end and edit or review. The edit will open a popup editing tool with worksheets",
                                   className="step-description")
                        ])
                    ]
                ),
            ]
        )
    ]
)
preview_modal = html.Div([
        html.Div([
            html.H3("Preview Data", style={'marginBottom': '20px'}),  
            html.Div(id="preview-data-info", style={'marginBottom': '20px'}),
            # Data table container
            html.Div(id="preview-data-table", style={'maxHeight': '500px', 'overflowY': 'auto', 'marginBottom': '20px'}),
            html.Div([
                html.Button(
                    "Close",
                    id="close-preview-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#6c757d',
                        'color': 'white',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer'
                    }
                ),
            ], style={'textAlign': 'center'})
        ], style={
            'backgroundColor': 'white',
            'padding': '30px',
            'borderRadius': '10px',
            'width': '90%',
            'maxWidth': '1400px',
            'maxHeight': '90vh',
            'overflowY': 'auto',
            'margin': 'auto'
        })
    ], id="preview-popup", style={
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.5)',
        'display': 'none',
        'justifyContent': 'center',
        'alignItems': 'center',
        'zIndex': '1000'
    })
upload_excel_popup_modal = html.Div([
        html.Div([
            html.H3("Upload Template File", style={'marginBottom': '20px'}),
            
            dcc.Upload(
                id='template-file-upload',
                children=html.Div([
                    'Drag and Drop or ',
                    html.A('Select Files')
                ]),
                style={
                    'width': '100%',
                    'height': '60px',
                    'lineHeight': '60px',
                    'borderWidth': '1px',
                    'borderStyle': 'dashed',
                    'borderRadius': '5px',
                    'textAlign': 'center',
                    'marginBottom': '20px'
                },
                multiple=False,
                accept='.xlsx'
            ),
            
            html.Div(id='upload-validation-result', style={'marginBottom': '20px'}),
            html.Div(id='existing-report-warning', style={'marginBottom': '20px'}),
            
            html.Div([
                html.Button(
                    "Dry Run",
                    id="dry-run-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#ffc107',
                        'color': 'black',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer',
                        'marginRight': '10px'
                    }
                ),
                html.Button(
                    "Upload",
                    id="upload-confirm-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#198754',
                        'color': 'white',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer',
                        'marginRight': '10px'
                    },
                    disabled=True
                ),
                html.Button(
                    "Cancel",
                    id="upload-cancel-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#6c757d',
                        'color': 'white',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer'
                    }
                ),
            ], style={'textAlign': 'center'})
        ], style={
            'backgroundColor': 'white',
            'padding': '30px',
            'borderRadius': '10px',
            'width': '500px',
            'margin': 'auto'
        })
    ], id="upload-popup", style={
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.5)',
        'display': 'none',
        'justifyContent': 'center',
        'alignItems': 'center',
        'zIndex': '1000'
    })
upload_dashboard_json_popup_modal = html.Div([
        html.Div([
            html.H3("Upload Json Template", style={'marginBottom': '20px'}),
            
            dcc.Upload(
                id='template-dashboard-file-upload',
                children=html.Div([
                    'Drag and Drop or ',
                    html.A('Select Files')
                ]),
                style={
                    'width': '100%',
                    'height': '60px',
                    'lineHeight': '60px',
                    'borderWidth': '1px',
                    'borderStyle': 'dashed',
                    'borderRadius': '5px',
                    'textAlign': 'center',
                    'marginBottom': '20px'
                },
                multiple=False,
                accept='.json'
            ),
            
            html.Div(id='upload-dashboard-validation-result', style={'marginBottom': '20px'}),
            html.Div(id='existing-dashboard-report-warning', style={'marginBottom': '20px'}),
            
            html.Div([
                html.Button(
                    "Dry Run",
                    id="dry-dashboard-run-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#ffc107',
                        'color': 'black',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer',
                        'marginRight': '10px'
                    }
                ),
                html.Button(
                    "Upload",
                    id="upload-dashboard-confirm-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#198754',
                        'color': 'white',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer',
                        'marginRight': '10px'
                    },
                    disabled=True
                ),
                html.Button(
                    "Cancel",
                    id="upload-dashboard-cancel-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#6c757d',
                        'color': 'white',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer'
                    }
                ),
            ], style={'textAlign': 'center'})
        ], style={
            'backgroundColor': 'white',
            'padding': '30px',
            'borderRadius': '10px',
            'width': '500px',
            'margin': 'auto'
        })
    ], id="upload-dashboard-popup", style={
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.5)',
        'display': 'none',
        'justifyContent': 'center',
        'alignItems': 'center',
        'zIndex': '1000'
    })
upload_prog_reports_json_popup_modal = html.Div([
        html.Div([
            html.H3("Upload Json Template", style={'marginBottom': '20px'}),
            
            dcc.Upload(
                id='template-prog-reports-file-upload',
                children=html.Div([
                    'Drag and Drop or ',
                    html.A('Select Files')
                ]),
                style={
                    'width': '100%',
                    'height': '60px',
                    'lineHeight': '60px',
                    'borderWidth': '1px',
                    'borderStyle': 'dashed',
                    'borderRadius': '5px',
                    'textAlign': 'center',
                    'marginBottom': '20px'
                },
                multiple=False,
                accept='.json'
            ),
            
            html.Div(id='upload-prog-reports-validation-result', style={'marginBottom': '20px'}),
            html.Div(id='existing-prog-reports-report-warning', style={'marginBottom': '20px'}),
            
            html.Div([
                html.Button(
                    "Dry Run",
                    id="dry-prog-reports-run-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#ffc107',
                        'color': 'black',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer',
                        'marginRight': '10px'
                    }
                ),
                html.Button(
                    "Upload",
                    id="upload-prog-reports-confirm-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#198754',
                        'color': 'white',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer',
                        'marginRight': '10px'
                    },
                    disabled=True
                ),
                html.Button(
                    "Cancel",
                    id="upload-prog-reports-cancel-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#6c757d',
                        'color': 'white',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer'
                    }
                ),
            ], style={'textAlign': 'center'})
        ], style={
            'backgroundColor': 'white',
            'padding': '30px',
            'borderRadius': '10px',
            'width': '500px',
            'margin': 'auto'
        })
    ], id="upload-prog-reports-popup", style={
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.5)',
        'display': 'none',
        'justifyContent': 'center',
        'alignItems': 'center',
        'zIndex': '1000'
    })
archive_popup_modal = html.Div([
        html.Div([
            html.H3("Edit Excel File", id="edit-popup-title", style={'marginBottom': '20px'}),
            
            # Tabs for different sheets
            dcc.Tabs(id="sheet-tabs", value=None),
            
            # Tables container
            html.Div(id="sheet-tables-container", style={'maxHeight': '400px', 'overflowY': 'auto', 'marginBottom': '20px'}),
            
            # Action buttons
            html.Div([
                html.Button(
                    "Save Changes",
                    id="save-excel-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#198754',
                        'color': 'white',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer',
                        'marginRight': '10px'
                    }
                ),
                html.Button(
                    "Cancel",
                    id="edit-cancel-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#6c757d',
                        'color': 'white',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer'
                    }
                ),
            ], style={'textAlign': 'center'})
        ], style={
            'backgroundColor': 'white',
            'padding': '30px',
            'borderRadius': '10px',
            'width': '90%',
            'maxWidth': '1200px',
            'maxHeight': '90vh',
            'overflowY': 'auto',
            'margin': 'auto'
        })
    ], id="edit-popup", style={
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.5)',
        'display': 'none',
        'justifyContent': 'center',
        'alignItems': 'center',
        'zIndex': '1000'
    })
archive_confirmation_modal = html.Div([
        html.Div([
            html.H3("Archive Report", style={'marginBottom': '20px'}),
            
            html.Div(id="archive-confirmation-message", style={'marginBottom': '20px', 'fontSize': '16px'}),
            
            html.Div([
                html.Button(
                    "Confirm Archive",
                    id="confirm-archive-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#dc3545',
                        'color': 'white',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer',
                        'marginRight': '10px'
                    }
                ),
                html.Button(
                    "Cancel",
                    id="cancel-archive-btn",
                    n_clicks=0,
                    style={
                        'backgroundColor': '#6c757d',
                        'color': 'white',
                        'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '6px',
                        'cursor': 'pointer'
                    }
                ),
            ], style={'textAlign': 'center'})
        ], style={
            'backgroundColor': 'white',
            'padding': '30px',
            'borderRadius': '10px',
            'width': '500px',
            'margin': 'auto'
        })
    ], id="archive-popup", style={
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.5)',
        'display': 'none',
        'justifyContent': 'center',
        'alignItems': 'center',
        'zIndex': '1000'
    })
reports_table = html.Div(id="reports-table-container")
def generate_dashboard_items_list(dashboard):
    """Generate the HTML for dashboard items list"""
    counts = dashboard.get('visualization_types', {}).get('counts', [])
    sections = dashboard.get('visualization_types', {}).get('charts', {}).get('sections', [])
    
    if not counts and not sections:
        return html.Div(
            className="empty-items",
            children=[
                html.Div(style={"textAlign": "center", "padding": "40px", "color": "#999"}, children=[
                    html.I(className="fas fa-chart-line", style={"fontSize": "48px"}),
                    html.P("No dashboard items yet", style={"marginTop": "16px"}),
                    html.P("Add counts or sections to get started", style={"fontSize": "12px"})
                ])
            ]
        )
    
    items_list = []
    
    # Add counts to the list
    for idx, count in enumerate(counts):
        items_list.append(
            html.Div(
                className="list-item",
                key=f"count-{idx}",
                children=[
                    html.Div(className="list-item-icon", children=[
                        html.I(className="fas fa-calculator")
                    ]),
                    html.Div(className="list-item-content", children=[
                        html.Div(className="list-title", children=count.get("name", f"{idx + 1}"))
                    ]),
                    html.Div(className="list-item-actions", children=[
                        html.Button(
                            "✏️",
                            id={"type": "count-edit", "index": idx},
                            n_clicks=0
                        ),
                        # html.Button(
                        #     "🗑",
                        #     id={"type": "count-delete", "index": idx},
                        #     n_clicks=0
                        # )
                    ])
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "padding": "12px",
                    "marginBottom": "8px",
                    "backgroundColor": "#f8f9fa",
                    "borderRadius": "6px",
                    "border": "1px solid #e9ecef"
                }
            )
        )
    
    # Add sections and their charts to the list
    for section_idx, section in enumerate(sections):
        # Add section header
        items_list.append(
            html.Div(
                className="list-item section-item",
                key=f"section-{section_idx}",
                children=[
                    html.Div(className="list-item-icon", children=[
                        html.I(className="fas fa-folder")
                    ]),
                    html.Div(className="list-item-content", children=[
                        html.Div(className="list-item-name", children=section.get("section_name", f"Section {section_idx + 1}"))
                    ]),
                    html.Div(className="list-item-actions", children=[
                        html.Button(
                            "✏️",
                            id={"type": "section-edit", "index": section_idx},
                            n_clicks=0,
                        ),
                        # html.Button(
                        #     "🗑",
                        #     id={"type": "section-delete", "index": section_idx},
                        #     n_clicks=0,
                        # )
                    ])
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "padding": "12px",
                    "marginBottom": "8px",
                    "backgroundColor": "#e8f4f8",
                    "borderRadius": "6px",
                    "border": "1px solid #cce5f0"
                }
            )
        )
        
        # Add charts within the section
        for chart_idx, chart in enumerate(section.get("items", [])):
            items_list.append(
                html.Div(
                    className="list-item chart-item",
                    key=f"section-{section_idx}-chart-{chart_idx}",
                    children=[
                        html.Div(className="list-item-icon", style={"marginLeft": "24px"}, children=[
                            html.I(className="fas fa-chart-bar")
                        ]),
                        html.Div(className="list-item-content", children=[
                            html.Div(className="list-title", children=chart.get("name", f"Chart {chart_idx + 1}"))
                        ]),
                        html.Div(className="list-item-actions", children=[
                            html.Button(
                                "✏️",
                                id={"type": "chart-edit", "section": section_idx, "chart": chart_idx},
                                n_clicks=0,
                            ),
                            # html.Button(
                            #     "🗑",
                            #     id={"type": "chart-delete", "section": section_idx, "chart": chart_idx},
                            #     n_clicks=0,
                            # )
                        ])
                    ],
                    style={
                        "display": "flex",
                        "alignItems": "center",
                        "padding": "12px",
                        "marginBottom": "8px",
                        "marginLeft": "24px",
                        "backgroundColor": "#ffffff",
                        "borderRadius": "6px",
                        "border": "1px solid #e9ecef"
                    }
                )
            )
    return html.Div(className="list-items", children=items_list)
# FOR DASHBOARDS
def create_edit_modal():
    selected_dashboard_index = 0  # Default index, will be updated by callbacks
    current_dashboard = None
    if dashboards_data and len(dashboards_data) > selected_dashboard_index:
        current_dashboard = dashboards_data[selected_dashboard_index]
    else:
        current_dashboard = {"counts": [], "sections": [], "report_name": "", "report_id": "", "date_created": ""}
    list_items_html = generate_dashboard_items_list(current_dashboard)

    return html.Div([
        # Modal backdrop
        html.Div(
            id="modal-backdrop",
            className="modal-backdrop",
            style={"display": "none"}
        ),
        # Modal content
        html.Div(
            id="modal-content",
            className="modal-content",
            style={"display": "none"},
            children=[
                # Modal Header with Cancel button
                html.Div(
                    className="modal-header",
                    children=[
                        html.H3("Dashboard Configuration", className="modal-title"),
                        html.Button(
                            "×",
                            id="cancel-btn",
                            n_clicks=0,
                            className="modal-close-btn",
                            title="Close"
                        )
                    ]
                ),
                
                # Modal Body
                html.Div(
                    className="modal-body",
                    children=[
                        html.Div(
                            style={
                                "display": "flex",
                                "gap": "24px",
                                "width": "100%"
                            },
                            children=[
                                # Left Column: Dashboard Selection/Creation & Items List
                                html.Div(
                                    className="dashboard-left-panel",
                                    children=[
                                        # Dashboard Selection Card
                                        html.Div(className="dashboard-card", children=[
                                            html.Div(className="dashboard-card-header", children=[
                                                html.H4("Dashboard Setup", className="dashboard-card-title"),
                                            ]),
                                            html.Div(className="dashboard-card-body", children=[
                                                html.Div(className="form-group", children=[
                                                    html.Label("Select Dashboard:", className="form-label"),
                                                    dcc.Dropdown(
                                                        id="dashboard-selector",
                                                        options=[{"label": f"{d.get('report_name', 'Unnamed')}", 
                                                                "value": i} for i, d in enumerate(dashboards_data)] + 
                                                                [{"label": "➕ Create New Dashboard", "value": "new"}],
                                                        value="new" if not dashboards_data else 0,
                                                        className="modern-dropdown",
                                                        clearable=False
                                                    ),
                                                ]),
                                                
                                                html.Div(className="form-group", children=[
                                                    html.Label("Report Name *", className="form-label"),
                                                    dcc.Input(
                                                        id="report-name-input",
                                                        type="text",
                                                        placeholder="Enter report name...",
                                                        className="modern-input"
                                                    ),
                                                ]),
                                                
                                                html.Div(className="form-row", children=[
                                                    html.Div(className="form-group", style={"flex": "1"}, children=[
                                                        html.Label("Report ID:", className="form-label-disabled"),
                                                        dcc.Input(
                                                            id="report-id-input",
                                                            type="text",
                                                            placeholder="auto-generated",
                                                            disabled=True,
                                                            className="modern-input-disabled"
                                                        ),
                                                    ]),
                                                    html.Div(className="form-group", style={"flex": "1"}, children=[
                                                        html.Label("Date Created:", className="form-label-disabled"),
                                                        dcc.Input(
                                                            id="date-created-input",
                                                            type="text",
                                                            disabled=True,
                                                            className="modern-input-disabled"
                                                        ),
                                                    ]),
                                                ]),
                                            ]),
                                        ]),
                                        
                                        # Dashboard Items List
                                        html.Div(className="dashboard-card",style={
                                            "flex": "1",  # Take remaining space
                                            "display": "flex",
                                            "flexDirection": "column",
                                            "minHeight": "0"
                                        }, children=[
                                            html.Div(
                                                id="dashboard-items-container",
                                                className="dashboard-card-body",
                                                children=[
                                                    list_items_html,
                                                ]
                                            )
                                        ]),
                                    ],
                                    style={
                                        "flex": "0.4",
                                        "display": "flex",
                                        "flexDirection": "column",
                                        "gap": "20px",
                                        "minHeight": "0",  # Critical for scrolling
                                        "height": "100%",   # Take full height
                                        "overflow": "hidden"  # Prevent overflow
                                    },
                                ),
                                
                                # Right Column: Metrics & Charts
                                html.Div(
                                    className="dashboard-right-panel",
                                    children=[
                                        # Metrics Section
                                        html.Div(className="dashboard-card", children=[
                                            html.Div(className="dashboard-card-header", children=[
                                                html.Div(className="card-header-flex", children=[
                                                    html.H4("🔢 Metrics", className="dashboard-card-title"),
                                                    html.Button(
                                                        "➕ Add Metric", 
                                                        id="add-count-btn", 
                                                        n_clicks=0, 
                                                        className="btn-primary-modern"
                                                    )
                                                ])
                                            ]),
                                            html.Div(
                                                id="counts-container", 
                                                className="dashboard-card-body",
                                                style={"maxHeight": "300px", "overflowY": "auto"}
                                            ),
                                        ]),
                                        
                                        # Charts & Sections Section
                                        html.Div(className="dashboard-card", children=[
                                            html.Div(className="dashboard-card-header", children=[
                                                html.Div(className="card-header-flex", children=[
                                                    html.H4("📈 Charts & Sections", className="dashboard-card-title"),
                                                    html.Button(
                                                        "➕ Add Section", 
                                                        id="add-section-btn", 
                                                        n_clicks=0, 
                                                        className="btn-primary-modern"
                                                    )
                                                ])
                                            ]),
                                            html.Div(
                                                id="sections-container", 
                                                className="dashboard-card-body",
                                                style={"display": "flex", "overflowY": "auto"}
                                            ),
                                        ]),
                                    ],
                                    style={
                                        "flex": "0.6",
                                        "display": "flex",
                                        "flexDirection": "column",
                                        "gap": "20px"
                                    }
                                )
                            ]
                        )
                    ]
                ),
                
                # Modal Footer with Action Buttons
                html.Div(
                    className="modal-footer",
                    children=[
                        html.Button(
                            "Save Dashboard", 
                            id="save-btn", 
                            n_clicks=0, 
                            className="btn-success-modern"
                        ),
                        html.Button(
                            "Delete Dashboard", 
                            id="delete-btn", 
                            n_clicks=0, 
                            className="btn-danger-modern"
                        ),
                    ]
                ),
                
                # Delete Confirmation Modal
                html.Div(
                    id="delete-confirmation-modal",
                    style={"display": "none"},
                    className="confirmation-modal-overlay",
                    children=[
                        html.Div(className="confirmation-modal", children=[
                            html.Div(className="confirmation-modal-header", children=[
                                html.H4("Confirm Delete"),
                                html.Button("×", id="close-confirmation-btn", className="confirmation-close-btn")
                            ]),
                            html.Div(className="confirmation-modal-body", children=[
                                html.P("Are you sure you want to delete this dashboard?"),
                                html.P("This action cannot be undone.", style={"color": "#dc3545", "fontSize": "14px"})
                            ]),
                            html.Div(className="confirmation-modal-footer", children=[
                                html.Button("Cancel", id="cancel-delete-btn", className="btn-secondary-modern"),
                                html.Button("Delete", id="confirm-delete-btn", className="btn-danger-modern"),
                            ])
                        ])
                    ]
                )
            ]
        )
    ])

layout = html.Div(
    style={
        "display": "flex",
        "height": "100vh",
        "overflow": "hidden",
        "background": "#f8f9fa"
    },
    children=[
        # ---------- LEFT SIDEBAR ----------
        html.Div(
            id="sidebar",
            className="sidebar-modern",
            children=[
                html.Div(
                    className="sidebar-header",
                    children=[
                        html.H3("Configuration", className="sidebar-title"),
                        html.P("Manage Reports & Dashboards", className="sidebar-subtitle")
                    ]
                ),
                
                html.Div(
                    className="sidebar-nav",
                    children=[
                        html.Button(
                            "Data Set Reports List",
                            id="dataset-reports-btn",
                            n_clicks=0,
                            className="nav-btn-modern success"
                        ),
                        html.Button(
                            "Add XLSX-DataSet Report",
                            id="add-from-template-btn",
                            n_clicks=0,
                            className="nav-btn-modern"
                        ),
                        html.Button(
                            "Add Dashboard File (JSON)",
                            id="add-dashboard-temp-btn",
                            n_clicks=0,
                            className="nav-btn-modern"
                        ),
                        html.Button(
                            "Add Prog Report File (JSON)",
                            id="add-prog-report-temp-btn",
                            n_clicks=0,
                            className="nav-btn-modern"
                        ),
                        html.Button(
                            "Add Dashboard (GUI)",
                            id="add-dashboard",
                            n_clicks=0,
                            className="nav-btn-modern"
                        ),
                        html.Button(
                            "Download XLSX Template",
                            id="download-sample",
                            n_clicks=0,
                            className="nav-btn-modern"
                        ),
                        html.Button(
                            "Preview Data",
                            id="preview-data",
                            n_clicks=0,
                            className="nav-btn-modern"
                        ),
                    ]
                ),
                
                html.Div(
                    className="sidebar-footer",
                    children=[
                        html.Div(className="footer-divider"),
                        html.P("MaHIS Admin Panel", className="footer-text"),
                        html.P("Version 1.0", className="footer-version")
                    ]
                )
            ],
        ),
        
        # ---------- MAIN CONTENT ----------
        html.Div(
            id="main-content",
            className="main-content-modern",
            children=[
                # Main Content Area
                html.Div(
                    className="content-area-modern",
                    children=[
                        # Instructions Section
                        instructions,
                        reports_table,
                    ]
                ),
                
                # Modals (kept as is but with modern styling)
                preview_modal,
                upload_excel_popup_modal,
                upload_dashboard_json_popup_modal,
                upload_prog_reports_json_popup_modal,
                archive_popup_modal,
                archive_confirmation_modal,
                create_edit_modal(),

                # Hidden Components
                dcc.Interval(id="refresh-interval", interval=10*60*1000, n_intervals=0),
                # html.Div(id="reports-table-container", style={'display': 'none'}),
                
                # Store components
                dcc.Store(id="reports-current-page", data=1),
                dcc.Store(id="dashboard-modal-initialized", data=False),
                dcc.Store(id="current-editing-report", data=None),
                dcc.Store(id="excel-sheet-data", data=None),
                dcc.Store(id="current-archive-report", data=None),
                dcc.Download(id="download-template"),
                dcc.Download(id="download-xlsx-report"),
                dcc.Store(id="preview-data-store", data=None),
                dcc.Store(id='current-dashboard-data', data={}),
                dcc.Store(id='current-dashboard-index', data=-1),
                dcc.Store(id='delete-confirmation', data=False),
                dcc.Interval(
                    id='configurations-interval-update-today',
                    interval=10*60*1000,
                    n_intervals=0
                ),
            ],
        ),
    ],
)

# update list of dashboard items
@callback(
    Output("dashboard-items-container", "children"),
    [Input("dashboard-selector", "value"),
     Input("refresh-interval", "n_intervals")
     ]
)
def update_dashboard_items(selected_dashboard, refresh):
    """Update the list of dashboard items when selection changes"""
    def load_dashboards_from_file():
        try:
            with open(dashboards_json_path, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, list) else [data]
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    dashboards_data = load_dashboards_from_file()
    if selected_dashboard == "new" or not dashboards_data:
        dashboard = {"counts": [], "sections": [], "report_name": "", "report_id": "", "date_created": ""}
    else:
        dashboard = dashboards_data[selected_dashboard]
    return [
        html.H4("Dashboard Items", style={"font-weight": "bold"}),
        generate_dashboard_items_list(dashboard)
    ]
# validate admins
@callback(
        [Output('sidebar', 'children'),
         Output('main-content', 'children')],
        [Input('url-params-store', 'data')])
def validate_admin_access(urlparams):
    user_data_path = os.path.join(path, 'data', 'users_data.csv')
    if not os.path.exists(user_data_path):
        user_data = pd.DataFrame(columns=['user_id', 'role'])
    else:
        user_data = pd.read_csv(os.path.join(path, 'data', 'users_data.csv'))
        authorized_users = user_data[user_data['role'] == 'Superuser,Superuser']
    test_admin = pd.DataFrame(columns=['user_id', 'role'], data=[['m3his@dhd', 'reports_admin']])
    user_data = pd.concat([authorized_users, test_admin], ignore_index=True)

    user_info = user_data[user_data['user_id'] == urlparams.get('uuid', [None])[0]]
    if user_info.empty:
        return dash.no_update, html.Div([
            html.H2("Access Denied"),
            html.P("You do not have permission to access this page. Please log in as an administrator.")], 
            style={'textAlign': 'center', 'marginTop': '100px'})
    else:
        return dash.no_update, dash.no_update


@callback(
    Output('download-template', 'data'),
    Input('download-sample', 'n_clicks'),
    prevent_initial_call=True
)
def download_template(clicks):
    if clicks:
        return dcc.send_file("data/report_template.xlsx")

# reports
@callback(
    Output("reports-table-container", "children"),
    Input("refresh-interval", "n_intervals")
)
def update_reports_table(_):
    # Load fresh data
    data = load_reports_data()
    reports = data.get("reports", [])

    # Build the table (this will filter out archived reports)
    return build_reports_table(reports)

@callback(
    Output("reports-current-page", "data"),
    Output("reports-table-container", "children", allow_duplicate=True),
    Input("prev-page", "n_clicks"),
    Input("next-page", "n_clicks"),
    State("reports-current-page", "data"),
    prevent_initial_call=True
)
def update_reports_page(prev_clicks, next_clicks, current_page):
    ctx = dash.callback_context

    if not ctx.triggered:
        raise PreventUpdate

    btn = ctx.triggered_id

    # Load reports fresh
    data = load_reports_data().get("reports", [])
    
    # Only active ones
    active_reports = [item for item in data if item.get("archived", "False") == "False"]

    page_size = 10
    total_pages = (len(active_reports) // page_size) + (1 if len(active_reports) % page_size else 0)

    # Determine button clicked
    if btn == "prev-page" and current_page > 1:
        current_page -= 1
    elif btn == "next-page" and current_page < total_pages:
        current_page += 1

    # Rebuild table using updated page number
    table = build_reports_table(
        data,
        page=current_page,
        page_size=page_size
    )

    return current_page, table
# excel
@callback(
    [Output("upload-popup", "style", allow_duplicate=True),
     Output("template-file-upload", "contents"),
     Output("upload-validation-result", "children", allow_duplicate=True),
     Output("existing-report-warning", "children", allow_duplicate=True)],
    [Input("add-from-template-btn", "n_clicks"),
     Input("upload-cancel-btn", "n_clicks")],
    prevent_initial_call=True
)
def toggle_excel_upload_popup(add_clicks, cancel_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == "add-from-template-btn":
        return {'display': 'flex', 'position': 'fixed', 'top': '0', 'left': '0', 
                'width': '100%', 'height': '100%', 'backgroundColor': 'rgba(0,0,0,0.5)', 
                'justifyContent': 'center', 'alignItems': 'center', 'zIndex': '1000'}, None, "", ""
    elif trigger_id == "upload-cancel-btn":
        return {'display': 'none'}, None, "", ""
    
    return dash.no_update

# json dashboard
@callback(
    [Output("upload-dashboard-popup", "style"),
     Output("template-dashboard-file-upload", "contents", allow_duplicate=True),
     Output("upload-dashboard-validation-result", "children", allow_duplicate=True),
     Output("existing-dashboard-report-warning", "children", allow_duplicate=True)],
    [Input("add-dashboard-temp-btn", "n_clicks"),
     Input("upload-dashboard-cancel-btn", "n_clicks")],
    prevent_initial_call=True
)
def toggle_dashboard_upload_popup(add_clicks, cancel_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == "add-dashboard-temp-btn":
        return {'display': 'flex', 'position': 'fixed', 'top': '0', 'left': '0', 
                'width': '100%', 'height': '100%', 'backgroundColor': 'rgba(0,0,0,0.5)', 
                'justifyContent': 'center', 'alignItems': 'center', 'zIndex': '1000'}, None, "", ""
    elif trigger_id == "upload-dashboard-cancel-btn":
        return {'display': 'none'}, None, "", ""
    
    return dash.no_update
# json prog reports
@callback(
    [Output("upload-prog-reports-popup", "style"),
     Output("template-prog-reports-file-upload", "contents", allow_duplicate=True),
     Output("upload-prog-reports-validation-result", "children", allow_duplicate=True),
     Output("existing-prog-reports-report-warning", "children", allow_duplicate=True)],
    [Input("add-prog-report-temp-btn", "n_clicks"),
     Input("upload-prog-reports-cancel-btn", "n_clicks")],
    prevent_initial_call=True
)
def toggle_prog_reports_upload_popup(add_clicks, cancel_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == "add-prog-report-temp-btn":
        return {'display': 'flex', 'position': 'fixed', 'top': '0', 'left': '0', 
                'width': '100%', 'height': '100%', 'backgroundColor': 'rgba(0,0,0,0.5)', 
                'justifyContent': 'center', 'alignItems': 'center', 'zIndex': '1000'}, None, "", ""
    elif trigger_id == "upload-prog-reports-cancel-btn":
        return {'display': 'none'}, None, "", ""
    
    return dash.no_update

@callback(
    [Output("upload-validation-result", "children", allow_duplicate=True),
     Output("existing-report-warning", "children", allow_duplicate=True),
     Output("upload-confirm-btn", "disabled", allow_duplicate=True),
     Output("dry-run-btn", "disabled", allow_duplicate=True)],
    [Input("template-file-upload", "contents"),
     Input("dry-run-btn", "n_clicks")],
    [State("template-file-upload", "contents")],
    prevent_initial_call=True
)
def handle_file_validation_and_dry_run(contents, dry_run_clicks, contents_state):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Use the most recent contents - either from upload or from state
    current_contents = contents if contents is not None else contents_state
    
    if current_contents is None:
        return html.Div("Please upload an Excel file", style={'color': 'orange'}), "", True, True
    
    is_valid, message, report_name_df, filters_df = validate_excel_file(current_contents)
    
    if not is_valid:
        return html.Div(f"Validation failed: {message}", style={'color': 'red'}), "", True, True
    
    # Check if report already exists
    page_name = report_name_df['id'].iloc[0]
    exists, existing_report = check_existing_report(page_name)
    
    warning_message = ""
    if exists:
        warning_message = html.Div([
            html.Div("⚠️ Warning: Report with this page_name already exists", style={'color': 'orange', 'fontWeight': 'bold', 'marginBottom': '5px'}),
            html.Div(f"Existing Report: {existing_report.get('report_name')} (ID: {existing_report.get('report_id')})", style={'color': 'orange'}),
            html.Div("This upload will replace the existing report.", style={'color': 'orange'})
        ])
    
    # If trigger was file upload, return basic validation results
    if trigger_id == "template-file-upload":
        return html.Div(message, style={'color': 'green'}), warning_message, False, False
    
    # If trigger was dry run button, return detailed dry run results
    elif trigger_id == "dry-run-btn":
        # Extract information for dry run
        report_name = report_name_df['name'].iloc[0]
        current_time = datetime.now().strftime("%Y-%m-%d")

        # Check if report has valid column names according to the column names
        filters_columns = [x for x in filters_df.columns.tolist() if x.startswith('variable')]
        filters_df_filtered = filters_df[filters_columns]
        variable_names_list = list(set([str(x).strip() for x in filters_df_filtered.values.flatten() if pd.notna(x) and x.strip()!='']))
        
        final_variable_names = []
        for item in variable_names_list:
            if isinstance(item, str):
                if "|" in item:
                    parts = [x.strip() for x in item.split("|")]
                    final_variable_names.extend(parts)
                elif item.startswith("[") and item.endswith("]"):
                    inner = item[1:-1].strip()
                    parts = [x.strip() for x in inner.split(",")]
                    final_variable_names.extend(parts)
                else:
                    final_variable_names.append(item.strip())
            elif isinstance(item, list):
                final_variable_names.extend([str(x).strip() for x in item])
            else:
                final_variable_names.append(str(item).strip())


        # Check if variable names are the same as in the data
        verification_df, nothing = load_preview_data()
        verification_df_columns = verification_df.columns.tolist()

        not_correct = []
        correct = []
        dry_run_warning = []

        for i in final_variable_names:
            if i in verification_df_columns:
                correct.append(i)
            else:
                not_correct.append(i)
        if len(not_correct)>0:
            dry_run_warning.append(html.Div(f"The following filter columns may need to be corrected: {not_correct}", style={'color': 'red', 'marginBottom': '5px'}))
        
        dry_run_info = [
            html.Div("Dry run successful!", style={'color': 'green', 'marginBottom': '10px', 'fontWeight': 'bold'}),
            html.Div(f"Report Name: {report_name}", style={'color': 'blue', 'marginBottom': '5px'}),
            # html.Div(f"Variable Filters: {variable_names_list}", style={'color': 'blue', 'marginBottom': '5px'}),
            # html.Div(f"All filter are correct: {correct}", style={'color': 'blue', 'marginBottom': '5px'}),
            # html.Div(f"Page Name: {page_name}", style={'color': 'blue', 'marginBottom': '5px'}),
            html.Div(f"Date Created/Updated: {current_time}", style={'color': 'blue', 'marginBottom': '5px'}),
        ]
        
        
        if exists:
            dry_run_warning.append(html.Div([
                html.Div("⚠️ Existing report will be updated:", style={'color': 'orange', 'fontWeight': 'bold', 'marginBottom': '5px'}),
                html.Div(f"Existing: {existing_report.get('report_name')} (ID: {existing_report.get('report_id')})", style={'color': 'orange'}),
                html.Div(f"New: {report_name}", style={'color': 'orange'})
            ]))
        else:
            new_id = get_next_report_id()
            dry_run_info.append(html.Div(f"New Report ID: {new_id}", style={'color': 'green', 'marginBottom': '5px'}))
        
        return html.Div(dry_run_info), dry_run_warning, False, False
    
    return dash.no_update

@callback(
    Output('upload-dashboard-validation-result', 'children',allow_duplicate=True),
    Output('upload-dashboard-confirm-btn', 'disabled',allow_duplicate=True),
    Output('existing-dashboard-report-warning', 'children',allow_duplicate=True),

    Output('template-dashboard-file-upload', 'contents',allow_duplicate=True),

    Input('template-dashboard-file-upload', 'contents'),
    Input('dry-dashboard-run-btn', 'n_clicks'),
    Input('upload-dashboard-confirm-btn', 'n_clicks'),
    Input('upload-dashboard-cancel-btn', 'n_clicks'),

    State('template-dashboard-file-upload', 'filename'),
    State('template-dashboard-file-upload', 'contents'),
    prevent_initial_call=True
)
def process_dashboard_json(uploaded_contents, dry_run_clicks, upload_clicks, cancel_clicks,
                 filename, contents):
    ctx = dash.callback_context

    action = ctx.triggered[0]["prop_id"].split(".")[0]
    if action == "upload-dashboard-cancel-btn":
        return "", True, "", None
    if action == "template-dashboard-file-upload":
        if filename:
            msg = html.Div([
                html.B(f"File selected: {filename}"),
                html.Br(),
                "Please click Dry Run to validate the JSON template."
            ], style={'color': 'blue'})
            return msg, True, "", contents
        else:
            return "Upload a JSON file first.", True, "", contents
    if not contents:
        return "Please upload a JSON file first.", True, "", None

    try:
        _, content_string = contents.split(',')
        decoded = base64.b64decode(content_string).decode('utf-8')
    except:
        return "Failed to read file content.", True, "", contents
    if action == "dry-dashboard-run-btn":
        ok, message = validate_dashboard_json(decoded)
        color = "green" if ok else "red"
        return html.Div(message, style={'color': color}), not ok, "", contents
    if action == "upload-dashboard-confirm-btn":
        result = upload_dashboard_json(contents)
        return html.Div(result, style={'color': 'green'}), True, "", contents
    
@callback(
    Output('upload-prog-reports-validation-result', 'children',allow_duplicate=True),
    Output('upload-prog-reports-confirm-btn', 'disabled',allow_duplicate=True),
    Output('existing-prog-reports-report-warning', 'children',allow_duplicate=True),

    Output('template-prog-reports-file-upload', 'contents',allow_duplicate=True),

    Input('template-prog-reports-file-upload', 'contents'),
    Input('dry-prog-reports-run-btn', 'n_clicks'),
    Input('upload-prog-reports-confirm-btn', 'n_clicks'),
    Input('upload-prog-reports-cancel-btn', 'n_clicks'),

    State('template-prog-reports-file-upload', 'filename'),
    State('template-prog-reports-file-upload', 'contents'),
    prevent_initial_call=True
)
def process_prog_dashboard_json(uploaded_contents, dry_run_clicks, upload_clicks, cancel_clicks,
                 filename, contents):
    ctx = dash.callback_context

    action = ctx.triggered[0]["prop_id"].split(".")[0]
    if action == "upload-prog-reports-cancel-btn":
        return "", True, "", None
    if action == "template-prog-reports-file-upload":
        if filename:
            msg = html.Div([
                html.B(f"File selected: {filename}"),
                html.Br(),
                "Please click Dry Run to validate the JSON template."
            ], style={'color': 'blue'})
            return msg, True, "", contents
        else:
            return "Upload a JSON file first.", True, "", contents
    if not contents:
        return "Please upload a JSON file first.", True, "", None

    try:
        _, content_string = contents.split(',')
        decoded = base64.b64decode(content_string).decode('utf-8')
    except:
        return "Failed to read file content.", True, "", contents
    if action == "dry-prog-reports-run-btn":
        ok, message = validate_prog_reports_json(decoded)
        color = "green" if ok else "red"
        return html.Div(message, style={'color': color}), not ok, "", contents
    if action == "upload-prog-reports-confirm-btn":
        result = upload_prog_reports_json(contents)
        return html.Div(result, style={'color': 'green'}), True, "", contents

@callback(
    [Output("upload-popup", "style", allow_duplicate=True),
     Output("upload-validation-result", "children", allow_duplicate=True),
     Output("existing-report-warning", "children", allow_duplicate=True)],
    Input("upload-confirm-btn", "n_clicks"),
    State("template-file-upload", "contents"),
    prevent_initial_call=True
)
def upload_file(n_clicks, contents):
    if contents is None:
        return dash.no_update, html.Div("No file to upload", style={'color': 'red'}), ""
    
    is_valid, message, report_name_df, filters_df = validate_excel_file(contents)
    
    if not is_valid:
        return dash.no_update, html.Div(f"Cannot upload: {message}", style={'color': 'red'}), ""
    
    try:
        # Create uploads directory if it doesn't exist
        upload_dir = os.path.join("data", "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        # Extract information from REPORT_NAME sheet
        page_name = report_name_df['id'].iloc[0]
        report_name = report_name_df['name'].iloc[0]
        filename = f"{page_name}.xlsx"
        
        # Check if report already exists
        exists, existing_report = check_existing_report(page_name)
        
        # Save the file
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        file_path = os.path.join(upload_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(decoded)
        
        # Update or create report in JSON
        updated_data = update_or_create_report(report_name_df, is_update=exists, existing_report=existing_report)
        
        # Prepare success message
        success_elements = [
            html.Div("File uploaded successfully!", style={'color': 'green', 'marginBottom': '10px', 'fontWeight': 'bold'}),
            html.Div(f"Saved as: {filename}", style={'color': 'blue', 'marginBottom': '5px'}),
            html.Div(f"Report Name: {report_name}", style={'color': 'blue', 'marginBottom': '5px'}),
            html.Div(f"Page Name: {page_name}", style={'color': 'blue', 'marginBottom': '5px'})
        ]
        
        if exists:
            success_elements.append(html.Div("Existing report was updated", style={'color': 'orange', 'marginBottom': '5px'}))
            success_elements.append(html.Div(f"Report ID: {existing_report.get('report_id')}", style={'color': 'blue', 'marginBottom': '5px'}))
        else:
            new_id = get_next_report_id() - 1  # Since we just added one
            success_elements.append(html.Div(f"New Report ID: {new_id}", style={'color': 'green', 'marginBottom': '5px'}))
        
        success_message = html.Div(success_elements)
        
        # Close popup after successful upload
        return {'display': 'none'}, success_message, ""
        
    except Exception as e:
        error_message = html.Div(f"Upload failed: {str(e)}", style={'color': 'red'})
        return dash.no_update, error_message, ""


@callback(
    [Output("edit-popup", "style", allow_duplicate=True),
     Output("current-editing-report", "data"),
     Output("edit-popup-title", "children"),
     Output("sheet-tabs", "children"),
     Output("sheet-tabs", "value"),
     Output("sheet-tables-container", "children", allow_duplicate=True),
     Output("excel-sheet-data", "data", allow_duplicate=True)],
    [Input({"type": "edit-btn", "index": dash.ALL}, "n_clicks"),
     Input("edit-cancel-btn", "n_clicks")],
    [State("reports-table-container", "children")],
    prevent_initial_call=True
)
def toggle_edit_popup(edit_clicks, cancel_clicks, reports_table):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    trigger_id = ctx.triggered[0]['prop_id']
    
    if "edit-cancel-btn" in trigger_id:
        return {'display': 'none'}, None, "", None, None, "", None
    
    if "edit-btn" in trigger_id:
        # Determine which edit button was clicked
        button_index = None
        for i, count in enumerate(edit_clicks):
            if count and count > 0:
                button_index = i
                break

        if button_index is None:
            return dash.no_update

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        button_id_dict = json.loads(button_id.replace("'", '"'))
        report_id = button_id_dict['index']
        
        # Find the report data
        data = load_reports_data()
        reports = data.get("reports", [])
        current_report = None
        
        for report in reports:
            if report.get("report_id") == report_id:
                current_report = report
                break
        
        if not current_report:
            return dash.no_update
        
        page_name = current_report.get("page_name")
        report_name = current_report.get("report_name")
        
        # Load the Excel file
        excel_file = load_excel_file(page_name)
        if not excel_file:
            return dash.no_update
        
        # Create tabs for each sheet
        sheet_names = excel_file.sheet_names
        tabs = []
        sheet_tables = []
        sheet_data_dict = {}
        
        for i, sheet_name in enumerate(sheet_names):
            # Read sheet data
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            sheet_data_dict[sheet_name] = df.to_dict('records')
            
            # Create tab
            tabs.append(dcc.Tab(label=sheet_name, value=sheet_name))
            
            # Create table for this sheet
            sheet_table = create_editable_table(df, sheet_name)
            sheet_tables.append(sheet_table)
        
        # Set first sheet as active
        active_tab = sheet_names[0] if sheet_names else None
        
        title = f"Editing: {report_name} ({page_name}.xlsx)"
        
        return (
            {'display': 'flex'}, 
            current_report,
            title,
            tabs,
            active_tab,
            sheet_tables[0] if sheet_tables else "No sheets found",
            sheet_data_dict
        )
    
    return dash.no_update


@callback(
    Output("sheet-tables-container", "children", allow_duplicate=True),
    Input("sheet-tabs", "value"),
    State("excel-sheet-data", "data"),
    prevent_initial_call=True
)
def update_sheet_display(selected_sheet, sheet_data):
    if not selected_sheet or not sheet_data or selected_sheet not in sheet_data:
        return "No sheet selected"
    
    # Convert the stored data back to DataFrame
    df = pd.DataFrame(sheet_data[selected_sheet])
    
    # Create the editable table
    return create_editable_table(df, selected_sheet)


@callback(
    Output("excel-sheet-data", "data", allow_duplicate=True),
    Input({"type": "editable-table", "sheet": dash.ALL}, "data"),
    State({"type": "editable-table", "sheet": dash.ALL}, "id"),
    State("excel-sheet-data", "data"),
    prevent_initial_call=True
)
def update_sheet_data(table_data, table_ids, current_sheet_data):
    if not table_data or not current_sheet_data:
        return dash.no_update
    
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    # Get the sheet that was updated
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    trigger_id_dict = json.loads(trigger_id.replace("'", '"'))
    updated_sheet = trigger_id_dict['sheet']
    
    # Find the index of the updated table
    for i, table_id in enumerate(table_ids):
        if table_id['sheet'] == updated_sheet:
            # Update the data for this sheet
            current_sheet_data[updated_sheet] = table_data[i]
            break
    
    return current_sheet_data


@callback(
    [Output("edit-popup", "style", allow_duplicate=True),
     Output("upload-validation-result", "children", allow_duplicate=True)],
    Input("save-excel-btn", "n_clicks"),
    [State("current-editing-report", "data"),
     State("excel-sheet-data", "data")],
    prevent_initial_call=True
)
def save_excel_changes(save_clicks, current_report, sheet_data):
    if not save_clicks or not current_report or not sheet_data:
        return dash.no_update
    
    try:
        page_name = current_report.get("page_name")
        report_id = current_report.get("report_id")
        
        # Convert sheet data back to DataFrames
        sheet_dataframes = {}
        for sheet_name, data_dict in sheet_data.items():
            sheet_dataframes[sheet_name] = pd.DataFrame(data_dict)
        
        # Save to Excel file
        save_excel_file(page_name, sheet_dataframes)
        
        # Update metadata in reports.json
        update_report_metadata(report_id)
        
        success_message = html.Div([
            html.Div("Excel file saved successfully!", style={'color': 'green', 'marginBottom': '10px', 'fontWeight': 'bold'}),
            html.Div(f"File: {page_name}.xlsx", style={'color': 'blue', 'marginBottom': '5px'}),
            html.Div(f"Updated: {datetime.now().strftime('%Y-%m-%d')}", style={'color': 'blue', 'marginBottom': '5px'})
        ])
        
        # Close the popup
        return {'display': 'none'}, success_message
        
    except Exception as e:
        error_message = html.Div(f"❌ Error saving file: {str(e)}", style={'color': 'red'})
        return dash.no_update, error_message


@callback(
    [Output("archive-popup", "style", allow_duplicate=True),
     Output("current-archive-report", "data"),
     Output("archive-confirmation-message", "children")],
    [Input({"type": "archive-btn", "index": dash.ALL}, "n_clicks"),
     Input("cancel-archive-btn", "n_clicks")],
    [State({"type": "archive-btn", "index": dash.ALL}, "id"),
     State("reports-table-container", "children")],
    prevent_initial_call=True
)
def toggle_archive_popup(archive_clicks, cancel_clicks, archive_buttons_ids, reports_table):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    trigger_id = ctx.triggered[0]['prop_id']
    
    if "cancel-archive-btn" in trigger_id:
        return {'display': 'none'}, None, ""
    
    if "archive-btn" in trigger_id:
        # Find which archive button was clicked
        button_index = None
        for i, clicks in enumerate(archive_clicks):
            if clicks and clicks > 0:  # Only proceed if button was actually clicked
                button_index = i
                break
        if button_index is None:
            return dash.no_update
        # if button_index == 0:
        #     return dash.no_update
        
        # Get the report_id from the button that was clicked
        report_id = archive_buttons_ids[button_index]['index']
        
        # Find the report data
        data = load_reports_data()
        reports = data.get("reports", [])
        current_report = None
        
        for report in reports:
            if report.get("report_id") == report_id:
                current_report = report
                break
        
        if not current_report:
            return dash.no_update
        
        # Create confirmation message
        confirmation_message = html.Div([
            html.Div("Are you sure you want to archive this report?", style={'marginBottom': '10px', 'fontWeight': 'bold'}),
            html.Div(f"Report ID: {current_report.get('report_id')}", style={'marginBottom': '5px'}),
            html.Div(f"Report Name: {current_report.get('report_name')}", style={'marginBottom': '5px'}),
            html.Div(f"Page Name: {current_report.get('page_name')}", style={'marginBottom': '10px'}),
            html.Div("⚠️ This action cannot be undone. The report will be hidden from the main list.", 
                    style={'color': 'orange', 'fontStyle': 'italic'})
        ])
        
        return {'display': 'flex'}, current_report, confirmation_message
    
    return dash.no_update

@callback(
     Output("download-xlsx-report", "data"),
     Input({"type": "download-btn", "index": dash.ALL}, "n_clicks"),
     State({"type": "download-btn", "index": dash.ALL}, "id"),
    prevent_initial_call=True
)
def download_xlsx_report(download_clicks,download_ids):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    trigger_id = ctx.triggered[0]['prop_id']
    
    if "download-btn" in trigger_id:
        # Find which archive button was clicked
        button_index = None
        for i, clicks in enumerate(download_clicks):
            if clicks and clicks > 0:  # Only proceed if button was actually clicked
                button_index = i
                break
        
        if button_index is None:
            return dash.no_update
        
        # Get the report_id from the button that was clicked
        report_id = download_ids[button_index]['index']
        
        # Find the report data
        data = load_reports_data()
        reports = data.get("reports", [])
        current_report = None
        
        for report in reports:
            if report.get("report_id") == report_id:
                current_report = report
                break
        if not current_report:
            return dash.no_update
        return dcc.send_file(os.path.join("data","uploads",f"{current_report.get('page_name')}.xlsx"))
    # return 'data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,' + encode_excel_for_download(current_report.get("page_name")), filename=f"{current_report.get('page_name')}.xlsx"


@callback(
    [Output("archive-popup", "style", allow_duplicate=True),
     Output("upload-validation-result", "children", allow_duplicate=True)],
    Input("confirm-archive-btn", "n_clicks"),
    [State("current-archive-report", "data"),
     State("confirm-archive-btn", "n_clicks")],
    prevent_initial_call=True
)
def confirm_archive(n_clicks, current_report, current_n_clicks):
    # Check if the button was actually clicked (n_clicks > 0)
    if not n_clicks or n_clicks == 0 or not current_report:
        return dash.no_update
    
    try:
        report_id = current_report.get("report_id")
        report_name = current_report.get("report_name")
        
        # Archive the report
        archive_report(report_id)
        
        success_message = html.Div([
            html.Div("Report archived successfully!", style={'color': 'green', 'marginBottom': '10px', 'fontWeight': 'bold'}),
            html.Div(f"Report: {report_name}", style={'color': 'blue', 'marginBottom': '5px'}),
            html.Div(f"Report ID: {report_id}", style={'color': 'blue', 'marginBottom': '5px'}),
            html.Div("The report has been archived and will no longer appear in the list.", 
                    style={'color': 'gray', 'fontStyle': 'italic'})
        ])
        
        # Close the popup
        return {'display': 'none'}, success_message
        
    except Exception as e:
        error_message = html.Div(f"❌ Error archiving report: {str(e)}", style={'color': 'red'})
        return dash.no_update, error_message
    
@callback(
    [Output("preview-popup", "style"),
     Output("preview-data-info", "children"),
     Output("preview-data-table", "children")],
    [Input("preview-data", "n_clicks"),
     Input("close-preview-btn", "n_clicks")],
    prevent_initial_call=True
)
def toggle_preview_popup(preview_clicks, close_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == "close-preview-btn":
        return {'display': 'none'}, "", ""
    
    if trigger_id == "preview-data" and preview_clicks:
        # Load the preview data
        df, error = load_preview_data()
        
        if error:
            error_message = html.Div([
                html.Div("❌ Error loading preview data", style={'color': 'red', 'marginBottom': '10px', 'fontWeight': 'bold'}),
                html.Div(error, style={'color': 'red'})
            ])
            return {'display': 'flex'}, error_message, ""
        
        if df is None or df.empty:
            no_data_message = html.Div([
                html.Div("No data available", style={'color': 'orange', 'marginBottom': '10px', 'fontWeight': 'bold'}),
                html.Div("The data file is empty or could not be loaded.", style={'color': 'orange'})
            ])
            return {'display': 'flex'}, no_data_message, ""
        
        # Create info message
        info_message = html.Div([
            html.Div("✅ Data loaded successfully", style={'color': 'green', 'marginBottom': '10px', 'fontWeight': 'bold'}),
            html.Div(f"Records loaded: {len(df)} ( records)", style={'color': 'blue', 'marginBottom': '5px'}),
            html.Div(f"Columns: {len(df.columns)}", style={'color': 'blue', 'marginBottom': '5px'}),
            html.Div("Tip: Use the filter icons in column headers to filter data", style={'color': 'gray', 'fontStyle': 'italic'})
        ])
        
        # Create the preview table
        preview_table = create_preview_table(df)
        
        return {'display': 'flex'}, info_message, preview_table
    
    return dash.no_update

# DASHBOARD
@callback(
    [Output("modal-backdrop", "style", allow_duplicate=True),
     Output("modal-content", "style", allow_duplicate=True),
     Output("dashboard-selector", "value", allow_duplicate=True),
     Output("dashboard-selector", "data"),
     Output("report-id-input", "value", allow_duplicate=True),
     Output("report-name-input", "value", allow_duplicate=True),
     Output("date-created-input", "value", allow_duplicate=True),
     Output("counts-container", "children", allow_duplicate=True),
     Output("sections-container", "children", allow_duplicate=True)],
    [Input("add-dashboard", "n_clicks"),
     Input("cancel-btn", "n_clicks"),
     Input("save-btn", "n_clicks"),
     Input("refresh-interval", "n_intervals")],
    prevent_initial_call=True
)
def toggle_modal(open_clicks, cancel_clicks, save_clicks, n_intervals):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    def load_dashboards_from_file():
        try:
            with open(dashboards_json_path, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, list) else [data]
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger == "add-dashboard" and open_clicks > 0:
        # Load current dashboards from file
        dashboards_data = load_dashboards_from_file()
        
        # Update dropdown options
        options = [{"label": f"📋 {d.get('report_name', 'Unnamed')})", 
                   "value": i} for i, d in enumerate(dashboards_data)] + \
                  [{"label": "➕ Create New Dashboard", "value": "new"}]
        
        
        # Return empty form for new dashboard
        return (
            {"display": "block"}, 
            {"display": "block"},
            "new",  # Select "new" in dropdown
            options,
            f"report_{uuid.uuid4().hex[:8]}",  # Auto-generate ID
            "New Dashboard",  # Default name
            datetime.now().strftime("%Y-%m-%d"),  # Current date
            [],  # Empty counts
            []   # Empty sections
        )
    
    elif trigger == "cancel-btn":
        # Just close the modal
        return {"display": "none"}, {"display": "none"}, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,dash.no_update
    
    elif trigger == "save-btn":
        # Just close the modal
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,dash.no_update
    
    return dash.no_update


@callback(
    [Output("report-id-input", "value", allow_duplicate=True),
     Output("report-name-input", "value", allow_duplicate=True),
     Output("date-created-input", "value", allow_duplicate=True),
     Output("counts-container", "children", allow_duplicate=True),
     Output("sections-container", "children", allow_duplicate=True)],
    [Input("dashboard-selector", "value"),
     Input({"type": "count-edit", "index": dash.ALL}, "n_clicks"),
     Input({"type": "section-edit", "index": dash.ALL}, "n_clicks"),
     Input({"type": "chart-edit", "section": dash.ALL, "chart": dash.ALL}, "n_clicks"),
     ],
    prevent_initial_call=True
)
def load_dashboard(selector_value, count_clicks, section_clicks, chart_clicks):
    """Load dashboard data when selector changes, or show a single edit form when an edit button is clicked."""
    if not ctx.triggered:
        raise PreventUpdate

    triggered_id = ctx.triggered_id


    def load_dashboards_from_file():
        try:
            with open(dashboards_json_path, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, list) else [data]
        except (FileNotFoundError, json.JSONDecodeError):
            return []


    # ── 1. Selector changed ───────────────────────────────────────────────────
    if triggered_id == "dashboard-selector":
        if selector_value == "new":
            return (
                f"report_{uuid.uuid4().hex[:8]}",
                "New Dashboard",
                datetime.now().strftime("%Y-%m-%d"),
                [],
                [],
            )
        dashboards_data = load_dashboards_from_file()
        if isinstance(selector_value, int) and 0 <= selector_value < len(dashboards_data):
            dashboard = dashboards_data[selector_value]
            return (
                dashboard.get("report_id", ""),
                dashboard.get("report_name", ""),
                dashboard.get("date_created", ""),
                [],  # clear containers on dashboard switch
                [],
            )
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    # ── 2. An edit button was clicked ────────────────────────────────────────
    dashboards_data = load_dashboards_from_file()

    if not (isinstance(selector_value, int) and 0 <= selector_value < len(dashboards_data)):
        raise PreventUpdate

    dashboard = dashboards_data[selector_value]
    counts   = dashboard.get("visualization_types", {}).get("counts", [])
    sections = dashboard.get("visualization_types", {}).get("charts", {}).get("sections", [])
    meta = (
        dashboard.get("report_id", ""),
        dashboard.get("report_name", ""),
        dashboard.get("date_created", ""),
    )

    # ── count-edit ────────────────────────────────────────────────────────────
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "count-edit":
        if not any(c for c in (count_clicks or []) if c and c > 0):
            raise PreventUpdate
        clicked_index = triggered_id["index"]
        try:
            count_form = create_count_item(counts[clicked_index], clicked_index)
        except (IndexError, Exception):
            count_form = []
        return (*meta, count_form, dash.no_update)

    # ── section-edit ──────────────────────────────────────────────────────────
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "section-edit":
        if not any(c for c in (section_clicks or []) if c and c > 0):
            raise PreventUpdate
        clicked_index = triggered_id["index"]
        try:
            section_form = create_section(sections[clicked_index], clicked_index)
        except (IndexError, Exception):
            section_form = []
        return (*meta, dash.no_update, section_form)

    # ── chart-edit ────────────────────────────────────────────────────────────
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "chart-edit":
        if not any(c for c in (chart_clicks or []) if c and c > 0):
            raise PreventUpdate
        section_idx = triggered_id["section"]
        try:
            section_form = create_section(sections[section_idx], section_idx)
        except (IndexError, Exception):
            section_form = []
        return (*meta, dash.no_update, section_form)

    raise PreventUpdate


# ── Count: add / save / delete ────────────────────────────────────────────────
@callback(
    Output("counts-container", "children", allow_duplicate=True),
    [Input("add-count-btn", "n_clicks"),
     Input({"type": "save-count",   "index": dash.ALL}, "n_clicks"),
     Input({"type": "remove-count", "index": dash.ALL}, "n_clicks")],
    [State("dashboard-selector", "value"),
     State({"type": "count-id",     "index": dash.ALL}, "value"),
     State({"type": "count-name",   "index": dash.ALL}, "value"),
     State({"type": "count-aggregations","index": dash.ALL}, "value"),
     State({"type": "count-unique", "index": dash.ALL}, "value"),
     State({"type": "count-var1",   "index": dash.ALL}, "value"),
     State({"type": "count-val1",   "index": dash.ALL}, "value"),
     State({"type": "count-var2",   "index": dash.ALL}, "value"),
     State({"type": "count-val2",   "index": dash.ALL}, "value"),
     State({"type": "count-var3",   "index": dash.ALL}, "value"),
     State({"type": "count-val3",   "index": dash.ALL}, "value"),
     State({"type": "count-var4",   "index": dash.ALL}, "value"),
     State({"type": "count-val4",   "index": dash.ALL}, "value"),
     State({"type": "count-var5",   "index": dash.ALL}, "value"),
     State({"type": "count-val5",   "index": dash.ALL}, "value"),
     State({"type": "count-var6",   "index": dash.ALL}, "value"),
     State({"type": "count-val6",   "index": dash.ALL}, "value"),
     State({"type": "count-var7",   "index": dash.ALL}, "value"),
     State({"type": "count-val7",   "index": dash.ALL}, "value"),
     State({"type": "count-var8",   "index": dash.ALL}, "value"),
     State({"type": "count-val8",   "index": dash.ALL}, "value"),
     State("counts-container", "children")],
    prevent_initial_call=True
)
def manage_counts(add_clicks, save_clicks, remove_clicks,
                  selector_value,
                  count_ids, count_names,count_aggr, count_uniques,
                  vars1, vals1, vars2, vals2, vars3, vals3,
                  vars4, vals4, vars5, vals5, vars6, vals6,
                  vars7, vals7, vars8, vals8,
                  current_counts):
    if not ctx.triggered:
        raise PreventUpdate
    def load_dashboards_from_file():
        try:
            with open(dashboards_json_path, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, list) else [data]
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    def _load_dashboard(selector_value):
        """Return (dashboards_data, dashboard, counts, sections) for the selected index."""
        data = load_dashboards_from_file()
        if not (isinstance(selector_value, int) and 0 <= selector_value < len(data)):
            return None, None, [], []
        db = data[selector_value]
        counts   = db.get("visualization_types", {}).get("counts", [])
        sections = db.get("visualization_types", {}).get("charts", {}).get("sections", [])
        return data, db, counts, sections
    def save_dashboards_to_file(data):
        with open(dashboards_json_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _save_dashboards(data):
        save_dashboards_to_file(data)

    triggered_id = ctx.triggered_id
    current_counts = current_counts or []

    # ── Add new blank count to the UI only (saved on "Save Count") ────────────
    if triggered_id == "add-count-btn":
        if add_clicks and add_clicks > 0:
            new_count = create_count_item(index=len(current_counts))
            # if isinstance(current_counts, dict):
            #     return [new_count]
            return [new_count]
        raise PreventUpdate

    # ── Save count: update the JSON file by count id ──────────────────────────
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "save-count":
        if not any(c for c in (save_clicks or []) if c and c > 0):
            raise PreventUpdate
        # ui_index = triggered_id["index"]          # position in the current UI list
        ui_index = 0 
        dashboards_data, dashboard, counts, sections = _load_dashboard(selector_value)
        if dashboard is None:
            raise PreventUpdate
        # Build updated count from form state at ui_index
        count_id = count_ids[ui_index] if ui_index < len(count_ids) else f"count_{uuid.uuid4().hex[:8]}"
        updated = {
            "id":   count_id,
            "name": count_names[ui_index] if ui_index < len(count_names) else "",
            "filters": {
                "measure":  count_aggr[ui_index] if ui_index < len(count_aggr) else "count",
                "unique":    count_uniques[ui_index] if ui_index < len(count_uniques) else "person_id",
                "variable1": vars1[ui_index] if ui_index < len(vars1) else "Program",
                "value1":    vals1[ui_index] if ui_index < len(vals1) else [],
                "variable2": vars2[ui_index] if ui_index < len(vars2) else "Encounter",
                "value2":    vals2[ui_index] if ui_index < len(vals2) else [],
                "variable3": vars3[ui_index] if ui_index < len(vars3) else "concept_name",
                "value3":    vals3[ui_index] if ui_index < len(vals3) else [],
                "variable4": vars4[ui_index] if ui_index < len(vars4) else "obs_value_coded",
                "value4":    vals4[ui_index] if ui_index < len(vals4) else "",
                "variable5": vars5[ui_index] if ui_index < len(vars5) else "ValueN",
                "value5":    vals5[ui_index] if ui_index < len(vals5) else "",
                "variable6": vars6[ui_index] if ui_index < len(vars6) else "Value",
                "value6":    vals6[ui_index] if ui_index < len(vals6) else "",
                "variable7": vars7[ui_index] if ui_index < len(vars7) else "Gender",
                "value7":    vals7[ui_index] if ui_index < len(vals7) else "",
                "variable8": vars8[ui_index] if ui_index < len(vars8) else "Age",
                "value8":    vals8[ui_index] if ui_index < len(vals8) else "",
            }
        }

        # Find and replace by id, or append if new
        matched = False
        for i, c in enumerate(counts):
            if c.get("id") == count_id:
                counts[i] = updated
                matched = True
                break
        if not matched:
            if updated["name"] !="":
                counts.append(updated)

        dashboard["visualization_types"]["counts"] = counts
        dashboards_data[selector_value] = dashboard
        _save_dashboards(dashboards_data)

        # Refresh the container from the saved data
        # return [create_count_item(c, i) for i, c in enumerate(counts)]
        return []

    # ── Delete count: remove from JSON by count id ────────────────────────────
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "remove-count":
        if not any(c for c in (remove_clicks or []) if c and c > 0):
            raise PreventUpdate
        ui_index = triggered_id["index"]
        dashboards_data, dashboard, counts, sections = _load_dashboard(selector_value)
        if dashboard is None:
            raise PreventUpdate

        count_id = count_ids[ui_index] if ui_index < len(count_ids) else None
        if count_id:
            counts = [c for c in counts if c.get("id") != count_id]
        else:
            # Fallback: remove by position if id is missing (new unsaved count)
            counts = [c for i, c in enumerate(counts) if i != ui_index]

        dashboard["visualization_types"]["counts"] = counts
        dashboards_data[selector_value] = dashboard
        _save_dashboards(dashboards_data)

        return [create_count_item(c, i) for i, c in enumerate(counts)]

    raise PreventUpdate

@callback(
    Output("sections-container", "children", allow_duplicate=True),
    [Input("add-section-btn", "n_clicks"),
     Input({"type": "remove-section", "index": dash.ALL}, "n_clicks"),
     Input({"type": "add-chart-btn",  "index": dash.ALL}, "n_clicks"),
     Input({"type": "save-chart",   "section": dash.ALL, "index": dash.ALL}, "n_clicks"),
     Input({"type": "remove-chart", "section": dash.ALL, "index": dash.ALL}, "n_clicks")],
    [State("dashboard-selector", "value"),
     State({"type": "section-name",  "index": dash.ALL}, "value"),
     # Chart form states - using index-based identification
     State({"type": "chart-id",      "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-name",    "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-type",    "section": dash.ALL, "index": dash.ALL}, "value"),
    #  State({"type": "chart-title",   "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-date_col","section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-y_col",   "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-x_col",   "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-x_title", "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-y_title", "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-unique_column",  "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-legend_title",   "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-color",          "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-label_col",      "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-value_col",      "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-top_n",          "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-names_col",      "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-values_col",     "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-age_col",        "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-gender_col",     "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-bin_size",       "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-index_col1",     "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-columns",        "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-aggfunc",        "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-duration_default","section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-colormap",       "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-filter_col1",    "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-filter_val1",    "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-filter_col2",    "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-filter_val2",    "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-filter_col3",    "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-filter_val3",    "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-filter_col4",    "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-filter_val4",    "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-filter_col5",    "section": dash.ALL, "index": dash.ALL}, "value"),
     State({"type": "chart-filter_val5",    "section": dash.ALL, "index": dash.ALL}, "value"),
     State("sections-container", "children")],
    prevent_initial_call=True
)
def manage_sections(add_section_clicks, remove_section_clicks,
                    add_chart_clicks, save_chart_clicks, remove_chart_clicks,
                    selector_value, section_names,
                    chart_ids, chart_names, chart_types, 
                    # chart_titles,
                    chart_date_cols, chart_y_cols, chart_x_cols,
                    chart_x_titles, chart_y_titles,
                    chart_unique_columns, chart_legend_titles, chart_colors,
                    chart_label_cols, chart_value_cols, chart_top_ns,
                    chart_names_cols, chart_values_cols,
                    chart_age_cols, chart_gender_cols, chart_bin_sizes,
                    chart_index_col1s, chart_columns, chart_aggfuncs,
                    chart_duration_defaults, chart_colormaps,
                    chart_filter_col1s, chart_filter_val1s,
                    chart_filter_col2s, chart_filter_val2s,
                    chart_filter_col3s, chart_filter_val3s,
                    chart_filter_col4s, chart_filter_val4s,
                    chart_filter_col5s, chart_filter_val5s,
                    current_sections):
    
    if not ctx.triggered:
        raise PreventUpdate
 
    def load_dashboards_from_file():
        try:
            with open(dashboards_json_path, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, list) else [data]
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def _load_dashboard(selector_value):
        data = load_dashboards_from_file()
        if not (isinstance(selector_value, int) and 0 <= selector_value < len(data)):
            return None, None, [], []
        db = data[selector_value]
        counts = db.get("visualization_types", {}).get("counts", [])
        sections = db.get("visualization_types", {}).get("charts", {}).get("sections", [])
        return data, db, counts, sections
    
    def save_dashboards_to_file(data):
        with open(dashboards_json_path, 'w') as f:
            json.dump(data, f, indent=2)
 
    triggered_id = ctx.triggered_id
 
    def get(lst, i, default=None):
        return lst[i] if lst and i < len(lst) else default

    def calculate_flat_index(section_idx, chart_idx):
        """Calculate the flat index of a chart in the form state lists"""
        flat_idx = 0
        for s_i, s in enumerate(sections):
            if s_i == section_idx:
                return flat_idx + chart_idx
            flat_idx += len(s.get("items", []))
        return None

    def build_chart_data_from_index(section_idx, chart_id, flat_idx, form_data):
        """Build chart data using flat index"""
        chart_type = get(chart_types, flat_idx, "Bar")
        
        # Build filters with all possible fields
        filters = {
            "measure": "nunique",
            "unique": "any",
            "duration_default": get(chart_duration_defaults, flat_idx, "any") or "any",
            "title": get(chart_names, flat_idx, ""),
            "unique_column": get(chart_unique_columns, flat_idx, "person_id"),
            # Filters
            "filter_col1": get(chart_filter_col1s, flat_idx, []),
            "filter_val1": get(chart_filter_val1s, flat_idx, ""),
            "filter_col2": get(chart_filter_col2s, flat_idx, []),
            "filter_val2": get(chart_filter_val2s, flat_idx, ""),
            "filter_col3": get(chart_filter_col3s, flat_idx, []),
            "filter_val3": get(chart_filter_val3s, flat_idx, ""),
            "filter_col4": get(chart_filter_col4s, flat_idx, []),
            "filter_val4": get(chart_filter_val4s, flat_idx, ""),
            "filter_col5": get(chart_filter_col5s, flat_idx, []),
            "filter_val5": get(chart_filter_val5s, flat_idx, ""),
        }

        # Add chart type specific fields
        if chart_type == "Line":
            filters.update({
                "date_col": get(chart_date_cols, flat_idx, ""),
                "y_col": get(chart_y_cols, flat_idx, ""),
                "x_title": get(chart_x_titles, flat_idx, ""),
                "y_title": get(chart_y_titles, flat_idx, ""),
                "legend_title": get(chart_legend_titles, flat_idx, ""),
                "color": get(chart_colors, flat_idx, "")
            })
        elif chart_type == "Bar":
            filters.update({
                "label_col": get(chart_label_cols, flat_idx, ""),
                "value_col": get(chart_value_cols, flat_idx, ""),
                "top_n": get(chart_top_ns, flat_idx, 10),
                "x_title": get(chart_x_titles, flat_idx, ""),
                "y_title": get(chart_y_titles, flat_idx, ""),
            })
        elif chart_type == "Pie":
            filters.update({
                "names_col": get(chart_names_cols, flat_idx, ""),
                "values_col": get(chart_values_cols, flat_idx, ""),
                "colormap": get(chart_colormaps, flat_idx, {})
            })
        elif chart_type == "Column":
            filters.update({
                "y_col": get(chart_y_cols, flat_idx, ""),
                "x_col": get(chart_x_cols, flat_idx, ""),
                "x_title": get(chart_x_titles, flat_idx, ""),
                "y_title": get(chart_y_titles, flat_idx, ""),
                "legend_title": get(chart_legend_titles, flat_idx, ""),
                "color": get(chart_colors, flat_idx, "")
            })
        elif chart_type == "Histogram":
            filters.update({
                "age_col": get(chart_age_cols, flat_idx, "Age"),
                "gender_col": get(chart_gender_cols, flat_idx, "Gender"),
                "bin_size": get(chart_bin_sizes, flat_idx, 5),
                "color": get(chart_colors, flat_idx, "")
            })
        elif chart_type == "PivotTable":
            filters.update({
                "index_col1": get(chart_index_col1s, flat_idx, ""),
                "columns": get(chart_columns, flat_idx, ""),
                "aggfunc": get(chart_aggfuncs, flat_idx, "count"),
                "values_col": get(chart_values_cols, flat_idx, ""),
            })
        
        return {
            "id": chart_id,
            "name": get(chart_names, flat_idx, ""),
            "type": chart_type,
            "filters": filters
        }

    def render_sections(sections):
        return [create_section(s, i) for i, s in enumerate(sections)]

    # Handle triggers
    if triggered_id == "add-section-btn":
        if add_section_clicks and add_section_clicks > 0:
            dashboards_data, dashboard, counts, sections = _load_dashboard(selector_value)
            if dashboard is None:
                raise PreventUpdate
            
            new_section_index = len(sections)
            new_section = {
                "section_name": f"Section {new_section_index + 1}",
                "items": [
                    {
                        "id": f"chart_{uuid.uuid4().hex[:8]}",
                        "name": "",
                        "type": "Bar",
                        "filters": {}
                    }
                ]
            }
            
            sections.append(new_section)
            dashboard["visualization_types"]["charts"]["sections"] = sections
            dashboards_data[selector_value] = dashboard
            save_dashboards_to_file(dashboards_data)
            return render_sections(sections)
        raise PreventUpdate

    if isinstance(triggered_id, dict) and triggered_id.get("type") == "remove-section":
        if not any(c for c in (remove_section_clicks or []) if c and c > 0):
            raise PreventUpdate
        
        section_ui_idx = triggered_id["index"]
        dashboards_data, dashboard, counts, sections = _load_dashboard(selector_value)
        if dashboard is None:
            raise PreventUpdate
        
        if 0 <= section_ui_idx < len(sections):
            sections.pop(section_ui_idx)
            dashboard["visualization_types"]["charts"]["sections"] = sections
            dashboards_data[selector_value] = dashboard
            save_dashboards_to_file(dashboards_data)
        
        return render_sections(sections)
 
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "add-chart-btn":
        if not any(c for c in (add_chart_clicks or []) if c and c > 0):
            raise PreventUpdate
        
        section_ui_idx = triggered_id["index"]
        dashboards_data, dashboard, counts, sections = _load_dashboard(selector_value)
        if dashboard is None:
            raise PreventUpdate
        
        if 0 <= section_ui_idx < len(sections):
            new_chart = {
                "id": f"chart_{uuid.uuid4().hex[:8]}",
                "name": "",
                "type": "Bar",
                "filters": {}
            }
            sections[section_ui_idx].setdefault("items", []).append(new_chart)
            dashboard["visualization_types"]["charts"]["sections"] = sections
            dashboards_data[selector_value] = dashboard
            save_dashboards_to_file(dashboards_data)
        
        return render_sections(sections)
 
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "save-chart":
        if not any(c for c in (save_chart_clicks or []) if c and c > 0):
            raise PreventUpdate
        
        section_ui_idx = triggered_id["section"]
        chart_ui_idx = triggered_id["index"]
        
        dashboards_data, dashboard, counts, sections = _load_dashboard(selector_value)
        if dashboard is None:
            raise PreventUpdate
        
        # Validate section and chart
        if section_ui_idx >= len(sections):
            raise PreventUpdate
        
        items = sections[section_ui_idx].get("items", [])
        if chart_ui_idx >= len(items):
            raise PreventUpdate
        
        
        # Calculate flat index
        flat_idx = calculate_flat_index(section_ui_idx, chart_ui_idx)
        if flat_idx is None:
            raise PreventUpdate
        
        # Update section name
        section_name = get(section_names, section_ui_idx, "")
        if section_name and section_name.strip():
            sections[section_ui_idx]["section_name"] = section_name
        
        # Build and save chart
        form_data = items[chart_ui_idx]
        chart_id = form_data.get("id", f"chart_{uuid.uuid4().hex[:8]}")
        updated_chart = build_chart_data_from_index(section_ui_idx, chart_id, flat_idx,form_data )
        
        if updated_chart:
            items[chart_ui_idx] = updated_chart
            sections[section_ui_idx]["items"] = items
            dashboard["visualization_types"]["charts"]["sections"] = sections
            dashboards_data[selector_value] = dashboard
            save_dashboards_to_file(dashboards_data)
        
        return render_sections(sections)
 
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "remove-chart":
        if not any(c for c in (remove_chart_clicks or []) if c and c > 0):
            raise PreventUpdate
        
        section_ui_idx = triggered_id["section"]
        chart_ui_idx = triggered_id["index"]
        
        dashboards_data, dashboard, counts, sections = _load_dashboard(selector_value)
        if dashboard is None:
            raise PreventUpdate
        
        if section_ui_idx < len(sections):
            items = sections[section_ui_idx].get("items", [])
            if 0 <= chart_ui_idx < len(items):
                items.pop(chart_ui_idx)
            
            if len(items) == 0:
                sections.pop(section_ui_idx)
            else:
                sections[section_ui_idx]["items"] = items
            
            dashboard["visualization_types"]["charts"]["sections"] = sections
            dashboards_data[selector_value] = dashboard
            save_dashboards_to_file(dashboards_data)
        
        return render_sections(sections)
 
    raise PreventUpdate

@callback(
    Output({"type": "chart-fields", "section": dash.MATCH, "index": dash.MATCH}, "children"),
    [Input({"type": "chart-type", "section": dash.MATCH, "index": dash.MATCH}, "value")],
    prevent_initial_call=True
)
def update_chart_fields(chart_type):
    if not chart_type:
        return dash.no_update
    
    triggered_id = ctx.triggered_id
    section_index = triggered_id['section']
    chart_index = triggered_id['index']
    
    # Load existing chart data to preserve values
    try:
        dashboards_data = load_dashboards_from_file()
        if dashboards_data and len(dashboards_data) > 0:
            # Find the current dashboard (you may need to track which dashboard is active)
            # For now, we'll assume the first dashboard or you need to pass the selector value
            current_dashboard = dashboards_data[0]  # This needs to be dynamic
            
            sections = current_dashboard.get("visualization_types", {}).get("charts", {}).get("sections", [])
            if section_index < len(sections):
                items = sections[section_index].get("items", [])
                if chart_index < len(items):
                    existing_chart = items[chart_index]
                    return create_chart_fields(chart_type, existing_chart, section_index, chart_index)
    except Exception as e:
        print(f"Error loading existing chart data: {e}")
    
    return create_chart_fields(chart_type, None, section_index, chart_index)

# @callback(
#     [Output("dashboard-selector", "options", allow_duplicate=True),
#      Output("modal-backdrop", "style", allow_duplicate=True),
#      Output("modal-content", "style", allow_duplicate=True)],
#     [Input("save-btn", "n_clicks")],
#     [State("dashboard-selector", "value"),  # Get selected dashboard from dropdown
#      State("report-name-input", "value"),
#      State("report-id-input", "value"),
#      State("date-created-input", "value"),
#      # Count states
#      State({"type": "count-id", "index": dash.ALL}, "value"),
#      State({"type": "count-name", "index": dash.ALL}, "value"),
#      State({"type": "count-unique", "index": dash.ALL}, "value"),
#      State({"type": "count-var1", "index": dash.ALL}, "value"),
#      State({"type": "count-val1", "index": dash.ALL}, "value"),
#      State({"type": "count-var2", "index": dash.ALL}, "value"),
#      State({"type": "count-val2", "index": dash.ALL}, "value"),
#      State({"type": "count-var3", "index": dash.ALL}, "value"),
#      State({"type": "count-val3", "index": dash.ALL}, "value"),
#      State({"type": "count-var4", "index": dash.ALL}, "value"),
#      State({"type": "count-val4", "index": dash.ALL}, "value"),

#      State({"type": "count-var5", "index": dash.ALL}, "value"),
#      State({"type": "count-val5", "index": dash.ALL}, "value"),
#      State({"type": "count-var6", "index": dash.ALL}, "value"),
#      State({"type": "count-val6", "index": dash.ALL}, "value"),
#      State({"type": "count-var7", "index": dash.ALL}, "value"),
#      State({"type": "count-val7", "index": dash.ALL}, "value"),
#      State({"type": "count-var8", "index": dash.ALL}, "value"),
#      State({"type": "count-val8", "index": dash.ALL}, "value"),
#      # Section states
#      State({"type": "section-name", "index": dash.ALL}, "value"),
#      # Chart states - IMPORTANT: We need to get the actual section and chart indices
#      State({"type": "chart-id", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-name", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-type", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-title", "section": dash.ALL, "index": dash.ALL}, "value"),
#      # Chart field states - include the IDs to track which chart they belong to
#      State({"type": "chart-date_col", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-y_col", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-x_title", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-y_title", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-unique_column", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-legend_title", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-color", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-label_col", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-value_col", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-top_n", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-names_col", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-values_col", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-x_col", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-age_col", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-gender_col", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-bin_size", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-index_col1", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-columns", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-aggfunc", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-duration_default", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-colormap", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-filter_col1", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-filter_val1", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-filter_col2", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-filter_val2", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-filter_col3", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-filter_val3", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-filter_col4", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-filter_val4", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-filter_col5", "section": dash.ALL, "index": dash.ALL}, "value"),
#      State({"type": "chart-filter_val5", "section": dash.ALL, "index": dash.ALL}, "value")],
#     prevent_initial_call=True
# )
# def save_dashboard(save_clicks, selector_value, report_name, report_id, date_created, 
#                   count_ids, count_names, count_uniques,
#                   count_vars1, count_vals1, count_vars2, count_vals2, count_vars3, count_vals3, count_vars4, count_vals4,
#                   count_vars5, count_vals5, count_vars6, count_vals6, count_vars7, count_vals7, count_vars8, count_vals8,
#                   section_names,
#                   chart_ids, chart_names, chart_types, chart_titles,
#                   chart_date_cols, chart_y_cols, chart_x_titles, chart_y_titles,
#                   chart_unique_columns, chart_legend_titles, chart_colors,
#                   chart_label_cols, chart_value_cols, chart_top_ns,
#                   chart_names_cols, chart_values_cols, chart_x_cols,
#                   chart_age_cols, chart_gender_cols, chart_bin_sizes,
#                   chart_index_col1s, chart_columns, chart_aggfuncs,
#                   chart_duration_defaults, chart_colormaps,
#                   chart_filter_col1s, chart_filter_val1s, chart_filter_col2s, chart_filter_val2s,
#                   chart_filter_col3s, chart_filter_val3s, chart_filter_col4s, chart_filter_val4s,
#                   chart_filter_col5s, chart_filter_val5s):
    
#     def load_dashboards_from_file():
#         try:
#             with open(dashboards_json_path, 'r') as f:
#                 data = json.load(f)
#                 return data if isinstance(data, list) else [data]
#         except (FileNotFoundError, json.JSONDecodeError):
#             return []
#     def save_dashboards_to_file(data):
#         with open(dashboards_json_path, 'w') as f:
#             json.dump(data, f, indent=2)
        
#     if save_clicks and save_clicks > 0:
#         if not report_name:
#             # Show error - you might want to add an error output
#             return dash.no_update, dash.no_update, dash.no_update
#         # Load current data from file


#         dashboards_data = load_dashboards_from_file()
        
#         # 1. Build counts data from UI state
#         counts_data = []
#         if count_ids and count_names:
#             for i, (count_id, count_name) in enumerate(zip(count_ids, count_names)):
#                 if count_id and count_name:
#                     count_data = {
#                         "id": count_id,
#                         "name": count_name,
#                         "filters": {
#                             "measure": "count",
#                             "unique": count_uniques[i] if i < len(count_uniques) and count_uniques[i] else "person_id"
#                         }
#                     }
                    
#                     # Add filters if provided
#                     if i < len(count_vars1) and count_vars1[i]:
#                         count_data["filters"]["variable1"] = count_vars1[i]
#                     if i < len(count_vals1) and count_vals1[i]:
#                         count_data["filters"]["value1"] = count_vals1[i]
                    
#                     if i < len(count_vars2) and count_vars2[i]:
#                         count_data["filters"]["variable2"] = count_vars2[i]
#                     if i < len(count_vals2) and count_vals2[i]:
#                         count_data["filters"]["value2"] = count_vals2[i]
                    
#                     if i < len(count_vars3) and count_vars3[i]:
#                         count_data["filters"]["variable3"] = count_vars3[i]
#                     if i < len(count_vals3) and count_vals3[i]:
#                         count_data["filters"]["value3"] = count_vals3[i]

#                     if i < len(count_vars4) and count_vars4[i]:
#                         count_data["filters"]["variable4"] = count_vars4[i]
#                     if i < len(count_vals4) and count_vals4[i]:
#                         count_data["filters"]["value4"] = count_vals4[i]
#                     if i < len(count_vars5) and count_vars5[i]:
#                         count_data["filters"]["variable5"] = count_vars5[i]
#                     if i < len(count_vals5) and count_vals5[i]:
#                         count_data["filters"]["value5"] = count_vals5[i]
#                     if i < len(count_vars6) and count_vars6[i]:
#                         count_data["filters"]["variable6"] = count_vars6[i]
#                     if i < len(count_vals6) and count_vals6[i]:
#                         count_data["filters"]["value6"] = count_vals6[i]
#                     if i < len(count_vars7) and count_vars7[i]:
#                         count_data["filters"]["variable7"] = count_vars7[i]
#                     if i < len(count_vals7) and count_vals7[i]:
#                         count_data["filters"]["value7"] = count_vals7[i]
#                     if i < len(count_vars8) and count_vars8[i]:
#                         count_data["filters"]["variable8"] = count_vars8[i]
#                     if i < len(count_vals8) and count_vals8[i]:
#                         count_data["filters"]["value8"] = count_vals8[i]
                    
#                     counts_data.append(count_data)
        
#         # 2. Build sections data - FIXED VERSION
#         sections_data = []
        
#         # First, organize charts by their actual section indices
#         # We need to extract section and chart indices from the pattern IDs
#         charts_by_section = {}
        
#         # Process all charts with their section assignments
#         for i in range(len(chart_ids)):
#             # Get the actual section and chart index from the pattern IDs
#             # This assumes the IDs follow the pattern from create_chart_item
#             section_idx = None
#             chart_idx = None
            
#             # Try to extract from the chart_id if it contains the info
#             # Or we need to track this differently - let's use a different approach
            
#             # Since we can't easily extract from IDs, we'll use a different strategy
#             # We'll create charts first, then assign them to sections based on index
            
#             if chart_ids[i] and chart_names[i] and chart_types[i]:
#                 chart_data = {
#                     "id": chart_ids[i],
#                     "name": chart_names[i],
#                     "type": chart_types[i],
#                     "filters": {
#                         "measure": "nunique",
#                         "unique": "any",
#                         "duration_default": "any"
#                     }
#                 }
                
#                 # Add title if available
#                 if i < len(chart_titles) and chart_titles[i]:
#                     chart_data["filters"]["title"] = chart_titles[i]
                
#                 # Add duration_default
#                 if i < len(chart_duration_defaults) and chart_duration_defaults[i]:
#                     chart_data["filters"]["duration_default"] = chart_duration_defaults[i]
                
#                 # Add chart type specific fields
#                 chart_type = chart_types[i]

#                 # Access values when list is less than i
#                 def get_safe_value(lst, default=None, index=i):
#                     """
#                     Pop and return the first item from a list.
#                     If the list is empty or None, return default.
#                     """
#                     try:
#                         if index < len(lst):
#                             return lst[index]
#                         else:
#                             return lst.pop(0)
#                     except (IndexError, TypeError):
#                         return default

#                 # Update all chart types with safe access
#                 if chart_type == "Line":
#                     chart_data["filters"]["date_col"] = get_safe_value(chart_date_cols, i)
#                     chart_data["filters"]["y_col"] = get_safe_value(chart_y_cols, i)
#                     chart_data["filters"]["title"] = get_safe_value(chart_titles, i)
#                     chart_data["filters"]["x_title"] = get_safe_value(chart_x_titles, i)
#                     chart_data["filters"]["y_title"] = get_safe_value(chart_y_titles, i)
#                     chart_data["filters"]["unique_column"] = get_safe_value(chart_unique_columns, i)
#                     chart_data["filters"]["legend_title"] = get_safe_value(chart_legend_titles, i)
#                     chart_data["filters"]["color"] = get_safe_value(chart_colors, i)
#                     chart_data["filters"]["filter_col1"] = get_safe_value(chart_filter_col1s, i)
#                     chart_data["filters"]["filter_val1"] = get_safe_value(chart_filter_val1s, i)
#                     chart_data["filters"]["filter_col2"] = get_safe_value(chart_filter_col2s, i)
#                     chart_data["filters"]["filter_val2"] = get_safe_value(chart_filter_val2s, i)
#                     chart_data["filters"]["filter_col3"] = get_safe_value(chart_filter_col3s, i)
#                     chart_data["filters"]["filter_val3"] = get_safe_value(chart_filter_val3s, i)
#                     chart_data["filters"]["filter_col4"] = get_safe_value(chart_filter_col4s, i)
#                     chart_data["filters"]["filter_val4"] = get_safe_value(chart_filter_val4s, i)
#                     chart_data["filters"]["filter_col5"] = get_safe_value(chart_filter_col5s, i)
#                     chart_data["filters"]["filter_val5"] = get_safe_value(chart_filter_val5s, i)


#                 elif chart_type == "Bar":
#                     chart_data["filters"]["label_col"] = get_safe_value(chart_label_cols, i)
#                     chart_data["filters"]["value_col"] = get_safe_value(chart_value_cols, i)
#                     chart_data["filters"]["title"] = get_safe_value(chart_titles, i)
#                     chart_data["filters"]["x_title"] = get_safe_value(chart_x_titles, i)
#                     chart_data["filters"]["y_title"] = get_safe_value(chart_y_titles, i)
#                     chart_data["filters"]["unique_column"] = get_safe_value(chart_unique_columns, i)
#                     chart_data["filters"]["top_n"] = get_safe_value(chart_top_ns, i)
#                     chart_data["filters"]["filter_col1"] = get_safe_value(chart_filter_col1s, i)
#                     chart_data["filters"]["filter_val1"] = get_safe_value(chart_filter_val1s, i)
#                     chart_data["filters"]["filter_col2"] = get_safe_value(chart_filter_col2s, i)
#                     chart_data["filters"]["filter_val2"] = get_safe_value(chart_filter_val2s, i)
#                     chart_data["filters"]["filter_col3"] = get_safe_value(chart_filter_col3s, i)
#                     chart_data["filters"]["filter_val3"] = get_safe_value(chart_filter_val3s, i)
#                     chart_data["filters"]["filter_col4"] = get_safe_value(chart_filter_col4s, i)
#                     chart_data["filters"]["filter_val4"] = get_safe_value(chart_filter_val4s, i)
#                     chart_data["filters"]["filter_col5"] = get_safe_value(chart_filter_col5s, i)
#                     chart_data["filters"]["filter_val5"] = get_safe_value(chart_filter_val5s, i)

#                 elif chart_type == "Pie":
#                     chart_data["filters"]["names_col"] = get_safe_value(chart_names_cols, i)
#                     chart_data["filters"]["values_col"] = get_safe_value(chart_values_cols, i)
#                     chart_data["filters"]["title"] = get_safe_value(chart_titles, i)
#                     chart_data["filters"]["unique_column"] = get_safe_value(chart_unique_columns, i)
#                     chart_data["filters"]["colormap"] = get_safe_value(chart_colormaps, i)
#                     chart_data["filters"]["filter_col1"] = get_safe_value(chart_filter_col1s, i)
#                     chart_data["filters"]["filter_val1"] = get_safe_value(chart_filter_val1s, i)
#                     chart_data["filters"]["filter_col2"] = get_safe_value(chart_filter_col2s, i)
#                     chart_data["filters"]["filter_val2"] = get_safe_value(chart_filter_val2s, i)
#                     chart_data["filters"]["filter_col3"] = get_safe_value(chart_filter_col3s, i)
#                     chart_data["filters"]["filter_val3"] = get_safe_value(chart_filter_val3s, i)
#                     chart_data["filters"]["filter_col4"] = get_safe_value(chart_filter_col4s, i)
#                     chart_data["filters"]["filter_val4"] = get_safe_value(chart_filter_val4s, i)
#                     chart_data["filters"]["filter_col5"] = get_safe_value(chart_filter_col5s, i)
#                     chart_data["filters"]["filter_val5"] = get_safe_value(chart_filter_val5s, i)

#                 elif chart_type == "Column":
#                     chart_data["filters"]["x_col"] = get_safe_value(chart_x_cols, i)
#                     chart_data["filters"]["y_col"] = get_safe_value(chart_y_cols, i)
#                     chart_data["filters"]["title"] = get_safe_value(chart_titles, i)
#                     chart_data["filters"]["x_title"] = get_safe_value(chart_x_titles, i)
#                     chart_data["filters"]["y_title"] = get_safe_value(chart_y_titles, i)
#                     chart_data["filters"]["unique_column"] = get_safe_value(chart_unique_columns, i)
#                     chart_data["filters"]["legend_title"] = get_safe_value(chart_legend_titles, i)
#                     chart_data["filters"]["color"] = get_safe_value(chart_colors, i)
#                     chart_data["filters"]["filter_col1"] = get_safe_value(chart_filter_col1s, i)
#                     chart_data["filters"]["filter_val1"] = get_safe_value(chart_filter_val1s, i)
#                     chart_data["filters"]["filter_col2"] = get_safe_value(chart_filter_col2s, i)
#                     chart_data["filters"]["filter_val2"] = get_safe_value(chart_filter_val2s, i)
#                     chart_data["filters"]["filter_col3"] = get_safe_value(chart_filter_col3s, i)
#                     chart_data["filters"]["filter_val3"] = get_safe_value(chart_filter_val3s, i)
#                     chart_data["filters"]["filter_col4"] = get_safe_value(chart_filter_col4s, i)
#                     chart_data["filters"]["filter_val4"] = get_safe_value(chart_filter_val4s, i)
#                     chart_data["filters"]["filter_col5"] = get_safe_value(chart_filter_col5s, i)
#                     chart_data["filters"]["filter_val5"] = get_safe_value(chart_filter_val5s, i)

#                 elif chart_type == "Histogram":
#                     chart_data["filters"]["age_col"] = get_safe_value(chart_age_cols, i)
#                     chart_data["filters"]["gender_col"] = get_safe_value(chart_gender_cols, i)
#                     chart_data["filters"]["title"] = get_safe_value(chart_titles, i)
#                     chart_data["filters"]["x_title"] = get_safe_value(chart_x_cols, i)
#                     chart_data["filters"]["y_title"] = get_safe_value(chart_y_cols, i)
#                     chart_data["filters"]["unique_column"] = get_safe_value(chart_unique_columns, i)
#                     chart_data["filters"]["bin_size"] = get_safe_value(chart_bin_sizes, i)
#                     chart_data["filters"]["color"] = get_safe_value(chart_colors, i)
#                     chart_data["filters"]["filter_col1"] = get_safe_value(chart_filter_col1s, i)
#                     chart_data["filters"]["filter_val1"] = get_safe_value(chart_filter_val1s, i)
#                     chart_data["filters"]["filter_col2"] = get_safe_value(chart_filter_col2s, i)
#                     chart_data["filters"]["filter_val2"] = get_safe_value(chart_filter_val2s, i)
#                     chart_data["filters"]["filter_col3"] = get_safe_value(chart_filter_col3s, i)
#                     chart_data["filters"]["filter_val3"] = get_safe_value(chart_filter_val3s, i)
#                     chart_data["filters"]["filter_col4"] = get_safe_value(chart_filter_col4s, i)
#                     chart_data["filters"]["filter_val4"] = get_safe_value(chart_filter_val4s, i)
#                     chart_data["filters"]["filter_col5"] = get_safe_value(chart_filter_col5s, i)
#                     chart_data["filters"]["filter_val5"] = get_safe_value(chart_filter_val5s, i)

#                 elif chart_type == "PivotTable":
#                     chart_data["filters"]["index_col1"] = get_safe_value(chart_index_col1s, i)
#                     chart_data["filters"]["columns"] = get_safe_value(chart_columns, i)
#                     chart_data["filters"]["title"] = get_safe_value(chart_titles, i)
#                     chart_data["filters"]["x_title"] = get_safe_value(chart_x_cols, i)
#                     chart_data["filters"]["y_title"] = get_safe_value(chart_y_cols, i)
#                     chart_data["filters"]["unique_column"] = get_safe_value(chart_unique_columns, i)
#                     chart_data["filters"]["values_col"] = get_safe_value(chart_values_cols, i)
#                     chart_data["filters"]["aggfunc"] = get_safe_value(chart_aggfuncs, i)
#                     chart_data["filters"]["filter_col1"] = get_safe_value(chart_filter_col1s, i)
#                     chart_data["filters"]["filter_val1"] = get_safe_value(chart_filter_val1s, i)
#                     chart_data["filters"]["filter_col2"] = get_safe_value(chart_filter_col2s, i)
#                     chart_data["filters"]["filter_val2"] = get_safe_value(chart_filter_val2s, i)
#                     chart_data["filters"]["filter_col3"] = get_safe_value(chart_filter_col3s, i)
#                     chart_data["filters"]["filter_val3"] = get_safe_value(chart_filter_val3s, i)
#                     chart_data["filters"]["filter_col4"] = get_safe_value(chart_filter_col4s, i)
#                     chart_data["filters"]["filter_val4"] = get_safe_value(chart_filter_val4s, i)
#                     chart_data["filters"]["filter_col5"] = get_safe_value(chart_filter_col5s, i)
#                     chart_data["filters"]["filter_val5"] = get_safe_value(chart_filter_val5s, i)
                

#                 total_charts_processed = i
                
#                 # Distribute charts to sections based on the number of sections
#                 if section_names:
#                     # Simple distribution: assign charts in order to sections
#                     section_idx = total_charts_processed % len(section_names)
                    
#                     if section_idx not in charts_by_section:
#                         charts_by_section[section_idx] = []
#                     charts_by_section[section_idx].append(chart_data)
        
#         # 3. Create sections with their assigned charts
#         for section_idx, section_name in enumerate(section_names):
#             if section_name:
#                 section_charts = charts_by_section.get(section_idx, [])
#                 section_data = {
#                     "section_name": section_name,
#                     "items": section_charts
#                 }
#                 sections_data.append(section_data)
        
#         # 4. Create complete dashboard structure
#         dashboard_structure = {
#             "report_id": report_id or f"report_{uuid.uuid4().hex[:8]}",
#             "report_name": report_name,
#             "date_created": date_created or datetime.now().strftime("%Y-%m-%d"),
#             "visualization_types": {
#                 "counts": counts_data,
#                 "charts": {
#                     "sections": sections_data
#                 }
#             }
#         }
        
#         # 5. Update or add to dashboards data
#         if selector_value == "new":  # New dashboard
#             dashboards_data.append(dashboard_structure)
#         elif isinstance(selector_value, int) and 0 <= selector_value < len(dashboards_data):
#             # Update existing dashboard
#             dashboards_data[selector_value] = dashboard_structure
#         else:  # Invalid selector, add as new
#             dashboards_data.append(dashboard_structure)
        
#         # 6. Save to file
#         try:
#             save_dashboards_to_file(dashboards_data)
#         except Exception as e:
#             print(f"Error saving dashboard: {e}")
#             # You might want to show an error message to the user
        
#         # 7. Update dropdown options
#         options = [
#             {"label": f"{d.get('report_name', 'Unnamed')}", 
#              "value": idx} 
#             for idx, d in enumerate(dashboards_data)
#         ] + [{"label": "➕ Create New Dashboard", "value": "new"}]
        
#         # 8. Close modal and return updated options
#         return options, {"display": "none"}, {"display": "none"}
    
#     return dash.no_update, dash.no_update, dash.no_update

@callback(
    [Output("dashboard-selector", "options", allow_duplicate=True),
     Output("modal-backdrop", "style", allow_duplicate=True),
     Output("modal-content", "style", allow_duplicate=True)],
    [Input("delete-btn", "n_clicks")],
    [State("current-dashboard-index", "data")],  # Use current index instead of selector value
    prevent_initial_call=True
)
def delete_dashboard(delete_clicks, current_index):
    def load_dashboards_from_file():
        try:
            with open(dashboards_json_path, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, list) else [data]
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    dashboards_data = load_dashboards_from_file()
    if delete_clicks and delete_clicks > 0:
        # Check if we have a valid dashboard to delete
        if current_index is not None and current_index >= 0 and current_index < len(dashboards_data):
            # Remove the dashboard from the data
            dashboards_data.pop(current_index)
            
            # Save the updated data to file
            try:
                with open(dashboards_json_path, 'w') as f:
                    json.dump(dashboards_data, f, indent=2)
            except Exception as e:
                print(f"Error saving after deletion: {e}")
            
            # Update dropdown options
            options = [{"label": f"📋 {d.get('report_name', 'Unnamed')} (ID: {d.get('report_id', '?')})", 
                       "value": i} for i, d in enumerate(dashboards_data)] + \
                      [{"label": "➕ Create New Dashboard", "value": "new"}]
            
            return options, {"display": "none"}, {"display": "none"}
        
        else:
            # If no valid dashboard is selected, just close the modal
            return dash.no_update, {"display": "none"}, {"display": "none"}
    
    return dash.no_update, dash.no_update, dash.no_update

@callback(
    Output("delete-confirmation-modal", "style"),
    Input("delete-confirmation", "data")
)
def toggle_confirmation_modal(show_confirmation):
    if show_confirmation:
        return {"display": "block", "position": "fixed", "top": "50%", "left": "50%", "transform": "translate(-50%, -50%)", "zIndex": "1000", "background": "white", "padding": "20px", "borderRadius": "5px", "boxShadow": "0 2px 10px rgba(0,0,0,0.1)"}
    else:
        return {"display": "none"}
