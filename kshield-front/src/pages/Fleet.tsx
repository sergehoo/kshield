/**
 * Fleet — Vue agrégée de tous les équipements vendors du tenant.
 *
 * Utile pour un admin qui gère 50+ sites : voir d'un coup d'œil
 * tous les targets ZKTeco/Hikvision/etc., leur état, filtrer par vendor.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Cpu, Search, Wifi, WifiOff, MapPin, Server,
  Camera, Fingerprint, KeyRound, Filter,
} from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { StatsRow } from "@/components/StatsRow";
import { edgeGatewayService } from "@/services/enrollment";
import { cn } from "@/lib/cn";
import { fmtRelative } from "@/lib/format";

const VENDOR_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  zkteco:    { label: "ZKTeco",     icon: <Fingerprint className="w-3.5 h-3.5" />, color: "text-brand-ink" },
  hikvision: { label: "Hikvision",  icon: <Camera      className="w-3.5 h-3.5" />, color: "text-red-500"   },
  suprema:   { label: "Suprema",    icon: <Fingerprint className="w-3.5 h-3.5" />, color: "text-blue-500"  },
  hid:       { label: "HID",        icon: <KeyRound    className="w-3.5 h-3.5" />, color: "text-purple-500" },
  dahua:     { label: "Dahua",      icon: <Camera      className="w-3.5 h-3.5" />, color: "text-orange-500" },
  axis:      { label: "Axis",       icon: <Camera      className="w-3.5 h-3.5" />, color: "text-cyan-500"  },
  onvif:     { label: "ONVIF",      icon: <Camera      className="w-3.5 h-3.5" />, color: "text-emerald-500" },
  generic:   { label: "Générique",  icon: <Cpu         className="w-3.5 h-3.5" />, color: "text-ink-muted" },
};

export default function FleetPage() {
  const [vendor, setVendor] = useState<string>("");
  const [status, setStatus] = useState<"" | "true" | "false">("");
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["fleet-targets", vendor, status, search],
    queryFn: async () => (await edgeGatewayService.fleetTargets({
      vendor: vendor || undefined,
      connected: status || undefined,
      search: search || undefined,
    })).data,
    refetchInterval: 30_000,
  });

  const targets = data?.targets ?? [];
  const byVendor = data?.by_vendor ?? {};
  const total = data?.count ?? 0;
  const connected = targets.filter((t) => t.connected).length;

  return (
    <div>
      <PageHeader
        icon={<Server className="w-5 h-5" />}
        title="Fleet — Équipements vendors"
        subtitle="Vue agrégée de tous les targets pilotés par vos gateways Edge"
      />

      <StatsRow
        stats={[
          { label: "Total équipements", value: total.toString(),
            tone: total > 0 ? "ok" : "warn" },
          { label: "En ligne", value: connected.toString(),
            hint: total > 0 ? `${Math.round((connected * 100) / total)}%` : "—",
            tone: connected === total ? "ok" : connected > total / 2 ? "warn" : "danger" },
          { label: "Vendors distincts",
            value: Object.keys(byVendor).length.toString(), tone: "info" },
          { label: "Hors ligne", value: (total - connected).toString(),
            tone: (total - connected) === 0 ? "ok" : "warn" },
        ]}
      />

      {/* Filtres */}
      <Card padded className="mt-3">
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[200px]">
            <label className="text-xs text-ink-muted mb-1 block">
              <Search className="w-3 h-3 inline mr-1" />
              Recherche (label, IP, serial, gateway)
            </label>
            <Input
              placeholder="192.168.1... ou 'Portail'..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="min-w-[180px]">
            <label className="text-xs text-ink-muted mb-1 block">
              <Filter className="w-3 h-3 inline mr-1" />
              Vendor
            </label>
            <select
              className="w-full h-9 border rounded px-2 text-sm"
              value={vendor}
              onChange={(e) => setVendor(e.target.value)}
            >
              <option value="">Tous ({total})</option>
              {Object.entries(byVendor).map(([v, c]) => (
                <option key={v} value={v}>
                  {VENDOR_META[v]?.label || v} ({c})
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-[140px]">
            <label className="text-xs text-ink-muted mb-1 block">État</label>
            <select
              className="w-full h-9 border rounded px-2 text-sm"
              value={status}
              onChange={(e) => setStatus(e.target.value as any)}
            >
              <option value="">Tous</option>
              <option value="true">En ligne</option>
              <option value="false">Hors ligne</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Liste des targets */}
      <Card padded className="mt-3">
        {isLoading && (
          <div className="text-center py-8 text-ink-muted">Chargement...</div>
        )}
        {!isLoading && targets.length === 0 && (
          <div className="text-center py-12 text-ink-muted">
            <Cpu className="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p className="text-sm">Aucun équipement — commencer par créer une gateway,</p>
            <p className="text-sm">puis ajouter des targets vendors dans sa modale de détail.</p>
          </div>
        )}
        {targets.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-muted border-b">
                <th className="py-2 px-2">Équipement</th>
                <th className="py-2 px-2">Vendor</th>
                <th className="py-2 px-2">IP</th>
                <th className="py-2 px-2">Gateway</th>
                <th className="py-2 px-2">Site</th>
                <th className="py-2 px-2">Events</th>
                <th className="py-2 px-2">Dernier</th>
                <th className="py-2 px-2 text-center">État</th>
              </tr>
            </thead>
            <tbody>
              {targets.map((t) => {
                const meta = VENDOR_META[t.vendor] || VENDOR_META.generic;
                return (
                  <tr key={t.id} className="border-b hover:bg-muted/40">
                    <td className="py-2 px-2 font-medium text-ink">
                      {t.label || "—"}
                      {!t.enabled && (
                        <Badge className="ml-2" tone="warn">désactivé</Badge>
                      )}
                    </td>
                    <td className="py-2 px-2">
                      <span className={cn("inline-flex items-center gap-1", meta.color)}>
                        {meta.icon} {meta.label}
                      </span>
                    </td>
                    <td className="py-2 px-2 font-mono text-xs">
                      {t.ip}{t.port > 0 ? `:${t.port}` : ""}
                    </td>
                    <td className="py-2 px-2">
                      <Link
                        to={`/edge-gateway?gateway=${t.gateway_id}`}
                        className="text-brand-ink hover:underline text-xs"
                      >
                        {t.gateway_label}
                      </Link>
                    </td>
                    <td className="py-2 px-2 text-xs text-ink-muted">
                      {t.gateway_site && (
                        <span className="inline-flex items-center gap-0.5">
                          <MapPin className="w-3 h-3" />
                          {t.gateway_site}
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-2 text-xs font-mono text-ink-muted">
                      {t.events_count}
                    </td>
                    <td className="py-2 px-2 text-xs text-ink-muted">
                      {t.last_seen_at ? fmtRelative(t.last_seen_at) : "jamais"}
                    </td>
                    <td className="py-2 px-2 text-center">
                      {t.connected ? (
                        <span className="text-success inline-flex items-center gap-0.5">
                          <Wifi className="w-3.5 h-3.5" />
                        </span>
                      ) : (
                        <span className="text-danger inline-flex items-center gap-0.5">
                          <WifiOff className="w-3.5 h-3.5" />
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
