import dash
from dash import html, dcc, dash_table, Input, Output, State, callback, ctx, MATCH, ALL
from dash.exceptions import PreventUpdate
import json
import os
import uuid
import pandas as pd
from datetime import datetime
from data_storage import DataStorage
import base64
import io
import warnings
warnings.filterwarnings("ignore")
from helpers.modal_functions import (validate_excel_file, load_reports_data, save_reports_data,
                        check_existing_report, get_next_report_id, update_or_create_report,load_excel_file,
                        save_excel_file, update_report_metadata, archive_report,
                        create_count_item,create_chart_item, create_section,create_chart_fields, create_mnid_indicator_item, validate_dashboard_json,
                        upload_dashboard_json,validate_prog_reports_json,upload_prog_reports_json,CHART_TEMPLATES,render_filter_rows,
                        build_reports_table, create_editable_table, create_preview_table,
                        generate_dashboard_items_list, create_edit_modal,
                        _build_ds_list, _build_users_table, create_html_report_modal)
from helpers.config_helper import (load_dashboards_from_file, save_dashboards_to_file,
                        _coerce_list, _normalize_filter_value, _safe_json_loads,
                        _empty_dashboard_structure, _find_dashboard_index,
                        _ensure_dashboard_for_edit, _dashboard_selector_options,
                        _load_datasources, _save_datasources, _list_ssh_keys,
                        _load_user_csv, _load_user_props, _save_user_props,_ssh_dir,
                        _load_facilities, _extract_identifiers, dashboards_json_path)
from config import actual_keys_in_data
from helpers.navigation_callbacks import DEMO_UUID

dash.register_page(__name__, path="/reports_config", title="Admin Dashboard")


