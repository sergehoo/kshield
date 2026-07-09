/**
 * KAYDAN SHIELD — Découverte réseau multi-protocole (Vague 7).
 *
 * Lance un scan combiné ONVIF + mDNS + SSDP + ARP + SNMP.
 * Affiche les équipements mergés par IP avec vendor déviné et bouton "Adopter".
 */
import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  Radar, PlayCircle, CheckCircle2, Cable, Cpu, Camera, DoorClosed,
  ShieldCheck, Wifi, RefreshCw,
} from "lucide-react";
import toast from "react-hot-toast";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { StatsRow } from "@/components/StatsRow";
import { discoveryService, DiscoveredNetDevice } from "@/services/enrollment";
import { cn } from "@/lib/cn";

const PROTOCOLS = [
  { key: "onvif", label: "ONVIF", desc: "Caméras IP + terminaux ONVIF" },
  { key: "mdns",  label: "mDNS",  desc: "Bonjour / _tcp.local." },
  { key: "ssdp",  label: "SSDP",  desc: "UPnP multicast" },
  { key: "arp",   label: "ARP",   desc: "Table ARP locale (Linux)" },
  { key: "snmp",  label: "SNMP",  desc: "sysDescr / sysName (nécessite plage IP)" },
];

const HINT_ICONS: Record<string, any> = {
  camera:        <Camera className="w-3.5 h-3.5" />,
  door_lock:     <DoorClosed className="w-3.5 h-3.5" />,
  face_terminal: <Cpu className="w-3.5 h-3.5" />,
  portique:      <ShieldCheck className="w-3.5 h-3.5" />,
  gateway:       <Cable className="w-3.5 h-3.5" />,
};

export function DiscoveryPage() {
  const [selected, setSelected] = useState<string[]>(["onvif", "mdns", "ssdp", "arp"]);
  const [ipRange, setIpRange] = useState("");
  const [timeout, setTimeout] = useState(4);
  const [results, setResults] = useState<DiscoveredNetDevice[]>([]);

  const scanMut = useMutation({
    mutationFn: () => discoveryService.scan({
      protocols: selected,
      ip_range: ipRange || undefined,
      timeout,
    }),
    onSuccess: (r) => {
      setResults(r.data.devices);
      toast.success(`${r.data.count} équipement${r.data.count > 1 ? "s détectés" : " détecté"}`);
    },
    onError: (e: any) => {
      toast.error(e?.response?.data?.error || "Scan impossible");
    },
  });

  const stats = useMemo(() => ({
    total: results.length,
    unknown: results.filter((d) => !d.already_known).length,
    known: results.filter((d) => d.already_known).length,
    with_vendor: results.filter((d) => d.vendor).length,
  }), [results]);

  const toggleProtocol = (key: string) => {
    setSelected((s) => s.includes(key)
      ? s.filter((k) => k !== key)
      : [...s, key]);
  };

  return (
    <div>
      <PageHeader
        title="Découverte réseau"
        subtitle="Scan multi-protocole ONVIF · mDNS · SSDP · ARP · SNMP"
        actions={
          <Button leftIcon={<PlayCircle className="w-4 h-4" />}
                  onClick={() => scanMut.mutate()}
                  loading={scanMut.isPending}
                  disabled={selected.length === 0}>
            Lancer le scan
          </Button>
        }
      />

      {/* Setup */}
      <Card padded>
        <div className="space-y-3">
          <div>
            <div className="text-xs font-medium text-ink-muted mb-2">
              Protocoles ({selected.length}/{PROTOCOLS.length})
            </div>
            <div className="flex flex-wrap gap-2">
              {PROTOCOLS.map((p) => (
                <button key={p.key}
                        onClick={() => toggleProtocol(p.key)}
                        className={cn(
                          "px-3 py-1.5 text-xs rounded-md border transition",
                          selected.includes(p.key)
                            ? "border-brand-500 bg-brand-500/10 text-brand-700"
                            : "border-surface-border hover:bg-surface-soft",
                        )}
                        title={p.desc}>
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Input label="Plage IP (SNMP+TCP)"
                   placeholder="192.168.1.0/24 ou 192.168.1.1-254"
                   value={ipRange}
                   onChange={(e) => setIpRange(e.target.value)} />
            <label className="block">
              <span className="text-xs font-medium text-ink-muted">Timeout par protocole (s)</span>
              <input type="number" min={1} max={30} value={timeout}
                     onChange={(e) => setTimeout(Number(e.target.value))}
                     className="field w-full mt-1.5" />
            </label>
          </div>
        </div>
      </Card>

      {/* Stats */}
      {results.length > 0 && (
        <>
          <StatsRow stats={[
            { label: "Détectés", value: stats.total,
              icon: <Radar className="w-4 h-4" />, tone: "brand" },
            { label: "Nouveaux", value: stats.unknown,
              icon: <PlayCircle className="w-4 h-4" />, tone: "info" },
            { label: "Déjà connus", value: stats.known,
              icon: <CheckCircle2 className="w-4 h-4" />, tone: "ok" },
            { label: "Vendor identifié", value: stats.with_vendor,
              icon: <Cpu className="w-4 h-4" />, tone: "info" },
          ]} />

          {/* Table résultats */}
          <Card padded={false}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-surface-soft/60 text-xs uppercase tracking-wider text-ink-muted">
                  <tr>
                    <th className="p-2 text-left">IP</th>
                    <th className="p-2 text-left">MAC</th>
                    <th className="p-2 text-left">Vendor</th>
                    <th className="p-2 text-left">Type</th>
                    <th className="p-2 text-left">Protocoles</th>
                    <th className="p-2 text-left">Hostname</th>
                    <th className="p-2 text-right">État</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {results.map((d) => (
                    <tr key={d.ip} className="hover:bg-surface-soft/40">
                      <td className="p-2 font-mono text-xs">{d.ip}</td>
                      <td className="p-2 font-mono text-xs text-ink-muted">{d.mac || "—"}</td>
                      <td className="p-2">
                        {d.vendor ? (
                          <Badge tone="info">{d.vendor}</Badge>
                        ) : <span className="text-ink-muted text-xs">—</span>}
                      </td>
                      <td className="p-2">
                        {d.device_type_hint ? (
                          <span className="inline-flex items-center gap-1 text-xs text-ink">
                            {HINT_ICONS[d.device_type_hint]}
                            {d.device_type_hint}
                          </span>
                        ) : <span className="text-ink-muted text-xs">—</span>}
                      </td>
                      <td className="p-2">
                        <div className="flex flex-wrap gap-0.5">
                          {d.protocols_detected.map((p) => (
                            <span key={p}
                                  className="text-[10px] font-mono bg-surface-soft border border-surface-border rounded px-1">
                              {p}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="p-2 text-xs text-ink-muted">{d.hostname || "—"}</td>
                      <td className="p-2 text-right">
                        {d.already_known ? (
                          <Badge tone="muted">Déjà en base</Badge>
                        ) : (
                          <Badge tone="ok">Nouveau</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      {results.length === 0 && !scanMut.isPending && (
        <Card padded>
          <div className="text-center py-8 text-ink-muted text-sm">
            <Radar className="w-8 h-8 mx-auto mb-2 opacity-30" />
            Lance un scan pour voir les équipements du LAN
          </div>
        </Card>
      )}
    </div>
  );
}
