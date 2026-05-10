"""KAYDAN SHIELD — Service geofence portable (sans GDAL).

Le champ `Site.geofence` est stocké en JSON (compatible GeoJSON Polygon).
Ce module fournit des helpers point-in-polygon basés sur Shapely, qui
fonctionne sans GDAL/PostGIS — donc utilisable en dev SQLite et en prod
PostgreSQL non-GIS.

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
    """Convertit un GeoJSON Polygon en shapely Polygon. Renvoie None si invalide."""
    if not geofence or not isinstance(geofence, dict):
        return None
    if geofence.get("type") not in ("Polygon", "MultiPolygon"):
        return None
    try:
        from shapely.geometry import MultiPolygon, Polygon, shape
        return shape(geofence)
    except Exception:
        logger.debug("Geofence invalide : %s", geofence, exc_info=True)
        return None


def site_contains_point(site, latitude, longitude) -> Optional[bool]:
    """Vérifie qu'un point (lat, lng) est dans le polygone du site.

    Retourne :
        True   point dans le polygone
        False  point hors polygone
        None   pas de polygone configuré (ne pas lever d'alerte)
    """
    if latitude is None or longitude is None:
        return None
    poly = _polygon_from_geojson(site.geofence)
    if poly is None:
        return None
    try:
        from shapely.geometry import Point
        return bool(poly.contains(Point(float(longitude), float(latitude))))
    except Exception:
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
