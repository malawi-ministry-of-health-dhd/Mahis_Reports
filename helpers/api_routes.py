import json
import os
from datetime import datetime as dt

import pandas as pd
from flask import jsonify, request

from config import DATA_FILE_NAME_, DATE_, FACILITY_CODE_, GENDER_
from data_storage import DataStorage
from helpers.date_ranges import get_month_start_end, get_quarter_start_end, get_week_start_end
from helpers.reports_class import ReportTableBuilder

from helpers.navigation_callbacks import DEMO_UUID

ALLOWED_API_UUIDS = {DEMO_UUID}


def _is_authorized(uuid_param):
    return uuid_param in ALLOWED_API_UUIDS


def register_api_routes(server):
    @server.route("/api/", methods=["GET"])
    def api_root():
        uuid_param = request.args.get("uuid")
        if not _is_authorized(uuid_param):
            return jsonify({"error": "Unauthorized, Please supply id"}), 403

        return jsonify(
            {
                "endpoints": {
                    "datasets": "/api/datasets",
                    "reports": "/api/reports",
                    "indicators": "/api/indicators",
                    "data_elements": "/api/dataElements",
                }
            }
        )

    @server.route("/api/reports", methods=["GET"])
    def get_reports_list():
        uuid_param = request.args.get("uuid")
        if not _is_authorized(uuid_param):
            return jsonify({"error": "Unauthorized, Please supply id"}), 403

        try:
            reports_json = os.path.join(os.getcwd(), "data", "hmis_reports.json")
            with open(reports_json, "r") as handle:
                json_data = json.load(handle)

            reports = [
                {
                    "report_id": report["page_name"],
                    "report_name": report["report_name"],
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
        uuid_param = request.args.get("uuid")
        period_param = request.args.get("period")
        facility_id = request.args.get("hf_code")
        report_name_id = request.args.get("report_name")

        if not all([period_param, facility_id, report_name_id]):
            return jsonify({"error": "Missing required parameters: Period, Health Facility ID, Report Name"}), 400

        if not _is_authorized(uuid_param):
            return jsonify({"error": "Unauthorized, Please supply id"}), 403

        try:
            period_parts = period_param.split(":")
            if len(period_parts) != 3:
                return jsonify({"error": "Invalid Period format. Expected 'Type:Value:Year' (e.g., 'Monthly:January:2025')"}), 400

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
                    report
                    for report in json_data.get("reports", [])
                    if report.get("page_name") == report_name_id and report.get("archived", "").lower() == "false"
                ),
                None,
            )
            if not report:
                return jsonify({"error": "Report Not Found"}), 404

            parquet_path = os.path.join(os.getcwd(), "data", "latest_data_opd.parquet")
            if not os.path.exists(parquet_path):
                return jsonify({"error": "Data file not found"}), 500

            sql = f"""
                SELECT *
                FROM 'data/{DATA_FILE_NAME_}'
                WHERE {FACILITY_CODE_} = '{facility_id}'
            """
            data = DataStorage.query_duckdb(sql)
            data[DATE_] = pd.to_datetime(data[DATE_], format="mixed")
            data[GENDER_] = data[GENDER_].replace({"M": "Male", "F": "Female"})
            data["DateValue"] = pd.to_datetime(data[DATE_]).dt.date
            today = dt.today().date()
            data["months"] = data["DateValue"].apply(lambda item: (today - item).days // 30)

            filtered = data[
                (pd.to_datetime(data[DATE_]) >= pd.to_datetime(start_date))
                & (pd.to_datetime(data[DATE_]) <= pd.to_datetime(end_date))
            ]

            original_data = data[pd.to_datetime(data[DATE_]) <= pd.to_datetime(end_date)].copy()
            original_data["days_before"] = original_data["DateValue"].apply(lambda item: (start_date - item).days)

            spec_path = os.path.join(os.getcwd(), "data", "uploads", f"{report['page_name']}.xlsx")
            if not os.path.exists(spec_path):
                return jsonify({"error": "Report template not found"}), 500

            builder = ReportTableBuilder(spec_path, filtered, original_data)
            builder.load_spec()
            sections = builder.build_section_tables()
            section_ids = builder.build_section_tables_with_ids()

            response_data = []
            for (section_name, section_df), (_, section_id_df) in zip(sections, section_ids):
                id_col = "Data Element"
                value_cols = [col for col in section_df.columns if col not in {id_col, "Section"}]
                section_long = section_df.melt(
                    id_vars=[col for col in section_df.columns if col in {"Section", id_col}],
                    value_vars=value_cols,
                    var_name="Category",
                    value_name="Value",
                )
                section_long[id_col] = section_long[id_col].astype(str) + " " + section_long["Category"].astype(str)
                values_df = section_long.drop(columns=["Category"])

                id_value_cols = [col for col in section_id_df.columns if col not in {id_col, "Section"}]
                section_id_long = section_id_df.melt(
                    id_vars=[col for col in section_id_df.columns if col in {"Section", id_col}],
                    value_vars=id_value_cols,
                    var_name="Category",
                    value_name="Value",
                )
                section_id_long[id_col] = section_id_long[id_col].astype(str) + " " + section_id_long["Category"].astype(str)
                ids_df = section_id_long.drop(columns=["Category"]).rename(columns={"Value": "Code"})

                combined_df = pd.merge(values_df, ids_df, on="Data Element", how="inner")
                final_df = combined_df[combined_df["Code"] != ""]

                response_data.append({"section_name": section_name, "data": final_df.to_dict(orient="records")})

            return jsonify(
                {
                    "report_id": report_name_id,
                    "report_name": report["report_name"],
                    "facility_id": facility_id,
                    "period": period_param,
                    "sections": response_data,
                }
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
