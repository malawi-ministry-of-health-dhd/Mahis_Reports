"""Reusable dashboard layout builders for premium program experiences."""

from copy import deepcopy

from dash import html

from config import FACILITY_
from helpers import build_single_chart, create_count_from_config, parse_filter_value


def _build_filter_chip(label, value):
    return html.Div(
        className="premium-filter-chip",
        children=[
            html.Span(label, className="premium-filter-label"),
            html.Span(value, className="premium-filter-value"),
        ],
    )


def _build_metric_card(value, label, accent):
    return html.Div(
        className="premium-metric-card",
        children=[
            html.Div(className=f"premium-metric-accent premium-accent-{accent}"),
            html.Div(label, className="premium-metric-label"),
            html.Div(f"{value:,}", className="premium-metric-value"),
            html.Div("Updated from the current filtered cohort", className="premium-metric-caption"),
        ],
    )


def _build_hero_stat(label, value):
    return html.Div(
        className="premium-hero-stat",
        children=[
            html.Div(label, className="premium-hero-stat-label"),
            html.Div(value, className="premium-hero-stat-value"),
        ],
    )


def _metric_value(count_config, filtered):
    return int(create_count_from_config(filtered, count_config["filters"]))


def _metric_progress(value, target):
    if not target:
        return 0
    return round((value / target) * 100)


def _metric_status(value, target):
    if value == 0:
        return "danger"
    progress = _metric_progress(value, target)
    if progress >= 100:
        return "ok"
    if progress >= 70:
        return "info"
    if progress >= 35:
        return "warn"
    return "danger"


def _get_metric_section_href(label):
    label_lower = label.lower()
    if any(term in label_lower for term in ["anc", "anemia", "infection", "blood pressure", "pocus", "gestational", "tetanus"]):
        return "#mnid-section-1"
    if any(term in label_lower for term in ["deliver", "labour", "digital monitoring", "pph", "corticosteroid", "azithromycin", "staff"]):
        return "#mnid-section-2"
    return "#mnid-section-3"


def _build_reference_metric_card(value, label, tone, target):
    return html.A(
        href=_get_metric_section_href(label),
        className=f"mnid-kpi-link mnid-kpi {tone}",
        children=[
            html.Div(label, className="mnid-kpi-label"),
            html.Div(f"{value:,}", className="mnid-kpi-value"),
            html.Div(
                f"Reference benchmark {target}% - open supporting visuals",
                className="mnid-kpi-sub",
            ),
        ],
    )


def _build_pill(pill):
    return html.A(
        pill.get("label", ""),
        href=pill.get("href", "#mnid-overview"),
        className=f"mnid-pill mnid-pill-{pill.get('tone', 'blue')}",
    )


def _build_alert_banner(metric_items):
    critical = [item for item in metric_items if item["tone"] == "danger"]
    watch = [item for item in metric_items if item["tone"] == "warn"]
    strong = [item for item in metric_items if item["tone"] in {"ok", "info"}]

    if critical:
        tone = "danger"
        headline = "Clinical review recommended"
        lead_items = ", ".join(item["label"] for item in critical[:2])
        body = f"{lead_items} show low observed coverage and should be reviewed for service delivery gaps, documentation gaps, or referral bottlenecks."
    elif watch:
        tone = "warn"
        headline = "Monitor closely"
        lead_items = ", ".join(item["label"] for item in watch[:2])
        body = f"{lead_items} remain below the expected benchmark and should be monitored closely."
    else:
        tone = "ok"
        headline = "Stable position"
        lead_items = ", ".join(item["label"] for item in strong[:2]) or "Current indicators"
        body = f"{lead_items} are currently the strongest-performing indicators in this view."

    if strong and tone != "ok":
        positive_note = f" Stronger areas include {', '.join(item['label'] for item in strong[:2])}."
    else:
        positive_note = ""

    return html.Div(
        className=f"mnid-alert mnid-alert-{tone}",
        children=[
            html.Div("!", className="mnid-alert-icon"),
            html.P(
                [
                    html.Strong(f"{headline}: "),
                    f"{body}{positive_note}",
                ],
                className="mnid-alert-copy",
            ),
        ],
    )


