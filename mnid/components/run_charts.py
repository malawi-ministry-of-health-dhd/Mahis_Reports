"""Reusable run-chart components for MNID dashboards."""
from __future__ import annotations

import re

import dash_mantine_components as dmc
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from mnid.charts.chart_helpers import _moving_average_values
from mnid.core.constants import MUTED

PRIMARY_GREEN = "#15803D"
_GEIST = "Geist, system-ui, sans-serif"

_EXEC_CHART_LAYOUT = dict(
    paper_bgcolor="white",
    plot_bgcolor="white",
    font=dict(family=_GEIST, color="#64748b", size=11),
    margin=dict(l=44, r=14, t=14, b=28),
    hovermode="x unified",
    hoverlabel=dict(
        bgcolor="#0f172a",
        font_color="white",
        font_size=11,
        font_family=_GEIST,
        bordercolor="#0f172a",
    ),
    xaxis=dict(
        showgrid=False,
        showline=False,
        zeroline=False,
        tickfont=dict(size=10, color="#94a3b8"),
        tickcolor="rgba(0,0,0,0)",
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="#f1f5f9",
        gridwidth=1,
        showline=False,
        zeroline=False,
        tickfont=dict(size=10, color="#94a3b8"),
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0,
        font=dict(size=11),
        bgcolor="rgba(0,0,0,0)",
    ),
)

_EXEC_GRAIN_OPTIONS = [
    {"label": "Daily", "value": "daily"},
    {"label": "Weekly", "value": "weekly"},
    {"label": "Monthly", "value": "monthly"},
    {"label": "Quarterly", "value": "quarterly"},
    {"label": "Yearly", "value": "yearly"},
]

_EXEC_DEFAULT_GRAINS = {
    "total-births": "monthly",
    "maternal-mortality": "monthly",
    "neonatal-mortality": "monthly",
    "stillbirths": "monthly",
    "pre-eclampsia-and-eclampsia": "monthly",
    "postpartum-haemorrhage": "monthly",
    "maternal-sepsis": "monthly",
    "obstructed-or-prolonged-labour": "monthly",
    "ruptured-uterus": "monthly",
    "birth-asphyxia": "monthly",
    "preterm-birth": "monthly",
    "neonatal-sepsis": "monthly",
}


def _exec_chart_layout(
    height: int = 300,
    xaxis: dict | None = None,
    yaxis: dict | None = None,
    margin: dict | None = None,
) -> dict:
    layout = dict(_EXEC_CHART_LAYOUT)
    layout["height"] = height
    if xaxis is not None:
        merged_xaxis = dict(_EXEC_CHART_LAYOUT.get("xaxis", {}))
        merged_xaxis.update(xaxis)
        layout["xaxis"] = merged_xaxis
    if yaxis is not None:
        merged_yaxis = dict(_EXEC_CHART_LAYOUT.get("yaxis", {}))
        merged_yaxis.update(yaxis)
        layout["yaxis"] = merged_yaxis
    if margin is not None:
        merged_margin = dict(_EXEC_CHART_LAYOUT.get("margin", {}))
        merged_margin.update(margin)
        layout["margin"] = merged_margin
    return layout


def _hex_to_rgba(color: str, alpha: float) -> str:
    if color.startswith("#") and len(color) == 7:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        return f"rgba({r},{g},{b},{alpha})"
    return f"rgba(15,23,42,{alpha})"


def _bucket_start(series: pd.Series, grain: str) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce")
    grain = str(grain or "monthly").strip().lower()
    if grain == "daily":
        return dt.dt.normalize()
    if grain == "weekly":
        return dt.dt.to_period("W-SUN").dt.start_time
    if grain == "quarterly":
        return dt.dt.to_period("Q").dt.start_time
    if grain == "yearly":
        return dt.dt.to_period("Y").dt.start_time
    return dt.dt.to_period("M").dt.start_time


