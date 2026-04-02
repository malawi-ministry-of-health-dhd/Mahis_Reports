"""MNID geospatial file helpers."""

import hashlib
import json
import math
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


def _iter_polygon_rings(geojson):
    if not geojson:
        return
    for feature in geojson.get('features', []):
        props = feature.get('properties', {})
        district = props.get('shapeName')
        geom = feature.get('geometry', {})
        gtype = geom.get('type')
        if gtype == 'Polygon':
            polygons = [geom.get('coordinates', [])]
        elif gtype == 'MultiPolygon':
            polygons = geom.get('coordinates', [])
        else:
            polygons = []
        for polygon in polygons:
            if not polygon:
                continue
            ring = polygon[0]
            if ring and district:
                yield district, ring


def build_geo_reference(geojson):
    """Return normalized district rings, centroids, and map bounds for MNID plotting."""
    if not geojson:
        return None

    bounds_lon = []
    bounds_lat = []
    district_points = {}
    raw_rings = []

    for district, ring in _iter_polygon_rings(geojson):
        raw_rings.append((district, ring))
        district_points.setdefault(district, []).extend(ring)
        bounds_lon.extend(pt[0] for pt in ring)
        bounds_lat.extend(pt[1] for pt in ring)

    if not bounds_lon or not bounds_lat:
        return None

    min_lon, max_lon = min(bounds_lon), max(bounds_lon)
    min_lat, max_lat = min(bounds_lat), max(bounds_lat)
    lon_span = max(max_lon - min_lon, 1e-6)
    lat_span = max(max_lat - min_lat, 1e-6)
    y_scale = lat_span / lon_span

    def norm(lon, lat):
        x = (lon - min_lon) / lon_span
        y = (lat - min_lat) / lat_span * y_scale
        return x, y

    district_rings = {}
    district_centroids = {}
    for district, pts in district_points.items():
        norm_pts = [norm(lon, lat) for lon, lat in pts]
        district_centroids[district] = (
            sum(p[0] for p in norm_pts) / len(norm_pts),
            sum(p[1] for p in norm_pts) / len(norm_pts),
        )
    for district, ring in raw_rings:
        district_rings.setdefault(district, []).append([norm(lon, lat) for lon, lat in ring])

    return {
        'min_lon': min_lon,
        'max_lon': max_lon,
        'min_lat': min_lat,
        'max_lat': max_lat,
        'y_scale': y_scale,
        'district_rings': district_rings,
        'district_centroids': district_centroids,
    }


def derive_facility_positions(facilities_by_district, district_centroids):
    """Create deterministic facility marker positions from district centroids.

    This avoids hardcoded facility coordinates while still giving each facility
    a stable position on the MNID map.
    """
    positions = {}
    for district, facility_codes in (facilities_by_district or {}).items():
        center = district_centroids.get(district)
        if not center:
            continue
        codes = sorted(str(code) for code in facility_codes if str(code).strip())
        if not codes:
            continue
        cx, cy = center
        count = len(codes)
        for idx, code in enumerate(codes):
            seed = int(hashlib.md5(code.encode('utf-8')).hexdigest()[:8], 16)
            angle = ((seed % 360) / 360.0) * 2 * math.pi
            ring = 0.012 + 0.008 * (idx % 3)
            spread = min(0.045, ring + (0.006 * max(count - 1, 0)))
            x = cx + math.cos(angle) * spread
            y = cy + math.sin(angle) * spread
            positions[code] = (min(max(x, 0.02), 0.98), min(max(y, 0.02), max(district_centroids.values(), key=lambda v: v[1])[1]))
    return positions
