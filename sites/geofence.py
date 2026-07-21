"""KAYDAN SHIELD — Service geofence portable (sans GDAL).

Le champ `Site.geofence` est stocké en JSON (compatible GeoJSON Polygon).
Ce module fournit des helpers point-in-polygon sans dépendance native, donc
utilisables en dev SQLite et en prod PostgreSQL non-GIS.

Format attendu pour `Site.geofence` :

    {
      "type": "Polygon",
      "coordinates": [
        [[lng1, lat1], [lng2, lat2], ..., [lng1, lat1]]
      ]
    }

Quand PostGIS sera adopté, on migrera ce champ vers `MultiPolygonField`
et on remplacera l'implémentation par `geofence.contains(Point(lng, lat))`
côté DB. L'API publique de ce module restera identique.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


def _polygon_from_geojson(geofence: dict):
    """Normalise un GeoJSON Polygon/MultiPolygon. Renvoie None si invalide."""
    if not geofence or not isinstance(geofence, dict):
        return None
    kind = geofence.get("type")
    coordinates = geofence.get("coordinates")
    if kind not in ("Polygon", "MultiPolygon") or not isinstance(coordinates, list):
        return None

    try:
        raw_polygons = [coordinates] if kind == "Polygon" else coordinates
        polygons = []
        for raw_polygon in raw_polygons:
            if not isinstance(raw_polygon, list) or not raw_polygon:
                return None
            rings = []
            for raw_ring in raw_polygon:
                if not isinstance(raw_ring, list) or len(raw_ring) < 3:
                    return None
                ring = []
                for coordinate in raw_ring:
                    if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
                        return None
                    ring.append((float(coordinate[0]), float(coordinate[1])))
                rings.append(ring)
            polygons.append(rings)
        return polygons or None
    except (TypeError, ValueError):
        logger.debug("Geofence invalide : %s", geofence, exc_info=True)
        return None


def _point_on_segment(point, start, end, epsilon=1e-12) -> bool:
    px, py = point
    ax, ay = start
    bx, by = end
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > epsilon:
        return False
    return (
        min(ax, bx) - epsilon <= px <= max(ax, bx) + epsilon
        and min(ay, by) - epsilon <= py <= max(ay, by) + epsilon
    )


def _ring_contains(ring, point) -> bool:
    """Ray casting, bord inclus."""
    inside = False
    previous = ring[-1]
    for current in ring:
        if _point_on_segment(point, previous, current):
            return True
        x1, y1 = previous
        x2, y2 = current
        px, py = point
        if (y1 > py) != (y2 > py):
            x_intersection = (x2 - x1) * (py - y1) / (y2 - y1) + x1
            if px < x_intersection:
                inside = not inside
        previous = current
    return inside


def _polygon_contains(rings, point) -> bool:
    if not _ring_contains(rings[0], point):
        return False
    return not any(_ring_contains(hole, point) for hole in rings[1:])


def site_contains_point(site, latitude, longitude) -> Optional[bool]:
    """Vérifie qu'un point (lat, lng) est dans le polygone du site.

    Retourne :
        True   point dans le polygone
        False  point hors polygone
        None   pas de polygone configuré (ne pas lever d'alerte)
    """
    if latitude is None or longitude is None:
        return None
    polygons = _polygon_from_geojson(site.geofence)
    if polygons is None:
        return None
    try:
        point = (float(longitude), float(latitude))
        return any(_polygon_contains(rings, point) for rings in polygons)
    except (TypeError, ValueError, IndexError):
        logger.exception("Échec point-in-polygon site=%s", site.id)
        return None


def closest_site(sites: Iterable, latitude, longitude):
    """Retourne le site dont le centroïde est le plus proche (haversine simple).
    Utilisé pour deviner le site quand un terminal n'est pas associé.
    """
    if latitude is None or longitude is None:
        return None
    import math
    best, best_dist = None, float("inf")
    for s in sites:
        if s.latitude is None or s.longitude is None:
            continue
        # haversine approximée — assez précis sur 100km
        lat1, lng1 = math.radians(float(latitude)), math.radians(float(longitude))
        lat2, lng2 = math.radians(float(s.latitude)), math.radians(float(s.longitude))
        dlat, dlng = lat2 - lat1, lng2 - lng1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
        d = 2 * math.asin(math.sqrt(a)) * 6371_000  # m
        if d < best_dist:
            best_dist, best = d, s
    return best