def _format_grain_label(period_start: pd.Timestamp, grain: str) -> str:
    if pd.isna(period_start):
        return ""
    grain = str(grain or "monthly").strip().lower()
    if grain == "daily":
        return period_start.strftime("%d %b %Y")
    if grain == "weekly":
        period_end = period_start + pd.Timedelta(days=6)
        if period_start.month == period_end.month:
            return f"{period_start.strftime('%b')} {period_start.day}-{period_end.day}"
        return f"{period_start.strftime('%b')} {period_start.day}-{period_end.strftime('%b')} {period_end.day}"
    if grain == "quarterly":
        quarter = ((period_start.month - 1) // 3) + 1
        return f"Q{quarter} {period_start.year}"
    if grain == "yearly":
        return period_start.strftime("%Y")
    return period_start.strftime("%b %Y")


def bucket_time_series(series_df: pd.DataFrame, grain: str, value_col: str = "value") -> pd.DataFrame:
    if series_df is None or series_df.empty or "month" not in series_df.columns or value_col not in series_df.columns:
        return pd.DataFrame(columns=["period_start", "bucket_key", "bucket_label", value_col])
    working = series_df.copy()
    working["period_start"] = _bucket_start(working["month"], grain)
    working = working.dropna(subset=["period_start"])
    if working.empty:
        return pd.DataFrame(columns=["period_start", "bucket_key", "bucket_label", value_col])
    count_cols = [c for c in ("numerator", "denominator") if c in working.columns]
    bucketed = (
        working.groupby("period_start", as_index=False)[[value_col, *count_cols]]
        .sum()
        .sort_values("period_start")
    )
    if not bucketed.empty:
        full_idx = pd.date_range(
            bucketed["period_start"].min(),
            bucketed["period_start"].max(),
            freq={
                "daily": "D",
                "weekly": "W-MON",
                "monthly": "MS",
                "quarterly": "QS",
                "yearly": "YS",
            }.get(str(grain or "monthly").lower(), "MS"),
        )
        bucketed = (
            bucketed.set_index("period_start")
            .reindex(full_idx)
            .rename_axis("period_start")
            .reset_index()
        )
        bucketed[value_col] = pd.to_numeric(bucketed[value_col], errors="coerce").fillna(0)
        for col in count_cols:
            bucketed[col] = pd.to_numeric(bucketed[col], errors="coerce").fillna(0)
    bucketed["bucket_key"] = bucketed["period_start"].dt.strftime("%Y-%m-%d")
    bucketed["bucket_label"] = bucketed["period_start"].apply(lambda ts: _format_grain_label(ts, grain))
    return bucketed


def describe_grain_window(bucketed_df: pd.DataFrame, grain: str) -> str:
    if bucketed_df is None or bucketed_df.empty or "period_start" not in bucketed_df.columns:
        return f"Showing {grain} data"
    start = bucketed_df["period_start"].min()
    end = bucketed_df["period_start"].max()
    if pd.isna(start) or pd.isna(end):
        return f"Showing {grain} data"
    grain = str(grain or "monthly").lower()
    if grain == "daily":
        return f"Showing daily data, {start.strftime('%d %b %Y')} to {end.strftime('%d %b %Y')}"
    if grain == "weekly":
        return f"Showing weekly data, {_format_grain_label(start, 'weekly')} to {_format_grain_label(end, 'weekly')}"
    if grain == "quarterly":
        return f"Showing quarterly data, {_format_grain_label(start, 'quarterly')} to {_format_grain_label(end, 'quarterly')}"
    if grain == "yearly":
        return f"Showing yearly data, {_format_grain_label(start, 'yearly')} to {_format_grain_label(end, 'yearly')}"
    return f"Showing monthly data, {start.strftime('%b %Y')} to {end.strftime('%b %Y')}"


def bucket_multi_series(series_df: pd.DataFrame, grain: str, value_col: str = "value") -> pd.DataFrame:
    if series_df is None or series_df.empty or "month" not in series_df.columns or "series" not in series_df.columns:
        return pd.DataFrame(columns=["period_start", "bucket_key", "bucket_label", "series", "color", value_col])
    frames = []
    for label in series_df["series"].dropna().unique():
        trace_df = series_df[series_df["series"] == label].copy()
        color = trace_df["color"].iloc[0] if "color" in trace_df.columns and not trace_df.empty else PRIMARY_GREEN
        bucketed = bucket_time_series(trace_df[["month", value_col]].copy(), grain, value_col=value_col)
        if bucketed.empty:
            continue
        bucketed["series"] = label
        bucketed["color"] = color
        frames.append(bucketed)
    if not frames:
        return pd.DataFrame(columns=["period_start", "bucket_key", "bucket_label", "series", "color", value_col])
    return pd.concat(frames, ignore_index=True)


def _grain_axis_title(grain: str) -> str:
    return {
        "daily": "Day",
        "weekly": "Week",
        "monthly": "Month",
        "quarterly": "Quarter",
        "yearly": "Year",
    }.get(str(grain or "monthly").lower(), "Month")


def _grain_tick_angle(grain: str) -> int:
    return {
        "daily": -32,
        "weekly": -32,
        "monthly": -28,
        "quarterly": 0,
        "yearly": 0,
    }.get(str(grain or "monthly").lower(), -28)


def _is_percentage_axis(y_title: str) -> bool:
    """Return whether a run chart represents a percentage rather than a count."""
    normalized = str(y_title or "").strip().lower()
    return "%" in normalized or "percent" in normalized


def _serialize_trend_series(series_df: pd.DataFrame) -> list[dict]:
    if series_df is None or series_df.empty:
        return []
    out = series_df.copy()
    if "month" in out.columns:
        out["month"] = pd.to_datetime(out["month"], errors="coerce").dt.strftime("%Y-%m-%d")
    return out.to_dict("records")


def _chart_key_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(title or "").strip().lower()).strip("-")
    return slug or "chart"


