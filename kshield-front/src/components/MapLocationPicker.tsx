/**
 * MapLocationPicker — sélecteur de position GPS sur carte Leaflet.
 *
 * Fonctionnalités :
 *  - Carte interactive (OpenStreetMap tiles).
 *  - Marqueur draggable pour affiner.
 *  - Clic sur la carte = place le marqueur.
 *  - Champ de recherche d'adresse (Nominatim / OpenStreetMap).
 *  - Bouton "ma position" (Geolocation API).
 *  - Champs lat/lng manuels synchronisés.
 *  - Callback onChange({ latitude, longitude, address? }).
 *
 * Défaut sur Abidjan (Côte d'Ivoire) : 5.348, -4.027.
 *
 * Aucune clé API requise — Nominatim est gratuit avec throttle 1 req/s.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { Search, MapPin, Crosshair, Loader2 } from "lucide-react";
import "leaflet/dist/leaflet.css";

export interface MapLocation {
  latitude: number;
  longitude: number;
  address?: string;
}

interface Props {
  latitude?: number | string | null;
  longitude?: number | string | null;
  onChange: (loc: MapLocation) => void;
  height?: number;
  /** Coordonnées de repli si aucune valeur fournie (défaut : Abidjan). */
  defaultLat?: number;
  defaultLng?: number;
  defaultZoom?: number;
}

// Icône marker — Leaflet ne trouve pas ses icônes par défaut avec les bundlers.
// On utilise une icône SVG inline pour éviter le problème de path.
const MARKER_ICON_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" width="34" height="46" viewBox="0 0 34 46">
  <path d="M17 0C7.6 0 0 7.4 0 16.7 0 27.8 15.4 44 16.1 44.7c.5.5 1.3.5 1.8 0C18.6 44 34 27.8 34 16.7 34 7.4 26.4 0 17 0z"
        fill="#0f172a"/>
  <circle cx="17" cy="16.7" r="6" fill="#fff"/>