def _build_tracker(metric_items, profile):
    tracker_items = []
    for item in metric_items[:6]:
        pct = min(item["progress"], 100)
        tone = item["tone"]
        tracker_items.append(
            html.Div(
                className="mnid-prog-row",
                children=[
                    html.Span(item["label"], className="mnid-prog-label"),
                    html.Div(
                        className="mnid-prog-track",
                        children=[
                            html.Div(className=f"mnid-prog-fill {tone}", style={"width": f"{pct}%"}),
                            html.Div(className="mnid-prog-target", style={"left": "80%"}),
                        ],
                    ),
                    html.Span(f"{item['progress']}%", className="mnid-prog-value"),
                ],
            )
        )

    return html.Div(
        className="mnid-card",
        children=[
            html.Div(profile.get("tracker_title", "Coverage tracker"), className="mnid-card-title"),
            html.Div(tracker_items),
            html.Div("| = target reference", className="mnid-target-note"),
        ],
    )


def _status_label(tone):
    if tone == "ok":
        return "On target"
    if tone == "info":
        return "Performing"
    if tone == "warn":
        return "Watch"
    return "Action needed"


def _build_indicator_status_card(metric_items):
    return html.Div(
        className="mnid-card mnid-status-card",
        children=[
            html.Div("Priority indicator status", className="mnid-card-title"),
            html.Div(
                className="mnid-status-header",
                children=[
                    html.Span("Indicator"),
                    html.Span("Current"),
                    html.Span("Benchmark"),
                    html.Span("Observed coverage"),
                    html.Span("Status"),
                ],
            ),
            html.Div(
                className="mnid-status-table",
                children=[
                    html.Div(
                        className="mnid-status-row",
                        children=[
                            html.Div(item["label"], className="mnid-status-indicator"),
                            html.Div(f"{item['value']:,}", className="mnid-status-metric"),
                            html.Div(f"{item['target']}%", className="mnid-status-target"),
                            html.Div(f"{item['coverage']}%", className="mnid-status-progress"),
                            html.Div(
                                _status_label(item["tone"]),
                                className=f"mnid-status-badge mnid-status-badge-{item['tone']}",
                            ),
                        ],
                    )
                    for item in metric_items
                ],
            ),
        ],
    )