def _run_chart(
    series: pd.DataFrame,
    title: str,
    color: str,
    y_title: str,
    target: float | None = None,
    grain: str = "monthly",
    measure: str = "median",
    scope_label: str | None = None,
) -> go.Figure:
    fig = go.Figure()
    if series.empty:
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=0, b=0),
            height=240,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            annotations=[dict(
                text="No trend data available",
                x=0.5,
                y=0.5,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(size=13, color=MUTED, family=_GEIST),
            )],
        )
        return fig

    plot_series = series.copy()
    x_values = (
        plot_series["bucket_label"]
        if "bucket_label" in plot_series.columns
        else pd.to_datetime(plot_series["month"], errors="coerce").dt.strftime("%b %Y")
    )
    hover_labels = (
        plot_series["bucket_label"]
        if "bucket_label" in plot_series.columns
        else pd.to_datetime(plot_series["month"], errors="coerce").dt.strftime("%b %Y")
    )
    smooth_grain = grain if grain in {"weekly", "monthly", "quarterly", "yearly"} else "monthly"
    # "Median" mode plots the real, unsmoothed values as the line itself (so
    # the actual trend is visible, not hidden behind a rolling median) and
    # gets its own flat median-of-the-whole-period reference line instead --
    # same idea as the target line. "Avg" mode keeps the original behavior:
    # the smoothed rolling mean IS the line.
    if measure == "median":
        plotted = plot_series["value"].tolist()
        _valid_for_median = [y for y in plotted if y is not None and pd.notna(y)]
        median_value = float(pd.Series(_valid_for_median, dtype="float64").median()) if _valid_for_median else None
    else:
        plotted, _ = _moving_average_values(plot_series["value"].tolist(), smooth_grain, method=measure)
        median_value = None
    smoothed = plotted
    measure_label = "Actual" if measure == "median" else "Moving avg"
    value_format = ".1f" if _is_percentage_axis(y_title) else ",.0f"
    has_counts = "numerator" in plot_series.columns and "denominator" in plot_series.columns
    if has_counts:
        customdata = list(zip(
            hover_labels,
            plot_series["value"].tolist(),
            plot_series["numerator"].tolist(),
            plot_series["denominator"].tolist(),
        ))
        hovertemplate = (
            "<b>%{customdata[0]}</b><br>"
            f"{measure_label}: " f"<b>%{{y:{value_format}}}</b><br>"
            f"Actual: <b>%{{customdata[1]:{value_format}}}</b><br>"
            "Clients: %{customdata[2]:.0f} / %{customdata[3]:.0f}"
            "<extra></extra>"
        )
    else:
        customdata = list(zip(hover_labels, plot_series["value"].tolist()))
        hovertemplate = (
            "<b>%{customdata[0]}</b><br>"
            f"{measure_label}: " f"<b>%{{y:{value_format}}}</b><br>"
            f"Actual: <b>%{{customdata[1]:{value_format}}}</b>"
            "<extra></extra>"
        )
    fig.add_trace(go.Scatter(
        x=x_values,
        y=smoothed,
        name=title,
        mode="lines+markers",
        line=dict(color=color, width=3.8, shape="spline", smoothing=0.55),
        marker=dict(size=7, color=color, line=dict(color="#fff", width=1.5)),
        fill="tozeroy",
        fillcolor=_hex_to_rgba(color, 0.08),
        customdata=customdata,
        hovertemplate=hovertemplate,
    ))
    if target is not None:
        fig.add_hline(
            y=target,
            line=dict(color="#f59e0b", width=1.4, dash="dash"),
            annotation_text="Target",
            annotation_font=dict(color="#f59e0b", size=10),
            annotation_position="right",
        )
    if median_value is not None:
        # A separate scatter trace (not just fig.add_hline's shape) so the
        # median participates in hovermode="x unified" below -- shapes drawn
        # via add_hline are static and don't respond to hover at all.
        fig.add_trace(go.Scatter(
            x=x_values, y=[median_value] * len(x_values), mode="lines",
            line=dict(color="#6366f1", width=1.4, dash="dot"),
            showlegend=False,
            hovertemplate=f"Median: {median_value:{value_format}}<extra></extra>",
        ))
        # x=1 + xshift is a *fixed pixel* offset from the plot's right edge,
        # sitting in the margin rather than right at the plot boundary
        # (xref="x domain") -- that boundary placement was getting clipped
        # by the previous, much narrower right margin, rendering as "Med-"
        # instead of the full "Median 17" label.
        fig.add_annotation(
            x=1, xshift=8, y=median_value, xref="paper", yref="y",
            xanchor="left", yanchor="middle",
            text=f"Median {median_value:{value_format}}", showarrow=False,
            font=dict(color="#6366f1", size=10),
        )
    fig.update_layout(**_exec_chart_layout(
        height=240,
        margin=dict(l=42, r=92, t=12, b=42),
        xaxis=dict(
            showgrid=False,
            showline=False,
            zeroline=False,
            tickfont=dict(size=11, color="#94a3b8"),
            tickangle=_grain_tick_angle(grain),
            title=dict(text=_grain_axis_title(grain), font=dict(size=10, color="#64748b")),
            type="category",
            automargin=True,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#e2e8f0",
            gridwidth=1,
            showline=False,
            zeroline=False,
            tickfont=dict(size=11, color="#94a3b8"),
            tickformat=None if _is_percentage_axis(y_title) else ",.0f",
            title=dict(text=y_title, font=dict(size=10, color="#64748b")),
            rangemode="tozero",
        ),
    ))
    fig.update_layout(showlegend=False, transition={"duration": 260, "easing": "cubic-in-out"})
    if scope_label:
        fig.add_annotation(
            text=scope_label, x=0, y=1, xref="paper", yref="paper",
            xanchor="left", yanchor="bottom", yshift=4, showarrow=False,
            font=dict(size=10, color="#94a3b8"),
        )
    return fig


