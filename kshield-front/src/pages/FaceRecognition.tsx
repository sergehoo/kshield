import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { KpiCard } from "@/components/KpiCard";
import { faceService, employeesService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtRelative } from "@/lib/format";
import {
  ScanFace, Cpu, Upload, Download, Users, Zap, Camera,
} from "lucide-react";
import toast from "react-hot-toast";

export function FaceRecognitionPage() {
  const qc = useQueryClient();

  const status = useLive(
    ["face", "status"],
    async () => (await faceService.status()).data,
    { intervalMs: 30_000 },
  );

  const employees = useQuery({
    queryKey: ["employees", "face-count"],
    queryFn: async () =>
      (await employeesService.list({ page_size: 1 })).data,
  });

  const pushMut = useMutation({
    mutationFn: () => faceService.pushToTerminals(),
    onSuccess: (r: any) => {
      toast.success(`${r.data?.pushed ?? 0} template(s) poussé(s)`);
      qc.invalidateQueries({ queryKey: ["face"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const pullMut = useMutation({
    mutationFn: () => faceService.pullFromTerminals(),
    onSuccess: (r: any) => {
      toast.success(`${r.data?.pulled ?? 0} template(s) récupéré(s)`);
      qc.invalidateQueries({ queryKey: ["face"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const s = status.data || {};

  return (
    <div>
      <PageHeader
        title="Reconnaissance faciale"
        subtitle="Moteur ArcFace + YOLOv8, terminaux ZKTeco / AiFace / Hikvision"
        live
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <KpiCard
          label="Moteur"
          value={s.engine || "—"}
          icon={<Cpu className="w-5 h-5" />}
          accent="brand"
          hint={s.engine_ready ? "Prêt" : "Non initialisé"}
          loading={status.isLoading}
        />
        <KpiCard
          label="Templates encodés"
          value={s.templates_count ?? 0}
          icon={<ScanFace className="w-5 h-5" />}
          accent="info"
          loading={status.isLoading}
        />
        <KpiCard
          label="Employés faciaux"
          value={s.employees_with_face ?? 0}
          icon={<Users className="w-5 h-5" />}
          accent="ok"
          hint={
            employees.data?.count
              ? `sur ${employees.data.count} total`
              : undefined
          }
          loading={status.isLoading}
        />
        <KpiCard
          label="Terminaux face"
          value={s.face_terminals_count ?? 0}
          icon={<Camera className="w-5 h-5" />}
          accent="warn"
          hint={
            s.last_sync ? fmtRelative(s.last_sync) : "Jamais sync"
          }
          loading={status.isLoading}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card
          title={
            <span className="flex items-center gap-2">
              <Upload className="w-4 h-4 text-brand-ink" /> Push vers terminaux
            </span>
          }
          subtitle="Envoie tous les templates vers les terminaux face configurés"
        >
          <p className="text-sm text-ink-muted mb-4">
            Utile après un enrôlement en masse d'employés. Chaque terminal reçoit
            les templates via son API vendor (ISAPI Hikvision, ADMS ZKTeco, etc.).
          </p>
          <Button
            className="w-full justify-center"
            leftIcon={<Zap className="w-4 h-4" />}
            onClick={() => pushMut.mutate()}
            loading={pushMut.isPending}
          >
            Lancer le push
          </Button>
        </Card>

        <Card
          title={
            <span className="flex items-center gap-2">
              <Download className="w-4 h-4 text-info" /> Pull depuis terminaux
            </span>
          }
          subtitle="Récupère les templates enrôlés directement sur les terminaux"
        >
          <p className="text-sm text-ink-muted mb-4">
            Si un employé a été enrôlé directement sur le terminal face (via l'écran
            tactile), cette action synchronise le template dans Shield.
          </p>
          <Button
            variant="ghost"
            className="w-full justify-center"
            leftIcon={<Download className="w-4 h-4" />}
            onClick={() => pullMut.mutate()}
            loading={pullMut.isPending}
          >
            Récupérer les templates
          </Button>
        </Card>
      </div>

      {s.recent_matches && (
        <Card title="Reconnaissances récentes" className="mt-4">
          <ul className="space-y-2">
            {s.recent_matches?.slice(0, 10).map((m: any, i: number) => (
              <li key={i} className="flex items-center justify-between p-2 rounded bg-surface-soft/40">
                <div className="flex items-center gap-2">
                  <ScanFace className="w-4 h-4 text-brand-ink" />
                  <span className="text-sm">{m.employee_name || m.badge_uid}</span>
                  <Badge tone={m.confidence > 0.8 ? "ok" : "warn"}>
                    {(m.confidence * 100).toFixed(0)}%
                  </Badge>
                </div>
                <span className="text-xs text-ink-soft">{fmtRelative(m.timestamp)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
