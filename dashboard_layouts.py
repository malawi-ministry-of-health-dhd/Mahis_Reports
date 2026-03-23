"""Reusable dashboard layout builders for premium program experiences."""

from copy import deepcopy

from dash import html

from helpers import build_single_chart, create_count_from_config


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
    progress = _metric_progress(value, target)
    return html.A(
        href=_get_metric_section_href(label),
        className=f"mnid-kpi-link mnid-kpi {tone}",
        children=[
            html.Div(label, className="mnid-kpi-label"),
            html.Div(f"{value:,}", className="mnid-kpi-value"),
            html.Div(f"{progress}% of reference target · click to inspect supporting visuals", className="mnid-kpi-sub"),
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
    strong = [item for item in metric_items if item["tone"] == "ok"]

    if critical:
        tone = "danger"
        headline = "Action required"
        lead_items = ", ".join(f"{item['label']} ({item['value']:,})" for item in critical[:2])
        body = f"{lead_items} are materially below the reference target and should be reviewed for documentation gaps, service bottlenecks, or referral issues."
    elif watch:
        tone = "warn"
        headline = "Monitor closely"
        lead_items = ", ".join(f"{item['label']} ({item['progress']}% of target)" for item in watch[:2])
        body = f"{lead_items} are improving but remain below the desired performance range."
    else:
        tone = "ok"
        headline = "Stable position"
        lead_items = ", ".join(f"{item['label']} ({item['progress']}% of target)" for item in strong[:2]) or "Current indicators"
        body = f"{lead_items} are at or above the current reference target. Continue monitoring for consistency and data completeness."

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


def _build_reference_chart_card(filtered, data_opd, delta_days, item_config, theme_name):
    chart_type = item_config.get("type", "")
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

    metric_items = [
        {
            "label": count_config["name"],
            "value": _metric_value(count_config, filtered),
        }
        for count_config in counts[:8]
    ]
    indicator_targets = profile.get("indicator_targets", {})
    default_target = profile.get("tracker_target", 80)
    for item in metric_items:
        target = indicator_targets.get(item["label"], default_target)
        item["target"] = target
        item["progress"] = _metric_progress(item["value"], target)
        item["tone"] = _metric_status(item["value"], target)

    topbar_meta = " | ".join(f"{label}: {value}" for label, value in filter_summary.items() if value)
    featured_items = sections[0]["items"][:2] if sections else []
    featured_item_ids = {item.get("id") for item in featured_items}
    featured_cards = [
        _build_reference_chart_card(filtered, data_opd, delta_days, item_config, theme_name)
        for item_config in featured_items
    ]

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

        section_cards.append(
            html.Details(
                open=True if section_index == 0 else False,
                id=f"mnid-section-{section_index}",
                className="mnid-section-details",
                children=[
                    html.Summary(
                        children=[
                            html.Span(section["section_name"], className="mnid-section-summary-title"),
                            html.Span(f"{len(section['items'])} visuals", className="mnid-section-summary-meta"),
                        ],
                        className="mnid-section-summary",
                    ),
                    html.Div(
                        className="mnid-grid-3",
                        children=[
                            _build_reference_chart_card(filtered, data_opd, delta_days, item_config, theme_name)
                            for item_config in section_items
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
            html.Div(
                id="mnid-overview",
                className="mnid-kpi-row",
                children=[
                    _build_reference_metric_card(item["value"], item["label"], item["tone"], item["target"])
                    for item in metric_items[:6]
                ],
            ),
            html.Div(
                className="mnid-grid-2",
                children=[
                    _build_tracker(metric_items, profile),
                    html.Div(
                        className="mnid-card mnid-overview-card",
                        children=[
                            html.Div(profile.get("overview_title", "Executive Snapshot"), className="mnid-card-title"),
                            html.P(profile.get("overview_copy", ""), className="mnid-overview-copy"),
                            html.Div(
                                className="mnid-stat-list",
                                children=[
                                    html.Div(
                                        className="mnid-stat-row",
                                        children=[
                                            html.Span("KPI cards", className="mnid-stat-label"),
                                            html.Span(str(min(len(counts), 8)), className="mnid-stat-value"),
                                        ],
                                    ),
                                    html.Div(
                                        className="mnid-stat-row",
                                        children=[
                                            html.Span("Sections", className="mnid-stat-label"),
                                            html.Span(str(len(sections)), className="mnid-stat-value"),
                                        ],
                                    ),
                                    html.Div(
                                        className="mnid-stat-row",
                                        children=[
                                            html.Span("Visuals", className="mnid-stat-label"),
                                            html.Span(str(sum(len(section["items"]) for section in sections)), className="mnid-stat-value"),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(className="mnid-grid-2", children=featured_cards),
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