def _multi_run_chart(
    series_df: pd.DataFrame,
    title: str,
    y_title: str,
    target: float | None = None,
    grain: str = "monthly",
    measure: str = "median",
    scope_label: str | None = None,
) -> go.Figure:
    fig = go.Figure()
    if series_df.empty:
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=0, b=0),
            height=240,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            annotations=[dict(
                text="No trend data available",
                x=0.5,
                y=0.5,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(size=13, color=MUTED, family=_GEIST),
            )],
        )
        return fig

    measure_label = "Actual" if measure == "median" else "Moving avg"
    value_format = ".1f" if _is_percentage_axis(y_title) else ",.0f"
    median_lines = []  # (label, color, median_value) -- one per series
    for label in series_df["series"].dropna().unique():
        trace_df = series_df[series_df["series"] == label]
        color = trace_df["color"].iloc[0] if "color" in trace_df.columns and not trace_df.empty else PRIMARY_GREEN
        # Same "Median" vs "Avg" split as _run_chart above: median mode shows
        # the real values as the line and gets its own flat per-series
        # median reference line; avg mode keeps the smoothed rolling mean.
        if measure == "median":
            plotted = trace_df["value"].tolist()
            _valid_for_median = [y for y in plotted if y is not None and pd.notna(y)]
            if _valid_for_median:
                median_lines.append((label, color, float(pd.Series(_valid_for_median, dtype="float64").median())))
        else:
            plotted, _ = _moving_average_values(trace_df["value"].tolist(), grain, method=measure)
        x_values = (
            trace_df["bucket_label"]
            if "bucket_label" in trace_df.columns
            else pd.to_datetime(trace_df["month"], errors="coerce").dt.strftime("%b %Y")
        )
        fig.add_trace(go.Scatter(
            x=x_values,
            y=plotted,
            name=label,
            mode="lines+markers",
            line=dict(color=color, width=3.0, shape="spline", smoothing=0.45),
            marker=dict(size=6, color=color, line=dict(color="#fff", width=1.0)),
            customdata=trace_df["value"].tolist(),
            hovertemplate=(
                f"<b>{label}</b><br>%{{x}}<br>"
                f"{measure_label}: " f"<b>%{{y:{value_format}}}</b><br>"
                f"Actual: <b>%{{customdata:{value_format}}}</b>"
                "<extra></extra>"
            ),
        ))
        if measure == "median" and _valid_for_median:
            fig.add_trace(go.Scatter(
                x=x_values, y=[median_lines[-1][2]] * len(x_values), mode="lines",
                line=dict(color=color, width=1.2, dash="dot"), opacity=0.6,
                showlegend=False,
                hovertemplate=f"{label} median: {median_lines[-1][2]:{value_format}}<extra></extra>",
            ))

    if target is not None:
        fig.add_hline(
            y=target,
            line=dict(color="#f59e0b", width=1.4, dash="dash"),
            annotation_text="Target",
            annotation_font=dict(color="#f59e0b", size=10),
            annotation_position="right",
        )

    fig.update_layout(**_exec_chart_layout(
        height=240,
        margin=dict(l=42, r=92, t=12, b=42),
        xaxis=dict(
            showgrid=False,
            showline=False,
            zeroline=False,
            tickfont=dict(size=11, color="#94a3b8"),
            tickangle=_grain_tick_angle(grain),
            title=dict(text=_grain_axis_title(grain), font=dict(size=10, color="#64748b")),
            type="category",
            automargin=True,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#e2e8f0",
            gridwidth=1,
            showline=False,
            zeroline=False,
            tickfont=dict(size=11, color="#94a3b8"),
            tickformat=None if _is_percentage_axis(y_title) else ",.0f",
            title=dict(text=y_title, font=dict(size=10, color="#64748b")),
            rangemode="tozero",
        ),
    ))
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=10, color="#64748b"),
        ),
        transition={"duration": 260, "easing": "cubic-in-out"},
    )
    if scope_label:
        # Top-right, above the legend (which sits top-left at y=1.02 above)
        # so the two don't overlap.
        fig.add_annotation(
            text=scope_label, x=1, y=1.08, xref="paper", yref="paper",
            xanchor="right", yanchor="bottom", showarrow=False,
            font=dict(size=10, color="#94a3b8"),
        )
    return fig


