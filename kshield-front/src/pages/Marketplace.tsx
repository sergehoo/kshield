/**
 * KAYDAN SHIELD — Plugin Marketplace (Vague 8).
 *
 * Catalogue des drivers vendor disponibles + upload d'un plugin custom (ZIP).
 */
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Package, CheckCircle2, Clock, Upload, Cpu, ShieldCheck, Cable,
} from "lucide-react";
import toast from "react-hot-toast";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { StatsRow } from "@/components/StatsRow";
import { marketplaceService } from "@/services/enrollment";
import { cn } from "@/lib/cn";

export function MarketplacePage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  const { data } = useQuery({
    queryKey: ["marketplace-plugins"],
    queryFn: async () => (await marketplaceService.list()).data,
  });

  const uploadMut = useMutation({
    mutationFn: (file: File) => marketplaceService.upload(file),
    onSuccess: (r: any) => {
      toast.success(r?.data?.message || "Plugin uploadé");
      qc.invalidateQueries({ queryKey: ["marketplace-plugins"] });
      if (fileRef.current) fileRef.current.value = "";
    },
    onError: (e: any) =>
      toast.error(e?.response?.data?.error || "Upload impossible"),
  });

  const plugins = data?.plugins || [];
  const installed = plugins.filter((p) => p.installed).length;
  const available = plugins.filter((p) => !p.installed && !p.coming_soon).length;
  const coming = plugins.filter((p) => p.coming_soon).length;

  return (
    <div>
      <PageHeader
        title="Marketplace de plugins"
        subtitle="Drivers constructeurs — extensible sans modifier le cœur de Kaydan Shield"
        actions={
          <>
            <input ref={fileRef} type="file" accept=".zip,.kshield-driver"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) uploadMut.mutate(f);
                    }} />
            <Button leftIcon={<Upload className="w-4 h-4" />}
                    onClick={() => fileRef.current?.click()}
                    loading={uploadMut.isPending}>
              Uploader un plugin
            </Button>
          </>
        }
      />

      <StatsRow stats={[
        { label: "Installés", value: installed, icon: <CheckCircle2 className="w-4 h-4" />, tone: "ok" },
        { label: "Disponibles", value: available, icon: <Package className="w-4 h-4" />, tone: "brand" },
        { label: "À venir", value: coming, icon: <Clock className="w-4 h-4" />, tone: "muted" },
        { label: "Total", value: plugins.length, icon: <Cpu className="w-4 h-4" />, tone: "info" },
      ]} />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {plugins.map((p) => (
          <div key={p.vendor}
               className={cn("rounded-lg border p-3 flex flex-col",
                              p.installed
                                ? "border-success/30 bg-success/5"
                                : p.coming_soon
                                ? "border-surface-border bg-surface-soft opacity-70"
                                : "border-surface-border")}>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-9 h-9 rounded-lg bg-info/10 text-info grid place-items-center">
                <Cpu className="w-4 h-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-ink truncate">{p.name}</div>
                <code className="text-xs text-ink-soft font-mono">{p.vendor}</code>
              </div>
              {p.verified && <ShieldCheck className="w-4 h-4 text-brand-500"
                                            title="Plugin vérifié Kaydan" />}
            </div>

            <div className="text-xs text-ink-muted mb-2 flex-1">
              Protocoles :{" "}
              {p.protocols.map((pr) => (
                <span key={pr} className="inline-flex items-center gap-0.5 mr-1">
                  <Cable className="w-3 h-3" />
                  <span>{pr}</span>
                </span>
              ))}
            </div>

            <div>
              {p.installed ? (
                <Badge tone="ok">
                  <CheckCircle2 className="w-3 h-3 mr-1 inline" />
                  Installé
                </Badge>
              ) : p.coming_soon ? (
                <Badge tone="muted">
                  <Clock className="w-3 h-3 mr-1 inline" />
                  À venir
                </Badge>
              ) : (
                <Badge tone="info">Non installé</Badge>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 p-3 rounded-lg border border-info/20 bg-info/5 text-xs text-ink">
        <div className="font-medium mb-1 flex items-center gap-1">
          <Upload className="w-3.5 h-3.5" /> Uploader un plugin custom
        </div>
        <div className="text-ink-muted">
          Le fichier <code>.zip</code> ou <code>.kshield-driver</code> doit contenir
          un <code>driver.py</code> qui hérite de <code>BaseDriver</code>. Après upload,
          le fichier est placé en staging (<code>/var/lib/kshield/plugin-staging/</code>) —
          un opérateur doit le valider et le déplacer dans <code>devices/drivers/</code>{" "}
          avant redémarrage Django.
        </div>
      </div>
    </div>
  );
}
