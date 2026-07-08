import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { employeesService, accessEventsService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtTime, fmtRelative, initials } from "@/lib/format";
import {
  ArrowLeft, Mail, Phone, Briefcase, Building2, Zap, ScanFace,
} from "lucide-react";
import toast from "react-hot-toast";

export function EmployeeDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const id = Number(params.id);

  const emp = useQuery({
    queryKey: ["employee", id],
    queryFn: async () => (await (employeesService as any).get(id)).data,
    enabled: !!id,
  });

  const events = useLive(
    ["employee", id, "events"],
    async () =>
      (
        await accessEventsService.list({
          holder_object_id: id,
          holder_kind: "employee",
          page_size: 20,
          ordering: "-timestamp",
        })
      ).data,
    { intervalMs: 15_000, enabled: !!id },
  );

  const pushZkMut = useMutation({
    mutationFn: () => (employeesService as any).pushToZk(id),
    onSuccess: () => toast.success("Push vers terminaux ZK lancé"),
    onError: (e) => toast.error(toApiError(e).message),
  });

  const e = emp.data;
  if (!e && emp.isLoading) return <div className="text-center py-16 text-ink-muted">Chargement…</div>;
  if (!e)
    return (
      <div className="text-center py-16">
        <p className="text-ink-muted mb-3">Employé introuvable</p>
        <Link to="/employees" className="btn-ghost inline-flex">
          <ArrowLeft className="w-4 h-4" /> Retour
        </Link>
      </div>
    );

  return (
    <div>
      <PageHeader
        title={e.full_name || `${e.first_name || ""} ${e.last_name || ""}`.trim()}
        subtitle={e.job_title || e.department}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              leftIcon={<ArrowLeft className="w-3.5 h-3.5" />}
              onClick={() => navigate("/employees")}
            >
              Retour
            </Button>
            <Button
              variant="ghost"
              size="sm"
              leftIcon={<Zap className="w-3.5 h-3.5" />}
              onClick={() => pushZkMut.mutate()}
              loading={pushZkMut.isPending}
            >
              Push vers ZK
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card>
          <div className="flex flex-col items-center text-center">
            {e.photo ? (
              <img src={e.photo} alt="" className="w-24 h-24 rounded-2xl object-cover border-2 border-brand-500/20" />
            ) : (
              <div className="w-24 h-24 rounded-2xl bg-brand-500/20 text-brand-400 grid place-items-center text-2xl font-bold border-2 border-brand-500/30">
                {initials(e.full_name)}
              </div>
            )}
            <h3 className="mt-3 text-lg font-semibold text-ink">{e.full_name}</h3>
            {e.matricule && (
              <code className="text-xs text-ink-soft font-mono">{e.matricule}</code>
            )}
          </div>

          <dl className="mt-6 space-y-3 text-sm">
            {e.email && (
              <Row icon={<Mail className="w-3.5 h-3.5" />} label="Email" value={e.email} />
            )}
            {e.phone && (
              <Row
                icon={<Phone className="w-3.5 h-3.5" />}
                label="Téléphone"
                value={<code className="font-mono">{e.phone}</code>}
              />
            )}
            {e.job_title && (
              <Row
                icon={<Briefcase className="w-3.5 h-3.5" />}
                label="Poste"
                value={e.job_title}
              />
            )}
            {typeof e.company === "object" && e.company && (
              <Row
                icon={<Building2 className="w-3.5 h-3.5" />}
                label="Société"
                value={e.company.name}
              />
            )}
            {e.has_face_template && (
              <Row
                icon={<ScanFace className="w-3.5 h-3.5" />}
                label="Face"
                value={<Badge tone="ok">Enrôlée</Badge>}
              />
            )}
          </dl>
        </Card>

        <Card className="lg:col-span-2" title="Événements récents">
          {events.data?.results?.length === 0 && (
            <div className="text-center py-8 text-ink-muted text-sm">
              Aucun événement pour cet employé
            </div>
          )}
          <ul className="space-y-2">
            {events.data?.results?.map((ev: any) => (
              <li key={ev.id} className="flex items-center gap-3 p-2 rounded-lg bg-surface-soft/40">
                <Badge tone={ev.decision === "granted" ? "ok" : "danger"} dot>
                  {ev.decision === "granted" ? "OK" : "Refus"}
                </Badge>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-ink truncate">
                    {typeof ev.device === "object" ? ev.device?.name : `Device #${ev.device}`}
                  </div>
                  <div className="text-xs text-ink-soft">
                    {ev.direction === "in" ? "Entrée" : "Sortie"}
                  </div>
                </div>
                <div className="text-right text-xs">
                  <div className="font-mono text-ink">{fmtTime(ev.timestamp)}</div>
                  <div className="text-ink-soft">{fmtRelative(ev.timestamp)}</div>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

function Row({
  icon, label, value,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="flex items-center gap-2 text-xs text-ink-muted">{icon}{label}</dt>
      <dd className="text-right min-w-0 truncate">{value}</dd>
    </div>
  );
}