def _trend_chart_card(
    title: str,
    subtitle: str,
    figure: go.Figure,
    accent: str,
    header_right=None,
    graph_id: str | dict | None = None,
    caption: str | None = None,
    caption_id: str | dict | None = None,
    graph_config: dict | None = None,
    graph_style: dict | None = None,
) -> dmc.Paper:
    return dmc.Paper(
        withBorder=True,
        radius="md",
        shadow="xs",
        p="md",
        style={
            "overflow": "hidden",
            "borderColor": "#dbe4f0",
            "background": "linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)",
            "borderTop": f"3px solid {accent}",
        },
        children=[
            html.Div([
                html.Div([
                    html.Div(title, style={
                        "fontSize": "13px",
                        "fontWeight": "800",
                        "color": "#0f172a",
                        "lineHeight": "1.2",
                        "marginBottom": "4px",
                    }),
                    html.Div(subtitle, style={
                        "fontSize": "11px",
                        "color": "#64748b",
                    }),
                ], style={"flex": "1", "minWidth": "0"}),
                *([header_right] if header_right is not None else []),
            ], style={
                "padding": "2px 4px 6px 4px",
                "display": "flex",
                "justifyContent": "space-between",
                "alignItems": "flex-start",
                "gap": "12px",
                "flexWrap": "wrap",
            }),
            dcc.Graph(
                **({"id": graph_id} if graph_id is not None else {}),
                figure=figure,
                config=graph_config or {"displayModeBar": True, "responsive": True},
                style=graph_style or {"height": "240px"},
            ),
            *([html.Div(
                caption or "",
                **({"id": caption_id} if caption_id is not None else {}),
                style={
                    "fontSize": "11px",
                    "color": "#64748b",
                    "padding": "0 4px 2px 4px",
                },
            )] if caption is not None or caption_id is not None else []),
        ],
    )


