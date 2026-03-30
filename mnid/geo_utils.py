"""MNID geospatial file helpers."""

import json
import os

MALAWI_DISTRICTS_GEOJSON = os.path.join('data', 'geo', 'malawi_districts.geojson')


def load_malawi_district_geojson():
    """Load Malawi district boundaries if a local GeoJSON file is available."""
    if not os.path.exists(MALAWI_DISTRICTS_GEOJSON):
        return None
    try:
        with open(MALAWI_DISTRICTS_GEOJSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None
