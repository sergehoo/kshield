/**
 * KAYDAN SHIELD — Page Drivers (Vague 7).
 *
 * Affiche tous les drivers vendor chargés côté serveur avec leurs capabilities
 * et modèles supportés. Chaque driver peut être testé sur un équipement précis.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Cpu, Cable, Package, Zap, ShieldCheck, ChevronRight, Radio,
} from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { StatsRow } from "@/components/StatsRow";
import { driversService } from "@/services/enrollment";
import { cn } from "@/lib/cn";

const CAPABILITY_ICONS: Record<string, any> = {
  ping:              <Zap className="w-3 h-3" />,
  discover:          <Radio className="w-3 h-3" />,
  get_info:          <Package className="w-3 h-3" />,
  get_status:        <ShieldCheck className="w-3 h-3" />,
  read_events:       <Cable className="w-3 h-3" />,
  enroll_rfid:       <Zap className="w-3 h-3" />,
  enroll_face:       <Zap className="w-3 h-3" />,
  enroll_fingerprint:<Zap className="w-3 h-3" />,
  sync_attendances:  <Cable className="w-3 h-3" />,
  restart:           <ChevronRight className="w-3 h-3" />,
  door_unlock:       <ChevronRight className="w-3 h-3" />,
  push_user:         <Cable className="w-3 h-3" />,
  update_firmware:   <ChevronRight className="w-3 h-3" />,
};

const CAP_LABELS: Record<string, string> = {
  ping: "Ping", discover: "Découverte", get_info: "Info",
  get_status: "Statut", read_events: "Événements",
  enroll_rfid: "Enrôlement RFID", enroll_face: "Enrôlement Face",
  enroll_fingerprint: "Enrôlement Empreinte",
  sync_attendances: "Sync pointages", restart: "Redémarrage",
  door_unlock: "Ouverture porte", push_user: "Push user",
  update_firmware: "Update firmware",
};

export function DriversPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["drivers-list"],
    queryFn: async () => (await driversService.list()).data,
  });

  const drivers = data?.drivers || [];
  const totalCaps = drivers.reduce((s, d) => s + (d.capabilities?.length || 0), 0);

  return (
    <div>
      <PageHeader
        title="Drivers"
        subtitle={`${drivers.length} plugin${drivers.length > 1 ? "s" : ""} constructeur chargé${drivers.length > 1 ? "s" : ""}`}
      />

      <StatsRow stats={[
        { label: "Drivers chargés", value: drivers.length,
          icon: <Cpu className="w-4 h-4" />, tone: "brand" },
        { label: "Capabilities totales", value: totalCaps,
          icon: <Zap className="w-4 h-4" />, tone: "info" },
        { label: "Vendors supportés", value: drivers.length,
          icon: <Package className="w-4 h-4" />, tone: "ok" },
      ]} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Liste */}
        <div className="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-3">
          {isLoading && (
            <div className="col-span-2 text-center py-10 text-ink-muted">
              Chargement des drivers…
            </div>
          )}
          {drivers.map((d) => (
            <button
              key={d.vendor}
              onClick={() => setSelected(d.vendor)}
              className={cn(
                "text-left p-3 rounded-lg border transition",
                selected === d.vendor
                  ? "border-brand-500 bg-brand-500/5"
                  : "border-surface-border hover:border-brand-500/30 hover:bg-surface-soft",
              )}
            >
              <div className="flex items-center gap-2">
                <div className={cn(
                  "w-9 h-9 rounded-lg grid place-items-center",
                  "bg-info/10 text-info",
                )}>
                  <Cpu className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-ink capitalize">
                    {d.vendor}
                  </div>
                  <code className="text-xs text-ink-soft font-mono truncate block">
                    {d.class}
                  </code>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {d.capabilities.slice(0, 4).map((c) => (
                  <span key={c}
                        className="inline-flex items-center gap-0.5 text-[10px] text-ink-muted bg-surface-soft border border-surface-border rounded px-1.5 py-0.5">
                    {CAPABILITY_ICONS[c]}
                    {CAP_LABELS[c] || c}
                  </span>
                ))}
                {d.capabilities.length > 4 && (
                  <span className="text-[10px] text-ink-muted">
                    +{d.capabilities.length - 4}
                  </span>
                )}
              </div>
              {d.supported_models.length > 0 && (
                <div className="mt-1 text-[10px] text-ink-muted truncate">
                  Modèles : {d.supported_models.slice(0, 3).join(", ")}
                  {d.supported_models.length > 3 && "…"}
                </div>
              )}
            </button>
          ))}
        </div>

        {/* Panneau détails */}
        <div>
          {selected ? (
            <DriverDetails drivers={drivers} vendor={selected} />
          ) : (
            <Card padded>
              <div className="text-center text-ink-muted text-sm py-8">
                Sélectionne un driver pour voir le détail
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function DriverDetails({ drivers, vendor }: {
  drivers: any[]; vendor: string;
}) {
  const d = drivers.find((x) => x.vendor === vendor);
  if (!d) return null;

  return (
    <Card padded>
      <div className="text-lg font-semibold text-ink capitalize mb-1">{d.vendor}</div>
      <code className="text-xs text-ink-muted font-mono block mb-3">
        {d.module}.{d.class}
      </code>

      <div className="mb-3">
        <div className="text-xs uppercase tracking-wider text-ink-muted mb-1.5">
          Capabilities ({d.capabilities.length})
        </div>
        <div className="flex flex-wrap gap-1">
          {d.capabilities.map((c: string) => (
            <Badge key={c} tone="info">
              {CAP_LABELS[c] || c}
            </Badge>
          ))}
        </div>
      </div>

      <div>
        <div className="text-xs uppercase tracking-wider text-ink-muted mb-1.5">
          Modèles supportés ({d.supported_models.length})
        </div>
        {d.supported_models.length > 0 ? (
          <ul className="text-xs text-ink space-y-0.5">
            {d.supported_models.map((m: string) => (
              <li key={m} className="font-mono">· {m}</li>
            ))}
          </ul>
        ) : (
          <div className="text-xs text-ink-muted italic">
            Aucun modèle spécifique — s'applique en fallback
          </div>
        )}
      </div>
    </Card>
  );
}
