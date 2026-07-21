import pandas as pd
pd.options.mode.chained_assignment = None
from typing import Any, Dict, List, Tuple
from helpers.visualizations import create_sum, create_count, create_count_sets
from helpers.dhis_integrater import get_dhis_data
import dash
import duckdb
import os
from datetime import datetime
from dash import html, dcc, dash_table
from config import (DATE_,CONCEPT_NAME_,FACILITY_,
                    ENCOUNTER_ID_,PERSON_ID_,VALUE_NUMERIC_,VALUE_DATETIME_,FACILITY_CODE_,
                    DHIS2_URL, actual_keys_in_data)



class ReportTableBuilder:
    def __init__(self, excel_path: str,report_start_date, 
                 report_end_date,data_route, location:str, facility=None,
                 dhis2_period= None, report_design = None, report_filters=None):
        self.excel_path = excel_path
        self.dhis_url = f"{DHIS2_URL}/api/dataValueSets.json"
        self.vars_df: pd.DataFrame | None = None
        self.filters_df: pd.DataFrame | None = None
        self.filters_map: Dict[str, Any] = {}
        self._value_cache: Dict[str, str] = {}
        self._patient_ids_cache: Dict[str, List] = {}
        self._errors: List[str] = []
        self.report_name: pd.DataFrame | None = None
        self.dhis2_period = dhis2_period
        self._set_cache = {}
        self._mask_cache = {}
        self.start_date = report_start_date
        self.end_date = report_end_date
        self.location = location
        self.facility = facility
        self.data_route = data_route
        self.report_design = report_design
        self.report_filters = report_filters
        self.facilities_path = os.path.join(os.getcwd(), data_route.replace("/parquet",""),'single_tables', 'locations_data.csv')


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
        self.facilities = pd.read_csv(self.facilities_path)
        self.location_name = self.facilities.set_index('location_id')['name'].to_dict().get(int(self.location), "")
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
            for i in range(1, 11):
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
        
        # When filters are updated in config, let them be used first as updated spec
        updated_spec = self.report_filters.get(filter_name, {})

        updated_pairs = []
        for i in range(1,11):
            col = updated_spec.get(f"variable{i}", "")
            val = updated_spec.get(f"value{i}", "")
            if not col:
                continue
            parsed_col = self._parse_col_value(col)
            parsed_val = self._parse_col_value(val)
            updated_pairs.append((parsed_col, parsed_val))
        
        if updated_spec:
            updated_spec['pairs'] = updated_pairs 
        # updated_spec = self.report_filters.get(filter_name, {})
        spec = updated_spec if updated_spec else  self.filters_map[filter_name]

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
        
        if self.facility:
            filtered_dates = f"{DATE_} BETWEEN '{self.start_date}'::TIMESTAMP AND '{self.end_date}'::TIMESTAMP AND {FACILITY_} = '{self.facility}' "
            original_dates = f"{DATE_} <= '{self.end_date}'::TIMESTAMP AND {FACILITY_} = '{self.facility}'"
        else:
            filtered_dates = f"{DATE_} BETWEEN '{self.start_date}'::TIMESTAMP AND '{self.end_date}'::TIMESTAMP AND {FACILITY_CODE_} = '{self.location}' "
            original_dates = f"{DATE_} <= '{self.end_date}'::TIMESTAMP AND {FACILITY_CODE_} = '{self.location}' "

        if measure == "sum":
            args = [filtered_dates,self.data_route, PERSON_ID_, spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result, patient_ids = create_sum(*args,self.start_date, self.end_date)
            
        elif measure == "cohort_sum":
            args = [original_dates,self.data_route, PERSON_ID_, spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result, patient_ids = create_sum(*args,self.start_date, self.end_date)

        elif measure == "count_set":
            args = [filtered_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result, patient_ids = create_count_sets(*args,self.start_date, self.end_date)
        
        elif measure == "cohort_count_set":
            args = [original_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result, patient_ids = create_count_sets(*args,self.start_date, self.end_date)

        elif measure == "cohort_count_set_defaulter":
            args = [original_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result, patient_ids = create_count_sets(*args,self.start_date, self.end_date)

        elif measure == "count_set_defaulter":
            args = [filtered_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result, patient_ids = create_count_sets(*args,self.start_date, self.end_date)

        elif measure == "count":
            args = [filtered_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result, patient_ids = create_count(*args,self.start_date, self.end_date)
        
        elif measure == "nunique":
            args = [filtered_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result, patient_ids = create_count(*args,self.start_date, self.end_date)

        elif measure == "cohort_count":
            args = [original_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result, patient_ids = create_count(*args,self.start_date, self.end_date)

        elif measure == "cohort_count_defaulter":
            args = [original_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result, patient_ids = create_count(*args,self.start_date, self.end_date)

        elif measure == "count_defaulter":
            args = [filtered_dates,self.data_route, "count", spec["unique_column"]]
            for fcol, fval in spec["pairs"]:
                args.extend([fcol, fval])
            result, patient_ids = create_count(*args,self.start_date, self.end_date)

        elif measure == "calculated":
            # Deferred arithmetic expression — resolved in Pass 2 of _precompute_all_filter_values.
            expression = str(spec.get("unique_column", "")).strip()
            self._value_cache[filter_name] = {"__calculated__": expression}
            return self._value_cache[filter_name]

        elif measure == "calculated_intersection":
            # Deferred set-intersection of patient_ids from {ref} tokens in unique_column.
            expression = str(spec.get("unique_column", "")).strip()
            self._value_cache[filter_name] = {"__calculated_intersection__": expression}
            return self._value_cache[filter_name]

        elif measure == "calculated_union":
            # Deferred set-union of patient_ids from {ref} tokens in unique_column.
            expression = str(spec.get("unique_column", "")).strip()
            self._value_cache[filter_name] = {"__calculated_union__": expression}
            return self._value_cache[filter_name]

        elif measure == "calculated_max":
            # Deferred: max of resolved numeric values from {ref} tokens in unique_column.
            expression = str(spec.get("unique_column", "")).strip()
            self._value_cache[filter_name] = {"__calculated_max__": expression}
            return self._value_cache[filter_name]

        elif measure == "calculated_min":
            # Deferred: min of resolved numeric values from {ref} tokens in unique_column.
            expression = str(spec.get("unique_column", "")).strip()
            self._value_cache[filter_name] = {"__calculated_min__": expression}
            return self._value_cache[filter_name]

        else:
            result, patient_ids = ("","")

        if patient_ids:
            self._patient_ids_cache[filter_name] = [str(p) for p in patient_ids]

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

    _DEFERRED_MEASURES = frozenset({
        "calculated",
        "calculated_intersection",
        "calculated_union",
        "calculated_max",
        "calculated_min",
    })

    def _precompute_all_filter_values(self) -> None:
        """Pre-compute every filter value so that deferred measures can reference
        other filters.  Two-pass approach:
          Pass 1 – compute all non-deferred filters (populates _value_cache and
                   _patient_ids_cache so set-operation measures can use them).
          Pass 2 – resolve all deferred filters in dependency order.
        """
        # Pass 1: all non-deferred filters
        for fname, spec in self.filters_map.items():
            if spec["measure"] not in self._DEFERRED_MEASURES:
                self._compute_value_from_filter(fname)

        # Pass 2: deferred filters
        _SENTINEL_KEY = {
            "calculated":              "__calculated__",
            "calculated_intersection": "__calculated_intersection__",
            "calculated_union":        "__calculated_union__",
            "calculated_max":          "__calculated_max__",
            "calculated_min":          "__calculated_min__",
        }
        for fname, spec in self.filters_map.items():
            measure = spec["measure"]
            if measure not in self._DEFERRED_MEASURES:
                continue

            # Ensure sentinel is in cache
            cached = self._value_cache.get(fname)
            sentinel_key = _SENTINEL_KEY[measure]
            if not isinstance(cached, dict) or sentinel_key not in cached:
                self._compute_value_from_filter(fname)
                cached = self._value_cache.get(fname)

            if not isinstance(cached, dict):
                continue

            if "__calculated__" in cached:
                resolved = self._resolve_calculated(cached["__calculated__"], fname)
            elif "__calculated_intersection__" in cached:
                resolved = self._resolve_set_operation(
                    cached["__calculated_intersection__"], fname, "intersection"
                )
            elif "__calculated_union__" in cached:
                resolved = self._resolve_set_operation(
                    cached["__calculated_union__"], fname, "union"
                )
            elif "__calculated_max__" in cached:
                resolved = self._resolve_minmax(cached["__calculated_max__"], fname, "max")
            elif "__calculated_min__" in cached:
                resolved = self._resolve_minmax(cached["__calculated_min__"], fname, "min")
            else:
                resolved = "N/A"

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

    def _resolve_set_operation(self, expression: str, filter_name: str, operation: str) -> str:
        """Compute intersection or union count of patient_ids for {ref} tokens in expression."""
        import re
        ref_names = [m.group(1).strip() for m in re.finditer(r"\{([^}]+)\}", expression)]
        if not ref_names:
            return "0"

        sets: List[set] = []
        for ref in ref_names:
            ids = self._patient_ids_cache.get(ref)
            # print(ids)
            if ids is None:
                continue
                # self._errors.append(
                #     f"calculated_{operation} filter '{filter_name}': "
                #     f"no patient IDs cached for '{ref}' — run its filter first."
                # )
                # ids = []
            sets.append(set(str(i) for i in ids))
        if not sets:
            return "0"

        if operation == "intersection":
            result_set = sets[0]
            for s in sets[1:]:
                result_set = result_set & s
        else:  # union
            result_set: set = set()
            for s in sets:
                result_set = result_set | s

        self._patient_ids_cache[filter_name] = list(result_set)
        return str(len(result_set))

    def _resolve_minmax(self, expression: str, filter_name: str, operation: str) -> str:
        """Return max or min of resolved numeric values for {ref} tokens in expression."""
        import re
        ref_names = [m.group(1).strip() for m in re.finditer(r"\{([^}]+)\}", expression)]
        if not ref_names:
            return "N/A"

        values: List[float] = []
        for ref in ref_names:
            cached = self._value_cache.get(ref)
            if isinstance(cached, dict):
                self._errors.append(
                    f"calculated_{operation} filter '{filter_name}': "
                    f"dependency '{ref}' is not yet resolved."
                )
                continue
            try:
                values.append(float(str(cached or "0").replace("%", "").strip()))
            except ValueError:
                self._errors.append(
                    f"calculated_{operation} filter '{filter_name}': "
                    f"'{ref}' value '{cached}' is not numeric — skipped."
                )

        if not values:
            return "N/A"

        result = max(values) if operation == "max" else min(values)
        return str(int(result)) if result == int(result) else f"{result:g}"

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
        if self.report_design and self.report_design.get("tables"):
            return self._build_from_design()
        return self._build_from_spec()

    def _build_from_design(self) -> List[Any]:
        """Render report from GUI-authored rpt-state design JSON, preserving exact positions."""
        self._precompute_all_filter_values()

        title        = self._title() or "HMIS DATASET REPORT"
        # page_design  = self._page_design()
        # is_landscape = page_design == "landscape"

        #Calculate canvas bounding box from all table positions
        canvas_w = 400
        canvas_h = 200
        for tbl in self.report_design.get("tables", []):
            pos         = tbl.get("pos", {"x": 20, "y": 20})
            x, y        = pos.get("x", 20), pos.get("y", 20)
            cw          = tbl.get("col_widths", [])
            rh          = tbl.get("row_heights", [])
            data        = tbl.get("data", [])
            tbl_w       = sum(cw) if cw else (len(data[0]) if data else 3) * 120
            tbl_h       = sum(rh) if rh else len(data) * 28
            extra       = (30 if tbl.get("ta") is not None else 0) + \
                          (30 if tbl.get("tb") is not None else 0)
            canvas_w    = max(canvas_w, x + tbl_w + 60)
            canvas_h    = max(canvas_h, y + tbl_h + extra + 60)

        outer_style = {
            "fontFamily": "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
            "maxWidth":   "1600px",
            "margin":     "0 auto",
        }

        hf_title = self.facility if self.facility else self.location_name

        header = html.Div(
            style={"textAlign": "center", "marginBottom": "14px",
                   "paddingBottom": "8px", "borderBottom": "2px solid #006401"},
            children=[
                html.H3(title.upper(),
                        style={"margin": "0", "color": "#000000",
                               "fontSize": "15px", "fontWeight": "700",
                               "letterSpacing": "0.5px"}),
                html.Div(f"{hf_title}", style={"textAlign":"center"}),
                html.Div(f"{self.start_date} to {self.end_date}", style={"textAlign":"center"})
            ],
        )
        table_els: List[Any] = []
        for tbl in self.report_design.get("tables", []):
            rendered = self._render_design_table(tbl)
            if rendered is not None:
                table_els.append(rendered)

        canvas = html.Div(
            table_els,
            style={
                "position":   "relative",
                "width":      f"{canvas_w}px",
                "minHeight":  f"{canvas_h}px",
                "overflowX":  "auto",
                "overflowY":  "visible",
                "background": "#FFFFFF",
                "border":     "1px solid #e5e7eb",
                "borderRadius": "6px",
            },
        )

        canvas_wrapper = html.Div(
            canvas,
            style={
                "display":         "flex",
                "justifyContent":  "center",
                "width":           "100%",
                "overflowX":       "auto",
            },
        )

        children: List[Any] = [header, canvas_wrapper]

        if self._errors:
            children.append(
                html.Div(
                    style={"marginTop": "12px", "padding": "10px 14px",
                           "background": "#fef2f2", "border": "1px solid #fecaca",
                           "borderRadius": "6px"},
                    children=[
                        html.Strong("⚠ Validation Notes", style={"color": "#dc2626"}),
                        html.Ul([html.Li(e, style={"fontSize": "12px"})
                                 for e in self._errors]),
                    ],
                )
            )

        return [html.Div(children, style=outer_style)]

    def _render_design_table(self, table: dict) -> Any:
        """Absolutely-position one rpt-state table using its saved pos/col_widths/row_heights/fill/color."""
        data        = table.get("data", [])
        if not data:
            return None

        pos         = table.get("pos", {"x": 20, "y": 20})
        x           = pos.get("x", 20)
        y           = pos.get("y", 20)
        ta          = table.get("ta")   # None means not present; "" means present but empty
        tb          = table.get("tb")
        col_widths  = table.get("col_widths", [])
        row_heights = table.get("row_heights", [])

        rows = []
        cell_stores: List[Any] = []
        seen_store_ids: set = set()
        for r_idx, row_cells in enumerate(data):
            h = row_heights[r_idx] if r_idx < len(row_heights) else 28
            tds = []
            vis_col = 0
            for c_idx, cell in enumerate(row_cells):
                if cell.get("hidden", False):
                    continue

                raw_v = cell.get("v", "")
                is_filter = bool(raw_v and raw_v in self.filters_map)
                display_v = (self._compute_value_from_filter(raw_v) if is_filter else raw_v)

                fill   = cell.get("fill",   "#ffffff")
                color  = cell.get("color",  "#000000")
                cs     = cell.get("cs", 1)
                rs     = cell.get("rs", 1)
                bold   = cell.get("bold",   False)
                italic = cell.get("italic", False)
                align  = cell.get("align",  "left")
                indent = cell.get("indent", 0)

                w = col_widths[vis_col] if vis_col < len(col_widths) else 120
                pl = 8 + indent * 20

                if is_filter:
                    has_ids = bool(self._patient_ids_cache.get(raw_v))
                    cell_content = html.Span(
                        display_v,
                        id={"type": "rpt-val-click", "index": raw_v},
                        n_clicks=0,
                        style={
                            "cursor":    "pointer" if has_ids else "default",
                            "color":     "#1d4ed8" if has_ids else color,
                            "textDecoration": "underline" if has_ids else "none",
                        },
                    )
                    if raw_v not in seen_store_ids:
                        seen_store_ids.add(raw_v)
                        cell_stores.append(dcc.Store(
                            id={"type": "rpt-cell-ids", "index": raw_v},
                            data={
                                "ids":        self._patient_ids_cache.get(raw_v, []),
                                "unique_col": PERSON_ID_,
                            },
                        ))
                else:
                    cell_content = display_v

                tds.append(html.Td(
                    cell_content,
                    colSpan=cs,
                    rowSpan=rs,
                    style={
                        "background":    fill,
                        "color":         color,
                        "width":         f"{w}px",
                        "minWidth":      f"{w}px",
                        "height":        f"{h}px",
                        "paddingTop":    "4px",
                        "paddingBottom": "4px",
                        "paddingLeft":   f"{pl}px",
                        "paddingRight":  "8px",
                        "border":        "1px solid #d1d5db",
                        "fontSize":      "15px",
                        "fontWeight":    "bold" if bold else "normal",
                        "fontStyle":     "italic" if italic else "normal",
                        "textAlign":     align,
                        "whiteSpace":    "normal",
                        "wordBreak":     "break-word",
                        "boxSizing":     "border-box",
                        "verticalAlign": "middle",
                        "lineHeight":    "1.3",
                    },
                ))
                vis_col += cs

            if tds:
                rows.append(html.Tr(tds, style={"height": f"{h}px"}))

        if not rows:
            return None

        # Compute rendered table pixel width from col_widths
        tbl_w = sum(col_widths) if col_widths else (len(data[0]) if data else 3) * 120

        ta_el = html.Div(
            str(ta) if ta else "",
            style={
                "background":    "#006401",
                "color":         "#ffffff",
                "fontSize":      "11px",
                "fontWeight":    "700",
                "letterSpacing": "0.5px",
                "padding":       "5px 10px",
                "borderRadius":  "4px 4px 0 0",
                "whiteSpace":    "nowrap",
                "overflow":      "hidden",
                "textOverflow":  "ellipsis",
            },
        ) if ta is not None and ta != "" else html.Div()

        table_el = html.Table(
            html.Tbody(rows),
            style={
                "borderCollapse": "collapse",
                "tableLayout":    "fixed",
                "width":          f"{tbl_w}px",
                "border":         "1px solid #d1d5db",
                "borderTop":      "none" if ta is not None else "1px solid #d1d5db",
                "borderRadius":   ("0" if ta is not None else "4px 4px 0 0")
                                   + (" 0 0" if tb is not None else " 4px 4px"),
                "background":     "#ffffff",
                "fontSize":       "11px",
            },
        )

        # print(table_el)

        tb_el = html.Div(
            str(tb) if tb else "",
            style={
                "background":    "#f3f4f6",
                "color":         "#374151",
                "fontSize":      "11px",
                "fontWeight":    "600",
                "padding":       "4px 10px",
                "border":        "1px solid #d1d5db",
                "borderTop":     "none",
                "borderRadius":  "0 0 4px 4px",
                "whiteSpace":    "nowrap",
                "overflow":      "hidden",
                "textOverflow":  "ellipsis",
            },
        ) if tb is not None else None

        block = ([ta_el] if ta_el else []) + [table_el] + ([tb_el] if tb_el else []) + cell_stores

        return html.Div(
            block,
            style={
                "position":    "absolute",
                "left":        f"{x}px",
                "top":         f"{y}px",
                "width":       f"{tbl_w}px",
                "boxShadow":   "0 1px 4px rgba(0,0,0,0.08)",
                "background":  "#ffffff",
                "borderRadius": "4px",
            },
        )


    def _build_from_spec(self) -> List[Any]:
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

        hf_title = self.facility if self.facility else self.location_name

        header = html.Div(
            style={"textAlign": "center", "marginBottom": "18px",
                   "paddingBottom": "10px",
                   "borderBottom": "2px solid #006401"},
            children=[
                html.H3(title.upper(),
                        style={"margin": "0 0 4px", "color": "#000000",
                               "fontSize": "15px", "fontWeight": "700",
                               "letterSpacing": "0.5px"}),
                html.Div(f"{hf_title}", style={"textAlign":"center"}),
                html.Div(f"{self.start_date} to {self.end_date}", style={"textAlign":"center"})
                # html.Span(
                #     f"{'Landscape' if is_landscape else 'Portrait'}  ·  "
                #     f"{num_page_columns}-column layout",
                #     style={"fontSize": "11px", "color": "#6b7280"}
                # ),
            ],
        )

        sections_refs = self.build_section_tables_with_ids()

        section_divs: List[Any] = []
        for section_idx, (subtitle, subdf) in enumerate(sections):
            subdf = self._apply_dhis_mapping(subdf)
            if len(subdf.columns) <= 1:
                continue
            _, refs_df = sections_refs[section_idx] if section_idx < len(sections_refs) else (subtitle, None)
            section_divs.append(
                html.Div(
                    style={"breakInside": "avoid", "pageBreakInside": "avoid",
                           "marginBottom": "16px"},
                    children=[self._create_modern_table(subdf, section_idx, subtitle, refs_df=refs_df)],
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

    def _create_modern_table(self, df: pd.DataFrame, section_idx: int, section_title: str,
                             refs_df: pd.DataFrame = None) -> html.Div:
        """Render a report section as a clean, branded table with clickable value cells."""
        df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)
        if df.empty:
            return html.Div(
                "No data available",
                style={"color": "#9ca3af", "fontSize": "12px",
                       "padding": "8px 0", "fontStyle": "italic"},
            )

        value_cols = [c for c in df.columns if c != "Data Element"]

        de_width   = min(max(len(str(x)) for x in df["Data Element"].tolist()) * 7 + 30, 340)
        val_widths = {
            col: min(max(len(str(x)) for x in df[col].tolist()) * 7 + 20, 160)
            for col in value_cols
        }

        # Align refs_df rows to df rows by index (both come from the same section)
        refs_records: List[Dict] = []
        if refs_df is not None:
            refs_records = refs_df.to_dict("records")

        th_base = {
            "padding": "9px 12px", "border": "1px solid #4b5563",
            "fontSize": "11px", "fontWeight": "700", "letterSpacing": "0.4px",
            "backgroundColor": "#374151", "color": "#f9fafb",
        }
        header_row = html.Tr([
            html.Th(
                section_title.upper() if section_title else "Data Element",
                style={**th_base, "textAlign": "left", "backgroundColor": "#1f2937",
                       "width": f"{de_width}px", "minWidth": "180px"},
            ),
            *[html.Th(col.upper(), style={**th_base, "textAlign": "center",
                                          "width": f"{val_widths[col]}px", "minWidth": "80px"})
              for col in value_cols],
        ])

        td_de = {
            "padding": "8px 12px", "border": "1px solid #e5e7eb",
            "fontSize": "12px", "fontWeight": "600", "color": "#1f2937",
            "backgroundColor": "#f9fafb", "whiteSpace": "normal", "wordBreak": "break-word",
            "width": f"{de_width}px", "minWidth": "180px", "verticalAlign": "middle",
        }
        td_val_base = {
            "padding": "8px 12px", "border": "1px solid #e5e7eb",
            "fontSize": "12px", "textAlign": "center", "color": "#374151",
            "whiteSpace": "normal", "wordBreak": "break-word",
            "minWidth": "80px", "verticalAlign": "middle",
        }

        cell_stores: List[Any] = []
        seen_store_ids: set = set()
        data_rows = []
        for row_idx, (_, row) in enumerate(df.iterrows()):
            refs_row = refs_records[row_idx] if row_idx < len(refs_records) else {}
            bg = "#ffffff" if row_idx % 2 == 0 else "#f9fafb"
            tds = [html.Td(str(row.get("Data Element", "")), style=td_de)]
            for col in value_cols:
                val       = str(row.get(col, ""))
                filter_ref = str(refs_row.get(col, "")).strip() if refs_row else ""
                has_ids   = bool(filter_ref and self._patient_ids_cache.get(filter_ref))
                if filter_ref and filter_ref in self.filters_map:
                    cell_content = html.Span(
                        val,
                        id={"type": "rpt-val-click", "index": filter_ref},
                        n_clicks=0,
                        style={
                            "cursor": "pointer" if has_ids else "default",
                            "color":  "#1d4ed8" if has_ids else "#374151",
                            "textDecoration": "underline" if has_ids else "none",
                        },
                    )
                    if filter_ref not in seen_store_ids:
                        seen_store_ids.add(filter_ref)
                        cell_stores.append(dcc.Store(
                            id={"type": "rpt-cell-ids", "index": filter_ref},
                            data={
                                "ids":        self._patient_ids_cache.get(filter_ref, []),
                                "unique_col": PERSON_ID_,
                            },
                        ))
                else:
                    cell_content = val
                tds.append(html.Td(cell_content, style={**td_val_base,
                                                         "backgroundColor": bg,
                                                         "width": f"{val_widths[col]}px"}))
            data_rows.append(html.Tr(tds))

        # title_bar = html.Div(
        #     section_title.upper() if section_title else "",
        #     style={
        #         "background": "#006401", "color": "#ffffff",
        #         "fontSize": "11px", "fontWeight": "700",
        #         "letterSpacing": "0.6px", "padding": "7px 12px",
        #         "borderRadius": "4px 4px 0 0",
        #     },
        # )
        title_bar = html.Div()
        table_el = html.Table(
            [html.Thead(header_row), html.Tbody(data_rows)],
            style={
                "width": "100%", "borderCollapse": "collapse",
                "fontSize": "12px", "tableLayout": "auto",
                "border": "1px solid #d1d5db", "borderTop": "none",
                "borderRadius": "0 0 4px 4px", "overflowX": "auto",
            },
        )

        return html.Div(
            style={"marginBottom": "0", "breakInside": "avoid"},
            children=[title_bar, table_el] + cell_stores,
        )