def build_trend_chart_card(*args, **kwargs) -> dmc.Paper:
    return _trend_chart_card(*args, **kwargs)


def _trend_chart_payload(
    chart_key: str,
    title: str,
    subtitle: str,
    accent: str,
    y_title: str,
    series_df: pd.DataFrame,
    multi: bool = False,
    measure: str = "median",
    include_daily: bool = True,
    scope_label: str | None = None,
    default_grain: str | None = None,
    refetch: dict | None = None,
) -> dict:
    # default_grain overrides the _EXEC_DEFAULT_GRAINS lookup when the caller
    # already knows what grain it fetched series_df at (e.g. Country
    # Profile's per-window _fetch_grain) -- falls back to the dict's own
    # per-chart default otherwise, same as before this param existed.
    default_grain = default_grain or _EXEC_DEFAULT_GRAINS.get(chart_key, "monthly")
    # DHIS2's aggregate only ever has monthly-grain rows -- offering "Daily"
    # there would silently show monthly data under a misleading label instead
    # of a real day-level view, so only offer it in MAHIS mode (include_daily
    # is False when the caller is rendering from the DHIS2 aggregate).
    grain_options = _EXEC_GRAIN_OPTIONS if include_daily else [
        opt for opt in _EXEC_GRAIN_OPTIONS if opt["value"] != "daily"
    ]
    bucketed = (
        bucket_multi_series(series_df, default_grain)
        if multi
        else bucket_time_series(series_df, default_grain)
    )
    figure = (
        _multi_run_chart(bucketed, title, y_title, grain=default_grain, measure=measure, scope_label=scope_label)
        if multi
        else _run_chart(bucketed, title, accent, y_title, grain=default_grain, measure=measure, scope_label=scope_label)
    )
    return {
        "card": _trend_chart_card(
            title,
            subtitle,
            figure,
            accent,
            header_right=html.Div([
                dmc.SegmentedControl(
                    id={"type": "mnid-cp-grain", "chart": chart_key},
                    value=default_grain,
                    data=grain_options,
                    radius="xl",
                    size="xs",
                    color="green",
                    styles={
                        "root": {
                            "background": "#fff",
                            "border": f"1px solid {_hex_to_rgba(accent, 0.22)}",
                            "padding": "2px",
                        },
                        "control": {"border": "0"},
                        "label": {
                            "fontSize": "11px",
                            "fontWeight": 600,
                            "color": "#64748b",
                            "padding": "4px 10px",
                        },
                        "indicator": {
                            "background": _hex_to_rgba(accent, 0.14),
                            "border": f"1px solid {_hex_to_rgba(accent, 0.18)}",
                        },
                    },
                ),
                dcc.Store(
                    id={"type": "mnid-cp-series", "chart": chart_key},
                    data=_serialize_trend_series(series_df),
                ),
                dcc.Store(
                    id={"type": "mnid-cp-meta", "chart": chart_key},
                    data={
                        "title": title,
                        "accent": accent,
                        "y_title": y_title,
                        "multi": multi,
                        # Read back by the grain-toggle callback
                        # (_update_country_profile_chart_grain in
                        # renderer.py) so the re-rendered figure on a grain
                        # change still shows the same scope annotation.
                        "scope_label": scope_label,
                        # Read by the grain-toggle callback to redo this
                        # chart's exact original fetch at the newly-selected
                        # grain (e.g. a real per-day scan for "Daily")
                        # instead of just re-bucketing whatever series_df
                        # already holds client-side.
                        "refetch": refetch,
                    },
                ),
            ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),
            graph_id={"type": "mnid-cp-graph", "chart": chart_key},
            caption=describe_grain_window(bucketed, default_grain),
            caption_id={"type": "mnid-cp-caption", "chart": chart_key},
        ),
        "default_grain": default_grain,
    }


__all__ = [
    "PRIMARY_GREEN",
    "_EXEC_CHART_LAYOUT",
    "_EXEC_DEFAULT_GRAINS",
    "_EXEC_GRAIN_OPTIONS",
    "_chart_key_slug",
    "_exec_chart_layout",
    "_hex_to_rgba",
    "_is_percentage_axis",
    "_multi_run_chart",
    "_run_chart",
    "_trend_chart_payload",
    "bucket_multi_series",
    "bucket_time_series",
    "build_trend_chart_card",
    "describe_grain_window",
]