</svg>
`;

export function MapLocationPicker({
  latitude, longitude, onChange,
  height = 340,
  defaultLat = 5.348, defaultLng = -4.027, defaultZoom = 12,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const markerRef = useRef<any>(null);
  const LRef = useRef<any>(null);

  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);
  const [locating, setLocating] = useState(false);
  const [manualLat, setManualLat] = useState<string>(
    latitude != null ? String(latitude) : "",
  );
  const [manualLng, setManualLng] = useState<string>(
    longitude != null ? String(longitude) : "",
  );

  const emit = useCallback((lat: number, lng: number, address?: string) => {
    setManualLat(lat.toFixed(6));
    setManualLng(lng.toFixed(6));
    onChange({ latitude: lat, longitude: lng, address });
  }, [onChange]);

  // Init map (dynamic import to lazy-load Leaflet)
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    let cancelled = false;

    (async () => {
      const L = (await import("leaflet")).default;
      if (cancelled || !containerRef.current) return;
      LRef.current = L;

      const startLat = latitude != null && !Number.isNaN(Number(latitude))
        ? Number(latitude) : defaultLat;
      const startLng = longitude != null && !Number.isNaN(Number(longitude))
        ? Number(longitude) : defaultLng;

      const map = L.map(containerRef.current, {
        zoomControl: true,
        attributionControl: true,
      }).setView([startLat, startLng], defaultZoom);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap",
      }).addTo(map);

      const icon = L.divIcon({
        html: MARKER_ICON_SVG,
        className: "kshield-marker",
        iconSize: [34, 46],
        iconAnchor: [17, 46],
      });

      const marker = L.marker([startLat, startLng], {
        draggable: true, icon,
      }).addTo(map);

      marker.on("dragend", () => {
        const p = marker.getLatLng();
        emit(p.lat, p.lng);
      });

      map.on("click", (e: any) => {
        marker.setLatLng(e.latlng);
        emit(e.latlng.lat, e.latlng.lng);
      });

      mapRef.current = map;
      markerRef.current = marker;
    })();

    return () => {
      cancelled = true;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
        markerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync des props externes -> map (utile en mode édition)
  useEffect(() => {
    if (!mapRef.current || !markerRef.current) return;
    const lat = Number(latitude), lng = Number(longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    markerRef.current.setLatLng([lat, lng]);
    setManualLat(String(latitude ?? ""));
    setManualLng(String(longitude ?? ""));
  }, [latitude, longitude]);

  // ─── Recherche adresse (Nominatim) ────────────────────────────
  const doSearch = useCallback(async () => {
    const q = query.trim();
    if (q.length < 3) return;
    setSearching(true);
    try {
      const params = new URLSearchParams({
        q, format: "jsonv2", limit: "6", "accept-language": "fr",
      });
      const r = await fetch(
        `https://nominatim.openstreetmap.org/search?${params.toString()}`,
        { headers: { "Accept": "application/json" } },
      );
      const data = await r.json();
      setSuggestions(Array.isArray(data) ? data : []);
    } catch (err) {
      setSuggestions([]);
    } finally {
      setSearching(false);
    }
  }, [query]);

  const pickSuggestion = (s: any) => {
    const lat = Number(s.lat), lng = Number(s.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    if (mapRef.current && markerRef.current) {
      mapRef.current.setView([lat, lng], 16);
      markerRef.current.setLatLng([lat, lng]);
    }
    emit(lat, lng, s.display_name);
    setSuggestions([]);
    setQuery(s.display_name);
  };

  // ─── Géolocalisation navigateur ──────────────────────────────
  const useMyLocation = () => {
    if (!("geolocation" in navigator)) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude: lat, longitude: lng } = pos.coords;
        if (mapRef.current && markerRef.current) {
          mapRef.current.setView([lat, lng], 15);
          markerRef.current.setLatLng([lat, lng]);
        }
        emit(lat, lng);
        setLocating(false);
      },
      () => setLocating(false),
      { enableHighAccuracy: true, timeout: 8000 },
    );
  };

  // ─── Saisie manuelle lat/lng ─────────────────────────────────
  const commitManual = () => {
    const lat = Number(manualLat), lng = Number(manualLng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    if (mapRef.current && markerRef.current) {
      mapRef.current.setView([lat, lng], 15);
      markerRef.current.setLatLng([lat, lng]);
    }
    emit(lat, lng);
  };

  return (
    <div className="space-y-2">
      {/* Barre de recherche + geolocalisation */}
      <div className="relative">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" size={14} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); doSearch(); } }}
              placeholder="Rechercher une adresse, une ville…"
              className="w-full pl-9 pr-3 py-2 text-sm rounded-xl border border-surface-border bg-surface-card text-ink"
            />
            {searching && (
              <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-ink-muted" size={14} />
            )}
          </div>
          <button
            type="button"
            onClick={doSearch}
            className="rounded-xl bg-ink text-surface-card text-sm px-4 py-2 hover:bg-ink/85"
          >
            Rechercher
          </button>
          <button
            type="button"
            onClick={useMyLocation}
            disabled={locating}
            className="inline-flex items-center gap-1.5 rounded-xl bg-surface-soft/60 text-ink text-sm px-3 py-2 hover:bg-surface-soft"
            title="Utiliser ma position"
          >
            {locating ? <Loader2 className="animate-spin" size={14} /> : <Crosshair size={14} />}
            Ma position
          </button>
        </div>

        {suggestions.length > 0 && (
          <ul className="absolute z-[500] left-0 right-0 mt-1 bg-surface-card rounded-xl shadow-lg border border-surface-border max-h-64 overflow-y-auto">
            {suggestions.map((s) => (
              <li key={`${s.place_id}`}>
                <button
                  type="button"
                  onClick={() => pickSuggestion(s)}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-surface-soft/60 flex items-start gap-2"
                >
                  <MapPin size={14} className="text-ink-muted mt-0.5 shrink-0" />
                  <span className="truncate">{s.display_name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Carte */}
      <div
        ref={containerRef}
        className="w-full rounded-2xl overflow-hidden border border-surface-border"
        style={{ height }}
      />

      {/* Champs lat/lng manuels */}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-[11px] uppercase tracking-wide text-ink-muted">Latitude *</label>
          <input
            value={manualLat}
            onChange={(e) => setManualLat(e.target.value)}
            onBlur={commitManual}
            placeholder="5.348"
            className="w-full mt-1 px-3 py-2 text-sm rounded-xl border border-surface-border bg-surface-card text-ink font-mono"
          />
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-wide text-ink-muted">Longitude *</label>
          <input
            value={manualLng}
            onChange={(e) => setManualLng(e.target.value)}
            onBlur={commitManual}
            placeholder="-4.027"
            className="w-full mt-1 px-3 py-2 text-sm rounded-xl border border-surface-border bg-surface-card text-ink font-mono"
          />
        </div>
      </div>

      <p className="text-[11px] text-ink-muted">
        Clique sur la carte, glisse le marqueur, ou saisis les coordonnées manuellement.
      </p>
    </div>
  );
}

export default MapLocationPicker;
