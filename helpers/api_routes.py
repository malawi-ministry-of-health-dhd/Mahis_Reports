import json
import os
from datetime import datetime as dt

import pandas as pd
pd.options.mode.chained_assignment = None
from flask import jsonify, request

from config import DATA_PATH_, DATE_, FACILITY_CODE_, GENDER_
from data_storage import DataStorage
from helpers.date_ranges import get_month_start_end, get_quarter_start_end, get_week_start_end
from helpers.reports_class import ReportTableBuilder

from helpers.navigation_callbacks import DEMO_UUID
from helpers.helpers import (create_linelist_from_config, create_pivot_table_from_config, 
                             create_crosstab_from_config
)
ALLOWED_API_UUIDS = {DEMO_UUID}


def _extract_token() -> str | None:
    """
    Resolve the API token (UUID) from the request using the following
    priority order:

    1. ``Authorization: Bearer <token>`` header
    2. ``X-API-Key: <token>`` header
    3. ``?token=<token>`` query parameter
    4. ``?uuid=<token>``  query parameter  (backward-compatible)

    Returns the first non-empty value found, or ``None``.
    """
    # 1. Authorization: Bearer
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    # 2. X-API-Key
    api_key = request.headers.get("X-API-Key", "").strip()
    if api_key:
        return api_key

    # 3. ?token=
    token_param = request.args.get("token", "").strip()
    if token_param:
        return token_param

    # 4. ?uuid=  (legacy / URL-embedded usage)
    uuid_param = request.args.get("uuid", "").strip()
    return uuid_param or None


def _is_authorized(token: str | None, route: str | None) -> bool:
    """
    Return True when *token* is a known UUID.

    Checks, in order:
      1. The ``user_properties.json`` file for the given data route.
      2. The ``ALLOWED_API_UUIDS`` set (always checked, even when the
         file is absent or the route is unknown).
    """
    if not token:
        return False

    if route:
        path = os.getcwd()
        user_props = os.path.join(path, f'data/{route}', 'dcc_dropdown_json',
                                  'user_properties.json')
        if os.path.exists(user_props): 
            try:
                with open(user_props, 'r') as f:
                    data = json.load(f)
                auth_users = [
                    user.get('properties', {}).get('uuid', '')
                    for user in data.get('users', [])
                ]
                if token in auth_users:
                    return True
            except (json.JSONDecodeError, KeyError):
                pass
    return token in ALLOWED_API_UUIDS


def _build_prog_report_df(report_cfg: dict, report_type: str,
                           base_where: str, data_path: str) -> pd.DataFrame:
    """Return a DataFrame from a program report config entry."""
    anonymize = True
    if report_type == "LineList":
        _, data = create_linelist_from_config(base_where, data_path, report_cfg,"", anonymize)
        return data
    elif report_type == "PivotTable":
        _, data = create_pivot_table_from_config(base_where, data_path, report_cfg.get("filters") or {})
        return data
    elif report_type == "CrossTab":
        _, data = create_crosstab_from_config(base_where, data_path, report_cfg.get("filters") or {})
        return data
    return pd.DataFrame()