# Load existing dashboards
path = os.getcwd()
dashboards_data = load_dashboards_from_file()


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
            # ── Header ────────────────────────────────────────────────────────
            html.Div(style={"display": "flex", "justifyContent": "space-between",
                            "alignItems": "center", "marginBottom": "16px"}, children=[
                html.H3("Preview Data", style={"margin": "0", "color": "#006401"}),
                html.Button("✕ Close", id="close-preview-btn", n_clicks=0,
                            className="btn-secondary btn-small"),
            ]),

            # ── SQL editor ────────────────────────────────────────────────────
            html.Div(style={"marginBottom": "14px"}, children=[
                html.Div(style={"display": "flex", "justifyContent": "space-between",
                                "alignItems": "flex-end", "marginBottom": "6px"}, children=[
                    html.Label("SQL Query - Query should exclude 'LIMIT CLAUSE'. Default Limit is 100 ", className="form-label",
                               style={"fontWeight": "600", "margin": "0"}),
                    html.Span(
                        f""
                        "Column names are validated as you type.",
                        style={"fontSize": "11px", "color": "#6b7280"},
                    ),
                ]),
                dcc.Textarea(
                    id="preview-sql-input",
                    placeholder=(
                        "SELECT person_id, Date, Program, Encounter\n"
                        "FROM data\n"
                        "WHERE Program = 'OPD Program'\n"
                    ),
                    style={
                        "width": "100%", "height": "110px",
                        "fontFamily": "monospace", "fontSize": "13px",
                        "padding": "10px", "border": "1px solid #d1d5db",
                        "borderRadius": "6px", "resize": "vertical",
                        "boxSizing": "border-box",
                    },
                ),
                # ── Live column-name validation ───────────────────────────────
                html.Div(
                    id="preview-col-validation",
                    style={"marginTop": "6px", "fontSize": "12px",
                           "lineHeight": "1.6", "minHeight": "20px"},
                ),
                html.Div(style={"display": "flex", "gap": "10px",
                                "alignItems": "center", "marginTop": "10px"}, children=[
                    html.Button(
                        "▶ Run Query",
                        id="preview-run-btn",
                        n_clicks=0,
                        className="btn-save",
                    ),
                    dcc.Loading(
                        id="preview-loading",
                        type="circle",
                        color="#006401",
                        children=html.Span(id="preview-run-status",
                                           style={"fontSize": "12px", "color": "#6b7280"}),
                    ),
                ]),
            ]),

            html.Hr(style={"borderColor": "#e5e7eb", "margin": "14px 0"}),

            # ── Results ───────────────────────────────────────────────────────
            html.Div(id="preview-data-info", style={"marginBottom": "10px"}),
            html.Div(id="preview-data-table",
                     style={"maxHeight": "420px", "overflowY": "auto"}),
        ], style={
            'backgroundColor': 'white',
            'padding': '28px',
            'borderRadius': '10px',
            'width': '92%',
            'maxWidth': '1500px',
            'maxHeight': '94vh',
            'overflowY': 'auto',
            'margin': 'auto',
        })
    ], id="preview-popup", style={
        'position': 'fixed',
        'top': '0', 'left': '0',
        'width': '100%', 'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.5)',
        'display': 'none',
        'justifyContent': 'center',
        'alignItems': 'center',
        'zIndex': '1000',
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

layout = html.Div(
    style={
        "display": "flex",
        "height": "100vh",
        "overflow": "hidden",
        "background": "#f8f9fa"
    },
    children=[
        dcc.Location(id='url', refresh=False),
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
                            "DataSet Reports",
                            id="dataset-reports-btn",
                            n_clicks=0,
                            className="nav-btn-modern success"
                        ),
                        html.Button(
                            "Upload Report Template",
                            id="add-from-template-btn",
                            n_clicks=0,
                            className="nav-btn-modern"
                        ),
                        html.Button(
                            "Update Reports (GUI)",
                            id="create-reports-gui-btn",
                            n_clicks=0,
                            className="nav-btn-modern"
                        ),
                        html.Button(
                            "Upload Dashboard Template (JSON)",
                            id="add-dashboard-temp-btn",
                            n_clicks=0,
                            className="nav-btn-modern"
                        ),
                        html.Button(
                            "Upload Program Report Template (JSON)",
                            id="add-prog-report-temp-btn",
                            n_clicks=0,
                            className="nav-btn-modern"
                        ),
                        html.Button(
                            "Create Dashboards (GUI)",
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
                        html.Button(
                            "Configure Users",
                            id="configure-users-btn",
                            n_clicks=0,
                            className="nav-btn-modern"
                        ),
                        html.Button(
                            "Configure Data Sources",
                            id="configure-datasources-btn",
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
                # Modals (kept as is but with modern styling)
                reports_table,
                preview_modal,
                upload_excel_popup_modal,
                upload_dashboard_json_popup_modal,
                upload_prog_reports_json_popup_modal,
                archive_popup_modal,
                archive_confirmation_modal,
                create_edit_modal(),
                create_html_report_modal(),

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
                dcc.Store(id="ds-refresh-store",
                          data={"running": False, "pid": None, "start_time": None}),
                dcc.Interval(id="ds-refresh-interval", interval=2000,
                             n_intervals=0, disabled=True),

                # ── Report Builder stores ────────────────────────────────────
                dcc.Store(id="rpt-state", data={"tables": [], "next_id": 1}),
                dcc.Store(id="rpt-sel",   data={"tid": None, "cells": []}),
                dcc.Store(id="rpt-drag-pos", data={}),
                dcc.Store(id="rpt-drag-init-store", data=0),
                dcc.Input(id="rpt-drag-hidden-input", value="{}",
                          style={"display": "none"}),
                dcc.Store(id="rpt-resize-store", data={}),
                dcc.Input(id="rpt-resize-hidden-input", value="{}",
                          style={"display": "none"}),
                dcc.Store(id="rpt-page-name", data=None),
                dcc.Store(id="rpt-variables-store", data={"all": []}),
                dcc.Input(id="rpt-var-drop-hidden", value="{}",
                          style={"display": "none"}),
                dcc.Interval(
                    id='configurations-interval-update-today',
                    interval=10*60*1000,
                    n_intervals=0
                ),

                # ── User Configuration Panel ─────────────────────────────────
                html.Div(
                    id="user-config-panel",
                    style={"display": "none"},
                    children=[
                        html.Div(
                            className="dashboard-card",
                            style={"margin": "16px 0"},
                            children=[
                                html.Div(
                                    className="dashboard-card-header",
                                    style={"display": "flex", "justifyContent": "space-between",
                                           "alignItems": "center"},
                                    children=[
                                        html.H4("Configure Users", className="dashboard-card-title"),
                                        html.Button("✕ Close", id="close-user-config-btn", n_clicks=0,
                                                    className="btn-secondary btn-small"),
                                    ],
                                ),
                                html.Div(
                                    className="dashboard-card-body",
                                    children=[
                                        html.Div(
                                            style={"display": "flex", "gap": "24px", "alignItems": "flex-start"},
                                            children=[

                                                # ── Left: search only ─────────────────────
                                                html.Div(
                                                    style={"flex": "0 0 260px"},
                                                    children=[
                                                        html.Label("Search & Select User",
                                                                   className="form-label"),
                                                        dcc.Dropdown(
                                                            id="user-search-dropdown",
                                                            options=[],
                                                            placeholder="Type to search username...",
                                                            className="modern-dropdown",
                                                            clearable=True,
                                                            searchable=True,
                                                        ),
                                                    ],
                                                ),

                                                # ── Right: form + saved users table ───────
                                                html.Div(
                                                    style={"flex": "1", "display": "flex",
                                                           "flexDirection": "column", "gap": "16px"},
                                                    children=[

                                                        # Placeholder (no user selected)
                                                        html.Div(
                                                            id="user-form-placeholder",
                                                            style={"color": "#9ca3af", "fontSize": "14px",
                                                                   "padding": "24px 0"},
                                                            children="Select a user from the left to configure their access properties.",
                                                        ),

                                                        # Property editor form
                                                        html.Div(
                                                            id="user-property-form",
                                                            style={"display": "none"},
                                                            children=[
                                                                # Row 1: username / uuid / facility_code / role / level
                                                                html.Div(
                                                                    style={"display": "flex", "gap": "12px",
                                                                           "flexWrap": "wrap",
                                                                           "marginBottom": "12px"},
                                                                    children=[
                                                                        html.Div(style={"flex": "1", "minWidth": "160px"}, children=[
                                                                            html.Label("Username", className="form-label"),
                                                                            dcc.Input(id="uc-username", disabled=True,
                                                                                      className="modern-input-disabled",
                                                                                      style={"width": "100%"}),
                                                                        ]),
                                                                        html.Div(style={"flex": "2", "minWidth": "240px"}, children=[
                                                                            html.Label("UUID", className="form-label"),
                                                                            dcc.Input(id="uc-uuid", disabled=True,
                                                                                      className="modern-input-disabled",
                                                                                      style={"width": "100%"}),
                                                                        ]),
                                                                        html.Div(style={"flex": "1", "minWidth": "120px"}, children=[
                                                                            html.Label("Facility Code", className="form-label"),
                                                                            dcc.Input(id="uc-facility-code", disabled=True,
                                                                                      className="modern-input-disabled",
                                                                                      style={"width": "100%"},
                                                                                      placeholder="from CSV"),
                                                                        ]),
                                                                        html.Div(style={"flex": "1", "minWidth": "160px"}, children=[
                                                                            html.Label("Role", className="form-label"),
                                                                            dcc.Dropdown(
                                                                                id="uc-role",
                                                                                options=[],
                                                                                placeholder="Select role",
                                                                                className="modern-dropdown",
                                                                                clearable=False,
                                                                            ),
                                                                        ]),
                                                                        html.Div(style={"flex": "1", "minWidth": "150px"}, children=[
                                                                            html.Label("User Level", className="form-label"),
                                                                            dcc.Dropdown(
                                                                                id="uc-user-level",
                                                                                options=[
                                                                                    {"label": "Facility",  "value": "facility"},
                                                                                    {"label": "District",  "value": "district"},
                                                                                    {"label": "National",  "value": "national"},
                                                                                ],
                                                                                value="facility",
                                                                                clearable=False,
                                                                                className="modern-dropdown",
                                                                            ),
                                                                        ]),
                                                                    ],
                                                                ),

                                                                # Row 2: district + facility (district level only)
                                                                html.Div(
                                                                    id="uc-district-facility-section",
                                                                    style={"display": "none",
                                                                           "marginBottom": "12px"},
                                                                    children=[
                                                                        html.Div(
                                                                            style={"display": "flex", "gap": "12px",
                                                                                   "flexWrap": "wrap"},
                                                                            children=[
                                                                                html.Div(style={"flex": "1", "minWidth": "220px"}, children=[
                                                                                    html.Label("District(s)", className="form-label"),
                                                                                    dcc.Dropdown(
                                                                                        id="uc-district",
                                                                                        options=[],
                                                                                        multi=True,
                                                                                        placeholder="Select district(s)",
                                                                                        className="modern-dropdown",
                                                                                    ),
                                                                                ]),
                                                                                html.Div(style={"flex": "1", "minWidth": "220px"}, children=[
                                                                                    html.Label("Facility Name(s)", className="form-label"),
                                                                                    dcc.Dropdown(
                                                                                        id="uc-facility-name",
                                                                                        options=[],
                                                                                        multi=True,
                                                                                        placeholder="Select facility/facilities (optional)",
                                                                                        className="modern-dropdown",
                                                                                    ),
                                                                                ]),
                                                                            ],
                                                                        ),
                                                                    ],
                                                                ),

                                                                # Action buttons
                                                                html.Div(
                                                                    style={"display": "flex", "gap": "10px",
                                                                           "alignItems": "center",
                                                                           "marginBottom": "4px"},
                                                                    children=[
                                                                        html.Button("💾 Save User",
                                                                                    id="uc-save-btn",
                                                                                    n_clicks=0,
                                                                                    className="btn-save"),
                                                                        html.Button("🗑️ Remove User",
                                                                                    id="uc-remove-btn",
                                                                                    n_clicks=0,
                                                                                    className="btn-danger btn-small"),
                                                                        html.Span(id="uc-save-status",
                                                                                  style={"fontSize": "13px",
                                                                                         "color": "#006401",
                                                                                         "fontWeight": "500"}),
                                                                    ],
                                                                ),
                                                            ],
                                                        ),

                                                        # Configured users table (always visible)
                                                        html.Div(children=[
                                                            html.Div(
                                                                style={"display": "flex",
                                                                       "alignItems": "center",
                                                                       "gap": "8px",
                                                                       "margin": "8px 0 6px"},
                                                                children=[
                                                                    html.Span("Configured Users",
                                                                              style={"fontWeight": "600",
                                                                                     "fontSize": "14px",
                                                                                     "color": "#374151"}),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                id="configured-users-table",
                                                                style={"overflowX": "auto",
                                                                       "borderRadius": "8px",
                                                                       "border": "1px solid #e5e7eb"},
                                                            ),
                                                        ]),

                                                    ],
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),

                # ── Data Sources Panel ───────────────────────────────────────
                html.Div(
                    id="datasource-panel",
                    style={"display": "none"},
                    children=[
                        html.Div(className="dashboard-card", style={"margin": "16px 0"}, children=[
                            html.Div(
                                className="dashboard-card-header",
                                style={"display": "flex", "justifyContent": "space-between",
                                       "alignItems": "center", "flexWrap": "wrap", "gap": "8px"},
                                children=[
                                    html.H4("Configure Data Sources", className="dashboard-card-title"),
                                    # Refresh summary (shown after a run completes)
                                    html.Span(id="ds-refresh-summary",
                                              style={"fontSize": "12px", "color": "#006401",
                                                     "fontStyle": "italic", "flex": "1",
                                                     "textAlign": "center"}),
                                    html.Div(style={"display": "flex", "gap": "8px",
                                                    "alignItems": "center"}, children=[
                                        html.Button("➕ New Data Source", id="ds-new-btn", n_clicks=0,
                                                    className="btn-primary-modern btn-small"),
                                        html.Button("🔄 Refresh Data", id="ds-run-btn", n_clicks=0,
                                                    className="btn-secondary btn-small",
                                                    title="Run data_storage.py to pull fresh data"),
                                        html.Button("✕ Close", id="close-datasource-btn", n_clicks=0,
                                                    className="btn-secondary btn-small"),
                                    ]),
                                ],
                            ),
                            html.Div(className="dashboard-card-body", children=[
                                html.Div(style={"display": "flex", "gap": "24px", "alignItems": "flex-start"}, children=[

                                    # ── Left: saved datasources list ──────────────────────
                                    html.Div(style={"flex": "0 0 280px"}, children=[
                                        html.Label("Saved Data Sources", className="form-label",
                                                   style={"fontWeight": "600"}),
                                        html.Div(
                                            id="ds-list-container",
                                            style={"overflowY": "auto", "maxHeight": "520px",
                                                   "border": "1px solid #e5e7eb", "borderRadius": "8px",
                                                   "marginTop": "8px"},
                                            children=_build_ds_list(_load_datasources()),
                                        ),
                                    ]),

                                    # ── Right: form ───────────────────────────────────────
                                    html.Div(style={"flex": "1", "display": "flex",
                                                    "flexDirection": "column", "gap": "14px"}, children=[

                                        html.Div(id="ds-form-placeholder",
                                                 style={"color": "#9ca3af", "fontSize": "14px",
                                                        "padding": "24px 0"},
                                                 children="Select a data source or click '➕ New Data Source'."),

                                        html.Div(id="ds-form", style={"display": "none"}, children=[

                                            # Hidden UUID store
                                            dcc.Input(id="ds-uuid", style={"display": "none"}),
                                            dcc.Input(id="ds-date-created", style={"display": "none"}),

                                            # ── Identity ──────────────────────────────────
                                            html.Div(className="form-group", children=[
                                                html.Label("Data Source Name *", className="form-label"),
                                                dcc.Input(id="ds-name", placeholder="e.g. Production MAHIS",
                                                          className="modern-input", style={"width": "100%"}),
                                            ]),

                                            # ── DB_CONFIG ─────────────────────────────────
                                            html.Details(open=True, children=[
                                                html.Summary("Database Configuration (DB_CONFIG)",
                                                             style={"fontWeight": "600", "cursor": "pointer",
                                                                    "color": "#006401", "padding": "6px 0"}),
                                                html.Div(style={"display": "flex", "gap": "10px",
                                                                "flexWrap": "wrap", "marginTop": "10px"}, children=[
                                                    html.Div(style={"flex": "2", "minWidth": "180px"}, children=[
                                                        html.Label("Host", className="form-label"),
                                                        dcc.Input(id="ds-db-host", value="127.0.0.1",
                                                                  className="modern-input", style={"width": "100%"}),
                                                    ]),
                                                    html.Div(style={"flex": "1", "minWidth": "80px"}, children=[
                                                        html.Label("Port", className="form-label"),
                                                        dcc.Input(id="ds-db-port", value="3306", type="number",
                                                                  className="modern-input", style={"width": "100%"}),
                                                    ]),
                                                    html.Div(style={"flex": "2", "minWidth": "160px"}, children=[
                                                        html.Label("Database", className="form-label"),
                                                        dcc.Input(id="ds-db-name", placeholder="database name",
                                                                  className="modern-input", style={"width": "100%"}),
                                                    ]),
                                                    html.Div(style={"flex": "1", "minWidth": "120px"}, children=[
                                                        html.Label("User", className="form-label"),
                                                        dcc.Input(id="ds-db-user", placeholder="db user",
                                                                  className="modern-input", style={"width": "100%"}),
                                                    ]),
                                                    html.Div(style={"flex": "1", "minWidth": "120px"}, children=[
                                                        html.Label("Password", className="form-label"),
                                                        dcc.Input(id="ds-db-password", placeholder="password",
                                                                  type="password",
                                                                  className="modern-input", style={"width": "100%"}),
                                                    ]),
                                                ]),
                                            ]),

                                            # ── SSH_CONFIG ────────────────────────────────
                                            html.Details(children=[
                                                html.Summary("SSH Tunnel Configuration (leave blank for USE_LOCALHOST)",
                                                             style={"fontWeight": "600", "cursor": "pointer",
                                                                    "color": "#006401", "padding": "6px 0"}),
                                                html.Div(style={"marginTop": "10px", "display": "flex",
                                                                "flexDirection": "column", "gap": "10px"}, children=[
                                                    html.Div(style={"display": "flex", "gap": "10px",
                                                                    "flexWrap": "wrap"}, children=[
                                                        html.Div(style={"flex": "2", "minWidth": "180px"}, children=[
                                                            html.Label("SSH Host", className="form-label"),
                                                            dcc.Input(id="ds-ssh-host", placeholder="ec2-xxx.compute.amazonaws.com",
                                                                      className="modern-input", style={"width": "100%"}),
                                                        ]),
                                                        html.Div(style={"flex": "1", "minWidth": "80px"}, children=[
                                                            html.Label("SSH Port", className="form-label"),
                                                            dcc.Input(id="ds-ssh-port", value="22", type="number",
                                                                      className="modern-input", style={"width": "100%"}),
                                                        ]),
                                                        html.Div(style={"flex": "1", "minWidth": "120px"}, children=[
                                                            html.Label("SSH User", className="form-label"),
                                                            dcc.Input(id="ds-ssh-user", value="ubuntu",
                                                                      className="modern-input", style={"width": "100%"}),
                                                        ]),
                                                    ]),
                                                    # Authentication type selector
                                                    html.Div(style={"display": "flex", "gap": "12px",
                                                                    "alignItems": "center"}, children=[
                                                        html.Label("Authentication", className="form-label",
                                                                   style={"marginBottom": "0",
                                                                          "whiteSpace": "nowrap"}),
                                                        dcc.RadioItems(
                                                            id="ds-ssh-auth-type",
                                                            options=[
                                                                {"label": "Key File", "value": "key"},
                                                                {"label": "Password", "value": "password"},
                                                            ],
                                                            value="key",
                                                            inline=True,
                                                            className="form-input",
                                                            inputStyle={"marginRight": "4px"},
                                                            labelStyle={"marginRight": "14px",
                                                                        "fontSize": "13px"},
                                                        ),
                                                    ]),

                                                    # Key file section (shown when auth=key)
                                                    html.Div(id="ds-ssh-key-section", children=[
                                                        html.Label("SSH Key File", className="form-label"),
                                                        html.Div(style={"display": "flex", "gap": "10px",
                                                                        "flexWrap": "wrap",
                                                                        "alignItems": "flex-end"}, children=[
                                                            html.Div(style={"flex": "1"}, children=[
                                                                dcc.Dropdown(id="ds-ssh-pkey-select",
                                                                             placeholder="Select existing .pem / .cer file",
                                                                             className="modern-dropdown",
                                                                             clearable=True),
                                                            ]),
                                                            html.Span("or", style={"padding": "0 6px",
                                                                                   "alignSelf": "center",
                                                                                   "color": "#6b7280"}),
                                                            dcc.Upload(id="ds-ssh-key-upload",
                                                                       children=html.Button(
                                                                           "Upload Key File",
                                                                           className="btn-secondary btn-small"),
                                                                       accept=".pem,.cer,.key"),
                                                        ]),
                                                        html.Span(id="ds-ssh-key-status",
                                                                  style={"fontSize": "12px", "color": "#006401"}),
                                                    ]),

                                                    # Password section (shown when auth=password)
                                                    html.Div(id="ds-ssh-password-section",
                                                             style={"display": "none"}, children=[
                                                        html.Label("SSH Password", className="form-label"),
                                                        dcc.Input(id="ds-ssh-password",
                                                                  placeholder="SSH tunnel password",
                                                                  type="password",
                                                                  className="modern-input",
                                                                  style={"width": "100%"}),
                                                    ]),
                                                    html.Div(style={"display": "flex", "gap": "10px",
                                                                    "flexWrap": "wrap"}, children=[
                                                        html.Div(style={"flex": "2", "minWidth": "180px"}, children=[
                                                            html.Label("Remote Bind Address (host)",
                                                                       className="form-label"),
                                                            dcc.Input(id="ds-ssh-remote-host",
                                                                      placeholder="rds-instance.rds.amazonaws.com",
                                                                      className="modern-input", style={"width": "100%"}),
                                                        ]),
                                                        html.Div(style={"flex": "1", "minWidth": "80px"}, children=[
                                                            html.Label("Remote Port", className="form-label"),
                                                            dcc.Input(id="ds-ssh-remote-port", value="3306",
                                                                      type="number",
                                                                      className="modern-input", style={"width": "100%"}),
                                                        ]),
                                                    ]),
                                                ]),
                                            ]),

                                            # ── Runtime settings ──────────────────────────
                                            html.Details(open=True, children=[
                                                html.Summary("Runtime Settings",
                                                             style={"fontWeight": "600", "cursor": "pointer",
                                                                    "color": "#006401", "padding": "6px 0"}),
                                                html.Div(style={"display": "flex", "gap": "10px",
                                                                "flexWrap": "wrap", "marginTop": "10px"}, children=[
                                                    html.Div(style={"flex": "1", "minWidth": "140px"}, children=[
                                                        html.Label("Start Date", className="form-label"),
                                                        dcc.DatePickerSingle(id="ds-start-date",
                                                                             display_format="YYYY-MM-DD",
                                                                             date="2026-01-01"),
                                                    ]),
                                                    html.Div(style={"flex": "1", "minWidth": "140px"}, children=[
                                                        html.Label("Batch Size", className="form-label"),
                                                        dcc.Input(id="ds-batch-size", value="1000", type="number",
                                                                  className="modern-input", style={"width": "100%"}),
                                                    ]),
                                                    html.Div(style={"flex": "1", "minWidth": "160px"}, children=[
                                                        html.Label("Data File Path *", className="form-label"),
                                                        dcc.Input(id="ds-data-file-name", value="default",
                                                                  placeholder="e.g. default",
                                                                  className="modern-input", style={"width": "100%"}),
                                                    ]),
                                                    html.Div(style={"flex": "1", "minWidth": "160px"}, children=[
                                                        html.Label("Load Fresh Data", className="form-label"),
                                                        dcc.Dropdown(id="ds-load-fresh",
                                                                     options=[{"label": "Yes (always reload)", "value": "true"},
                                                                              {"label": "No (use cache)", "value": "false"}],
                                                                     value="false", clearable=False,
                                                                     className="modern-dropdown"),
                                                    ]),
                                                    html.Div(style={"flex": "1", "minWidth": "160px"}, children=[
                                                        html.Label("Pause Data Source", className="form-label"),
                                                        dcc.Dropdown(id="ds-is-harmonized",
                                                                     options=[{"label": "No", "value": "false"},
                                                                              {"label": "Yes", "value": "true"}],
                                                                     value="false", clearable=False,
                                                                     className="modern-dropdown"),
                                                    ]),
                                                ]),
                                            ]),

                                            # ── Base Query ────────────────────────────────
                                            html.Details(children=[
                                                html.Summary("Base SQL Query",
                                                             style={"fontWeight": "600", "cursor": "pointer",
                                                                    "color": "#006401", "padding": "6px 0"}),
                                                html.Div(style={"marginTop": "10px"}, children=[
                                                    html.Span("Use {date_filter} as a placeholder where the date "
                                                              "range WHERE condition will be injected.",
                                                              style={"fontSize": "12px", "color": "#6b7280"}),
                                                    dcc.Textarea(id="ds-base-query",
                                                                 placeholder="SELECT ... FROM encounter e\n"
                                                                             "...\nWHERE e.voided = 0\n{date_filter}",
                                                                 className="modern-input",
                                                                 style={"width": "100%", "minHeight": "160px",
                                                                        "fontFamily": "monospace",
                                                                        "fontSize": "12px",
                                                                        "resize": "vertical",
                                                                        "marginTop": "8px"}),
                                                ]),
                                            ]),

                                            # ── Actions ───────────────────────────────────
                                            html.Div(style={"display": "flex", "gap": "10px",
                                                            "alignItems": "center", "marginTop": "8px"}, children=[
                                                html.Button("Test Connection", id="ds-test-btn", n_clicks=0,
                                                            className="btn-secondary"),
                                                html.Button("Save", id="ds-save-btn", n_clicks=0,
                                                            className="btn-save"),
                                                html.Button("Delete", id="ds-delete-btn", n_clicks=0,
                                                            className="btn-danger btn-small"),
                                                html.Span(id="ds-status",
                                                          style={"fontSize": "13px", "fontWeight": "500"}),
                                            ]),
                                        ]),
                                    ]),
                                ]),
                            ]),
                        ]),
                    ],
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

@callback(
    Output("current-dashboard-index", "data", allow_duplicate=True),
    Input("dashboard-selector", "value"),
    prevent_initial_call=True
)
def sync_current_dashboard_index(selector_value):
    return selector_value if isinstance(selector_value, int) else -1

@callback(
    Output("mnid-section", "style"),
    Input("dashboard-type-selector", "value"),
    prevent_initial_call=False,
)
def toggle_mnid_section(dashboard_type):
    if dashboard_type == "mnid":
        return {"display": "block"}
    return {"display": "none"}

DATA_ROUTE = ""
# validate admins
@callback(
        [Output('sidebar', 'children'),
         Output('main-content', 'children')],
        [Input('url-params-store', 'data')])
def validate_admin_access(urlparams):
    location = (urlparams.get("Location") or urlparams.get("?Location") or [None])[0]
    data_route = urlparams.get('route', ["default"])[0]
    user_uuid = urlparams.get('uuid', [None])[0]
    DATA_PATH_ = f"data/{data_route}/parquet"

    props_data = _load_user_props(data_route)
    existing   = next((u for u in props_data.get("users", []) if u.get("properties").get("uuid") == user_uuid), None)
    # if not existing:
    #     existing = {"properties": {"role": "none", "uuid": "none"}}
    if existing and existing.get("properties").get("role").strip() == "reports_admin":
        return dash.no_update, dash.no_update
    if not existing:
        if user_uuid == DEMO_UUID:
            return dash.no_update, dash.no_update
        else:
            return dash.no_update, html.Div([
                html.H2("Access Denied"),
                html.P("You do not have permission to access this page. Please log in as an administrator.")], 
                style={'textAlign': 'center', 'marginTop': '100px'})
    return dash.no_update, html.Div([
                html.H2("Access Denied"),
                html.P("You do not have permission to access this page. Please log in as an administrator.")], 
                style={'textAlign': 'center', 'marginTop': '100px'})

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


        # Validate filter column names against the actual report dataset schema.
        valid_filter_columns = {str(col).strip() for col in actual_keys_in_data if str(col).strip()}
        not_correct = sorted({name for name in final_variable_names if name not in valid_filter_columns})
        dry_run_warning = []

        if len(not_correct) > 0:
            dry_run_warning.append(html.Div(
                f"The following filter columns may need to be corrected: {not_correct}",
                style={'color': 'red', 'marginBottom': '5px'}
            ))
        
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
     Output("reports-table-container", "style", allow_duplicate=True)],
    [Input("preview-data", "n_clicks"),
     Input("close-preview-btn", "n_clicks")],
    prevent_initial_call=True,
)
def toggle_preview_popup(preview_clicks, close_clicks):
    trigger_id = ctx.triggered_id
    if trigger_id == "close-preview-btn":
        return {"display": "none"}, {}
    if trigger_id == "preview-data" and preview_clicks:
        return {"display": "flex"}, {"display": "none"}
    return dash.no_update, dash.no_update

# DASHBOARD
@callback(
    [Output("modal-backdrop", "style", allow_duplicate=True),
     Output("modal-content", "style", allow_duplicate=True),
     Output("dashboard-selector", "value", allow_duplicate=True),
     Output("dashboard-selector", "data"),
     Output("report-id-input", "value", allow_duplicate=True),
     Output("report-name-input", "value", allow_duplicate=True),
     Output("date-created-input", "value", allow_duplicate=True),
     Output("dashboard-type-selector", "value", allow_duplicate=True),
     Output("mnid-categories-selector", "value", allow_duplicate=True),
     Output("mnid-indicators-container", "children", allow_duplicate=True),
     Output("mnid-indicators-input", "value", allow_duplicate=True),
     Output("counts-container", "children", allow_duplicate=True),
     Output("sections-container", "children", allow_duplicate=True),
     Output("count-items-per-row-input", "value", allow_duplicate=True)],
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
            "standard",
            [],
            [],
            "",
            [],  # Empty counts
            [],  # Empty sections
            5    # Default counts per row
        )

    elif trigger == "cancel-btn":
        # Just close the modal
        return {"display": "none"}, {"display": "none"}, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    elif trigger == "save-btn":
        # Just close the modal
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    return dash.no_update


@callback(
    [Output("report-id-input", "value", allow_duplicate=True),
     Output("report-name-input", "value", allow_duplicate=True),
     Output("date-created-input", "value", allow_duplicate=True),
     Output("dashboard-type-selector", "value", allow_duplicate=True),
     Output("mnid-categories-selector", "value", allow_duplicate=True),
     Output("mnid-indicators-container", "children", allow_duplicate=True),
     Output("mnid-indicators-input", "value", allow_duplicate=True),
     Output("counts-container", "children", allow_duplicate=True),
     Output("sections-container", "children", allow_duplicate=True),
     Output("count-items-per-row-input", "value", allow_duplicate=True)],
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
                "standard",
                [],
                [],
                "",
                [],
                [],
                5,
            )
        dashboards_data = load_dashboards_from_file()
        if isinstance(selector_value, int) and 0 <= selector_value < len(dashboards_data):
            dashboard = dashboards_data[selector_value]
            priority_indicators = dashboard.get("priority_indicators", [])
            return (
                dashboard.get("report_id", ""),
                dashboard.get("report_name", ""),
                dashboard.get("date_created", ""),
                dashboard.get("dashboard_type", "standard"),
                dashboard.get("mnid_categories", []),
                [create_mnid_indicator_item(ind, i) for i, ind in enumerate(priority_indicators)],
                json.dumps(priority_indicators, indent=2) if priority_indicators else "",
                [],  # clear containers on dashboard switch
                [],
                dashboard.get("count_items_per_row", 5),
            )
        return (dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update)

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
        dashboard.get("dashboard_type", "standard"),
        dashboard.get("mnid_categories", []),
        [create_mnid_indicator_item(ind, i) for i, ind in enumerate(dashboard.get("priority_indicators", []))],
        json.dumps(dashboard.get("priority_indicators", []), indent=2) if dashboard.get("priority_indicators") else "",
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
        return (*meta, count_form, dash.no_update, dash.no_update)

    # ── section-edit ──────────────────────────────────────────────────────────
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "section-edit":
        if not any(c for c in (section_clicks or []) if c and c > 0):
            raise PreventUpdate
        clicked_index = triggered_id["index"]
        try:
            section_form = create_section(sections[clicked_index], clicked_index)
        except (IndexError, Exception):
            section_form = []
        return (*meta, dash.no_update, section_form, dash.no_update)

    # ── chart-edit ────────────────────────────────────────────────────────────
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "chart-edit":
        if not any(c for c in (chart_clicks or []) if c and c > 0):
            raise PreventUpdate
        section_idx = triggered_id["section"]
        chart_idx   = triggered_id["chart"]
        try:
            section_form = create_section(sections[section_idx], section_idx, active_chart_index=chart_idx)
        except (IndexError, Exception):
            section_form = []
        return (*meta, dash.no_update, section_form, dash.no_update)

    raise PreventUpdate


# ── Close buttons for edit forms ─────────────────────────────────────────────
@callback(
    Output("counts-container", "children", allow_duplicate=True),
    Input({"type": "close-count-form", "index": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def close_count_form(n_clicks):
    if not any(c for c in (n_clicks or []) if c and c > 0):
        raise PreventUpdate
    return []


@callback(
    Output("sections-container", "children", allow_duplicate=True),
    Input({"type": "close-section-form", "index": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def close_section_form(n_clicks):
    if not any(c for c in (n_clicks or []) if c and c > 0):
        raise PreventUpdate
    return []


# ── Count: add / save / delete ────────────────────────────────────────────────
@callback(
    Output("counts-container", "children", allow_duplicate=True),
    [Input("add-count-btn", "n_clicks"),
     Input({"type": "save-count",   "index": dash.ALL}, "n_clicks"),
     Input({"type": "remove-count", "index": dash.ALL}, "n_clicks")],
    [State("dashboard-selector", "value"),
     State("report-id-input", "value"),
     State("report-name-input", "value"),
     State("date-created-input", "value"),
     State({"type": "count-id",     "index": dash.ALL}, "value"),
     State({"type": "count-name",   "index": dash.ALL}, "value"),
     State({"type": "count-aggregations","index": dash.ALL}, "value"),
     State({"type": "count-unique", "index": dash.ALL}, "value"),
     State({"type": "count-level",          "index": dash.ALL}, "value"),
     State({"type": "count-flag",           "index": dash.ALL}, "value"),
     State({"type": "count-display-average","index": dash.ALL}, "value"),
     State({"type": "count-href",           "index": dash.ALL}, "value"),
     State({"type": "count-href-name",      "index": dash.ALL}, "value"),
     State({"type": "count-var", "count": dash.ALL, "filter": dash.ALL}, "value"),
     State({"type": "count-val", "count": dash.ALL, "filter": dash.ALL}, "value"),
     State("counts-container", "children")],
    prevent_initial_call=True
)
def manage_counts(add_clicks, save_clicks, remove_clicks,
                  selector_value, report_id, report_name, date_created,
                  count_ids, count_names, count_aggr, count_uniques,
                  count_levels, count_flags, count_display_averages,
                  count_hrefs, count_href_names,
                  count_var_values, count_val_values,
                  current_counts):
    if not ctx.triggered:
        raise PreventUpdate

    triggered_id = ctx.triggered_id
    # Dash returns a dict (not a list) when the container has exactly one child
    if isinstance(current_counts, dict):
        current_counts = [current_counts]
    current_counts = current_counts or []

    # ── Add new blank count to the UI only (saved on "Save Count") ────────────
    if triggered_id == "add-count-btn":
        if add_clicks and add_clicks > 0:
            new_count = create_count_item(index=len(current_counts))
            return current_counts + [new_count]
        raise PreventUpdate

    # ── Save count: update the JSON file by count id ──────────────────────────
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "save-count":
        if not any(c for c in (save_clicks or []) if c and c > 0):
            raise PreventUpdate
        ui_index = triggered_id["index"]
        dashboards_data, dashboard, dashboard_index = _ensure_dashboard_for_edit(
            selector_value, report_id, report_name, date_created
        )
        counts = dashboard.get("visualization_types", {}).get("counts", [])
        count_id = count_ids[0] if count_ids else f"count_{uuid.uuid4().hex[:8]}"

        # ── Build filter pairs from pattern-matched states ────────────────────
        var_state_list = ctx.states_list[-3]  # count-var states
        val_state_list = ctx.states_list[-2]  # count-val states

        # Group by filter index for this specific count (ui_index is the count's actual index)
        pairs = {}
        for s in var_state_list:
            if s["id"]["count"] == ui_index:
                pairs.setdefault(s["id"]["filter"], ["", ""])[0] = s["value"] or ""
        for s in val_state_list:
            if s["id"]["count"] == ui_index:
                pairs.setdefault(s["id"]["filter"], ["", ""])[1] = s["value"] or ""

        filter_dict = {
            "measure":  count_aggr[0]    if len(count_aggr)    > 0 else "nunique",
            "unique":   count_uniques[0] if len(count_uniques) > 0 else "person_id",
        }
        for i, fi in enumerate(sorted(pairs.keys()), start=1):
            var, val = pairs[fi]
            if var:
                filter_dict[f"variable{i}"] = var
                if val not in (None, ""):
                    filter_dict[f"value{i}"] = val

        updated = {
            "id":   count_id,
            "name": count_names[0] if len(count_names) > 0 else "",
            "level":           count_levels[0]           if len(count_levels)           > 0 else "facility",
            "flag":            count_flags[0]             if len(count_flags)            > 0 else None,
            "display_average": count_display_averages[0]  if len(count_display_averages) > 0 else None,
            "href":            count_hrefs[0]             if len(count_hrefs)            > 0 else "",
            "href_name":       count_href_names[0]        if len(count_href_names)       > 0 else "",
            "filters":         filter_dict,
        }
        # Remove None/empty optional top-level fields
        for k in ["flag", "display_average", "href", "href_name"]:
            if updated[k] in (None, ""):
                updated.pop(k)

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
        dashboards_data[dashboard_index] = dashboard
        save_dashboards_to_file(dashboards_data)
        return [create_count_item(c, i) for i, c in enumerate(counts)]

    # ── Delete count: remove from JSON by count id ────────────────────────────
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "remove-count":
        if not any(c for c in (remove_clicks or []) if c and c > 0):
            raise PreventUpdate
        ui_index = triggered_id["index"]
        dashboards_data, dashboard, dashboard_index = _ensure_dashboard_for_edit(
            selector_value, report_id, report_name, date_created
        )
        counts = dashboard.get("visualization_types", {}).get("counts", [])

        count_id = count_ids[0] if count_ids else None
        if count_id:
            counts = [c for c in counts if c.get("id") != count_id]
        else:
            # Fallback: remove by position if id is missing (new unsaved count)
            counts = [c for i, c in enumerate(counts) if i != ui_index]

        dashboard["visualization_types"]["counts"] = counts
        dashboards_data[dashboard_index] = dashboard
        save_dashboards_to_file(dashboards_data)

        return [create_count_item(c, i) for i, c in enumerate(counts)]

    raise PreventUpdate


@callback(
    Output({"type": "count-filters-container", "count": MATCH}, "children"),
    [Input({"type": "count-add-filter",    "count": MATCH}, "n_clicks"),
     Input({"type": "count-remove-filter", "count": MATCH, "filter": ALL}, "n_clicks")],
    [State({"type": "count-var", "count": MATCH, "filter": ALL}, "value"),
     State({"type": "count-val", "count": MATCH, "filter": ALL}, "value")],
    prevent_initial_call=True,
)
def manage_count_filters(add_clicks, remove_clicks, var_values, val_values):
    if not ctx.triggered:
        raise PreventUpdate
    triggered_id = ctx.triggered_id
    count_idx = triggered_id["count"]
    current_pairs = list(zip(
        [v or "" for v in (var_values or [])],
        [v or "" for v in (val_values or [])],
    ))
    if not current_pairs:
        current_pairs = [("", "")]
    if triggered_id.get("type") == "count-add-filter":
        current_pairs.append(("", ""))
    elif triggered_id.get("type") == "count-remove-filter":
        fi = triggered_id["filter"]
        if len(current_pairs) > 1:
            current_pairs = [p for i, p in enumerate(current_pairs) if i != fi]
    return render_filter_rows(count_idx, current_pairs)


@callback(
    [Output("mnid-indicators-container", "children", allow_duplicate=True),
     Output("mnid-indicators-input", "value", allow_duplicate=True)],
    [Input("add-mnid-indicator-btn", "n_clicks"),
     Input({"type": "save-mnid-indicator", "index": dash.ALL}, "n_clicks"),
     Input({"type": "remove-mnid-indicator", "index": dash.ALL}, "n_clicks")],
    [State("dashboard-selector", "value"),
     State("report-id-input", "value"),
     State("report-name-input", "value"),
     State("date-created-input", "value"),
     State({"type": "mnid-indicator-id", "index": dash.ALL}, "value"),
     State({"type": "mnid-indicator-label", "index": dash.ALL}, "value"),
     State({"type": "mnid-indicator-category", "index": dash.ALL}, "value"),
     State({"type": "mnid-indicator-target", "index": dash.ALL}, "value"),
     State({"type": "mnid-indicator-status", "index": dash.ALL}, "value"),
     State({"type": "mnid-indicator-unique", "index": dash.ALL}, "value"),
     State({"type": "mnid-indicator-note", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-var1", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-val1", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-var2", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-val2", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-var3", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-val3", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-var4", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-val4", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-var1", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-val1", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-var2", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-val2", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-var3", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-val3", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-var4", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-val4", "index": dash.ALL}, "value"),
     State("mnid-indicators-container", "children")],
    prevent_initial_call=True
)
def manage_mnid_indicators(add_clicks, save_clicks, remove_clicks,
                           selector_value, report_id, report_name, date_created,
                           indicator_ids, labels, categories, targets, statuses, uniques, notes,
                           n_var1, n_val1, n_var2, n_val2, n_var3, n_val3, n_var4, n_val4,
                           d_var1, d_val1, d_var2, d_val2, d_var3, d_val3, d_var4, d_val4,
                           current_children):
    if not ctx.triggered:
        raise PreventUpdate

    def parse_indicator_value(raw_value):
        if raw_value in (None, ""):
            return ""
        if isinstance(raw_value, (list, dict, int, float)):
            return raw_value
        raw_text = str(raw_value).strip()
        if not raw_text:
            return ""
        if raw_text.startswith("[") or raw_text.startswith("{"):
            try:
                return json.loads(raw_text)
            except json.JSONDecodeError:
                return raw_text
        return raw_text

    def build_filter_block(unique_value, var_values, val_values):
        filters = {"unique": unique_value or "person_id"}
        for pos, (var_list, val_list) in enumerate(zip(var_values, val_values), start=1):
            variable = var_list[ui_index] if ui_index < len(var_list) else None
            value = parse_indicator_value(val_list[ui_index] if ui_index < len(val_list) else "")
            if variable:
                filters[f"variable{pos}"] = variable
                if value not in ("", [], {}):
                    filters[f"value{pos}"] = value
        return filters

    def render(indicators):
        return [create_mnid_indicator_item(ind, i) for i, ind in enumerate(indicators)]

    triggered_id = ctx.triggered_id
    current_children = current_children or []

    if triggered_id == "add-mnid-indicator-btn":
        if add_clicks and add_clicks > 0:
            return current_children + [create_mnid_indicator_item(index=len(current_children))], dash.no_update
        raise PreventUpdate

    dashboards_data, dashboard, dashboard_index = _ensure_dashboard_for_edit(
        selector_value, report_id, report_name, date_created
    )
    indicators = list(dashboard.get("priority_indicators", []))

    if isinstance(triggered_id, dict) and triggered_id.get("type") == "save-mnid-indicator":
        if not any(c for c in (save_clicks or []) if c and c > 0):
            raise PreventUpdate
        ui_index = triggered_id["index"]
        indicator_id = indicator_ids[ui_index] if ui_index < len(indicator_ids) else f"mnid_{uuid.uuid4().hex[:8]}"
        updated = {
            "id": indicator_id,
            "label": labels[ui_index] if ui_index < len(labels) else "",
            "category": categories[ui_index] if ui_index < len(categories) else "",
            "target": targets[ui_index] if ui_index < len(targets) and targets[ui_index] not in (None, "") else 80,
            "status": statuses[ui_index] if ui_index < len(statuses) else "tracked",
            "numerator_filters": build_filter_block(
                uniques[ui_index] if ui_index < len(uniques) else "person_id",
                [n_var1, n_var2, n_var3, n_var4],
                [n_val1, n_val2, n_val3, n_val4],
            ),
            "denominator_filters": build_filter_block(
                uniques[ui_index] if ui_index < len(uniques) else "person_id",
                [d_var1, d_var2, d_var3, d_var4],
                [d_val1, d_val2, d_val3, d_val4],
            ),
        }
        note_value = notes[ui_index] if ui_index < len(notes) else ""
        if note_value:
            updated["note"] = note_value

        matched = False
        for i, indicator in enumerate(indicators):
            if indicator.get("id") == indicator_id:
                indicators[i] = updated
                matched = True
                break
        if not matched and updated["label"]:
            indicators.append(updated)

        dashboard["dashboard_type"] = "mnid"
        dashboard["priority_indicators"] = indicators
        dashboards_data[dashboard_index] = dashboard
        save_dashboards_to_file(dashboards_data)
        return render(indicators), json.dumps(indicators, indent=2)

    if isinstance(triggered_id, dict) and triggered_id.get("type") == "remove-mnid-indicator":
        if not any(c for c in (remove_clicks or []) if c and c > 0):
            raise PreventUpdate
        ui_index = triggered_id["index"]
        indicator_id = indicator_ids[ui_index] if ui_index < len(indicator_ids) else None
        if indicator_id:
            indicators = [item for item in indicators if item.get("id") != indicator_id]
        else:
            indicators = [item for i, item in enumerate(indicators) if i != ui_index]

        dashboard["priority_indicators"] = indicators
        dashboards_data[dashboard_index] = dashboard
        save_dashboards_to_file(dashboards_data)
        return render(indicators), json.dumps(indicators, indent=2) if indicators else ""

    raise PreventUpdate

@callback(
    Output("sections-container", "children", allow_duplicate=True),
    [Input("add-section-btn", "n_clicks"),
     Input({"type": "remove-section", "index": dash.ALL}, "n_clicks"),
     Input({"type": "add-chart-btn",  "index": dash.ALL}, "n_clicks"),
     Input({"type": "save-chart",   "section": dash.ALL, "index": dash.ALL}, "n_clicks"),
     Input({"type": "remove-chart", "section": dash.ALL, "index": dash.ALL}, "n_clicks")],
    [State("dashboard-selector", "value"),
     State("report-id-input", "value"),
     State("report-name-input", "value"),
     State("date-created-input", "value"),
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
     State({"type": "section-chart-items-per-row", "index": dash.ALL}, "value"),
     State({"type": "chart-level", "section": dash.ALL, "index": dash.ALL}, "value"),
     State("sections-container", "children")],
    prevent_initial_call=True
)
def manage_sections(add_section_clicks, remove_section_clicks,
                    add_chart_clicks, save_chart_clicks, remove_chart_clicks,
                    selector_value, report_id, report_name, date_created, section_names,
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
                    section_chart_items_per_row_values, chart_levels,
                    current_sections):
    
    if not ctx.triggered:
        raise PreventUpdate
 
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
            "filter_col1": _normalize_filter_value(get(chart_filter_col1s, flat_idx, [])),
            "filter_val1": _normalize_filter_value(get(chart_filter_val1s, flat_idx, "")),
            "filter_col2": _normalize_filter_value(get(chart_filter_col2s, flat_idx, [])),
            "filter_val2": _normalize_filter_value(get(chart_filter_val2s, flat_idx, "")),
            "filter_col3": _normalize_filter_value(get(chart_filter_col3s, flat_idx, [])),
            "filter_val3": _normalize_filter_value(get(chart_filter_val3s, flat_idx, "")),
            "filter_col4": _normalize_filter_value(get(chart_filter_col4s, flat_idx, [])),
            "filter_val4": _normalize_filter_value(get(chart_filter_val4s, flat_idx, "")),
            "filter_col5": _normalize_filter_value(get(chart_filter_col5s, flat_idx, [])),
            "filter_val5": _normalize_filter_value(get(chart_filter_val5s, flat_idx, "")),
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
                "colormap": _safe_json_loads(get(chart_colormaps, flat_idx, {}), {})
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
                "index_col1": _normalize_filter_value(get(chart_index_col1s, flat_idx, "")),
                "columns": _normalize_filter_value(get(chart_columns, flat_idx, "")),
                "aggfunc": get(chart_aggfuncs, flat_idx, "count"),
                "values_col": get(chart_values_cols, flat_idx, ""),
            })
        
        return {
            "id": chart_id,
            "name": get(chart_names, flat_idx, ""),
            "type": chart_type,
            "level": get(chart_levels, flat_idx, "facility"),
            "filters": filters
        }

    def render_sections(sections, active_state=None):
        """Render sections; active_state = {section_idx: chart_idx} controls which chart is open."""
        active_state = active_state or {}
        return [create_section(s, i, active_chart_index=active_state.get(i)) for i, s in enumerate(sections)]

    # Handle triggers
    if triggered_id == "add-section-btn":
        if add_section_clicks and add_section_clicks > 0:
            dashboards_data, dashboard, dashboard_index = _ensure_dashboard_for_edit(
                selector_value, report_id, report_name, date_created
            )
            sections = dashboard.get("visualization_types", {}).get("charts", {}).get("sections", [])

            new_section_index = len(sections)
            new_section = {
                "section_name": f"Section {new_section_index + 1}",
                "chart_items_per_row": 2,
                "items": [
                    {
                        "id": f"chart_{uuid.uuid4().hex[:8]}",
                        "name": "",
                        "type": "Bar",
                        "level": "facility",
                        "filters": {}
                    }
                ]
            }

            sections.append(new_section)
            dashboard["visualization_types"]["charts"]["sections"] = sections
            dashboards_data[dashboard_index] = dashboard
            save_dashboards_to_file(dashboards_data)
            # Open the blank chart that was just created in the new section
            return render_sections(sections, {new_section_index: 0})
        raise PreventUpdate

    if isinstance(triggered_id, dict) and triggered_id.get("type") == "remove-section":
        if not any(c for c in (remove_section_clicks or []) if c and c > 0):
            raise PreventUpdate

        section_ui_idx = triggered_id["index"]
        dashboards_data, dashboard, dashboard_index = _ensure_dashboard_for_edit(
            selector_value, report_id, report_name, date_created
        )
        sections = dashboard.get("visualization_types", {}).get("charts", {}).get("sections", [])

        if 0 <= section_ui_idx < len(sections):
            sections.pop(section_ui_idx)
            dashboard["visualization_types"]["charts"]["sections"] = sections
            dashboards_data[dashboard_index] = dashboard
            save_dashboards_to_file(dashboards_data)

        return render_sections(sections)

    if isinstance(triggered_id, dict) and triggered_id.get("type") == "add-chart-btn":
        if not any(c for c in (add_chart_clicks or []) if c and c > 0):
            raise PreventUpdate

        section_ui_idx = triggered_id["index"]
        dashboards_data, dashboard, dashboard_index = _ensure_dashboard_for_edit(
            selector_value, report_id, report_name, date_created
        )
        sections = dashboard.get("visualization_types", {}).get("charts", {}).get("sections", [])

        if 0 <= section_ui_idx < len(sections):
            new_chart = {
                "id": f"chart_{uuid.uuid4().hex[:8]}",
                "name": "",
                "type": "Bar",
                "filters": {}
            }
            sections[section_ui_idx].setdefault("items", []).append(new_chart)
            dashboard["visualization_types"]["charts"]["sections"] = sections
            dashboards_data[dashboard_index] = dashboard
            save_dashboards_to_file(dashboards_data)
            # Show only the new blank chart; hide any previously open chart
            new_chart_idx = len(sections[section_ui_idx]["items"]) - 1
            return render_sections(sections, {section_ui_idx: new_chart_idx})

        return render_sections(sections)

    if isinstance(triggered_id, dict) and triggered_id.get("type") == "save-chart":
        if not any(c for c in (save_chart_clicks or []) if c and c > 0):
            raise PreventUpdate

        section_ui_idx = triggered_id["section"]
        chart_ui_idx = triggered_id["index"]

        dashboards_data, dashboard, dashboard_index = _ensure_dashboard_for_edit(
            selector_value, report_id, report_name, date_created
        )
        sections = dashboard.get("visualization_types", {}).get("charts", {}).get("sections", [])

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

        # Update section chart_items_per_row
        raw_cipr = get(section_chart_items_per_row_values, section_ui_idx, 2)
        sections[section_ui_idx]["chart_items_per_row"] = int(raw_cipr or 2)

        # Build and save chart
        form_data = items[chart_ui_idx]
        chart_id = form_data.get("id", f"chart_{uuid.uuid4().hex[:8]}")
        updated_chart = build_chart_data_from_index(section_ui_idx, chart_id, flat_idx, form_data)

        if updated_chart:
            items[chart_ui_idx] = updated_chart
            sections[section_ui_idx]["items"] = items
            dashboard["visualization_types"]["charts"]["sections"] = sections
            dashboards_data[dashboard_index] = dashboard
            save_dashboards_to_file(dashboards_data)

        # Keep the saved chart open after save
        return render_sections(sections, {section_ui_idx: chart_ui_idx})

    if isinstance(triggered_id, dict) and triggered_id.get("type") == "remove-chart":
        if not any(c for c in (remove_chart_clicks or []) if c and c > 0):
            raise PreventUpdate

        section_ui_idx = triggered_id["section"]
        chart_ui_idx = triggered_id["index"]

        dashboards_data, dashboard, dashboard_index = _ensure_dashboard_for_edit(
            selector_value, report_id, report_name, date_created
        )
        sections = dashboard.get("visualization_types", {}).get("charts", {}).get("sections", [])

        if section_ui_idx < len(sections):
            items = sections[section_ui_idx].get("items", [])
            if 0 <= chart_ui_idx < len(items):
                items.pop(chart_ui_idx)

            if len(items) == 0:
                sections.pop(section_ui_idx)
            else:
                sections[section_ui_idx]["items"] = items

            dashboard["visualization_types"]["charts"]["sections"] = sections
            dashboards_data[dashboard_index] = dashboard
            save_dashboards_to_file(dashboards_data)

        return render_sections(sections)
 
    raise PreventUpdate

@callback(
    Output({"type": "chart-fields", "section": dash.MATCH, "index": dash.MATCH}, "children"),
    [Input({"type": "chart-type", "section": dash.MATCH, "index": dash.MATCH}, "value")],
    [State("dashboard-selector", "value"),
     State("report-id-input", "value")],
    prevent_initial_call=True
)
def update_chart_fields(chart_type, selector_value, report_id):
    if not chart_type:
        return dash.no_update
    
    triggered_id = ctx.triggered_id
    section_index = triggered_id['section']
    chart_index = triggered_id['index']
    
    # Load existing chart data to preserve values
    try:
        dashboards_data = load_dashboards_from_file()
        dashboard_index = _find_dashboard_index(dashboards_data, selector_value, report_id)
        if dashboard_index is not None and dashboard_index < len(dashboards_data):
            current_dashboard = dashboards_data[dashboard_index]
            sections = current_dashboard.get("visualization_types", {}).get("charts", {}).get("sections", [])
            if section_index < len(sections):
                items = sections[section_index].get("items", [])
                if chart_index < len(items):
                    existing_chart = items[chart_index]
                    return create_chart_fields(chart_type, existing_chart, section_index, chart_index)
    except Exception as e:
        print(f"Error loading existing chart data: {e}")
    
    return create_chart_fields(chart_type, None, section_index, chart_index)


@callback(
    [Output("dashboard-selector", "options", allow_duplicate=True),
     Output("dashboard-selector", "value", allow_duplicate=True),
     Output("current-dashboard-index", "data", allow_duplicate=True),
     Output("modal-backdrop", "style", allow_duplicate=True),
     Output("modal-content", "style", allow_duplicate=True)],
    Input("save-btn", "n_clicks"),
    [State("dashboard-selector", "value"),
     State("report-id-input", "value"),
     State("report-name-input", "value"),
     State("date-created-input", "value"),
     State("dashboard-type-selector", "value"),
     State("mnid-categories-selector", "value"),
     State("mnid-indicators-input", "value"),
     State("count-items-per-row-input", "value"),
     State({"type": "mnid-indicator-id", "index": dash.ALL}, "value"),
     State({"type": "mnid-indicator-label", "index": dash.ALL}, "value"),
     State({"type": "mnid-indicator-category", "index": dash.ALL}, "value"),
     State({"type": "mnid-indicator-target", "index": dash.ALL}, "value"),
     State({"type": "mnid-indicator-status", "index": dash.ALL}, "value"),
     State({"type": "mnid-indicator-unique", "index": dash.ALL}, "value"),
     State({"type": "mnid-indicator-note", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-var1", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-val1", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-var2", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-val2", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-var3", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-val3", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-var4", "index": dash.ALL}, "value"),
     State({"type": "mnid-numerator-val4", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-var1", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-val1", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-var2", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-val2", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-var3", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-val3", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-var4", "index": dash.ALL}, "value"),
     State({"type": "mnid-denominator-val4", "index": dash.ALL}, "value")],
    prevent_initial_call=True
)
def save_dashboard_config(save_clicks, selector_value, report_id, report_name, date_created,
                          dashboard_type, mnid_categories, mnid_indicators_raw,
                          count_items_per_row,
                          indicator_ids, indicator_labels, indicator_categories, indicator_targets,
                          indicator_statuses, indicator_uniques, indicator_notes,
                          n_var1, n_val1, n_var2, n_val2, n_var3, n_val3, n_var4, n_val4,
                          d_var1, d_val1, d_var2, d_val2, d_var3, d_val3, d_var4, d_val4):
    if not save_clicks:
        raise PreventUpdate

    def parse_indicator_value(raw_value):
        if raw_value in (None, ""):
            return ""
        if isinstance(raw_value, (list, dict, int, float)):
            return raw_value
        raw_text = str(raw_value).strip()
        if not raw_text:
            return ""
        if raw_text.startswith("[") or raw_text.startswith("{"):
            try:
                return json.loads(raw_text)
            except json.JSONDecodeError:
                return raw_text
        return raw_text

    def build_indicator_filters(unique_value, index, var_groups, val_groups):
        filters = {"unique": unique_value or "person_id"}
        for pos, (var_group, val_group) in enumerate(zip(var_groups, val_groups), start=1):
            variable = var_group[index] if index < len(var_group) else None
            value = parse_indicator_value(val_group[index] if index < len(val_group) else "")
            if variable:
                filters[f"variable{pos}"] = variable
                if value not in ("", [], {}):
                    filters[f"value{pos}"] = value
        return filters

    dashboards_data = load_dashboards_from_file()
    dashboard_index = _find_dashboard_index(dashboards_data, selector_value, report_id)

    if dashboard_index is None:
        dashboard = _empty_dashboard_structure(report_id, report_name, date_created)
        dashboards_data.append(dashboard)
        dashboard_index = len(dashboards_data) - 1
    else:
        dashboard = dashboards_data[dashboard_index]

    dashboard["report_id"] = report_id or dashboard.get("report_id") or f"report_{uuid.uuid4().hex[:8]}"
    dashboard["report_name"] = report_name or dashboard.get("report_name") or "New Dashboard"
    dashboard["date_created"] = date_created or dashboard.get("date_created") or datetime.now().strftime("%Y-%m-%d")
    dashboard["count_items_per_row"] = int(count_items_per_row or 5)
    dashboard.setdefault("visualization_types", {})
    dashboard["visualization_types"].setdefault("counts", [])
    dashboard["visualization_types"].setdefault("charts", {})
    dashboard["visualization_types"]["charts"].setdefault("sections", [])

    if dashboard_type == "mnid":
        built_indicators = []
        for i, label in enumerate(indicator_labels or []):
            if not label:
                continue
            indicator = {
                "id": indicator_ids[i] if i < len(indicator_ids) and indicator_ids[i] else f"mnid_{uuid.uuid4().hex[:8]}",
                "label": label,
                "category": indicator_categories[i] if i < len(indicator_categories) else "",
                "target": indicator_targets[i] if i < len(indicator_targets) and indicator_targets[i] not in (None, "") else 80,
                "status": indicator_statuses[i] if i < len(indicator_statuses) and indicator_statuses[i] else "tracked",
                "numerator_filters": build_indicator_filters(
                    indicator_uniques[i] if i < len(indicator_uniques) else "person_id",
                    i,
                    [n_var1, n_var2, n_var3, n_var4],
                    [n_val1, n_val2, n_val3, n_val4],
                ),
                "denominator_filters": build_indicator_filters(
                    indicator_uniques[i] if i < len(indicator_uniques) else "person_id",
                    i,
                    [d_var1, d_var2, d_var3, d_var4],
                    [d_val1, d_val2, d_val3, d_val4],
                ),
            }
            if i < len(indicator_notes) and indicator_notes[i]:
                indicator["note"] = indicator_notes[i]
            built_indicators.append(indicator)

        dashboard["dashboard_type"] = "mnid"
        dashboard["mnid_categories"] = _coerce_list(mnid_categories)
        dashboard["priority_indicators"] = built_indicators or _safe_json_loads(mnid_indicators_raw, [])
    else:
        dashboard.pop("dashboard_type", None)
        dashboard.pop("mnid_categories", None)
        dashboard.pop("priority_indicators", None)

    dashboards_data[dashboard_index] = dashboard
    save_dashboards_to_file(dashboards_data)

    return (
        _dashboard_selector_options(dashboards_data),
        dashboard_index,
        dashboard_index,
        {"display": "none"},
        {"display": "none"},
    )

@callback(
    [Output("dashboard-selector", "options", allow_duplicate=True),
     Output("modal-backdrop", "style", allow_duplicate=True),
     Output("modal-content", "style", allow_duplicate=True)],
    [Input("delete-btn", "n_clicks")],
    [State("current-dashboard-index", "data"),
     State("dashboard-selector", "value"),
     State("report-id-input", "value")],
    prevent_initial_call=True
)
def delete_dashboard(delete_clicks, current_index, selector_value, report_id):
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


# 1. Toggle panel visibility — show user config, hide main content area (and vice-versa)
@callback(
    [Output("user-config-panel",  "style"),
     Output("reports-table-container", "style", allow_duplicate=True)],
    [Input("configure-users-btn",  "n_clicks"),
     Input("close-user-config-btn","n_clicks")],
    prevent_initial_call=True,
)
def toggle_user_config_panel(open_clicks, close_clicks):
    if ctx.triggered_id == "configure-users-btn":
        return {"display": "block"}, {"display": "none"}
    return {"display": "none"}, {"display": "block"}


# 2. Populate user search dropdown when panel opens
@callback(
    Output("user-search-dropdown", "options"),
    [Input("user-config-panel", "style"),
    Input('url-params-store', 'data')],
)
def populate_user_dropdown(panel_style, urlparams):
    data_route = urlparams.get('route', ["default"])[0]
    if not panel_style or panel_style.get("display") == "none":
        raise PreventUpdate
    df = _load_user_csv(data_route)
    return [{"label": row["User"], "value": row["User"]} for _, row in df.iterrows()]


# 3. Load user properties into the form when a user is selected
@callback(
    [Output("user-property-form",    "style"),
     Output("user-form-placeholder", "style"),
     Output("uc-username",           "value"),
     Output("uc-uuid",               "value"),
     Output("uc-facility-code",      "value"),
     Output("uc-role",               "options"),
     Output("uc-role",               "value"),
     Output("uc-user-level",         "value"),
     Output("uc-district",           "value"),
     Output("uc-facility-name",      "value")],
    Input("user-search-dropdown", "value"),
    Input('url-params-store', 'data'),
    prevent_initial_call=True,
)
def load_user_into_form(username, urlparams):
    route = urlparams.get('route', ["default"])[0]
    placeholder_shown  = {"display": "block", "color": "#9ca3af",
                          "fontSize": "14px", "padding": "24px 0"}
    placeholder_hidden = {"display": "none"}

    if not username:
        return ({"display": "none"}, placeholder_shown,
                "", "", "", [], None, "facility", [], [])

    df = _load_user_csv(route)
    user_row = df[df["User"] == username]
    csv_uuid = ""
    csv_location = ""
    csv_roles = []
    if not user_row.empty:
        row = user_row.iloc[0]
        csv_uuid     = str(row.get("uuid",        "") or "")
        csv_location = str(row.get("location_id", "") or "")
        raw_role     = str(row.get("role",        "") or "")
        csv_roles    = [r.strip() for r in raw_role.replace(";", ",").split(",") if r.strip()]

    all_roles    = list(dict.fromkeys(csv_roles + ["reports_admin"]))
    role_options = [{"label": r, "value": r} for r in all_roles]
    default_role = all_roles[0] if all_roles else "reports_admin"

    # Overlay with any existing saved properties
    props_data = _load_user_props(route)
    existing   = next((u for u in props_data.get("users", []) if u.get("username") == username), None)
    if existing:
        p            = existing.get("properties", {})
        saved_uuid   = p.get("uuid",          csv_uuid)     or csv_uuid
        saved_fcode  = p.get("facility_code", csv_location) or csv_location
        saved_role   = p.get("role",          default_role)
        saved_level  = p.get("user_level",    "facility")
        saved_dist   = p.get("district")      or []
        saved_fac    = p.get("facility_name") or []
        if isinstance(saved_dist, str):
            saved_dist = [saved_dist]
        if isinstance(saved_fac, str):
            saved_fac = [saved_fac]
    else:
        saved_uuid  = csv_uuid
        saved_fcode = csv_location
        saved_role  = default_role
        saved_level = "facility"
        saved_dist  = []
        saved_fac   = []

    return (
        {"display": "block"},
        placeholder_hidden,
        username,
        saved_uuid,
        saved_fcode,
        role_options,
        saved_role,
        saved_level,
        saved_dist,
        saved_fac,
    )


# 4. Show/hide district+facility section based on user level
@callback(
    Output("uc-district-facility-section", "style"),
    Input("uc-user-level", "value"),
)
def toggle_district_section(level):
    if level == "district":
        return {"display": "block"}
    return {"display": "none"}


# 5. Populate district options (always from facilities_dropdowns.json)
@callback(
    Output("uc-district", "options"),
    Input("uc-user-level", "value"),
    Input('url-params-store', 'data')
)
def populate_districts(level, urlparams):
    route = urlparams.get('route', ["default"])[0]
    facilities = _load_facilities(route)
    return [{"label": d, "value": d} for d in sorted(facilities.keys())]


# 6. Cascade: update facility options based on selected districts
@callback(
    Output("uc-facility-name", "options"),
    Input("uc-district", "value"),
    Input('url-params-store', 'data')
)
def update_facility_options(districts, urlparams):
    route = urlparams.get('route', ["default"])[0]
    if not districts:
        return []
    facilities = _load_facilities(route)
    opts = []
    for d in (districts or []):
        for fac in facilities.get(d, []):
            opts.append({"label": f"{fac} ({d})", "value": fac})
    return opts


# 7. Save user properties
@callback(
    [Output("uc-save-status",         "children"),
     Output("configured-users-table", "children")],
    [Input("uc-save-btn", "n_clicks"),
     Input('url-params-store', 'data')],
    [State("uc-username",      "value"),
     State("uc-uuid",          "value"),
     State("uc-facility-code", "value"),
     State("uc-role",          "value"),
     State("uc-user-level",    "value"),
     State("uc-district",      "value"),
     State("uc-facility-name", "value")],
    prevent_initial_call=True,
)
def save_user_properties(n_clicks,urlparams, username, uuid_val, facility_code, role, user_level, districts, facilities):
    route = urlparams.get('route', ["default"])[0]
    if not n_clicks or not username:
        raise PreventUpdate

    props_data = _load_user_props(route)
    users = props_data.get("users", [])

    new_entry = {
        "username": username,
        "properties": {
            "uuid":          uuid_val      or "",
            "role":          role          or "facility",
            "user_level":    user_level    or "facility",
            "district":      districts      if user_level == "district" else None,
            "facility_name": facilities     if (user_level == "district" and facilities) else None,
            "facility_code": facility_code or None,
        },
    }

    idx = next((i for i, u in enumerate(users) if u.get("username") == username), None)
    if idx is not None:
        users[idx] = new_entry
    else:
        users.append(new_entry)

    props_data["users"] = users
    _save_user_props(props_data, route)

    return "✓ Saved", _build_users_table(users)


# 8. Remove user
@callback(
    [Output("uc-save-status",         "children", allow_duplicate=True),
     Output("configured-users-table", "children", allow_duplicate=True),
     Output("user-property-form",     "style",    allow_duplicate=True),
     Output("user-form-placeholder",  "style",    allow_duplicate=True),
     Output("user-search-dropdown",   "value")],
    Input("uc-remove-btn", "n_clicks"),
    Input('url-params-store', 'data'),
    State("uc-username", "value"),
    prevent_initial_call=True,
)
def remove_user(n_clicks,urlparams, username):
    route = urlparams.get('route', ["default"])[0]
    if not n_clicks or not username:
        raise PreventUpdate
    props_data = _load_user_props(route)
    props_data["users"] = [u for u in props_data.get("users", []) if u.get("username") != username]
    _save_user_props(props_data, route)
    placeholder_style = {"display": "block", "color": "#9ca3af", "fontSize": "14px",
                          "padding": "40px", "textAlign": "center"}
    return "✓ Removed", _build_users_table(props_data["users"]), {"display": "none"}, placeholder_style, None


# 9. Populate configured-users-table when panel opens
@callback(
    Output("configured-users-table", "children", allow_duplicate=True),
    Input("user-config-panel", "style"),
    Input('url-params-store', 'data'),
    prevent_initial_call=True,
)
def refresh_users_table(panel_style, urlparams):
    route = urlparams.get('route', ["default"])[0]
    if not panel_style or panel_style.get("display") == "none":
        raise PreventUpdate
    data = _load_user_props(route)
    return _build_users_table(data.get("users", []))


# ── Configure Data Sources callbacks ─────────────────────────────────────────

# 1. Toggle panel (also hides user-config-panel so both never show at once)
@callback(
    [Output("datasource-panel",  "style"),
     Output("user-config-panel", "style", allow_duplicate=True),
     Output("reports-table-container", "style", allow_duplicate=True)],
    [Input("configure-datasources-btn", "n_clicks"),
     Input("close-datasource-btn",      "n_clicks")],
    prevent_initial_call=True,
)
def toggle_datasource_panel(open_clicks, close_clicks):
    if ctx.triggered_id == "configure-datasources-btn":
        return {"display": "block"}, {"display": "none"}, {"display": "none"}
    return {"display": "none"}, {"display": "none"}, {"display": "block"}


# 2. Populate SSH key dropdown and datasource list when panel opens
@callback(
    [Output("ds-ssh-pkey-select", "options"),
     Output("ds-list-container",  "children")],   # primary owner — no allow_duplicate
    Input("datasource-panel", "style"),
    prevent_initial_call=True,
)
def populate_ds_panel(panel_style):
    if not panel_style or panel_style.get("display") == "none":
        raise PreventUpdate
    key_opts = [{"label": k, "value": k} for k in _list_ssh_keys()]
    return key_opts, _build_ds_list(_load_datasources())


# 3. Open blank form for new datasource
@callback(
    [Output("ds-form",            "style",    allow_duplicate=True),
     Output("ds-form-placeholder","style",    allow_duplicate=True),
     Output("ds-uuid",            "value",    allow_duplicate=True),
     Output("ds-date-created",    "value",    allow_duplicate=True),
     Output("ds-name",            "value",    allow_duplicate=True),
     Output("ds-db-host",         "value",    allow_duplicate=True),
     Output("ds-db-port",         "value",    allow_duplicate=True),
     Output("ds-db-name",         "value",    allow_duplicate=True),
     Output("ds-db-user",         "value",    allow_duplicate=True),
     Output("ds-db-password",     "value",    allow_duplicate=True),
     Output("ds-ssh-host",        "value",    allow_duplicate=True),
     Output("ds-ssh-port",        "value",    allow_duplicate=True),
     Output("ds-ssh-user",        "value",    allow_duplicate=True),
     Output("ds-ssh-auth-type",   "value",    allow_duplicate=True),
     Output("ds-ssh-pkey-select", "value",    allow_duplicate=True),
     Output("ds-ssh-password",    "value",    allow_duplicate=True),
     Output("ds-ssh-remote-host", "value",    allow_duplicate=True),
     Output("ds-ssh-remote-port", "value",    allow_duplicate=True),
     Output("ds-start-date",      "date",     allow_duplicate=True),
     Output("ds-batch-size",      "value",    allow_duplicate=True),
     Output("ds-data-file-name",  "value",    allow_duplicate=True),
     Output("ds-load-fresh",      "value",    allow_duplicate=True),
     Output("ds-is-harmonized",   "value",    allow_duplicate=True),
     Output("ds-base-query",      "value",    allow_duplicate=True),
     Output("ds-status",          "children", allow_duplicate=True)],
    Input("ds-new-btn", "n_clicks"),
    prevent_initial_call=True,
)
def new_datasource(_):
    new_id = f"ds_{uuid.uuid4().hex[:8]}"
    today  = datetime.now().strftime("%Y-%m-%d")
    return (
        {"display": "block"}, {"display": "none"},
        new_id, today,
        "",                                    # name
        "127.0.0.1", "3306", "", "", "",       # DB_CONFIG
        "", "22", "ubuntu",                    # SSH host/port/user
        "key", None, "",                       # auth_type, pkey, password
        "", "3306",                            # remote bind address
        today, "1000", "default", "false", "true", "",
        "",
    )


# 4. Load existing datasource into form when edit button clicked
@callback(
    [Output("ds-form",            "style",    allow_duplicate=True),
     Output("ds-form-placeholder","style",    allow_duplicate=True),
     Output("ds-uuid",            "value",    allow_duplicate=True),
     Output("ds-date-created",    "value",    allow_duplicate=True),
     Output("ds-name",            "value",    allow_duplicate=True),
     Output("ds-db-host",         "value",    allow_duplicate=True),
     Output("ds-db-port",         "value",    allow_duplicate=True),
     Output("ds-db-name",         "value",    allow_duplicate=True),
     Output("ds-db-user",         "value",    allow_duplicate=True),
     Output("ds-db-password",     "value",    allow_duplicate=True),
     Output("ds-ssh-host",        "value",    allow_duplicate=True),
     Output("ds-ssh-port",        "value",    allow_duplicate=True),
     Output("ds-ssh-user",        "value",    allow_duplicate=True),
     Output("ds-ssh-auth-type",   "value",    allow_duplicate=True),
     Output("ds-ssh-pkey-select", "value",    allow_duplicate=True),
     Output("ds-ssh-password",    "value",    allow_duplicate=True),
     Output("ds-ssh-remote-host", "value",    allow_duplicate=True),
     Output("ds-ssh-remote-port", "value",    allow_duplicate=True),
     Output("ds-start-date",      "date",     allow_duplicate=True),
     Output("ds-batch-size",      "value",    allow_duplicate=True),
     Output("ds-data-file-name",  "value",    allow_duplicate=True),
     Output("ds-load-fresh",      "value",    allow_duplicate=True),
     Output("ds-is-harmonized",   "value",    allow_duplicate=True),
     Output("ds-base-query",      "value",    allow_duplicate=True),
     Output("ds-status",          "children", allow_duplicate=True)],
    Input({"type": "ds-edit-btn", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def load_datasource_into_form(n_clicks_list):
    if not any(c for c in (n_clicks_list or []) if c and c > 0):
        raise PreventUpdate
    idx = ctx.triggered_id["index"]
    sources = _load_datasources()
    if idx >= len(sources):
        raise PreventUpdate
    ds  = sources[idx]
    db  = ds.get("db_config", {})
    ssh = ds.get("ssh_config", {})
    if ssh:
        rba = ssh.get("remote_bind_address", ["", 3306])
    else:
        rba = []
    # Determine saved auth type from what keys exist
    saved_auth = "password" if (ssh and ssh.get("ssh_password")) else "key"
    return (
        {"display": "block"}, {"display": "none"},
        ds.get("uuid", ""), ds.get("date_created", ""),
        ds.get("name", ""),
        db.get("host", "127.0.0.1"), str(db.get("port", 3306)),
        db.get("database", ""), db.get("user", ""), db.get("password", ""),
        ssh.get("ssh_host", "") if ssh else "",
        str(ssh.get("ssh_port", 22)) if ssh else "22",
        ssh.get("ssh_user", "ubuntu") if ssh else "ubuntu",
        saved_auth,
        ssh.get("ssh_pkey", None) if ssh else None,
        ssh.get("ssh_password", "") if ssh else "",
        rba[0] if isinstance(rba, list) and len(rba) > 0 else "",
        str(rba[1]) if isinstance(rba, list) and len(rba) > 1 else "3306",
        ds.get("start_date", datetime.now().strftime("%Y-%m-%d")),
        str(ds.get("batch_size", 1000)),
        ds.get("data_path", "default"),
        "true" if ds.get("load_fresh_data") else "false",
        "true" if ds.get("pause_data_source", True) else "false",
        ds.get("base_query", ""),
        "",
    )


# 5. Handle SSH key file upload — save to ssh/ directory
@callback(
    [Output("ds-ssh-pkey-select", "options", allow_duplicate=True),
     Output("ds-ssh-pkey-select", "value",   allow_duplicate=True),
     Output("ds-ssh-key-status",  "children")],
    Input("ds-ssh-key-upload", "contents"),
    State("ds-ssh-key-upload",  "filename"),
    prevent_initial_call=True,
)
def upload_ssh_key(contents, filename):
    if not contents or not filename:
        raise PreventUpdate
    os.makedirs(_ssh_dir, exist_ok=True)
    _, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)
    dest = os.path.join(_ssh_dir, filename)
    with open(dest, "wb") as f:
        f.write(decoded)
    key_opts = [{"label": k, "value": k} for k in _list_ssh_keys()]
    return key_opts, filename, f"✓ Uploaded: {filename}"


# 6. Test connection
@callback(
    Output("ds-status", "children", allow_duplicate=True),
    Input("ds-test-btn", "n_clicks"),
    [State("ds-db-host",         "value"),
     State("ds-db-port",         "value"),
     State("ds-db-name",         "value"),
     State("ds-db-user",         "value"),
     State("ds-db-password",     "value"),
     State("ds-ssh-host",        "value"),
     State("ds-ssh-port",        "value"),
     State("ds-ssh-user",        "value"),
     State("ds-ssh-auth-type",   "value"),
     State("ds-ssh-pkey-select", "value"),
     State("ds-ssh-password",    "value"),
     State("ds-ssh-remote-host", "value"),
     State("ds-ssh-remote-port", "value")],
    prevent_initial_call=True,
)
def test_datasource_connection(n_clicks,
                                db_host, db_port, db_name, db_user, db_pass,
                                ssh_host, ssh_port, ssh_user,
                                ssh_auth_type, ssh_pkey, ssh_password,
                                ssh_remote_host, ssh_remote_port):
    if not n_clicks:
        raise PreventUpdate
    use_ssh = bool(ssh_host and ssh_host.strip())
    try:
        if use_ssh:
            try:
                from sshtunnel import SSHTunnelForwarder
            except ImportError:
                return "⚠ sshtunnel not installed. Run: pip install sshtunnel"

            # Build tunnel kwargs based on selected auth type
            tunnel_kwargs = {
                "ssh_username": ssh_user,
                "remote_bind_address": (ssh_remote_host or "localhost",
                                        int(ssh_remote_port or 3306)),
            }
            if ssh_auth_type == "password":
                if not ssh_password:
                    return "✗ Password auth selected but no SSH password entered."
                tunnel_kwargs["ssh_password"] = ssh_password
            else:
                pkey_path = os.path.join(_ssh_dir, ssh_pkey) if ssh_pkey else None
                if not pkey_path:
                    return "✗ Key auth selected but no key file chosen."
                tunnel_kwargs["ssh_pkey"] = pkey_path

            with SSHTunnelForwarder(
                (ssh_host, int(ssh_port or 22)),
                **tunnel_kwargs,
            ) as tunnel:
                try:
                    import pymysql
                    conn = pymysql.connect(
                        host="127.0.0.1", port=tunnel.local_bind_port,
                        user=db_user, password=db_pass, database=db_name,
                        connect_timeout=8,
                    )
                    conn.close()
                    return "✓ SSH + DB connection successful"
                except ImportError:
                    return "⚠ pymysql not installed. Run: pip install pymysql"
        else:
            try:
                import pymysql
                conn = pymysql.connect(
                    host=db_host or "127.0.0.1", port=int(db_port or 3306),
                    user=db_user, password=db_pass, database=db_name,
                    connect_timeout=8,
                )
                conn.close()
                return "✓ Direct DB connection successful"
            except ImportError:
                return "⚠ pymysql not installed. Run: pip install pymysql"
    except Exception as exc:
        return f"✗ Connection failed: {exc}"


# 7. Save datasource
@callback(
    [Output("ds-status",       "children",  allow_duplicate=True),
     Output("ds-list-container","children", allow_duplicate=True)],
    Input("ds-save-btn", "n_clicks"),
    [State("ds-uuid",            "value"),
     State("ds-date-created",    "value"),
     State("ds-name",            "value"),
     State("ds-db-host",         "value"),
     State("ds-db-port",         "value"),
     State("ds-db-name",         "value"),
     State("ds-db-user",         "value"),
     State("ds-db-password",     "value"),
     State("ds-ssh-host",        "value"),
     State("ds-ssh-port",        "value"),
     State("ds-ssh-user",        "value"),
     State("ds-ssh-auth-type",   "value"),
     State("ds-ssh-pkey-select", "value"),
     State("ds-ssh-password",    "value"),
     State("ds-ssh-remote-host", "value"),
     State("ds-ssh-remote-port", "value"),
     State("ds-start-date",      "date"),
     State("ds-batch-size",      "value"),
     State("ds-data-file-name",  "value"),
     State("ds-load-fresh",      "value"),
     State("ds-is-harmonized",   "value"),
     State("ds-base-query",      "value")],
    prevent_initial_call=True,
)
def save_datasource(n_clicks, ds_uuid, date_created, name,
                    db_host, db_port, db_name, db_user, db_pass,
                    ssh_host, ssh_port, ssh_user,
                    ssh_auth_type, ssh_pkey, ssh_password,
                    ssh_remote_host, ssh_remote_port,
                    start_date, batch_size, data_file_name,
                    load_fresh, is_harmonized, base_query):
    if not n_clicks or not name:
        raise PreventUpdate
    use_ssh = bool(ssh_host and ssh_host.strip())

    # Build SSH_CONFIG only when SSH host is provided;
    # include either ssh_pkey OR ssh_password depending on auth type (never both)
    if use_ssh:
        ssh_cfg = {
            "ssh_host": ssh_host,
            "ssh_port": int(ssh_port or 22),
            "ssh_user": ssh_user or "ubuntu",
            "remote_bind_address": [ssh_remote_host or "localhost",
                                    int(ssh_remote_port or 3306)],
        }
        if ssh_auth_type == "password" and ssh_password:
            ssh_cfg["ssh_password"] = ssh_password   # only key present
        elif ssh_pkey:
            ssh_cfg["ssh_pkey"] = ssh_pkey            # only pkey present
    else:
        ssh_cfg = None

    entry = {
        "uuid":            ds_uuid or f"ds_{uuid.uuid4().hex[:8]}",
        "name":            name,
        "date_created":    date_created or datetime.now().strftime("%Y-%m-%d"),
        "date_updated":    datetime.now().strftime("%Y-%m-%d"),
        "use_localhost":   not use_ssh,
        "start_date":      start_date or datetime.now().strftime("%Y-%m-%d"),
        "load_fresh_data": load_fresh == "true",
        "data_path":       data_file_name or "default",
        "base_query":      base_query or "",
        "pause_data_source": is_harmonized == "true",
        "batch_size":      int(batch_size or 1000),
        "db_config": {
            "host":     db_host or "127.0.0.1",
            "port":     int(db_port or 3306),
            "database": db_name or "",
            "user":     db_user or "",
            "password": db_pass or "",
        },
        "ssh_config": ssh_cfg,
    }
    sources = _load_datasources()
    for items in sources:
        if entry.get("data_path") == items.get("data_path") and entry.get("uuid") != items.get("uuid"):
            return html.Div(f"Another datasource with the same data file name exists: {items.get('name', 'Unnamed')}", style={"color": "red"}), _build_ds_list(sources)
        if entry.get("base_query") =="":
            return html.Div("Base query cannot be empty.", style={"color": "red"}), _build_ds_list(sources)
    idx = next((i for i, s in enumerate(sources) if s.get("uuid") == ds_uuid), None)
    if idx is not None:
        sources[idx] = entry
    else:
        sources.append(entry)
    _save_datasources(sources)
    return "✓ Saved", _build_ds_list(sources)


# 8. Delete datasource
@callback(
    [Output("ds-status",        "children", allow_duplicate=True),
     Output("ds-list-container","children", allow_duplicate=True),
     Output("ds-form",          "style",    allow_duplicate=True),
     Output("ds-form-placeholder","style",  allow_duplicate=True)],
    Input("ds-delete-btn", "n_clicks"),
    State("ds-uuid", "value"),
    prevent_initial_call=True,
)
def delete_datasource(n_clicks, ds_uuid):
    if not n_clicks or not ds_uuid:
        raise PreventUpdate
    sources = [s for s in _load_datasources() if s.get("uuid") != ds_uuid]
    _save_datasources(sources)
    placeholder_shown = {"display": "block", "color": "#9ca3af",
                          "fontSize": "14px", "padding": "24px 0"}
    return "✓ Deleted", _build_ds_list(sources), {"display": "none"}, placeholder_shown

import subprocess as _subprocess
import sys as _sys
import time as _time

# Module-level dict to hold the running Popen object keyed by PID.
# dcc.Store cannot hold a process object, so we park it here.
_refresh_processes: dict = {}


@callback(
    [Output("ds-refresh-store",    "data",     allow_duplicate=True),
     Output("ds-refresh-interval", "disabled", allow_duplicate=True),
     Output("ds-run-btn",          "disabled"),
     Output("ds-run-btn",          "children"),
     Output("ds-refresh-summary",  "children", allow_duplicate=True)],
    Input("ds-run-btn", "n_clicks"),
    State("ds-refresh-store", "data"),
    prevent_initial_call=True,
)
def start_data_refresh(n_clicks, store):
    """Launch data_storage.py as a background subprocess and lock the button."""
    if not n_clicks:
        raise PreventUpdate

    store = store or {}

    if store.get("running"):
        return (store, True, True, "🔄 Refreshing...",
                "⚠ A refresh is already running.")
    script_path = os.path.join(path, "data_storage.py")
    try:
        proc = _subprocess.Popen(
            [_sys.executable, script_path],
            stdout=_subprocess.PIPE,
            stderr=_subprocess.PIPE,
        )
    except Exception as exc:
        return ({"running": False, "pid": None, "start_time": None},
                True, False, "🔄 Refresh Data",
                f"✗ Failed to start: {exc}")

    start_ts = _time.time()
    _refresh_processes[proc.pid] = (proc, start_ts)

    new_store = {"running": True, "pid": proc.pid,
                 "start_time": start_ts}
    return (new_store, False, True, "🔄 Refreshing...", "⏳ Running…")


@callback(
    [Output("ds-refresh-store",    "data",     allow_duplicate=True),
     Output("ds-refresh-interval", "disabled", allow_duplicate=True),
     Output("ds-run-btn",          "disabled", allow_duplicate=True),
     Output("ds-run-btn",          "children", allow_duplicate=True),
     Output("ds-refresh-summary",  "children", allow_duplicate=True)],
    Input("ds-refresh-interval",  "n_intervals"),
    State("ds-refresh-store",     "data"),
    prevent_initial_call=True,
)
def poll_data_refresh(n_intervals, store):
    """Poll every 2 s; when the process finishes, show a summary."""
    store = store or {}

    if not store.get("running"):
        raise PreventUpdate

    pid        = store.get("pid")
    start_time = store.get("start_time", _time.time())

    entry = _refresh_processes.get(pid)
    if entry is None:
        # Process not found — treat as completed (e.g. after a server restart)
        return ({"running": False, "pid": None, "start_time": None},
                True, False, "🔄 Refresh Data", "✓ Completed (process not found).")

    proc, _ = entry
    retcode  = proc.poll()   # None = still running

    if retcode is None:
        elapsed = _time.time() - start_time
        return (store, False, True, "🔄 Refreshing…",
                f"⏳ Running… ({elapsed:.0f}s)")

    # ── Process finished ──────────────────────────────────────────────────────
    elapsed  = round(_time.time() - start_time, 1)
    _refresh_processes.pop(pid, None)

    # Count rows in the parquet file
    row_count = "—"
    try:
        from data_storage import DataStorage
        _route    = "default"
        pq_path   = os.path.join(path, "data", _route, "parquet")
        if os.path.isdir(pq_path) or os.path.exists(pq_path):
            count_df  = DataStorage.query_duckdb(
                f"SELECT COUNT(*) AS n FROM '{pq_path}'"
            )
            row_count = f"{int(count_df['n'].iloc[0]):,}"
    except Exception:
        pass

    if retcode == 0:
        summary = (f"✓ Completed in {elapsed}s — {row_count} rows in dataset")
    else:
        stderr_out = proc.stderr.read().decode(errors="replace")[-300:] if proc.stderr else ""
        summary    = f"✗ Failed (exit {retcode}) after {elapsed}s. {stderr_out}"

    done_store = {"running": False, "pid": None, "start_time": None}
    return (done_store, True, False, "🔄 Refresh Data", summary)


# ── SSH auth-type toggle (key ↔ password) ─────────────────────────────────────
@callback(
    [Output("ds-ssh-key-section",      "style"),
     Output("ds-ssh-password-section", "style")],
    Input("ds-ssh-auth-type", "value"),
    prevent_initial_call=False,
)
def toggle_ssh_auth_type(auth_type):
    if auth_type == "password":
        return {"display": "none"}, {"display": "block"}
    return {"display": "block"}, {"display": "none"}


# All valid column names the user can reference in a query
_VALID_COLS = set(actual_keys_in_data)


@callback(
    Output("preview-col-validation", "children"),
    Input("preview-sql-input", "n_blur"),
    State("preview-sql-input", "value"),
    prevent_initial_call=True,
)
def validate_sql_columns(n_blur, sql):
    """Validate column-name tokens against actual_keys_in_data while typing."""
    if not sql or not sql.strip():
        return ""

    tokens = _extract_identifiers(sql)
    if not tokens:
        return ""

    valid, invalid = [], []
    for tok in dict.fromkeys(tokens):    # deduplicate, preserve order
        if tok in _VALID_COLS:
            valid.append(tok)
        else:
            # Suggest close matches
            suggestions = [c for c in _VALID_COLS
                           if tok.lower() in c.lower() or c.lower().startswith(tok.lower())][:3]
            invalid.append((tok, suggestions))

    parts = []
    if valid:
        parts.append(html.Span(
            "✓ " + ", ".join(valid),
            style={"color": "#006401", "marginRight": "12px", "fontWeight": "500"},
        ))
    for tok, suggestions in invalid:
        hint = f"  (did you mean: {', '.join(suggestions)}?)" if suggestions else ""
        parts.append(html.Span(
            f"✗ {tok}{hint}",
            style={"color": "#dc2626", "marginRight": "10px"},
        ))

    return parts


@callback(
    [Output("preview-data-info",  "children", allow_duplicate=True),
     Output("preview-data-table", "children", allow_duplicate=True),
     Output("preview-run-status", "children")],
    Input("preview-run-btn", "n_clicks"),
    Input("url-params-store", "data"),
    State("preview-sql-input", "value"),
    prevent_initial_call=True,
)
def run_preview_query(n_clicks,urlparams, sql):
    """Execute the user-supplied SQL via DuckDB and display results."""
    if not n_clicks or not sql or not sql.strip():
        raise PreventUpdate

    try:
        route = urlparams.get('route', ["default"])[0]

        if f"'data/{route}/parquet'" not in sql:
            query = (sql.replace("data", f"'data/{route}/parquet'")
                     .replace("given_name","identifier")
                     .replace("family_name","identifier")
                     .replace("User","identifier"))
        else:
            query = sql
        
        if ("LIMIT" or "limit") not in query:
            query = query  + " LIMIT 100"
        df = DataStorage.query_duckdb(query.strip())
        sensitive_columns=["given_name", "family_name","User"]
        df = df.drop(columns=[col for col in sensitive_columns if col in df.columns])

    except Exception as exc:
        err_msg = str(exc)
        error_div = html.Div([
            html.Div("✗ SQL Error", style={"color": "#dc2626", "fontWeight": "700",
                                            "marginBottom": "6px"}),
            html.Pre(err_msg, style={
                "background": "#fef2f2", "border": "1px solid #fecaca",
                "borderRadius": "6px", "padding": "12px",
                "fontSize": "12px", "whiteSpace": "pre-wrap",
                "color": "#dc2626", "maxHeight": "160px", "overflowY": "auto",
            }),
        ])
        return error_div, "", ""

    if df is None or df.empty:
        return (
            html.Div("⚠ Query returned no rows.",
                     style={"color": "#f59e0b", "fontWeight": "600"}),
            "", "",
        )

    info = html.Div(style={"display": "flex", "gap": "20px", "flexWrap": "wrap"}, children=[
        html.Span(f"✓ {len(df):,} rows",
                  style={"color": "#006401", "fontWeight": "600"}),
        html.Span(f"{len(df.columns)} columns",
                  style={"color": "#374151"}),
        html.Span("Use column headers to sort/filter.",
                  style={"color": "#6b7280", "fontStyle": "italic", "fontSize": "12px"}),
    ])

    return info, create_preview_table(df), ""


# =============================================================================
# Report Builder – helper + callbacks
# =============================================================================

_REFLOW_GAP        = 16   # minimum vertical gap between tables (px)
_REFLOW_MARGIN_TOP = 20   # minimum Y from canvas top (px)


def _table_pixel_height(table: dict) -> int:
    rh   = table.get("row_heights", [])
    data = table.get("data", [])
    h    = int(sum(rh)) if rh else len(data) * 28
    if table.get("ta") is not None:
        h += 30
    if table.get("tb") is not None:
        h += 30
    return h


def _reflow_tables(tables: list) -> None:
    """Re-stack tables vertically (sorted by Y) in-place to eliminate gaps and overlaps."""
    if not tables:
        return
    tables.sort(key=lambda t: t.get("pos", {}).get("y", 0))
    cursor_y = _REFLOW_MARGIN_TOP
    for t in tables:
        x = t.get("pos", {}).get("x", 20)
        t["pos"] = {"x": x, "y": cursor_y}
        cursor_y += _table_pixel_height(t) + _REFLOW_GAP


def _rpt_render_canvas(state, sel, drag_pos, resize_store=None):
    """Return a list of Dash components representing all tables on the canvas."""
    sel = sel or {"tid": None, "cells": []}
    drag_pos = drag_pos or {}
    resize_store = resize_store or {}
    components = []

    _RESIZE_HANDLE_COL = {
        "position": "absolute", "right": "0", "top": "0",
        "width": "5px", "height": "100%", "cursor": "col-resize",
        "zIndex": "10", "background": "transparent", "userSelect": "none",
    }
    _RESIZE_HANDLE_ROW = {
        "position": "absolute", "bottom": "0", "left": "0",
        "height": "5px", "width": "100%", "cursor": "row-resize",
        "zIndex": "10", "background": "transparent", "userSelect": "none",
    }

    for table in state.get("tables", []):
        tid = table["id"]
        pos = drag_pos.get(tid, table.get("pos", {"x": 20, "y": 20}))
        x, y = pos.get("x", 20), pos.get("y", 20)
        selected_table = sel.get("tid") == tid
        selected_cells = {(r, c) for r, c in sel.get("cells", [])}

        # Resize dimensions: prefer resize_store over table state
        tdims = resize_store.get(tid, {})
        col_widths = tdims.get("col_widths", table.get("col_widths", []))
        row_heights = tdims.get("row_heights", table.get("row_heights", []))

        inner = []

        # Drag handle
        inner.append(
            html.Div(
                tid,
                id={"type": "rpt-handle", "tid": tid},
                n_clicks=0,
                style={
                    "padding": "3px 8px", "fontSize": "11px", "cursor": "move",
                    "background": "#16a34a" if selected_table else "#9ca3af",
                    "color": "#ffffff", "borderRadius": "4px 4px 0 0",
                    "userSelect": "none",
                },
            )
        )

        # Title above
        if table.get("ta") is not None:
            inner.append(
                dcc.Input(
                    id={"type": "rpt-ta", "tid": tid},
                    value=table["ta"],
                    debounce=True,
                    placeholder="Title above…",
                    style={"width": "100%", "padding": "4px 6px", "fontSize": "13px",
                           "fontWeight": "600", "border": "1px solid #d1d5db",
                           "borderRadius": "4px", "marginBottom": "4px",
                           "boxSizing": "border-box"},
                )
            )

        # Table rows
        rows = []
        data = table.get("data", [])
        for r_idx, row in enumerate(data):
            tds = []
            vis_col = 0  # visual column counter (skips hidden cells)
            for c_idx, cell in enumerate(row):
                if cell.get("hidden", False):
                    continue
                is_selected = (r_idx, c_idx) in selected_cells

                # Resolve explicit dimensions for this visual column/row
                w = col_widths[vis_col] if vis_col < len(col_widths) else 80
                h = row_heights[r_idx] if r_idx < len(row_heights) else 30

                tds.append(
                    html.Td(
                        children=[
                            dcc.Input(
                                id={"type": "rpt-ci", "tid": tid, "r": r_idx, "c": c_idx},
                                value=cell.get("v", ""),
                                debounce=True,
                                style={
                                    "border": "none", "background": "transparent",
                                    "width": "100%", "color": cell.get("color", "#000000"),
                                    "fontSize": "12px", "boxSizing": "border-box",
                                    "fontWeight": "bold" if cell.get("bold") else "normal",
                                    "fontStyle": "italic" if cell.get("italic") else "normal",
                                    "textAlign": cell.get("align", "left"),
                                    "paddingLeft": f"{4 + cell.get('indent', 0) * 20}px",
                                },
                            ),
                            # Column resize handle (right edge)
                            html.Div(
                                id={"type": "rpt-col-resize", "tid": tid, "col": vis_col},
                                style=_RESIZE_HANDLE_COL,
                            ),
                            # Row resize handle (bottom edge)
                            html.Div(
                                id={"type": "rpt-row-resize", "tid": tid, "row": r_idx},
                                style=_RESIZE_HANDLE_ROW,
                            ),
                        ],
                        id={"type": "rpt-td", "tid": tid, "r": r_idx, "c": c_idx},
                        n_clicks=0,
                        colSpan=cell.get("cs", 1),
                        rowSpan=cell.get("rs", 1),
                        style={
                            "position": "relative",
                            "border": "2px solid #16a34a" if is_selected else "1px solid #d1d5db",
                            "background": cell.get("fill", "#ffffff"),
                            "padding": "2px 4px",
                            "width": f"{w}px",
                            "minWidth": f"{w}px",
                            "height": f"{h}px",
                            "minHeight": f"{h}px",
                            "overflow": "hidden",
                        },
                    )
                )
                vis_col += cell.get("cs", 1)
            rows.append(html.Tr(
                tds,
                style={"height": f"{row_heights[r_idx]}px" if r_idx < len(row_heights) else "30px"},
            ))

        inner.append(
            html.Table(
                html.Tbody(rows),
                style={"borderCollapse": "collapse", "background": "#ffffff",
                       "fontSize": "12px", "tableLayout": "fixed"},
            )
        )

        # Title below
        if table.get("tb") is not None:
            inner.append(
                dcc.Input(
                    id={"type": "rpt-tb", "tid": tid},
                    value=table["tb"],
                    debounce=True,
                    placeholder="Title below…",
                    style={"width": "100%", "padding": "4px 6px", "fontSize": "13px",
                           "fontWeight": "600", "border": "1px solid #d1d5db",
                           "borderRadius": "4px", "marginTop": "4px",
                           "boxSizing": "border-box"},
                )
            )

        components.append(
            html.Div(
                inner,
                id={"type": "rpt-wrap", "tid": tid},
                style={
                    "position": "absolute",
                    "left": f"{x}px",
                    "top": f"{y}px",
                    "border": "2px solid #16a34a" if selected_table else "1px solid #d1d5db",
                    "borderRadius": "4px",
                    "boxShadow": "0 2px 8px rgba(0,0,0,0.12)",
                    "background": "#ffffff",
                    "minWidth": "120px",
                },
            )
        )

    return components


# 1. Toggle modal
@callback(
    Output("create-reports-modal", "style"),
    Input("create-reports-gui-btn", "n_clicks"),
    Input("close-create-reports-modal", "n_clicks"),
    State("create-reports-modal", "style"),
    prevent_initial_call=True,
)
def _toggle_create_reports_modal(open_clicks, close_clicks, current_style):
    triggered = ctx.triggered_id
    if triggered == "create-reports-gui-btn":
        return {**current_style, "display": "flex"}
    return {**current_style, "display": "none"}


# 2. Select table / cell
@callback(
    Output("rpt-sel", "data"),
    Input({"type": "rpt-handle", "tid": ALL}, "n_clicks"),
    Input({"type": "rpt-td", "tid": ALL, "r": ALL, "c": ALL}, "n_clicks"),
    State("rpt-sel", "data"),
    prevent_initial_call=True,
)
def _rpt_select(handle_clicks, cell_clicks, sel):
    triggered = ctx.triggered_id
    if triggered is None:
        raise PreventUpdate
    if isinstance(triggered, dict):
        t = triggered.get("type")
        if t == "rpt-handle":
            return {"tid": triggered["tid"], "cells": []}
        if t == "rpt-td":
            return {"tid": triggered["tid"], "cells": [[triggered["r"], triggered["c"]]]}
    raise PreventUpdate


# 3. Canvas render
@callback(
    Output("html-report-canvas", "children"),
    Output("html-report-status", "children"),
    Input("rpt-state", "data"),
    Input("rpt-sel", "data"),
    Input("rpt-drag-pos", "data"),
    State("rpt-resize-store", "data"),
    prevent_initial_call=False,
)
def _rpt_render(state, sel, drag_pos, resize_store):
    state = state or {"tables": [], "next_id": 1}
    sel = sel or {"tid": None, "cells": []}
    drag_pos = drag_pos or {}
    children = _rpt_render_canvas(state, sel, drag_pos, resize_store)
    tid = sel.get("tid")
    ncells = len(sel.get("cells", []))
    if tid:
        status = f"Table {tid} selected, {ncells} cell(s)"
    else:
        status = "No selection"
    return children, status


def _empty_cell():
    return {"v": "", "fill": "#ffffff", "color": "#000000", "cs": 1, "rs": 1, "hidden": False,
            "bold": False, "italic": False, "align": "left", "indent": 0}


def _new_table(tid, x, y, rows=3, cols=3):
    data = [[_empty_cell() for _ in range(cols)] for _ in range(rows)]
    return {"id": tid, "pos": {"x": x, "y": y}, "ta": None, "tb": None, "data": data}


# 4. Add table
@callback(
    Output("rpt-state", "data", allow_duplicate=True),
    Input("rpt-add-table-btn", "n_clicks"),
    Input("rpt-add-above-btn", "n_clicks"),
    Input("rpt-add-below-btn", "n_clicks"),
    Input("rpt-add-left-btn", "n_clicks"),
    Input("rpt-add-right-btn", "n_clicks"),
    State("rpt-state", "data"),
    State("rpt-sel", "data"),
    prevent_initial_call=True,
)
def _rpt_add_table(n_new, n_above, n_below, n_left, n_right, state, sel):
    state = state or {"tables": [], "next_id": 1}
    triggered = ctx.triggered_id
    if triggered is None:
        raise PreventUpdate

    tables = state["tables"]
    nid = state["next_id"]
    tid = f"t{nid}"
    n = len(tables)
    sel = sel or {"tid": None}
    selected_tid = sel.get("tid")
    sel_table = next((t for t in tables if t["id"] == selected_tid), None)

    if triggered == "rpt-add-table-btn" or sel_table is None:
        x, y = 20 + n * 30, 20 + n * 30
    else:
        sx, sy = sel_table["pos"]["x"], sel_table["pos"]["y"]
        if triggered == "rpt-add-above-btn":
            x, y = sx, sy - 160
        elif triggered == "rpt-add-below-btn":
            x, y = sx, sy + 120
        elif triggered == "rpt-add-left-btn":
            x, y = sx - 220, sy
        elif triggered == "rpt-add-right-btn":
            x, y = sx + 220, sy
        else:
            x, y = 20 + n * 30, 20 + n * 30

    tables.append(_new_table(tid, x, y))
    _reflow_tables(tables)
    return {"tables": tables, "next_id": nid + 1}


# 5. Structural operations
@callback(
    Output("rpt-state", "data", allow_duplicate=True),
    Input("rpt-add-row-btn", "n_clicks"),
    Input("rpt-del-row-btn", "n_clicks"),
    Input("rpt-add-col-btn", "n_clicks"),
    Input("rpt-del-col-btn", "n_clicks"),
    Input("rpt-merge-btn", "n_clicks"),
    Input("rpt-split-btn", "n_clicks"),
    Input("rpt-clear-btn", "n_clicks"),
    State("rpt-state", "data"),
    State("rpt-sel", "data"),
    prevent_initial_call=True,
)
def _rpt_structural(n_ar, n_dr, n_ac, n_dc, n_mg, n_sp, n_cl, state, sel):
    state = state or {"tables": [], "next_id": 1}
    sel = sel or {"tid": None, "cells": []}
    triggered = ctx.triggered_id
    if triggered is None:
        raise PreventUpdate

    tid = sel.get("tid")
    if not tid:
        raise PreventUpdate

    tables = state["tables"]
    idx = next((i for i, t in enumerate(tables) if t["id"] == tid), None)
    if idx is None:
        raise PreventUpdate

    table = tables[idx]
    data = table["data"]
    selected_cells = sel.get("cells", [])

    if triggered == "rpt-add-row-btn":
        col_count = max((len(r) for r in data), default=1)
        data.append([_empty_cell() for _ in range(col_count)])

    elif triggered == "rpt-del-row-btn":
        if selected_cells:
            rows_to_del = sorted({r for r, c in selected_cells}, reverse=True)
            for r in rows_to_del:
                if 0 <= r < len(data):
                    data.pop(r)
        elif data:
            data.pop()

    elif triggered == "rpt-add-col-btn":
        for row in data:
            row.append(_empty_cell())

    elif triggered == "rpt-del-col-btn":
        if selected_cells:
            cols_to_del = sorted({c for r, c in selected_cells}, reverse=True)
            for row in data:
                for c in cols_to_del:
                    if 0 <= c < len(row):
                        row.pop(c)
        else:
            for row in data:
                if row:
                    row.pop()

    elif triggered == "rpt-merge-btn":
        if len(selected_cells) < 2:
            raise PreventUpdate
        rows = [r for r, c in selected_cells]
        cols = [c for r, c in selected_cells]
        min_r, max_r = min(rows), max(rows)
        min_c, max_c = min(cols), max(cols)
        rs = max_r - min_r + 1
        cs = max_c - min_c + 1
        # set top-left cell span
        data[min_r][min_c]["rs"] = rs
        data[min_r][min_c]["cs"] = cs
        data[min_r][min_c]["hidden"] = False
        # hide remaining cells in rectangle
        for r in range(min_r, max_r + 1):
            for c in range(min_c, max_c + 1):
                if r == min_r and c == min_c:
                    continue
                if r < len(data) and c < len(data[r]):
                    data[r][c]["hidden"] = True

    elif triggered == "rpt-split-btn":
        if len(selected_cells) != 1:
            raise PreventUpdate
        r, c = selected_cells[0]
        cell = data[r][c]
        rs = cell.get("rs", 1)
        cs_val = cell.get("cs", 1)
        # restore hidden cells
        for rr in range(r, r + rs):
            for cc in range(c, c + cs_val):
                if rr < len(data) and cc < len(data[rr]):
                    data[rr][cc]["hidden"] = False
                    data[rr][cc]["rs"] = 1
                    data[rr][cc]["cs"] = 1

    elif triggered == "rpt-clear-btn":
        for r, c in selected_cells:
            if r < len(data) and c < len(data[r]):
                data[r][c]["v"] = ""

    table["data"] = data
    tables[idx] = table
    return {"tables": tables, "next_id": state["next_id"]}


# 6. Apply fill / font color
@callback(
    Output("rpt-state", "data", allow_duplicate=True),
    Input("rpt-apply-fill-btn", "n_clicks"),
    Input("rpt-apply-font-btn", "n_clicks"),
    State("rpt-state", "data"),
    State("rpt-sel", "data"),
    State("rpt-fill-color", "value"),
    State("rpt-font-color", "value"),
    prevent_initial_call=True,
)
def _rpt_apply_color(n_fill, n_font, state, sel, fill_color, font_color):
    state = state or {"tables": [], "next_id": 1}
    sel = sel or {"tid": None, "cells": []}
    triggered = ctx.triggered_id
    if triggered is None:
        raise PreventUpdate

    tid = sel.get("tid")
    if not tid:
        raise PreventUpdate

    tables = state["tables"]
    idx = next((i for i, t in enumerate(tables) if t["id"] == tid), None)
    if idx is None:
        raise PreventUpdate

    data = tables[idx]["data"]
    for r, c in sel.get("cells", []):
        if r < len(data) and c < len(data[r]):
            if triggered == "rpt-apply-fill-btn":
                data[r][c]["fill"] = fill_color
            elif triggered == "rpt-apply-font-btn":
                data[r][c]["color"] = font_color

    tables[idx]["data"] = data
    return {"tables": tables, "next_id": state["next_id"]}


# 6b. Apply text style (bold, italic, alignment, indent)
@callback(
    Output("rpt-state", "data", allow_duplicate=True),
    Input("rpt-bold-btn",         "n_clicks"),
    Input("rpt-italic-btn",       "n_clicks"),
    Input("rpt-align-left-btn",   "n_clicks"),
    Input("rpt-align-center-btn", "n_clicks"),
    Input("rpt-align-right-btn",  "n_clicks"),
    Input("rpt-indent-btn",       "n_clicks"),
    Input("rpt-dedent-btn",       "n_clicks"),
    State("rpt-state", "data"),
    State("rpt-sel",   "data"),
    prevent_initial_call=True,
)
def _rpt_apply_text_style(nb, ni, nal, nac, nar, nind, nded, state, sel):
    state = state or {"tables": [], "next_id": 1}
    sel   = sel   or {"tid": None, "cells": []}
    triggered = ctx.triggered_id
    if triggered is None:
        raise PreventUpdate

    tid = sel.get("tid")
    if not tid:
        raise PreventUpdate

    tables = state["tables"]
    idx = next((i for i, t in enumerate(tables) if t["id"] == tid), None)
    if idx is None:
        raise PreventUpdate

    data = tables[idx]["data"]
    for r, c in sel.get("cells", []):
        if r >= len(data) or c >= len(data[r]):
            continue
        cell = data[r][c]
        if triggered == "rpt-bold-btn":
            cell["bold"] = not cell.get("bold", False)
        elif triggered == "rpt-italic-btn":
            cell["italic"] = not cell.get("italic", False)
        elif triggered == "rpt-align-left-btn":
            cell["align"] = "left"
        elif triggered == "rpt-align-center-btn":
            cell["align"] = "center"
        elif triggered == "rpt-align-right-btn":
            cell["align"] = "right"
        elif triggered == "rpt-indent-btn":
            cell["indent"] = min(cell.get("indent", 0) + 1, 1)
        elif triggered == "rpt-dedent-btn":
            cell["indent"] = max(cell.get("indent", 0) - 1, 0)

    tables[idx]["data"] = data
    return {"tables": tables, "next_id": state["next_id"]}


# 7. Add title above/below
@callback(
    Output("rpt-state", "data", allow_duplicate=True),
    Input("rpt-title-above-btn", "n_clicks"),
    Input("rpt-title-below-btn", "n_clicks"),
    State("rpt-state", "data"),
    State("rpt-sel", "data"),
    prevent_initial_call=True,
)
def _rpt_add_title(n_above, n_below, state, sel):
    state = state or {"tables": [], "next_id": 1}
    sel = sel or {"tid": None}
    triggered = ctx.triggered_id
    if triggered is None:
        raise PreventUpdate

    tid = sel.get("tid")
    if not tid:
        raise PreventUpdate

    tables = state["tables"]
    idx = next((i for i, t in enumerate(tables) if t["id"] == tid), None)
    if idx is None:
        raise PreventUpdate

    if triggered == "rpt-title-above-btn":
        tables[idx]["ta"] = ""
    elif triggered == "rpt-title-below-btn":
        tables[idx]["tb"] = ""

    return {"tables": tables, "next_id": state["next_id"]}


# 8. Remove table
@callback(
    Output("rpt-state", "data", allow_duplicate=True),
    Output("rpt-sel", "data", allow_duplicate=True),
    Input("rpt-remove-table-btn", "n_clicks"),
    State("rpt-state", "data"),
    State("rpt-sel", "data"),
    prevent_initial_call=True,
)
def _rpt_remove_table(n_clicks, state, sel):
    state = state or {"tables": [], "next_id": 1}
    sel = sel or {"tid": None}
    tid = sel.get("tid")
    if not tid:
        raise PreventUpdate
    tables = [t for t in state["tables"] if t["id"] != tid]
    _reflow_tables(tables)
    return {"tables": tables, "next_id": state["next_id"]}, {"tid": None, "cells": []}


# 9. Update cell value
@callback(
    Output("rpt-state", "data", allow_duplicate=True),
    Input({"type": "rpt-ci", "tid": ALL, "r": ALL, "c": ALL}, "value"),
    State("rpt-state", "data"),
    prevent_initial_call=True,
)
def _rpt_update_cell(values, state):
    if not ctx.triggered or not any(v is not None for v in (ctx.triggered or [])):
        raise PreventUpdate
    state = state or {"tables": [], "next_id": 1}
    triggered = ctx.triggered_id
    if triggered is None or not isinstance(triggered, dict):
        raise PreventUpdate

    tid = triggered["tid"]
    r = triggered["r"]
    c = triggered["c"]
    val = ctx.triggered[0]["value"]

    tables = state["tables"]
    idx = next((i for i, t in enumerate(tables) if t["id"] == tid), None)
    if idx is None:
        raise PreventUpdate

    if r < len(tables[idx]["data"]) and c < len(tables[idx]["data"][r]):
        tables[idx]["data"][r][c]["v"] = val if val is not None else ""

    return {"tables": tables, "next_id": state["next_id"]}


# 10. Update title above/below
@callback(
    Output("rpt-state", "data", allow_duplicate=True),
    Input({"type": "rpt-ta", "tid": ALL}, "value"),
    Input({"type": "rpt-tb", "tid": ALL}, "value"),
    State("rpt-state", "data"),
    prevent_initial_call=True,
)
def _rpt_update_title(ta_values, tb_values, state):
    state = state or {"tables": [], "next_id": 1}
    triggered = ctx.triggered_id
    if triggered is None or not isinstance(triggered, dict):
        raise PreventUpdate

    tid = triggered["tid"]
    val = ctx.triggered[0]["value"]
    tables = state["tables"]
    idx = next((i for i, t in enumerate(tables) if t["id"] == tid), None)
    if idx is None:
        raise PreventUpdate

    t_type = triggered.get("type")
    if t_type == "rpt-ta":
        tables[idx]["ta"] = val
    elif t_type == "rpt-tb":
        tables[idx]["tb"] = val

    return {"tables": tables, "next_id": state["next_id"]}


# 11. Drag position sync (clientside)
dash.clientside_callback(
    """
    function(children) {
        setTimeout(function() {
            var allEls = document.querySelectorAll('[id]');

            function writeDashInput(inputId, value) {
                var inp = document.getElementById(inputId);
                if (!inp) return;
                var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(inp, value);
                inp.dispatchEvent(new Event('input', {bubbles: true}));
            }

            function readJsonInput(inputId) {
                var inp = document.getElementById(inputId);
                if (!inp) return {};
                try { return JSON.parse(inp.value || '{}'); } catch(e) { return {}; }
            }

            // ── Table drag (snap to 8px grid) ────────────────────────────────
            var GRID = 8;
            function snapGrid(v) { return Math.max(0, Math.round(v / GRID) * GRID); }
            allEls.forEach(function(el) {
                if (!el.id || !el.id.includes('"type":"rpt-handle"')) return;
                if (el._dragBound) return;
                el._dragBound = true;
                var wrapper = el.parentElement;
                el.addEventListener('mousedown', function(ev) {
                    ev.preventDefault();
                    var sx = ev.clientX, sy = ev.clientY;
                    var ol = parseInt(wrapper.style.left)||0, ot = parseInt(wrapper.style.top)||0;
                    function mv(e) {
                        wrapper.style.left = snapGrid(ol + e.clientX - sx) + 'px';
                        wrapper.style.top  = snapGrid(ot + e.clientY - sy) + 'px';
                    }
                    function up() {
                        document.removeEventListener('mousemove', mv);
                        document.removeEventListener('mouseup', up);
                        try {
                            var parsed = JSON.parse(el.id);
                            var d = readJsonInput('rpt-drag-hidden-input');
                            d[parsed.tid] = {x: parseInt(wrapper.style.left)||0, y: parseInt(wrapper.style.top)||0};
                            writeDashInput('rpt-drag-hidden-input', JSON.stringify(d));
                        } catch(ex) {}
                    }
                    document.addEventListener('mousemove', mv);
                    document.addEventListener('mouseup', up);
                });
            });

            // ── Column resize ───────────────────────────────────────────────
            allEls.forEach(function(el) {
                if (!el.id || !el.id.includes('"type":"rpt-col-resize"')) return;
                if (el._colResizeBound) return;
                el._colResizeBound = true;
                el.addEventListener('mousedown', function(ev) {
                    ev.stopPropagation();
                    ev.preventDefault();
                    var td = el.parentElement;
                    var table = td.closest('table');
                    var startX = ev.clientX;
                    var startWidth = td.offsetWidth;
                    var tr = td.parentElement;
                    var colIdx = Array.from(tr.querySelectorAll('td')).indexOf(td);
                    function mv(e) {
                        var nw = Math.max(30, startWidth + e.clientX - startX);
                        table.querySelectorAll('tr').forEach(function(row) {
                            var cells = row.querySelectorAll('td');
                            if (cells[colIdx]) {
                                cells[colIdx].style.width = nw + 'px';
                                cells[colIdx].style.minWidth = nw + 'px';
                            }
                        });
                    }
                    function up() {
                        document.removeEventListener('mousemove', mv);
                        document.removeEventListener('mouseup', up);
                        var colWidths = [];
                        var firstRow = table.querySelector('tr');
                        if (firstRow) {
                            firstRow.querySelectorAll('td').forEach(function(c) { colWidths.push(c.offsetWidth); });
                        }
                        try {
                            var parsed = JSON.parse(el.id);
                            var d = readJsonInput('rpt-resize-hidden-input');
                            if (!d[parsed.tid]) d[parsed.tid] = {};
                            d[parsed.tid].col_widths = colWidths;
                            writeDashInput('rpt-resize-hidden-input', JSON.stringify(d));
                        } catch(ex) {}
                    }
                    document.addEventListener('mousemove', mv);
                    document.addEventListener('mouseup', up);
                });
            });

            // ── Row resize ──────────────────────────────────────────────────
            allEls.forEach(function(el) {
                if (!el.id || !el.id.includes('"type":"rpt-row-resize"')) return;
                if (el._rowResizeBound) return;
                el._rowResizeBound = true;
                el.addEventListener('mousedown', function(ev) {
                    ev.stopPropagation();
                    ev.preventDefault();
                    var td = el.parentElement;
                    var tr = td.parentElement;
                    var table = tr.closest('table');
                    var startY = ev.clientY;
                    var startHeight = tr.offsetHeight;
                    function mv(e) {
                        var nh = Math.max(20, startHeight + e.clientY - startY);
                        tr.style.height = nh + 'px';
                        tr.querySelectorAll('td').forEach(function(c) {
                            c.style.height = nh + 'px';
                            c.style.minHeight = nh + 'px';
                        });
                    }
                    function up() {
                        document.removeEventListener('mousemove', mv);
                        document.removeEventListener('mouseup', up);
                        var rowHeights = [];
                        table.querySelectorAll('tr').forEach(function(row) { rowHeights.push(row.offsetHeight); });
                        try {
                            var parsed = JSON.parse(el.id);
                            var d = readJsonInput('rpt-resize-hidden-input');
                            if (!d[parsed.tid]) d[parsed.tid] = {};
                            d[parsed.tid].row_heights = rowHeights;
                            writeDashInput('rpt-resize-hidden-input', JSON.stringify(d));
                        } catch(ex) {}
                    }
                    document.addEventListener('mousemove', mv);
                    document.addEventListener('mouseup', up);
                });
            });

            // ── Cell drop targets ────────────────────────────────────────────
            allEls.forEach(function(el) {
                if (!el.id || !el.id.includes('"type":"rpt-td"')) return;
                if (el._dropBound) return;
                el._dropBound = true;
                el.addEventListener('dragover', function(e) {
                    e.preventDefault();
                    el.style.outline = '2px dashed #16a34a';
                });
                el.addEventListener('dragleave', function() {
                    el.style.outline = '';
                });
                el.addEventListener('drop', function(e) {
                    e.preventDefault();
                    el.style.outline = '';
                    var varName = e.dataTransfer.getData('text/plain');
                    if (!varName) return;
                    try {
                        var parsed = JSON.parse(el.id);
                        var payload = JSON.stringify({
                            action: 'drop',
                            variable: varName,
                            tid: parsed.tid,
                            r: parsed.r,
                            c: parsed.c
                        });
                        writeDashInput('rpt-var-drop-hidden', payload);
                    } catch(ex) {}
                });
            });

        }, 200);
        return window.dash_clientside.no_update;
    }
    """,
    Output("rpt-drag-init-store", "data"),
    Input("html-report-canvas", "children"),
    prevent_initial_call=True,
)

# 11b. Variable item drag initialisation (re-binds when panel content changes)
dash.clientside_callback(
    """
    function(children) {
        setTimeout(function() {
            document.querySelectorAll('.rpt-var-item').forEach(function(el) {
                if (el._varDragBound) return;
                el._varDragBound = true;
                el.setAttribute('draggable', 'true');
                el.addEventListener('dragstart', function(e) {
                    var varName = el.getAttribute('data-var') || el.textContent.trim();
                    e.dataTransfer.setData('text/plain', varName);
                    e.dataTransfer.effectAllowed = 'copy';
                });
            });
        }, 100);
        return window.dash_clientside.no_update;
    }
    """,
    Output("rpt-drag-init-store", "data", allow_duplicate=True),
    Input("report-variables-panel-content", "children"),
    prevent_initial_call=True,
)


# 12. Drag hidden input → commit positions into state + reflow
@callback(
    Output("rpt-drag-pos", "data"),
    Output("rpt-state", "data", allow_duplicate=True),
    Input("rpt-drag-hidden-input", "value"),
    State("rpt-state", "data"),
    prevent_initial_call=True,
)
def _rpt_sync_drag_pos(raw, state):
    try:
        drag_pos = json.loads(raw or "{}")
    except Exception:
        drag_pos = {}

    if not drag_pos or not state:
        return drag_pos, dash.no_update

    tables = state.get("tables", [])
    for table in tables:
        if table["id"] in drag_pos:
            table["pos"] = drag_pos[table["id"]]

    _reflow_tables(tables)

    return {}, {"tables": tables, "next_id": state.get("next_id", 1)}


# 12b. Resize hidden input → resize store
@callback(
    Output("rpt-resize-store", "data"),
    Input("rpt-resize-hidden-input", "value"),
    prevent_initial_call=True,
)
def _rpt_sync_resize(raw):
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}


# 12c. Render variables panel
def _get_used_variables(state, all_vars):
    all_set = set(all_vars)
    used = set()
    for table in (state or {}).get("tables", []):
        for row in table.get("data", []):
            for cell in row:
                v = cell.get("v", "")
                if v in all_set:
                    used.add(v)
    return used


@callback(
    Output("report-variables-panel-content", "children"),
    Input("rpt-variables-store", "data"),
    Input("rpt-state", "data"),
    prevent_initial_call=False,
)
def _rpt_render_variables(var_store, state):
    all_vars   = (var_store or {}).get("all", [])
    id_to_label = (var_store or {}).get("id_to_label", {})
    if not all_vars:
        return html.Div("Select a report to load variables.",
                        style={"fontSize": "12px", "color": "#9ca3af"})
    used = _get_used_variables(state, all_vars)
    items = []
    for var in all_vars:
        if var in used:
            continue
        label = id_to_label.get(var, var)
        items.append(
            html.Div(
                label,
                className="rpt-var-item",
                **{"data-var": var},   # drag payload = raw filter_name ID
                style={
                    "padding": "5px 8px",
                    "marginBottom": "4px",
                    "background": "#e0f2fe",
                    "border": "1px solid #38bdf8",
                    "borderRadius": "5px",
                    "fontSize": "11px",
                    "cursor": "grab",
                    "userSelect": "none",
                    "color": "#0c4a6e",
                    "wordBreak": "break-word",
                },
            )
        )
    if not items:
        return html.Div("All variables placed.", style={"fontSize": "12px", "color": "#6b7280"})
    return items


# 12d. Apply variable drop to rpt-state
@callback(
    Output("rpt-state", "data", allow_duplicate=True),
    Input("rpt-var-drop-hidden", "value"),
    State("rpt-state", "data"),
    prevent_initial_call=True,
)
def _rpt_apply_var_drop(raw, state):
    try:
        payload = json.loads(raw or "{}")
    except Exception:
        raise PreventUpdate
    if payload.get("action") != "drop":
        raise PreventUpdate
    var = payload.get("variable", "")
    tid = payload.get("tid")
    r = payload.get("r")
    c = payload.get("c")
    if not var or not tid or r is None or c is None:
        raise PreventUpdate
    state = state or {"tables": [], "next_id": 1}
    tables = state["tables"]
    idx = next((i for i, t in enumerate(tables) if t["id"] == tid), None)
    if idx is None:
        raise PreventUpdate
    data = tables[idx]["data"]
    if r < len(data) and c < len(data[r]):
        data[r][c]["v"] = var
    tables[idx]["data"] = data
    return {"tables": tables, "next_id": state["next_id"]}


# 13a. Populate report dropdown when modal opens
@callback(
    Output("html-report-name", "options"),
    Input("create-reports-modal", "style"),
    prevent_initial_call=True,
)
def _rpt_populate_dropdown(modal_style):
    if not modal_style or modal_style.get("display") == "none":
        raise PreventUpdate
    hmis_path = os.path.join(os.getcwd(), "data", "hmis_reports.json")
    try:
        with open(hmis_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        active = [r for r in data.get("reports", []) if r.get("archived", "False") == "False"]
        return [{"label": r["report_name"], "value": r["page_name"]} for r in active]
    except Exception:
        return []


# 13b. Build rpt-state tables from VARIABLE_NAMES sheet
def _build_tables_from_variable_names(vn_df):
    """One table per 'section' row. Section's value cells = column headers; data rows' value cells = filter_name IDs."""
    all_vcols = [c for c in vn_df.columns if str(c).startswith("value_1x")]

    sections = []
    cur_sec, cur_rows = None, []
    for _, row in vn_df.iterrows():
        if str(row.get("type", "")).strip().lower() == "section":
            if cur_sec is not None:
                sections.append((cur_sec, cur_rows))
            cur_sec, cur_rows = row, []
        else:
            if pd.notna(row.get("name")):
                cur_rows.append(row)
    if cur_sec is not None:
        sections.append((cur_sec, cur_rows))

    def _val(raw):
        s = str(raw).strip()
        return "" if (pd.isna(raw) or s in ("nan", "None", "")) else s

    HEADER_FILL = "#e5e7eb"
    NAME_FILL   = "#f0fdf4"
    VAL_FILL    = "#ffffff"
    NAME_W, VAL_W, ROW_H = 250, 140, 28

    tables, nid, y = [], 1, 20
    for sec_row, data_rows in sections:
        if not data_rows:
            continue

        # Active value columns: section header defines it OR at least one data row has a value
        active_vc = [
            vc for vc in all_vcols
            if _val(sec_row.get(vc, "")) or any(_val(r.get(vc)) for r in data_rows)
        ]

        col_widths  = [NAME_W] + [VAL_W] * len(active_vc)
        row_heights = [ROW_H] * (1 + len(data_rows))   # header + data

        def mk(v, fill, color="#000000"):
            return {"v": v, "fill": fill, "color": color, "cs": 1, "rs": 1, "hidden": False}

        # Header row (from section row's value columns)
        hdr = [mk("", HEADER_FILL, "#374151")]
        for vc in active_vc:
            hdr.append(mk(_val(sec_row.get(vc, "")), HEADER_FILL, "#374151"))

        # Data rows
        tdata = [hdr]
        for dr in data_rows:
            cells = [mk(_val(dr.get("name", "")), NAME_FILL)]
            for vc in active_vc:
                cells.append(mk(_val(dr.get(vc, "")), VAL_FILL))
            tdata.append(cells)

        tables.append({
            "id": f"t{nid}",
            "pos": {"x": 20, "y": y},
            "ta": _val(sec_row.get("name", "")),
            "tb": None,
            "data": tdata,
            "col_widths": col_widths,
            "row_heights": row_heights,
        })
        nid += 1
        y += 24 + 34 + len(tdata) * (ROW_H + 2) + 30

    return {"tables": tables, "next_id": nid}


# 13c. Load existing design when a report is selected
@callback(
    Output("rpt-state", "data", allow_duplicate=True),
    Output("rpt-page-name", "data"),
    Output("rpt-variables-store", "data"),
    Input("html-report-name", "value"),
    prevent_initial_call=True,
)
def _rpt_load_design(page_name):
    if not page_name:
        raise PreventUpdate

    xlsx_path = os.path.join(os.getcwd(), "data", "uploads", f"{page_name}.xlsx")

    # ── 1. FILTERS sheet → variables (raw IDs + display labels) ────────────
    vars_list   = []   # raw filter_name IDs in sheet order
    id_to_label = {}   # filter_name → display string
    try:
        fl = pd.read_excel(xlsx_path, sheet_name="FILTERS")
        if "filter_name" in fl.columns:
            has_desc = "filter_name_desc" in fl.columns
            for _, row in fl.iterrows():
                fn = row.get("filter_name")
                if pd.isna(fn):
                    continue
                fn = str(fn).strip()
                if not fn:
                    continue
                vars_list.append(fn)
                if has_desc:
                    fd = row.get("filter_name_desc", "")
                    id_to_label[fn] = (f"{fn}: {fd}" if pd.notna(fd) and str(fd).strip()
                                       else fn)
                else:
                    id_to_label[fn] = fn
    except Exception:
        pass

    # ── 2. Saved design in hmis_reports.json (takes priority) ──────────────
    state = None
    hmis_path = os.path.join(os.getcwd(), "data", "hmis_reports.json")
    try:
        with open(hmis_path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        for report in saved_data.get("reports", []):
            if report.get("page_name") == page_name:
                design = report.get("design") or {}
                if design and design.get("tables"):
                    state = design
                break
    except Exception:
        pass

    # ── 3. Fall back to VARIABLE_NAMES sheet → prebuilt tables ─────────────
    if state is None:
        try:
            vn = pd.read_excel(xlsx_path, sheet_name="VARIABLE_NAMES")
            if not vn.empty and "name" in vn.columns:
                state = _build_tables_from_variable_names(vn)
        except Exception:
            pass

    if state is None:
        state = {"tables": [], "next_id": 1}

    return state, page_name, {"all": vars_list, "id_to_label": id_to_label}


# 13. Save report — writes design back into hmis_reports.json under the matched page_name
@callback(
    Output("html-report-save-status", "children"),
    Input("save-html-report-btn", "n_clicks"),
    State("rpt-state", "data"),
    State("rpt-page-name", "data"),
    State("rpt-drag-pos", "data"),
    State("rpt-resize-store", "data"),
    prevent_initial_call=True,
)
def _rpt_save_report(n_clicks, state, page_name, drag_pos, resize_store):
    if not n_clicks:
        raise PreventUpdate
    if not page_name:
        return "Select a report first."

    state = state or {"tables": [], "next_id": 1}
    drag_pos = drag_pos or {}
    resize_store = resize_store or {}

    # Merge drag positions and resize dimensions into state
    for table in state["tables"]:
        tid = table["id"]
        if tid in drag_pos:
            table["pos"] = drag_pos[tid]
        if tid in resize_store:
            if "col_widths" in resize_store[tid]:
                table["col_widths"] = resize_store[tid]["col_widths"]
            if "row_heights" in resize_store[tid]:
                table["row_heights"] = resize_store[tid]["row_heights"]

    hmis_path = os.path.join(os.getcwd(), "data", "hmis_reports.json")
    try:
        with open(hmis_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        updated = False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for report in data.get("reports", []):
            if report.get("page_name") == page_name:
                report["design"] = state
                report["date_updated"] = now
                updated = True
                break
        if not updated:
            return f"Report '{page_name}' not found in hmis_reports.json."
        with open(hmis_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return f"Saved! {now}"
    except Exception as e:
        return f"Error: {e}"
