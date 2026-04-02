
import pandas as pd
from typing import Any, Dict, List, Tuple
from visualizations import create_sum, create_count, create_count_sets

class ReportTableBuilder:
    def __init__(self, excel_path: str, filtered_df: pd.DataFrame, original_df: pd.DataFrame):
        self.excel_path = excel_path
        self.filtered_df = filtered_df
        self.original_df = original_df

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
            measure = str(row.get("measure", "")).strip().lower()
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
            # if "," in s:
            #     return [x.strip() for x in s.split(",")]
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
            # if "," in s:
            #     return [x.strip() for x in s.split(",")]
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
        args_cohort: List[Any] = [self.original_df] #cohort data that is not filtered on report to display all patients from the beginning

        # FILTERED DATA
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
            args.append(spec["unique_column"])
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result = create_count(*args)
        
        # COHORT DATA - FROM PATIENT ENTRY
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
            result = "" #no result if none has been indicated

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
            # outx = {"Data Element": name}
            for vc in value_cols:
                filter_ref = str(row.get(vc, "")).strip()
                out[current_headers.get(vc, vc)] = (
                    self._compute_value_from_filter(filter_ref) if filter_ref else ""
                )
            buffer.append(out)

        if buffer:
            df = pd.DataFrame(buffer)
            df = df.loc[:, (df != "").any(axis=0)]
            sections.append((current_section_name, df))
        return sections
    
    # Note this method is done to bring out IDs instead of calculated data so that the json can has the IDs
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
                out[current_headers.get(vc, vc)] = (
                    filter_ref if filter_ref else ""
                )
            buffer.append(out)


        if buffer:
            df = pd.DataFrame(buffer)
            df = df.loc[:, (df != "").any(axis=0)]
            sections.append((current_section_name, df))
        return sections

    
    def build_dash_components(self) -> List[Any]:
        from dash import html, dash_table

        title = self._title() or "Report"  # Or use self._title() if DESIGN sheet still has Title
        sections = self.build_section_tables()  # New method for multi-section tables

        children: List[Any] = [html.H2(title, style={"textAlign": "center"})] 
        
        for subtitle, subdf in sections:
            if subtitle:
                children.append(html.H3(subtitle, style={"marginBottom": "0px"}))

            value_cols = [c for c in subdf.columns if c != "Data Element"]
            columns = [{"name": "Data Element", "id": "Data Element"}]
            for cid in value_cols:
                columns.append({"name": cid, "id": cid})

            children.append(
                dash_table.DataTable(
                    data=subdf.to_dict("records"),
                    columns=columns,
                    style_table={"overflowX": "auto"},
                    style_cell={
                        "padding": "6px",
                        "fontFamily": "Segoe UI, Arial, sans-serif",
                        "fontSize": "14px",
                        "border": "1px solid #e9ecef",
                        "minWidth": "120px",
                    },
                    style_header={
                        "backgroundColor": "#198754",
                        "fontWeight": "bold",
                        "border": "1px solid #dee2e6",
                        "color": "#ffffff",
                        "textAlign": "center"
                    },
                    style_data_conditional=[
                        {"if": {"column_id": "Data Element"}, "textAlign": "left", "fontWeight": "600"},
                        *[{"if": {"column_id": cid}, "textAlign": "center"} for cid in value_cols],
                        # Grey background for empty cells
                        {"if": {"column_id": "Data Element", "filter_query": "{Data Element} = ''"}, "backgroundColor": "#f1f3f4"},
                        *[
                            {"if": {"column_id": cid, "filter_query": f"{{{cid}}} = ''"}, "backgroundColor": "#f1f3f4"}
                            for cid in value_cols
                        ]
                    ]
                )
            )

        # Optional: show any parsing errors below the tables
        if self._errors:
            children.append(
                html.Div(
                    [html.Small(e) for e in self._errors],
                    style={"color": "#b02a37", "marginTop": "8px"}
                )
            )

        return children
