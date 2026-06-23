import pandas as pd
pd.options.mode.chained_assignment = None
from typing import Any, Dict, List, Tuple
from helpers.visualizations import create_sum, create_count, create_count_sets
from helpers.dhis_integrater import get_dhis_data
import dash
import duckdb
from datetime import datetime
from dash import html, dash_table
from config import (DATE_,CONCEPT_NAME_,
                    ENCOUNTER_ID_,PERSON_ID_,VALUE_NUMERIC_,VALUE_DATETIME_,FACILITY_CODE_,
                    DHIS2_URL, actual_keys_in_data)


class ReportTableBuilder:
    def __init__(self, excel_path: str,report_start_date, report_end_date,data_route, location:str, dhis2_period: str):
        self.excel_path = excel_path
        self.dhis_url = f"{DHIS2_URL}/api/dataValueSets.json"
        self.vars_df: pd.DataFrame | None = None
        self.filters_df: pd.DataFrame | None = None
        self.filters_map: Dict[str, Any] = {}
        self._value_cache: Dict[str, str] = {}
        self._errors: List[str] = []
        self.report_name: pd.DataFrame | None = None
        self.dhis2_period = dhis2_period
        self._set_cache = {}
        self._mask_cache = {}
        self.start_date = report_start_date
        self.end_date = report_end_date
        self.location = location
        self.data_route = data_route


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
            num_field = str(row.get("num_field", VALUE_NUMERIC_)).strip()
            unique_column = str(row.get("unique_column", PERSON_ID_)).strip()
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
            cached = self._value_cache[filter_name]
            # If a sentinel dict is cached (calculated not yet resolved), resolve now.
            if isinstance(cached, dict) and "__calculated__" in cached:
                resolved = self._resolve_calculated(cached["__calculated__"], filter_name)
                self._value_cache[filter_name] = resolved
                return resolved
            return cached
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

        filtered_dates = f"{DATE_} BETWEEN '{self.start_date}'::TIMESTAMP AND '{self.end_date}'::TIMESTAMP AND {FACILITY_CODE_} = '{self.location}' "
        original_dates = f"{DATE_} <= '{self.end_date}'::TIMESTAMP AND {FACILITY_CODE_} = '{self.location}' "

        if measure == "sum":
            args = [filtered_dates,self.data_route, PERSON_ID_, spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_sum(*args,self.start_date, self.end_date)
            
        elif measure == "cohort_sum":
            args = [original_dates,self.data_route, PERSON_ID_, spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_sum(*args,self.start_date, self.end_date)

        elif measure == "count_set":
            args = [filtered_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_count_sets(*args,self.start_date, self.end_date)
        
        elif measure == "cohort_count_set":
            args = [original_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_count_sets(*args,self.start_date, self.end_date)

        elif measure == "cohort_count_set_defaulter":
            args = [original_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_count_sets(*args,self.start_date, self.end_date)

        elif measure == "count_set_defaulter":
            args = [filtered_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_count_sets(*args,self.start_date, self.end_date)

        elif measure == "count":
            args = [filtered_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_count(*args,self.start_date, self.end_date)
        
        elif measure == "nunique":
            args = [filtered_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_count(*args,self.start_date, self.end_date)

        elif measure == "cohort_count":
            args = [original_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_count(*args,self.start_date, self.end_date)

        elif measure == "cohort_count_defaulter":
            args = [original_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_count(*args,self.start_date, self.end_date)

        elif measure == "count_defaulter":
            args = [filtered_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_count(*args,self.start_date, self.end_date)

        elif measure == "calculated":
            # Store the expression for deferred evaluation; resolved after
            # all other filter values are pre-computed in _precompute_all_filter_values.
            expression = str(spec.get("unique_column", "")).strip()
            self._value_cache[filter_name] = {"__calculated__": expression}
            return self._value_cache[filter_name]
        else:
            result = ""

        result_str = "" if result is None else str(result)
        self._value_cache[filter_name] = result_str
        if isinstance(result, (int, float)):
            self._value_cache[filter_name] = f"{result:g}" # format to remove trailing zeros
        return result_str

    def _collect_value_columns(self) -> List[str]:
        return sorted([c for c in self.vars_df.columns if c.lower().startswith("value_")])
    
    def _title(self) -> str:
        if self.report_name is None or "name" not in self.report_name.columns:
            return "Report"
        vals = [str(v).strip() for v in self.report_name["name"].tolist() if str(v).strip()]
        return vals[0] if vals else "Report"
    
    def _page_design(self) -> str:
        if self.report_name is None or "page_design" not in self.report_name.columns:
            return "portrait"
        vals = [str(v).strip() for v in self.report_name["page_design"].tolist() if str(v).strip()]
        return vals[0] if vals else "portrait"
    
    def _page_columns(self) -> int:
        if self.report_name is None or "page_columns" not in self.report_name.columns:
            return 1
        vals = [str(v).strip() for v in self.report_name["page_columns"].tolist() if str(v).strip()]
        return int(vals[0]) if vals else 1
    
    def _generate_dhis_params(self) -> Dict:
        if "dhis2_id" in self.report_name.columns:
            dataSetID = self.report_name['dhis2_id'].iloc[0]
        else:
            dataSetID = self.report_name['id'].iloc[0]
        params = {
            'dataSet':dataSetID,
            'period':self.dhis2_period,
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

    def _precompute_all_filter_values(self) -> None:
        """Pre-compute every filter value so that 'calculated' expressions can
        reference filters from any section.  Two-pass approach:
          Pass 1 – compute all non-calculated filters (populates _value_cache).
          Pass 2 – resolve all calculated filters using the fully-populated cache.
        """
        import re

        # Pass 1: non-calculated filters
        for fname, spec in self.filters_map.items():
            if spec["measure"] != "calculated":
                self._compute_value_from_filter(fname)

        # Pass 2: calculated filters (expression evaluation)
        for fname, spec in self.filters_map.items():
            if spec["measure"] == "calculated":
                # Ensure the sentinel dict is in cache (handles first-call case)
                cached = self._value_cache.get(fname)
                if not isinstance(cached, dict) or "__calculated__" not in cached:
                    self._compute_value_from_filter(fname)
                    cached = self._value_cache.get(fname)

                if isinstance(cached, dict) and "__calculated__" in cached:
                    resolved = self._resolve_calculated(cached["__calculated__"], fname)
                    self._value_cache[fname] = resolved

    def _resolve_calculated(self, expression: str, filter_name: str) -> str:
        import re
        has_division = "/" in expression
        token_pattern = re.compile(r"\{([^}]+)\}")

        def replace_token(match: re.Match) -> str:
            ref_name = match.group(1).strip()
            cached = self._value_cache.get(ref_name)
            if isinstance(cached, dict):
                self._errors.append(
                    f"Calculated filter '{filter_name}': dependency '{ref_name}' "
                    "is also calculated and could not be pre-resolved."
                )
                return "0"
            val_str = str(cached or "0").replace("%", "").strip()
            try:
                float(val_str)  # validate it's numeric
                return val_str
            except ValueError:
                return "0"

        substituted = token_pattern.sub(replace_token, expression)

        try:
            raw_result = eval(substituted, {"__builtins__": {}})  # safe – only arithmetic
            if has_division:
                rounded = round(float(raw_result), 2)
                # Strip unnecessary trailing zeros (e.g. 3.10 → 3.1, 3.00 → 3)
                result_str = f"{rounded:.2f}".rstrip("0").rstrip(".")
            else:
                result_str = str(int(round(float(raw_result))))
        except Exception as exc:
            self._errors.append(
                f"Calculated filter '{filter_name}': could not evaluate "
                f"'{substituted}' — {exc}"
            )
            result_str = "N/A"

        return result_str

    def build_section_tables(self) -> List[Tuple[str, pd.DataFrame]]:
        self._precompute_all_filter_values()
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
                    out[current_headers.get(vc, vc)] = (self._compute_value_from_filter(filter_ref) if filter_ref else "")       
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
        title = self._title() or "HMIS DATASET REPORT (UNNAMED)"
        page_design = self._page_design()
        page_columns = self._page_columns() or 1
        sections = self.build_section_tables()

        num_page_columns = 1
        if self.report_name is not None and not self.report_name.empty:
            try:
                num_page_columns = page_columns
            except (ValueError, TypeError):
                num_page_columns = 1
            num_page_columns = max(1, min(4, num_page_columns))
            design = str(page_design).lower()
            if design not in ("portrait", "landscape"):
                design = "portrait"
            

        is_landscape = page_design == "landscape"
        container_style = {
            "fontFamily": "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
            "maxWidth": "1400px" if is_landscape else "960px",
            "margin": "0 auto",
        }

        header = html.Div(
            style={"textAlign": "center", "marginBottom": "18px",
                   "paddingBottom": "10px",
                   "borderBottom": "2px solid #006401"},
            children=[
                html.H3(title.upper(),
                        style={"margin": "0 0 4px", "color": "#006401",
                               "fontSize": "15px", "fontWeight": "700",
                               "letterSpacing": "0.5px"}),
                html.Span(
                    f"{'Landscape' if is_landscape else 'Portrait'}  ·  "
                    f"{num_page_columns}-column layout",
                    style={"fontSize": "11px", "color": "#6b7280"}
                ),
            ],
        )

        # ── Build section list ─────────────────────────────────────────────────
        section_divs: List[Any] = []
        for section_idx, (subtitle, subdf) in enumerate(sections):
            subdf = self._apply_dhis_mapping(subdf)
            if len(subdf.columns) <= 1:
                continue
            section_divs.append(
                html.Div(
                    style={"breakInside": "avoid", "pageBreakInside": "avoid",
                           "marginBottom": "16px"},
                    children=[self._create_modern_table(subdf, section_idx, subtitle)],
                )
            )

        if num_page_columns == 1:
            body = html.Div(section_divs)
        else:
            body = html.Div(
                style={
                    "display": "grid",
                    "gridTemplateColumns": f"repeat({num_page_columns}, 1fr)",
                    "gap": "16px",
                    "alignItems": "start",
                },
                children=section_divs,
            )

        children: List[Any] = [header, body]

        if self._errors:
            children.append(
                html.Div(
                    style={"marginTop": "14px", "padding": "10px 14px",
                           "background": "#fef2f2", "border": "1px solid #fecaca",
                           "borderRadius": "6px"},
                    children=[
                        html.Strong("⚠ Validation Notes", style={"color": "#dc2626"}),
                        html.Ul([html.Li(e, style={"fontSize": "12px"})
                                 for e in self._errors]),
                    ],
                )
            )

        return [html.Div(children, style=container_style)]

    def _create_modern_table(self, df: pd.DataFrame, section_idx: int, section_title: str) -> html.Div:
        """Render a report section as a clean, branded table."""
        df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)
        if df.empty:
            return html.Div(
                "No data available",
                style={"color": "#9ca3af", "fontSize": "12px",
                       "padding": "8px 0", "fontStyle": "italic"},
            )

        value_cols = [c for c in df.columns if c != "Data Element"]

        # ── Dynamic column widths ──────────────────────────────────────────────
        de_width   = min(max(len(str(x)) for x in df["Data Element"].tolist()) * 7 + 30, 340)
        val_widths = {
            col: min(max(len(str(x)) for x in df[col].tolist()) * 7 + 20, 160)
            for col in value_cols
        }

        # ── Section title bar ──────────────────────────────────────────────────
        title_bar = html.Div(
            section_title.upper() if section_title else "",
            style={
                "background": "#006401",
                "color": "#ffffff",
                "fontSize": "11px",
                "fontWeight": "700",
                "letterSpacing": "0.6px",
                "padding": "7px 12px",
                "borderRadius": "4px 4px 0 0",
            },
        )

        table = dash_table.DataTable(
            id=f"report-table-{section_idx}",
            data=df.to_dict("records"),
            columns=(
                [{"name": section_title.upper(), "id": "Data Element"}]
                + [{"name": col.upper(), "id": col} for col in value_cols]
            ),
            # ── Table container ─────────────────────────────────────────────
            style_table={
                "overflowX": "auto",
                "overflowY": "visible",
                "minWidth": "100%",
                "borderRadius": "0 0 4px 4px",
                "border": "1px solid #d1d5db",
                "borderTop": "none",
            },
            # ── Cell base ───────────────────────────────────────────────────
            style_cell={
                "fontFamily": "'Segoe UI', Tahoma, sans-serif",
                "fontSize": "12px",
                "padding": "8px 12px",
                "border": "1px solid #e5e7eb",
                "textAlign": "left",
                "whiteSpace": "normal",
                "wordBreak": "break-word",
                "height": "auto",
                "minHeight": "28px",
                "lineHeight": "1.4",
            },
            # ── Per-column overrides ─────────────────────────────────────────
            style_cell_conditional=[
                {
                    "if": {"column_id": "Data Element"},
                    "fontWeight": "600",
                    "color": "#1f2937",
                    "backgroundColor": "#f9fafb",
                    "width": f"{de_width}px",
                    "minWidth": "180px",
                    "position": "sticky",
                    "left": 0,
                    "zIndex": 1,
                    "borderRight": "2px solid #d1d5db",
                },
                *[
                    {
                        "if": {"column_id": col},
                        "textAlign": "center",
                        "width": f"{val_widths[col]}px",
                        "minWidth": "80px",
                        "color": "#374151",
                    }
                    for col in value_cols
                ],
            ],
            # ── Header ──────────────────────────────────────────────────────
            style_header={
                "backgroundColor": "#374151",
                "color": "#f9fafb",
                "fontWeight": "700",
                "fontSize": "11px",
                "textAlign": "center",
                "padding": "9px 12px",
                "border": "1px solid #4b5563",
                "letterSpacing": "0.4px",
                "position": "sticky",
                "top": 0,
                "zIndex": 2,
            },
            style_header_conditional=[
                {
                    "if": {"column_id": "Data Element"},
                    "textAlign": "left",
                    "backgroundColor": "#1f2937",
                }
            ],
            # ── Data rows ───────────────────────────────────────────────────
            style_data={
                "whiteSpace": "normal",
                "height": "auto",
                "minHeight": "32px",
            },
            style_data_conditional=[
                {"if": {"row_index": "odd"}, "backgroundColor": "#f9fafb"},
                {"if": {"row_index": "even"}, "backgroundColor": "#ffffff"},
                *[
                    {"if": {"filter_query": f"{{{col}}} = ''",
                             "column_id": col},
                     "backgroundColor": "#f3f4f6", "color": "#d1d5db"}
                    for col in value_cols
                ],
                {
                    "if": {"filter_query": "{Data Element} = ''"},
                    "backgroundColor": "#f3f4f6",
                },
            ],
            css=[{
                "selector": ".dash-spreadsheet td div",
                "rule": "line-height: 1.4; max-height: none; "
                        "overflow: visible; white-space: normal;",
            }],
            tooltip_data=[
                {
                    col: {"value": str(val), "type": "markdown"}
                    for col, val in row.items()
                    if val and len(str(val)) > 50
                }
                for row in df.to_dict("records")
            ],
            tooltip_duration=None,
            style_as_list_view=False,
            filter_action="none",
            sort_action="native",
            sort_mode="single",
            page_action="none",
            virtualization=False,
            fixed_rows={"headers": True},
        )

        return html.Div(
            style={"marginBottom": "0", "breakInside": "avoid"},
            children=[table],
        )