from dash import html

from helpers.helpers import build_single_chart, create_count_from_config


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


def _build_metric_band(filtered, counts):
    metric_values = []
    accent_cycle = ["blue", "mint", "teal", "gold"]
    for index, count_config in enumerate(counts[:8]):
        value = create_count_from_config(filtered, count_config["filters"])
        metric_values.append(
            _build_metric_card(value, count_config["name"], accent_cycle[index % len(accent_cycle)])
        )
    return html.Div(metric_values, className="premium-metric-grid")


def _build_section_item(filtered, data_opd, delta_days, item_config):
    chart_type = item_config.get("type", "")
    card_class = "premium-stage-card"
    if chart_type in ["PivotTable", "CrossTab", "LineList"]:
        card_class += " premium-stage-card-wide"
    elif chart_type == "Pie":
        card_class += " premium-stage-card-compact"

    return html.Div(
        className=card_class,
        children=[
            html.Div(item_config.get("name", ""), className="premium-stage-card-title"),
            build_single_chart(filtered, data_opd, delta_days, item_config, style="premium-graph", theme_name="premium_mch"),
        ],
    )


def build_premium_dashboard(filtered, data_opd, delta_days, dashboard_config, filter_summary=None):
    counts = dashboard_config["visualization_types"]["counts"]
    sections = dashboard_config["visualization_types"]["charts"]["sections"]

    filter_summary = filter_summary or {}
    filter_chips = [
        _build_filter_chip(label, value)
        for label, value in filter_summary.items()
        if value
    ]

    section_links = [
        html.A("Overview", href="#premium-overview", className="premium-rail-item premium-rail-item-active")
    ]
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
                            _build_section_item(filtered, data_opd, delta_days, item_config)
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
                            html.Div("Maternal & Child", className="premium-rail-brand"),
                            html.Div(
                                "A high-clarity dashboard shell for maternal, newborn, and postnatal monitoring.",
                                className="premium-rail-copy",
                            ),
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
                                            html.Div("Strategic Overview", className="premium-kicker"),
                                            html.H2(
                                                dashboard_config["report_name"],
                                                className="premium-title",
                                            ),
                                            html.P(
                                                "A more deliberate dashboard composition with stronger hierarchy, cleaner cards, and section-led analysis inspired by executive health reporting.",
                                                className="premium-subtitle",
                                            ),
                                        ],
                            ),
                            html.Div(filter_chips, className="premium-filter-strip"),
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
                                            html.H3("Key maternal and child indicators at a glance", className="premium-overview-title"),
                                            html.P(
                                                "This reusable shell separates strategic KPIs from the detailed analysis area, giving donors and clinicians a faster read on service performance.",
                                                className="premium-overview-text",
                                            ),
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
