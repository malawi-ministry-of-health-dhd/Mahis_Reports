import pandas as pd
from typing import Any, Dict, List, Tuple
from helpers.visualizations import create_sum, create_count, create_count_sets
from helpers.dhis_integrater import get_dhis_data
import dash
from datetime import datetime
from dash import html, dash_table

class ReportTableBuilder:
    def __init__(self, excel_path: str, filtered_df: pd.DataFrame, original_df: pd.DataFrame):
        self.excel_path = excel_path
        self.filtered_df = filtered_df
        self.original_df = original_df
        self.dhis_url = 'https://dhis2.health.gov.mw/api/dataValueSets.json'
        self.vars_df: pd.DataFrame | None = None
        self.filters_df: pd.DataFrame | None = None
        self.filters_map: Dict[str, Any] = {}
        self._value_cache: Dict[str, str] = {}
        self._errors: List[str] = []
        self.report_name: pd.DataFrame | None = None

    def load_spec(self) -> None:
        xls = pd.ExcelFile(self.excel_path, engine="openpyxl")
        self.vars_df = pd.read_excel(xls, sheet_name="VARIABLE_NAMES", engine="openpyxl")
        self.filters_df = pd.read_excel(xls, sheet_name="FILTERS", engine="openpyxl")
        self.vars_df.columns = [str(c).strip() for c in self.vars_df.columns]
        self.filters_df.columns = [str(c).strip() for c in self.filters_df.columns]
        self.vars_df = self.vars_df.fillna("")
        self.filters_df = self.filters_df.fillna("")
        self.report_name = pd.read_excel(xls, sheet_name="REPORT_NAME", engine="openpyxl")
        self.report_name.columns = [str(c).strip() for c in self.report_name.columns]
        self._build_filters_map()

    def _build_filters_map(self) -> None:
        self.filters_map.clear()
        for _, row in self.filters_df.iterrows():
            fname = str(row.get("filter_name", "")).strip()
            if not fname:
                continue
            measure = str(row.get("measure", "count")).strip().lower()
            num_field = str(row.get("num_field", "ValueN")).strip()
            unique_column = str(row.get("unique_column", "encounter_id")).strip()
            pairs: List[Tuple[str, Any]] = []
            for i in range(1, 10):
                fcol = str(row.get(f"variable{i}", "")).strip()
                if not fcol:
                    continue
                parsed_col = self._parse_col_value(fcol)

                fval = row.get(f"value{i}", "")
                parsed_val = self._parse_filter_value(fval)
                pairs.append((parsed_col, parsed_val))
            self.filters_map[fname] = {
                "measure": measure,
                "num_field": num_field,
                "unique_column": unique_column,
                "pairs": pairs,
                "literal_value": row.get("literal_value", ""),
                "numerator_filter": str(row.get("numerator_filter", "")).strip(),
                "denominator_filter": str(row.get("denominator_filter", "")).strip(),
            }

    @staticmethod
    def _parse_filter_value(val: Any) -> Any:
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return ""
            if s.startswith("[") and s.endswith("]"):
                inner = s[1:-1].strip()
                return [] if not inner else [x.strip() for x in inner.split(",")]
            if "|" in s:
                return [x.strip() for x in s.split("|")]
        return val
    
    @staticmethod
    def _parse_col_value(col: Any) -> Any:
        if isinstance(col, list):
            return col
        if isinstance(col, str):
            s = col.strip()
            if not s:
                return ""
            if s.startswith("[") and s.endswith("]"):
                inner = s[1:-1].strip()
                return [] if not inner else [x.strip() for x in inner.split(",")]
            if "|" in s:
                return [x.strip() for x in s.split("|")]
        return col

    def _compute_value_from_filter(self, filter_name: str) -> str:
        if not filter_name:
            return ""
        if filter_name in self._value_cache:
            return self._value_cache[filter_name]
        if filter_name not in self.filters_map:
            self._errors.append(f"FILTERS row not found: '{filter_name}'")
            self._value_cache[filter_name] = "N/A"
            return "N/A"

        spec = self.filters_map[filter_name]
        measure = spec["measure"]
        if measure == "literal":
            result_str = "" if spec["literal_value"] is None else str(spec["literal_value"])
            self._value_cache[filter_name] = result_str
            return result_str

        if measure == "percentage":
            numerator_name = spec.get("numerator_filter", "")
            denominator_name = spec.get("denominator_filter", "")
            num_raw = self._compute_value_from_filter(numerator_name)
            den_raw = self._compute_value_from_filter(denominator_name)
            try:
                num = float(str(num_raw).replace("%", "").strip() or 0)
                den = float(str(den_raw).replace("%", "").strip() or 0)
                result = 0 if den == 0 else round((num / den) * 100, 1)
                result_str = f"{result:g}%"
            except Exception:
                result_str = "N/A"
            self._value_cache[filter_name] = result_str
            return result_str

        args: List[Any] = [self.filtered_df]
        args_cohort: List[Any] = [self.original_df]

        if measure == "sum":
            args.append(spec["num_field"])
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_sum(*args)
        elif measure == "count_set":
            args.append(spec["unique_column"])
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_count_sets(*args)
        elif measure == "count":
            args: List[Any] = [self.filtered_df, measure]
            args.append(spec["unique_column"])
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_count(*args)
        elif measure == "cohort_sum":
            args_cohort.append(spec["num_field"])
            for fcol, fval in spec["pairs"]:
                args_cohort.extend([fcol, fval])
            result = create_sum(*args_cohort)
        elif measure == "cohort_count_set":
            args_cohort.append(spec["unique_column"])
            for fcol, fval in spec["pairs"]:
                args_cohort.extend([fcol, fval])
            result = create_count_sets(*args_cohort)
        elif measure == "cohort_count":
            args_cohort.append(spec["unique_column"])
            for fcol, fval in spec["pairs"]:
                args_cohort.extend([fcol, fval])
            result = create_count(*args_cohort)
        else:
            result = ""

        result_str = "" if result is None else str(result)
        self._value_cache[filter_name] = result_str
        return result_str

    def _collect_value_columns(self) -> List[str]:
        return sorted([c for c in self.vars_df.columns if c.lower().startswith("value_")])
    
    def _title(self) -> str:
        if self.report_name is None or "name" not in self.report_name.columns:
            return "Report"
        vals = [str(v).strip() for v in self.report_name["name"].tolist() if str(v).strip()]
        return vals[0] if vals else "Report"
    
    def _generate_dhis_params(self) -> Dict:
        params = {
            'dataSet':self.report_name['id'].iloc[0],
            'period':'202512',
            'orgUnit':'glIscvEdIJz'}
        return params
    
    def _prepare_for_dhis_integration(self)-> List:
        json_data = get_dhis_data(self.dhis_url, params=self._generate_dhis_params())
        return json_data
    
    def _apply_dhis_mapping(self, df):
        if "DHIS2-SCANFORM" not in df.columns:
            return df
        dhis_data = self._prepare_for_dhis_integration()
        composite_key = {
            f"{item['dataElement']}-{item['categoryOptionCombo']}": item['value']
            for item in dhis_data
        }
        single_key = {
            item['dataElement']: item['value']
            for item in dhis_data
        }
        mapped = df["DHIS2-SCANFORM"].map(composite_key)
        mapped = mapped.fillna(df["DHIS2-SCANFORM"].map(single_key))
        df["DHIS2-SCANFORM"] = mapped
        return df

    def build_section_tables(self) -> List[Tuple[str, pd.DataFrame]]:
        value_cols = self._collect_value_columns()
        sections: List[Tuple[str, pd.DataFrame]] = []
        current_section_name = ""
        current_headers: Dict[str, str] = {}
        buffer: List[Dict[str, Any]] = []

        for _, row in self.vars_df.iterrows():
            row_type = str(row.get("type", "")).strip().lower()
            name = str(row.get("name", "")).strip()
            if not name:
                continue

            if row_type == "section":
                if buffer:
                    df = pd.DataFrame(buffer)
                    df = df.loc[:, (df != "").any(axis=0)]
                    # df = self._apply_dhis_mapping(df)
                    sections.append((current_section_name, df))
                    buffer = []
                current_section_name = name
                current_headers = {}
                for vc in value_cols:
                    header_val = str(row.get(vc, "")).strip()
                    if header_val:
                        current_headers[vc] = header_val
                continue

            out = {"Data Element": name}
            for vc in value_cols:
                filter_ref = str(row.get(vc, "")).strip()
                if current_headers.get(vc, vc) == 'DHIS2-SCANFORM':
                    out[current_headers.get(vc, vc)] = filter_ref
                else:
                    out[current_headers.get(vc, vc)] = (
                        self._compute_value_from_filter(filter_ref) if filter_ref else ""
                )
            buffer.append(out)

        if buffer:
            df = pd.DataFrame(buffer)
            df = df.loc[:, (df != "").any(axis=0)]
            # df = self._apply_dhis_mapping(df)
            sections.append((current_section_name, df))    
        return sections
    
 
    def build_section_tables_with_ids(self) -> List[Tuple[str, pd.DataFrame]]:
        value_cols = self._collect_value_columns()
        sections: List[Tuple[str, pd.DataFrame]] = []
        current_section_name = ""
        current_headers: Dict[str, str] = {}
        buffer: List[Dict[str, Any]] = []

        for _, row in self.vars_df.iterrows():
            row_type = str(row.get("type", "")).strip().lower()
            name = str(row.get("name", "")).strip()
            if not name:
                continue

            if row_type == "section":
                if buffer:
                    df = pd.DataFrame(buffer)
                    df = df.loc[:, (df != "").any(axis=0)]
                    sections.append((current_section_name, df))
                    buffer = []
                current_section_name = name
                current_headers = {}
                for vc in value_cols:
                    header_val = str(row.get(vc, "")).strip()
                    if header_val:
                        current_headers[vc] = header_val
                continue

            out = {"Data Element": name}
            for vc in value_cols:
                filter_ref = str(row.get(vc, "")).strip()
                out[current_headers.get(vc, vc)] = filter_ref if filter_ref else ""
            buffer.append(out)

        if buffer:
            df = pd.DataFrame(buffer)
            df = df.loc[:, (df != "").any(axis=0)]
            sections.append((current_section_name, df))
        return sections
    
    
    def build_dash_components(self) -> List[Any]:
        title = self._title() or "Report"
        sections = self.build_section_tables()
        children: List[Any] = [
            html.Div(
                children=[
                    html.H2(title, style={"text-align":"center"}),
                ]
            )
        ]
        for section_idx, (subtitle, subdf) in enumerate(sections):
            subdf = self._apply_dhis_mapping(subdf)
            if len(subdf.columns) <=1: #skip if the column has nothing in place of data. Only allow the forms that have value1x1,etc to be previewed
                continue
            if subtitle:
                children.append(
                    html.Div(
                        className="report-section",
                        children=[
                            html.H3(subtitle, className="section-title"),
                            self._create_modern_table(subdf, section_idx)
                        ]
                    )
                )
            else:
                children.append(self._create_modern_table(subdf, section_idx))

        if self._errors:
            children.append(
                html.Div(
                    className="report-errors",
                    children=[
                        html.I(className="fas fa-exclamation-triangle"),
                        html.Span(" Validation Notes:"),
                        html.Ul([html.Li(e) for e in self._errors])
                    ]
                )
            )

        return children
    
    def _create_modern_table(self, df: pd.DataFrame, section_idx: int) -> html.Div:
        """Create a modern, well-aligned table with proper column widths and no internal scrolling"""
        df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
        if df.empty:
            return html.Div("No data available", className="empty-table-message")
        value_cols = [c for c in df.columns if c != "Data Element"]
        column_widths = {}
        # Data Element column
        max_data_element_len = max(
            [len(str(x)) for x in df["Data Element"].tolist()] + [len("Data Element")]
        )
        column_widths["Data Element"] = min((len(value_cols) +1) * 8, 350)
        # Value columns
        for col in value_cols:
            max_val_len = max(
                [len(str(x)) for x in df[col].tolist()] + [len(str(col))]
            )
            column_widths[col] = min(max_val_len * 8, 250)
        
        # Create table without filters and page controls
        return html.Div(
            className="report-table-wrapper",
            style={
                "overflowX": "auto",  # Only horizontal scroll if needed
                "overflowY": "visible",  # No vertical scroll
                "marginBottom": "20px"
            },
            children=[
                dash_table.DataTable(
                    id=f"report-table-{section_idx}",
                    data=df.to_dict("records"),
                    columns=[{"name": "Data Element", "id": "Data Element"}] + 
                            [{"name": col, "id": col} for col in value_cols],
                    style_table={
                        "overflowX": "auto",
                        "overflowY": "visible",
                        "borderRadius": "12px",
                        "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
                        "minWidth": "100%"
                    },
                    style_cell={
                        "padding": "12px 16px",
                        "fontFamily": "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
                        "fontSize": "13px",
                        "border": "1px solid #e9ecef",
                        "textAlign": "left",
                        "whiteSpace": "normal",
                        "wordBreak": "break-word",
                        "height": "auto",  # Allow height to adjust to content
                        "minHeight": "45px"
                    },
                    style_cell_conditional=[
                        {
                            "if": {"column_id": "Data Element"},
                            "fontWeight": "600",
                            "backgroundColor": "#f8f9fa",
                            "width": f"{column_widths['Data Element']}px",
                            "minWidth": "200px",
                            "position": "sticky",
                            "left": 0,
                            "zIndex": 1
                        },
                        *[
                            {
                                "if": {"column_id": col},
                                "textAlign": "center",
                                "width": f"{column_widths[col]}px",
                                "minWidth": "100px"
                            }
                            for col in value_cols
                        ]
                    ],
                    style_header={
                        "backgroundColor": "#AAAAAA",
                        "fontWeight": "600",
                        "border": "1px solid #dee2e6",
                        "color": "#ffffff",
                        "padding": "12px 16px",
                        "fontSize": "14px",
                        "textAlign": "center",
                        "position": "sticky",
                        "top": 0,
                        "zIndex": 2
                    },
                    style_data={
                        "whiteSpace": "normal",
                        "height": "auto",
                        "minHeight": "45px"
                    },
                    style_data_conditional=[
                        # Zebra striping
                        {
                            "if": {"row_index": "odd"},
                            "backgroundColor": "#f8f9fa"
                        },
                        *[
                            {
                                "if": {"filter_query": f"{{{col}}} = ''"},
                                "backgroundColor": "#f1f3f4",
                                # "color": "#adb5bd"
                            }
                            for col in value_cols
                        ],
                        # Empty cell styling for Data Element column
                        {
                            "if": {"filter_query": "{Data Element} = ''"},
                            "backgroundColor": "#f1f3f4"
                        }
                    ],
                    css=[{
                        'selector': '.dash-spreadsheet td div',
                        'rule': '''
                            line-height: 1.4;
                            max-height: none;
                            overflow: visible;
                            white-space: normal;
                        '''
                    }],
                    tooltip_data=[
                        {
                            column: {'value': str(value), 'type': 'markdown'}
                            for column, value in row.items()
                            if value and len(str(value)) > 50
                        }
                        for row in df.to_dict('records')
                    ],
                    tooltip_duration=None,
                    style_as_list_view=True,
                    # Remove all filtering and pagination features
                    filter_action="none",
                    sort_action="native",
                    sort_mode="single",
                    page_action="none",
                    virtualization=False,  # Disable virtualization to show all rows
                    fixed_rows={'headers': True},  # Only header is fixed
                )
            ]
        )