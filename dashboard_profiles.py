"""Configuration registry for dashboards that opt into premium layouts."""

DASHBOARD_PROFILES = {
    "Maternal and Child Health": {
        "layout": "premium",
        "variant": "mnid_light",
        "theme": "premium_mch",
        "brand": "Maternal & Child",
        "kicker": "Strategic Overview",
        "subtitle": (
            "A reusable clinical dashboard shell for maternal, newborn, labour, and postnatal monitoring."
        ),
        "overview_title": "Key maternal and child indicators at a glance",
        "overview_copy": (
            "This layout separates executive KPIs from clinical detail so programme teams, clinicians, "
            "and donor reviewers can assess service coverage, intervention quality, and referral burden quickly."
        ),
        "section_chip_label": "Focus Areas",
        "topbar_pills": [
            {"label": "M-NID view", "tone": "blue"},
            {"label": "Clinical quality", "tone": "green"},
            {"label": "Facility dashboard", "tone": "amber"},
        ],
        "tracker_title": "Priority intervention coverage tracker",
        "tracker_target": 80,
    }
}
