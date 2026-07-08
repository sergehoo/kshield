import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { sitesService, devicesService } from "@/services";
import { List, Map as MapIcon, MapPin, Cpu, Users } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import "leaflet/dist/leaflet.css";

/**
 * Vue carte Leaflet des chantiers.
 *
 * Attend que chaque site expose `lat` et `lng` (ou `latitude`/`longitude`).
 * Les sites sans coordonnées sont listés en side-panel avec un bouton "géocoder"
 * (à implémenter côté back plus tard).
 *
 * Leaflet est chargé dynamiquement pour ne pas alourdir le bundle des autres pages.
 */
export function SitesMapPage() {
  const navigate = useNavigate();
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const markersLayer = useRef<any>(null);
  const [selected, setSelected] = useState<any | null>(null);

  const { data: sites, isLoading } = useQuery({
    queryKey: ["sites", "map"],
    queryFn: async () => (await sitesService.list({ page_size: 500 })).data,
  });

  // Compte terminaux par site pour le popup
  const { data: devices } = useQuery({
    queryKey: ["devices", "for-map"],
    queryFn: async () => (await devicesService.list({ page_size: 500 })).data,
  });

  const devicesBySite = (devices?.results || []).reduce<Record<string, number>>((acc, d: any) => {
    const sid = typeof d.site === "object" ? d.site?.id : d.site;
    if (sid) acc[String(sid)] = (acc[String(sid)] || 0) + 1;
    return acc;
  }, {});

  // Init Leaflet — dynamic import pour lazy load
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;
    let cancelled = false;

    (async () => {
      const L = (await import("leaflet")).default;
      if (cancelled || !mapContainer.current) return;

      // Centre par défaut : Abidjan
      const map = L.map(mapContainer.current, {
        zoomControl: true,
        attributionControl: true,
      }).setView([5.348, -4.027], 11);

      L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        { maxZoom: 19, attribution: "© OpenStreetMap" },
      ).addTo(map);

      markersLayer.current = L.layerGroup().addTo(map);
      mapRef.current = map;

      // Force resize après montage (fix Leaflet qui affiche mal si conteneur pas prêt)
      setTimeout(() => map.invalidateSize(), 100);
    })();

    return () => {
      cancelled = true;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  // Update markers quand sites changent
  useEffect(() => {
    if (!mapRef.current || !markersLayer.current || !sites?.results) return;
    let cancelled = false;

    (async () => {
      const L = (await import("leaflet")).default;
      if (cancelled) return;

      markersLayer.current.clearLayers();
      const bounds: any[] = [];

      sites.results.forEach((s: any) => {
        const lat = Number(s.lat ?? s.latitude);
        const lng = Number(s.lng ?? s.longitude);
        if (Number.isFinite(lat) && Number.isFinite(lng)) {
          const marker = L.marker([lat, lng], {
            icon: L.divIcon({
              className: "kshield-marker",
              html: `<div style="
                background: #f97316; color: white; width: 28px; height: 28px;
                border-radius: 50%; display: grid; place-items: center;
                border: 3px solid rgba(255,255,255,0.9); box-shadow: 0 4px 12px rgba(0,0,0,0.4);
                font-weight: 700; font-size: 11px;">
                ${(s.name || "").slice(0, 1).toUpperCase()}
              </div>`,
              iconSize: [28, 28],
              iconAnchor: [14, 14],
            }),
          });
          const deviceCount = devicesBySite[String(s.id)] || 0;
          marker.bindPopup(`
            <div style="min-width:180px">
              <div style="font-weight:600;font-size:13px">${s.name}</div>
              ${s.address ? `<div style="color:#666;font-size:11px;margin-top:2px">${s.address}</div>` : ""}
              <div style="margin-top:6px;font-size:11px">
                🖥️ ${deviceCount} équipement(s)
              </div>
              <a href="/sites/${s.id}" style="display:inline-block;margin-top:6px;color:#f97316;font-size:11px;font-weight:600">
                Ouvrir la fiche →
              </a>
            </div>
          `);
          marker.on("click", () => setSelected(s));
          marker.addTo(markersLayer.current);
          bounds.push([lat, lng]);
        }
      });

      if (bounds.length > 0) {
        mapRef.current.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sites, devicesBySite]);

  const sitesWithoutCoords = (sites?.results || []).filter(
    (s: any) => !Number.isFinite(Number(s.lat ?? s.latitude)),
  );

  return (
    <div>
      <PageHeader
        title="Carte des chantiers"
        subtitle={`${sites?.count ?? 0} chantiers · ${sitesWithoutCoords.length} sans coordonnées GPS`}
        actions={
          <div className="flex gap-2">
            <Link to="/sites" className="btn-ghost inline-flex">
              <List className="w-4 h-4" /> Vue liste
            </Link>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Carte */}
        <Card padded={false} className="lg:col-span-3">
          <div
            ref={mapContainer}
            className="w-full h-[70vh] rounded-2xl overflow-hidden"
            style={{ background: "rgb(var(--c-surface-soft))" }}
          />
        </Card>

        {/* Side panel : sites sans coordonnées + détail sélection */}
        <div className="space-y-4">
          {selected && (
            <Card
              title={
                <span className="flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-brand-500" /> {selected.name}
                </span>
              }
              actions={
                <button
                  onClick={() => setSelected(null)}
                  className="text-ink-soft hover:text-ink text-xs"
                >
                  ✕
                </button>
              }
            >
              <div className="space-y-2 text-sm">
                {selected.address && (
                  <div className="text-xs text-ink-muted">{selected.address}</div>
                )}
                <div className="flex items-center gap-2 text-xs">
                  <Cpu className="w-3.5 h-3.5 text-info" />
                  {devicesBySite[String(selected.id)] || 0} équipements
                </div>
                <Button
                  size="sm"
                  className="w-full justify-center mt-3"
                  onClick={() => navigate(`/sites/${selected.id}`)}
                >
                  Ouvrir la fiche
                </Button>
              </div>
            </Card>
          )}

          {sitesWithoutCoords.length > 0 && (
            <Card
              title={
                <span className="flex items-center gap-2 text-xs">
                  <MapPin className="w-3.5 h-3.5 text-warn" /> Sans coordonnées
                </span>
              }
              subtitle={`${sitesWithoutCoords.length} site(s) à géolocaliser`}
              padded={false}
            >
              <ul className="max-h-80 overflow-y-auto divide-y divide-surface-border/50">
                {sitesWithoutCoords.slice(0, 20).map((s: any) => (
                  <li key={s.id} className="px-4 py-2 flex items-center justify-between">
                    <Link
                      to={`/sites/${s.id}`}
                      className="text-xs text-ink hover:text-brand-400 truncate"
                    >
                      {s.name}
                    </Link>
                    <Badge tone="warn">Géo ?</Badge>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {isLoading && (
            <Card>
              <div className="text-xs text-ink-muted text-center py-2">
                Chargement des chantiers…
              </div>
            </Card>
          )}
        </div>
      </div>

      <style>{`
        .kshield-marker { background: transparent !important; border: none !important; }
        .leaflet-popup-content-wrapper {
          border-radius: 12px;
          background: rgb(var(--c-surface-card));
          color: rgb(var(--c-ink));
        }
        .leaflet-popup-tip { background: rgb(var(--c-surface-card)); }
        .dark .leaflet-container { background: #1a1f2e; }
        .dark .leaflet-tile { filter: brightness(0.9) contrast(1.05) hue-rotate(180deg) invert(0.85); }
      `}</style>
    </div>
  );
}