def _build_attention_card(metric_items, filter_summary):
    urgent = [item for item in metric_items if item["tone"] == "danger"][:3]
    watch = [item for item in metric_items if item["tone"] == "warn"][:2]
    strong = [item for item in metric_items if item["tone"] in {"ok", "info"}][:2]

    def _build_insight_group(title, items, tone):
        entries = items or [{"label": "No indicators currently in this group", "progress": 0}]
        return html.Div(
            className="mnid-insight-group",
            children=[
                html.Div(title, className="mnid-insight-title"),
                html.Div(
                    className="mnid-insight-list",
                    children=[
                        html.Div(
                            className="mnid-insight-item",
                            children=[
                                html.Span(entry["label"], className="mnid-insight-label"),
                                html.Span(
                                    f"{entry['progress']}%" if entry["progress"] else "Stable",
                                    className=f"mnid-insight-pill mnid-insight-pill-{tone}",
                                ),
                            ],
                        )
                        for entry in entries
                    ],
                ),
            ],
        )

    return html.Div(
        className="mnid-card mnid-overview-card",
        children=[
            html.Div("Facility summary and action points", className="mnid-card-title"),
            html.Div(
                className="mnid-facility-strip",
                children=[
                    html.Div(
                        className="mnid-facility-stat",
                        children=[
                            html.Span("Facility"),
                            html.Strong(filter_summary.get("Facility", "Current facility")),
                        ],
                    ),
                    html.Div(
                        className="mnid-facility-stat",
                        children=[
                            html.Span("Critical indicators"),
                            html.Strong(str(len([item for item in metric_items if item["tone"] == "danger"]))),
                        ],
                    ),
                    html.Div(
                        className="mnid-facility-stat",
                        children=[
                            html.Span("At or near target"),
                            html.Strong(str(len([item for item in metric_items if item["tone"] in {"ok", "info"}]))),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="mnid-insight-grid",
                children=[
                    _build_insight_group("Needs immediate review", urgent, "danger"),
                    _build_insight_group("Monitor closely", watch, "warn"),
                    _build_insight_group("Current strengths", strong, "ok"),
                ],
            ),
        ],
    )


def _build_metric_registry(counts, profile):
    benchmark_registry = profile.get("benchmark_filters", {})
    registry = {}
    for count_config in counts:
        metric_copy = deepcopy(count_config)
        if count_config["name"] in benchmark_registry:
            metric_copy["benchmark_filters"] = benchmark_registry[count_config["name"]]
        registry[count_config["name"]] = metric_copy
    for metric_config in profile.get("supplemental_metrics", []):
        metric_copy = deepcopy(metric_config)
        if metric_config["name"] in benchmark_registry and "benchmark_filters" not in metric_copy:
            metric_copy["benchmark_filters"] = benchmark_registry[metric_config["name"]]
        registry[metric_config["name"]] = metric_copy
    return registry


def _build_metric_item(metric_config, filtered, target):
    value = _metric_value(metric_config, filtered)
    benchmark_filters = metric_config.get("benchmark_filters")
    benchmark_total = int(create_count_from_config(filtered, benchmark_filters)) if benchmark_filters else 0
    coverage = round((value / benchmark_total) * 100) if benchmark_total else _metric_progress(value, target)
    return {
        "label": metric_config["name"],
        "value": value,
        "target": target,
        "coverage": coverage,
        "benchmark_total": benchmark_total,
        "progress": coverage,
        "tone": _metric_status(coverage, target),
    }


def _resolve_cluster_metrics(profile, metric_registry, filtered):
    indicator_targets = profile.get("indicator_targets", {})
    default_target = profile.get("tracker_target", 80)
    metric_lookup = {}

    for cluster in profile.get("indicator_clusters", []):
        for metric_name in cluster.get("metrics", []):
            if metric_name in metric_lookup or metric_name not in metric_registry:
                continue
            target = indicator_targets.get(metric_name, default_target)
            metric_lookup[metric_name] = _build_metric_item(metric_registry[metric_name], filtered, target)

    return metric_lookup


def _build_cluster_grid(clusters, metric_lookup):
    cluster_cards = []
    for cluster in clusters:
        cluster_metrics = [metric_lookup[name] for name in cluster.get("metrics", []) if name in metric_lookup]
        if not cluster_metrics:
            continue

        cluster_cards.append(
            html.Div(
                className=f"mnid-card mnid-cluster-card mnid-cluster-{cluster.get('tone', 'blue')}",
                children=[
                    html.Div(cluster.get("title", ""), className="mnid-cluster-title"),
                    html.Div(
                        className="mnid-cluster-grid",
                        children=[
                            html.A(
                                href=_get_metric_section_href(item["label"]),
                                className=f"mnid-cluster-metric mnid-cluster-metric-{item['tone']}",
                                children=[
                                    html.Div(item["label"], className="mnid-cluster-label"),
                                    html.Div(f"{item['value']:,}", className="mnid-cluster-value"),
                                    html.Div(f"Observed coverage {item['coverage']}% | Benchmark {item['target']}%", className="mnid-cluster-sub"),
                                ],
                            )
                            for item in cluster_metrics
                        ],
                    ),
                ],
            )
        )

    return html.Div(cluster_cards, className="mnid-cluster-layout")


def _filter_chart_data(filtered, chart_filters):
    data = filtered.copy()
    for idx in range(1, 4):
        filter_col = chart_filters.get(f"filter_col{idx}")
        filter_value = parse_filter_value(chart_filters.get(f"filter_val{idx}"))
        if not filter_col or filter_value in (None, ""):
            continue
        if isinstance(filter_value, list):
            data = data[data[filter_col].isin(filter_value)]
        else:
            data = data[data[filter_col] == filter_value]
    return data


def _preferred_distribution_label(summary):
    preferred_terms = ["screened", "yes", "completed", "used", "assessed", "stable", "linked", "all available", "bcg"]
    for _, row in summary.iterrows():
        label = str(row["label"]).lower()
        if any(term in label for term in preferred_terms):
            return row["label"]
    return summary.iloc[0]["label"]


def _distribution_summary(filtered, item_config):
    chart_filters = item_config.get("filters", {})
    names_col = chart_filters.get("names_col")
    values_col = chart_filters.get("values_col", "person_id")
    unique_column = chart_filters.get("unique_column", values_col)
    data = _filter_chart_data(filtered, chart_filters)

    if data.empty or names_col not in data.columns:
        return None

    summary = (
        data.groupby(names_col)[unique_column]
        .nunique()
        .reset_index(name="value")
        .rename(columns={names_col: "label"})
        .sort_values("value", ascending=False)
    )
    total = int(summary["value"].sum()) if not summary.empty else 0
    if total == 0:
        return None

    summary["percent"] = (summary["value"] / total * 100).round().astype(int)
    primary_label = _preferred_distribution_label(summary)
    primary_row = summary[summary["label"] == primary_label].iloc[0]
    return {
        "summary": summary,
        "total": total,
        "primary_label": primary_label,
        "gauge_value": int(primary_row["percent"]),
    }


def _build_distribution_card(filtered, item_config):
    distribution = _distribution_summary(filtered, item_config)
    if distribution is None:
        return html.Div(
            className="mnid-card mnid-distribution-card",
            children=[
                html.Div(item_config.get("name", ""), className="mnid-card-title"),
                html.Div("No data available for the current filters.", className="mnid-overview-copy"),
            ],
        )

    summary = distribution["summary"]
    total = distribution["total"]
    primary_label = distribution["primary_label"]
    gauge_value = distribution["gauge_value"]

    return html.Div(
        className="mnid-card mnid-distribution-card",
        children=[
            html.Div(item_config.get("name", ""), className="mnid-card-title"),
            html.Div(
                className="mnid-distribution-shell",
                children=[
                    html.Div(
                        className="mnid-gauge-card",
                        children=[
                            html.Div(
                                className="mnid-gauge-ring",
                                style={"--mnid-gauge-value": f"{gauge_value}%"},
                                children=[
                                    html.Div(
                                        className="mnid-gauge-inner",
                                        children=[
                                            html.Strong(f"{gauge_value}%"),
                                            html.Span(str(primary_label)),
                                        ],
                                    )
                                ],
                            ),
                            html.Div(f"{total:,} clients in current cohort", className="mnid-gauge-caption"),
                        ],
                    ),
                    html.Div(
                        className="mnid-distribution-list",
                        children=[
                            html.Div(
                                className="mnid-distribution-row",
                                children=[
                                    html.Div(
                                        className="mnid-distribution-main",
                                        children=[
                                            html.Span(str(row["label"]), className="mnid-distribution-label"),
                                            html.Div(
                                                className="mnid-distribution-track",
                                                children=[
                                                    html.Div(
                                                        className="mnid-distribution-fill",
                                                        style={"width": f"{int(row['percent'])}%"},
                                                    )
                                                ],
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="mnid-distribution-metric",
                                        children=[
                                            html.Strong(f"{int(row['percent'])}%"),
                                            html.Span(f"{int(row['value'])}"),
                                        ],
                                    ),
                                ],
                            )
                            for _, row in summary.head(4).iterrows()
                        ],
                    ),
                ],
            ),
        ],
    )


def _build_facility_comparison_panel(filtered, metric_registry, profile):
    facility_metrics = [metric_registry[name] for name in profile.get("facility_comparison_metrics", []) if name in metric_registry]
    if FACILITY_ not in filtered.columns or not facility_metrics:
        return html.Div(
            className="mnid-card mnid-comparison-card",
            children=[
                html.Div("Facility comparison", className="mnid-card-title"),
                html.Div("Facility comparison is unavailable for the current dataset.", className="mnid-overview-copy"),
            ],
        )

    facility_rows = []
    for facility_name in sorted(filtered[FACILITY_].dropna().unique()):
        facility_df = filtered[filtered[FACILITY_] == facility_name]
        metric_items = []
        for metric_config in facility_metrics:
            target = profile.get("indicator_targets", {}).get(metric_config["name"], profile.get("tracker_target", 80))
            metric_items.append(_build_metric_item(metric_config, facility_df, target))

        if not metric_items:
            continue

        avg_progress = round(sum(min(item["progress"], 100) for item in metric_items) / len(metric_items))
        critical_count = len([item for item in metric_items if item["tone"] == "danger"])
        facility_rows.append(
            {
                "facility": facility_name,
                "avg_progress": avg_progress,
                "critical": critical_count,
                "top_metric": max(metric_items, key=lambda item: item["progress"])["label"],
                "tone": _metric_status(avg_progress, 100),
            }
        )

    facility_rows = sorted(facility_rows, key=lambda row: (-row["avg_progress"], row["facility"]))[:8]
    if not facility_rows:
        return html.Div(
            className="mnid-card mnid-comparison-card",
            children=[
                html.Div("Facility comparison", className="mnid-card-title"),
                html.Div("No facility records are available for comparison.", className="mnid-overview-copy"),
            ],
        )

    return html.Div(
        className="mnid-card mnid-comparison-card",
        children=[
            html.Div("Facility comparison panel", className="mnid-card-title"),
            html.Div(
                className="mnid-comparison-header",
                children=[
                    html.Span("Facility"),
                    html.Span("Average performance"),
                    html.Span("Critical indicators"),
                ],
            ),
            html.Div(
                className="mnid-comparison-table",
                children=[
                    html.Div(
                        className="mnid-comparison-row",
                        children=[
                            html.Div(
                                className="mnid-comparison-facility",
                                children=[
                                    html.Strong(row["facility"]),
                                    html.Span(row["top_metric"]),
                                ],
                            ),
                            html.Div(
                                className="mnid-comparison-progress",
                                children=[
                                    html.Div(
                                        className="mnid-comparison-track",
                                        children=[
                                            html.Div(
                                                className=f"mnid-comparison-fill mnid-comparison-fill-{row['tone']}",
                                                style={"width": f"{row['avg_progress']}%"},
                                            )
                                        ],
                                    ),
                                    html.Span(f"{row['avg_progress']}%"),
                                ],
                            ),
                            html.Div(
                                className=f"mnid-status-badge mnid-status-badge-{row['tone']}",
                                children=[str(row["critical"])],
                            ),
                        ],
                    )
                    for row in facility_rows
                ],
            ),
            html.Div("Facility ranking", className="mnid-comparison-subtitle"),
            html.Div(
                className="mnid-ranking-header",
                children=[
                    html.Span("Rank"),
                    html.Span("Facility"),
                    html.Span("Avg"),
                    html.Span("Critical"),
                ],
            ),
            html.Div(
                className="mnid-ranking-table",
                children=[
                    html.Div(
                        className="mnid-ranking-row",
                        children=[
                            html.Strong(str(index + 1)),
                            html.Span(row["facility"]),
                            html.Span(f"{row['avg_progress']}%"),
                            html.Span(str(row["critical"])),
                        ],
                    )
                    for index, row in enumerate(facility_rows[:5])
                ],
            ),
        ],
    )


def _build_reference_chart_card(filtered, data_opd, delta_days, item_config, theme_name):
    chart_type = item_config.get("type", "")
    if chart_type == "Pie":
        return _build_distribution_card(filtered, item_config)

    card_class = "mnid-card mnid-card-chart"
    if chart_type in ["Line", "Heatmap"]:
        card_class += " mnid-card-chart-wide"
    elif chart_type in ["Bar", "Column", "PivotTable", "CrossTab", "LineList"]:
        card_class += " mnid-card-chart-mid"
    else:
        card_class += " mnid-card-chart-compact"

    normalized_item = deepcopy(item_config)
    normalized_item.setdefault("filters", {})
    normalized_item["filters"]["title"] = ""

    return html.Div(
        className=card_class,
        children=[
            html.Div(item_config.get("name", ""), className="mnid-card-title"),
            build_single_chart(
                filtered,
                data_opd,
                delta_days,
                normalized_item,
                style="mnid-graph",
                theme_name=theme_name,
            ),
        ],
    )


def build_mnid_light_dashboard(filtered, data_opd, delta_days, dashboard_config, profile, filter_summary=None):
    """Reference-inspired maternal and child layout that remains profile-configurable."""
    counts = dashboard_config["visualization_types"]["counts"]
    sections = dashboard_config["visualization_types"]["charts"]["sections"]
    theme_name = profile.get("theme")
    filter_summary = filter_summary or {}

    metric_registry = _build_metric_registry(counts, profile)
    metric_lookup = _resolve_cluster_metrics(profile, metric_registry, filtered)
    metric_items = list(metric_lookup.values())
    primary_metric_items = [
        metric_lookup[count_config["name"]]
        for count_config in counts[:8]
        if count_config["name"] in metric_lookup
    ]

    topbar_meta = " | ".join(f"{label}: {value}" for label, value in filter_summary.items() if value)
    performance_items = sections[0]["items"][:2] if sections else []
    featured_item_ids = {item.get("id") for item in performance_items}
    performance_stage = []
    if performance_items:
        performance_stage.append(
            html.Div(
                className="mnid-grid-2 mnid-performance-stage",
                children=[
                    _build_reference_chart_card(filtered, data_opd, delta_days, performance_items[0], theme_name),
                    _build_facility_comparison_panel(filtered, metric_registry, profile),
                ],
            )
        )
        if len(performance_items) > 1:
            performance_stage.append(
                html.Div(
                    className="mnid-grid-2",
                    children=[
                        _build_reference_chart_card(filtered, data_opd, delta_days, performance_items[1], theme_name),
                        _build_indicator_status_card(metric_items),
                    ],
                )
            )

    section_nav = [
        html.A("Overview", href="#mnid-overview", className="mnid-nav-chip mnid-nav-chip-active")
    ]
    section_nav.extend(
        html.A(section["section_name"], href=f"#mnid-section-{section_index}", className="mnid-nav-chip")
        for section_index, section in enumerate(sections)
    )

    section_cards = []
    for section_index, section in enumerate(sections):
        section_items = section["items"]
        if section_index == 0:
            section_items = [
                item for item in section_items
                if item.get("id") not in featured_item_ids
            ]
        if not section_items:
            continue

        section_cards.append(
            html.Details(
                open=True if section_index == 0 else False,
                id=f"mnid-section-{section_index}",
                className="mnid-section-details",
                children=[
                    html.Summary(
                        children=[
                            html.Span(section["section_name"], className="mnid-section-summary-title"),
                            html.Span(f"{len(section_items)} visuals", className="mnid-section-summary-meta"),
                        ],
                        className="mnid-section-summary",
                    ),
                    html.Div(
                        className="mnid-grid-2 mnid-section-stage",
                        children=[_build_reference_chart_card(filtered, data_opd, delta_days, section_items[0], theme_name)],
                    ),
                    html.Div(
                        className="mnid-grid-3",
                        children=[
                            _build_reference_chart_card(filtered, data_opd, delta_days, item_config, theme_name)
                            for item_config in section_items[1:]
                        ],
                    ),
                ],
            )
        )

    return html.Div(
        className="premium-dashboard premium-theme-mch mnid-light-shell",
        children=[
            html.Div(
                className="mnid-topbar",
                children=[
                    html.Div(
                        className="mnid-topbar-left",
                        children=[
                            html.H2(dashboard_config["report_name"], className="mnid-topbar-title"),
                            html.P(topbar_meta, className="mnid-topbar-meta"),
                        ],
                    ),
                    html.Div(
                        className="mnid-topbar-right",
                        children=[_build_pill(pill) for pill in profile.get("topbar_pills", [])],
                    ),
                ],
            ),
            _build_alert_banner(metric_items),
            html.Div(className="mnid-nav-row", children=section_nav),
            html.Div("Key facility indicators", className="mnid-section-label"),
            html.Div(id="mnid-overview", className="mnid-clusters-wrap", children=[_build_cluster_grid(profile.get("indicator_clusters", []), metric_lookup)]),
            html.Div(
                className="mnid-grid-2",
                children=[
                    _build_tracker(primary_metric_items or metric_items, profile),
                    _build_attention_card(metric_items, filter_summary),
                ],
            ),
            html.Div(performance_stage),
            html.Div(section_cards, className="mnid-sections"),
        ],
    )


def _build_metric_band(filtered, counts):
    accents = ["blue", "mint", "teal", "gold"]
    cards = []
    for index, count_config in enumerate(counts[:8]):
        value = create_count_from_config(filtered, count_config["filters"])
        cards.append(_build_metric_card(value, count_config["name"], accents[index % len(accents)]))
    return html.Div(cards, className="premium-metric-grid")


def _build_section_item(filtered, data_opd, delta_days, item_config, theme_name):
    chart_type = item_config.get("type", "")
    card_class = "premium-stage-card"
    if chart_type in ["Line", "PivotTable", "CrossTab", "LineList"]:
        card_class += " premium-stage-card-wide"
    elif chart_type == "Pie":
        card_class += " premium-stage-card-compact"

    return html.Div(
        className=card_class,
        children=[
            html.Div(
                className="premium-stage-card-header",
                children=[
                    html.Div(item_config.get("name", ""), className="premium-stage-card-title"),
                    html.Div(chart_type, className="premium-stage-card-type"),
                ],
            ),
            build_single_chart(
                filtered,
                data_opd,
                delta_days,
                item_config,
                style="premium-graph",
                theme_name=theme_name,
            ),
        ],
    )


def build_premium_dashboard(filtered, data_opd, delta_days, dashboard_config, profile, filter_summary=None):
    """Render a premium dashboard shell using a profile-driven configuration."""
    if profile.get("variant") == "mnid_light":
        return build_mnid_light_dashboard(
            filtered,
            data_opd,
            delta_days,
            dashboard_config,
            profile,
            filter_summary=filter_summary,
        )

    counts = dashboard_config["visualization_types"]["counts"]
    sections = dashboard_config["visualization_types"]["charts"]["sections"]
    theme_name = profile.get("theme")

    filter_summary = filter_summary or {}
    filter_chips = [
        _build_filter_chip(label, value)
        for label, value in filter_summary.items()
        if value
    ]

    section_links = [
        html.A("Overview", href="#premium-overview", className="premium-rail-item premium-rail-item-active")
    ]
    section_links.insert(0, html.Div(profile.get("section_chip_label", "Sections"), className="premium-rail-label"))
    section_links.extend(
        html.A(section["section_name"], href=f"#premium-section-{index}", className="premium-rail-item")
        for index, section in enumerate(sections)
    )

    section_blocks = []
    for index, section in enumerate(sections):
        section_blocks.append(
            html.Section(
                id=f"premium-section-{index}",
                className="premium-section-block",
                children=[
                    html.Div(
                        className="premium-section-header",
                        children=[
                            html.H3(section["section_name"], className="premium-section-title"),
                            html.Div(f"{len(section['items'])} visuals", className="premium-section-meta"),
                        ],
                    ),
                    html.Div(
                        className="premium-stage-grid",
                        children=[
                            _build_section_item(filtered, data_opd, delta_days, item_config, theme_name)
                            for item_config in section["items"]
                        ],
                    ),
                ],
            )
        )

    return html.Div(
        className="premium-dashboard premium-theme-mch",
        children=[
            html.Div(
                className="premium-shell",
                children=[
                    html.Aside(
                        className="premium-rail",
                        children=[
                            html.Div(profile.get("brand", dashboard_config["report_name"]), className="premium-rail-brand"),
                            html.Div(profile.get("subtitle", ""), className="premium-rail-copy"),
                            html.Div(section_links, className="premium-rail-nav"),
                        ],
                    ),
                    html.Div(
                        className="premium-main",
                        children=[
                            html.Div(
                                className="premium-hero",
                                children=[
                                    html.Div(
                                        className="premium-hero-copy",
                                        children=[
                                            html.Div(profile.get("kicker", "Overview"), className="premium-kicker"),
                                            html.H2(dashboard_config["report_name"], className="premium-title"),
                                            html.P(profile.get("subtitle", ""), className="premium-subtitle"),
                                        ],
                                    ),
                                    html.Div(
                                        className="premium-hero-side",
                                        children=[
                                            html.Div(filter_chips, className="premium-filter-strip"),
                                            html.Div(
                                                className="premium-hero-stats",
                                                children=[
                                                    _build_hero_stat("KPI Cards", str(min(len(counts), 8))),
                                                    _build_hero_stat("Sections", str(len(sections))),
                                                    _build_hero_stat("Visuals", str(sum(len(section["items"]) for section in sections))),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                id="premium-overview",
                                className="premium-overview-band",
                                children=[
                                    html.Div(
                                        className="premium-overview-copy",
                                        children=[
                                            html.Div("Executive Snapshot", className="premium-overview-kicker"),
                                            html.H3(profile.get("overview_title", "Key indicators at a glance"), className="premium-overview-title"),
                                            html.P(profile.get("overview_copy", ""), className="premium-overview-text"),
                                        ],
                                    ),
                                    _build_metric_band(filtered, counts),
                                ],
                            ),
                            html.Div(section_blocks, className="premium-sections"),
                        ],
                    ),
                ],
            )
        ],
    )