def register_api_routes(server):
    @server.route("/api/", methods=["GET"])
    def api_root():
        token      = _extract_token()
        data_route = request.args.get("route")
        if not _is_authorized(token, data_route):
            return jsonify({"error": "Unauthorized"}), 403

        return jsonify(
            {
                "endpoints": {
                    "datasets":     "/api/datasets",
                    "reports":      "/api/reports",
                    "indicators":   "/api/indicators",
                    "data_elements":"/api/dataElements",
                    "clinical_reports":"/api/clinicalReports"
                },
                "auth_methods": [
                    "Authorization: Bearer <token>  (header)",
                    "X-API-Key: <token>              (header)",
                    "?token=<token>                  (query param)",
                    "?uuid=<token>                   (query param, legacy)",
                ],
            }
        )

    @server.route("/api/reports", methods=["GET"])
    def get_reports_list():
        token      = _extract_token()
        data_route = request.args.get("route")
        if not _is_authorized(token, data_route):
            return jsonify({"error": "Unauthorized"}), 403

        try:
            reports_json = os.path.join(os.getcwd(), "data", "hmis_reports.json")
            with open(reports_json, "r") as handle:
                json_data = json.load(handle)

            reports = [
                {
                    "report_id":    report["page_name"],
                    "report_name":  report["report_name"],
                    "date_updated": report["date_updated"],
                }
                for report in json_data.get("reports", [])
                if report.get("archived", "").lower() == "false"
            ]
            return jsonify({"reports": reports})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @server.route("/api/datasets", methods=["GET"])
    def get_report_dataset():
        token          = _extract_token()
        period_param   = request.args.get("period")
        facility_id    = (request.args.get("Location") or request.args.get("?Location"))
        report_name_id = request.args.get("report_name")
        data_route     = request.args.get("route")
        DATA_PATH_     = f"data/{data_route}/parquet"

        if not all([period_param, facility_id, report_name_id]):
            return jsonify({"error": "Missing required parameters: period, Location, report_name"}), 400

        if not _is_authorized(token, data_route):
            return jsonify({"error": "Unauthorized"}), 403

        try:
            period_parts = period_param.split(":")
            if len(period_parts) != 3:
                return jsonify({"error": "Invalid period format. Expected 'Type:Value:Year' (e.g., 'Monthly:January:2025')"}), 400

            period_type, period_value, period_year = period_parts
            if period_type == "Weekly":
                start_date, end_date = get_week_start_end(period_value, period_year)
            elif period_type == "Monthly":
                start_date, end_date = get_month_start_end(period_value, period_year)
            elif period_type == "Quarterly":
                start_date, end_date = get_quarter_start_end(period_value, period_year)
            else:
                return jsonify({"error": f"Invalid period type: {period_type}"}), 400

            reports_json = os.path.join(os.getcwd(), "data", "hmis_reports.json")
            with open(reports_json, "r") as handle:
                json_data = json.load(handle)

            report = next(
                (
                    r for r in json_data.get("reports", [])
                    if r.get("page_name") == report_name_id
                    and r.get("archived", "").lower() == "false"
                ),
                None,
            )

            report_filters = report.get("filters", {})
            
            if not report:
                return jsonify({"error": "Report not found"}), 404

            spec_path = os.path.join(os.getcwd(), "data", "uploads",
                                     f"{report['page_name']}.xlsx")
            if not os.path.exists(spec_path):
                return jsonify({"error": "Report template not found"}), 500

            builder = ReportTableBuilder(
                spec_path, start_date, end_date, DATA_PATH_,
                facility_id, dhis2_period=None,report_filters=report_filters
            )
            builder.load_spec()
            sections    = builder.build_section_tables()
            section_ids = builder.build_section_tables_with_ids()

            response_data = []
            for (section_name, section_df), (_, section_id_df) in zip(sections, section_ids):
                id_col     = "Data Element"
                value_cols = [c for c in section_df.columns if c not in {id_col, "Section"}]
                section_long = section_df.melt(
                    id_vars=[c for c in section_df.columns if c in {"Section", id_col}],
                    value_vars=value_cols,
                    var_name="Category",
                    value_name="Value",
                )
                section_long[id_col] = (section_long[id_col].astype(str)
                                         + " " + section_long["Category"].astype(str))
                values_df = section_long.drop(columns=["Category"])

                id_value_cols = [c for c in section_id_df.columns if c not in {id_col, "Section"}]
                section_id_long = section_id_df.melt(
                    id_vars=[c for c in section_id_df.columns if c in {"Section", id_col}],
                    value_vars=id_value_cols,
                    var_name="Category",
                    value_name="Value",
                )
                section_id_long[id_col] = (section_id_long[id_col].astype(str)
                                            + " " + section_id_long["Category"].astype(str))
                ids_df = (section_id_long.drop(columns=["Category"])
                                         .rename(columns={"Value": "Code"}))

                combined_df = pd.merge(values_df, ids_df, on="Data Element", how="inner")
                final_df    = combined_df[combined_df["Code"] != ""]

                response_data.append({
                    "section_name": section_name,
                    "data": final_df.to_dict(orient="records"),
                })

            return jsonify({
                "report_id":   report_name_id,
                "report_name": report["report_name"],
                "facility_id": facility_id,
                "period":      period_param,
                "sections":    response_data,
            })
        except ValueError as exc:
            import traceback; traceback.print_exc()
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            import traceback; traceback.print_exc()
            return jsonify({"error": str(exc)}), 500

    @server.route("/api/clinicalReports", methods=["GET"])
    def get_clinical_report():
        token        = _extract_token()
        start_date   = request.args.get("startDate", "").strip()
        end_date     = request.args.get("endDate", "").strip()
        report_id    = request.args.get("report_id", "").strip()
        data_route   = request.args.get("route", "default").strip()
        location_raw = request.args.get("Location", "").strip()

        if not all([start_date, end_date, report_id]):
            return jsonify({"error": "Missing required parameters"}), 400

        if not _is_authorized(token, data_route):
            return jsonify({"error": "Unauthorized"}), 403

        try:
            try:
                dt.strptime(start_date, "%Y-%m-%d")
                dt.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                return jsonify({"error": "Invalid date format. Expected YYYY-MM-DD"}), 400

            prog_reports_path = os.path.join(
                os.getcwd(), "data", "visualizations", "validated_prog_reports.json"
            )
            if not os.path.exists(prog_reports_path):
                return jsonify({"error": "Program report configuration not found"}), 500

            with open(prog_reports_path, "r") as f:
                config = json.load(f)

            report_cfg = next(
                (r for r in config.get("reports", []) if str(r.get("id")) == report_id),
                None,
            )
            if not report_cfg:
                return jsonify({"error": f"Report id '{report_id}' not found"}), 404

            parquet_path = os.path.join(os.getcwd(), f"data/{data_route}/parquet")

            base_where = (
                f"Date BETWEEN '{start_date} 00:00:00'::TIMESTAMP"
                f" AND '{end_date} 23:59:59'::TIMESTAMP"
            )

            locations = [l.strip() for l in location_raw.split(",") if l.strip()] if location_raw else []
            if locations:
                quoted      = ", ".join(f"'{l}'" for l in locations)
                base_where += f" AND Facility_CODE IN ({quoted})"
                facility_id = location_raw
            else:
                facility_id = "All facilities"

            report_type = report_cfg.get("type", "LineList")
            df          = _build_prog_report_df(report_cfg, report_type, base_where, parquet_path)

            if df is None or df.empty:
                data_out = []
            else:
                data_out = df.fillna("").astype(str).to_dict(orient="records")

            return jsonify({
                "report_id":   report_id,
                "report_name": report_cfg.get("report_name", ""),
                "facility_id": facility_id,
                "start_date":  start_date,
                "end_date":    end_date,
                "data":        data_out,
            })

        except Exception as exc:
            import traceback; traceback.print_exc()
            return jsonify({"error": str(exc)}), 500
