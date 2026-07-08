import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { workersService, accessEventsService, attendanceService } from "@/services";
import { fmtDate, fmtTime, fmtRelative, initials } from "@/lib/format";
import {
  ArrowLeft, HardHat, CreditCard, MapPin, Briefcase, Calendar, TrendingUp,
  ArrowDownToLine, ArrowUpFromLine, CheckCircle2, Ban,
} from "lucide-react";

export function WorkerDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const id = Number(params.id);

  const worker = useQuery({
    queryKey: ["worker", id],
    queryFn: async () => (await workersService.get(id)).data,
    enabled: !!id,
  });

  // Events live pour ce worker
  const events = useLive(
    ["worker", id, "events"],
    async () =>
      (
        await accessEventsService.list({
          holder_object_id: id,
          holder_kind: "worker",
          page_size: 20,
          ordering: "-timestamp",
        })
      ).data,
    { intervalMs: 15_000, enabled: !!id },
  );

  // 7 derniers jours de présence
  const days = useQuery({
    queryKey: ["worker", id, "days"],
    queryFn: async () =>
      (
        await attendanceService.daysList({
          worker: id,
          page_size: 30,
          ordering: "-date",
        })
      ).data,
    enabled: !!id,
  });

  if (worker.isLoading && !worker.data) {
    return <div className="text-center py-16 text-ink-muted">Chargement…</div>;
  }
  const w = worker.data;
  if (!w) {
    return (
      <div className="text-center py-16">
        <p className="text-ink-muted mb-3">Ouvrier introuvable</p>
        <Link to="/workers" className="btn-ghost inline-flex">
          <ArrowLeft className="w-4 h-4" /> Retour
        </Link>
      </div>
    );
  }

  // Stats semaine
  const daysList = days.data?.results || [];
  const totalMinutes = daysList.reduce((s, d) => s + (d.worked_minutes || 0), 0);
  const totalOvertime = daysList.reduce((s, d) => s + (d.overtime_minutes || 0), 0);

  return (
    <div>
      <PageHeader
        title={w.full_name}
        subtitle={
          <div className="flex items-center gap-2 text-xs">
            {w.matricule && <code className="font-mono">{w.matricule}</code>}
            {w.trade && (
              <>
                <span>·</span>
                <span>{w.trade}</span>
              </>
            )}
          </div>
        }
        live
        actions={
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<ArrowLeft className="w-3.5 h-3.5" />}
            onClick={() => navigate("/workers")}
          >
            Retour à la liste
          </Button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Colonne profil */}
        <Card className="lg:col-span-1">
          <div className="flex flex-col items-center text-center">
            {w.photo ? (
              <img
                src={w.photo}
                alt=""
                className="w-24 h-24 rounded-2xl object-cover border-2 border-brand-500/20"
              />
            ) : (
              <div className="w-24 h-24 rounded-2xl bg-warn/20 text-warn grid place-items-center text-2xl font-bold border-2 border-warn/30">
                {initials(w.full_name)}
              </div>
            )}
            <h3 className="mt-3 text-lg font-semibold text-ink">{w.full_name}</h3>
            <div className="mt-1 flex items-center gap-1 text-xs text-ink-muted">
              <Briefcase className="w-3.5 h-3.5" />
              {w.trade || "—"}
            </div>
          </div>

          <dl className="mt-6 space-y-3">
            {typeof w.site === "object" && w.site && (
              <Row
                icon={<MapPin className="w-3.5 h-3.5" />}
                label="Chantier"
                value={
                  <Badge tone="brand" dot>
                    {w.site.name}
                  </Badge>
                }
              />
            )}
            <Row
              icon={<CreditCard className="w-3.5 h-3.5" />}
              label="Badge"
              value={
                typeof w.badge === "object" && w.badge?.uid ? (
                  <code className="font-mono text-xs text-ink">{w.badge.uid}</code>
                ) : (
                  <span className="text-ink-soft text-xs">Aucun</span>
                )
              }
            />
            <Row
              icon={<HardHat className="w-3.5 h-3.5" />}
              label="Casque"
              value={
                typeof w.helmet === "object" && w.helmet?.uid ? (
                  <code className="font-mono text-xs text-ink">{w.helmet.uid}</code>
                ) : (
                  <span className="text-ink-soft text-xs">Aucun</span>
                )
              }
            />
          </dl>
        </Card>

        {/* Colonne stats + events */}
        <div className="lg:col-span-2 space-y-4">
          {/* Stats */}
          <div className="grid grid-cols-3 gap-3">
            <StatBlock
              label="Jours présent (30j)"
              value={daysList.filter((d) => d.status === "present" || d.status === "partial").length}
              icon={<Calendar className="w-4 h-4" />}
            />
            <StatBlock
              label="Total heures"
              value={`${Math.floor(totalMinutes / 60)}h${(totalMinutes % 60).toString().padStart(2, "0")}`}
              icon={<Calendar className="w-4 h-4" />}
            />
            <StatBlock
              label="Heures supp"
              value={`${Math.round(totalOvertime / 60)}h`}
              icon={<TrendingUp className="w-4 h-4" />}
              accent="warn"
            />
          </div>

          {/* Events live */}
          <Card
            title="Événements récents"
            subtitle="Scans du badge de cet ouvrier"
          >
            {events.data?.results?.length === 0 && (
              <div className="text-center py-6 text-ink-muted text-sm">
                Aucun événement récent
              </div>
            )}
            <ul className="space-y-2 max-h-[300px] overflow-y-auto">
              {events.data?.results?.map((e) => (
                <li
                  key={e.id}
                  className="flex items-center gap-3 p-2 rounded-lg bg-surface-soft/40"
                >
                  <div
                    className={
                      e.decision === "granted"
                        ? "w-8 h-8 rounded-lg bg-ok/10 text-ok grid place-items-center shrink-0"
                        : "w-8 h-8 rounded-lg bg-danger/10 text-danger grid place-items-center shrink-0"
                    }
                  >
                    {e.decision === "granted" ? (
                      <CheckCircle2 className="w-4 h-4" />
                    ) : (
                      <Ban className="w-4 h-4" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge tone={e.direction === "in" ? "info" : "muted"}>
                        {e.direction === "in" ? (
                          <>
                            <ArrowDownToLine className="w-3 h-3" /> Entrée
                          </>
                        ) : (
                          <>
                            <ArrowUpFromLine className="w-3 h-3" /> Sortie
                          </>
                        )}
                      </Badge>
                      <span className="text-xs text-ink-muted truncate">
                        {typeof e.device === "object" ? e.device?.name : `Device #${e.device}`}
                      </span>
                    </div>
                  </div>
                  <div className="text-right shrink-0 text-xs">
                    <div className="font-mono">{fmtTime(e.timestamp)}</div>
                    <div className="text-ink-soft">{fmtRelative(e.timestamp)}</div>
                  </div>
                </li>
              ))}
            </ul>
          </Card>

          {/* Journal présence 30j */}
          <Card title="Présence — 30 derniers jours">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-ink-muted border-b border-surface-border">
                    <th className="text-left py-2 font-medium">Date</th>
                    <th className="text-left py-2 font-medium">Entrée</th>
                    <th className="text-left py-2 font-medium">Sortie</th>
                    <th className="text-left py-2 font-medium">Travail</th>
                    <th className="text-left py-2 font-medium">Supp</th>
                    <th className="text-left py-2 font-medium">Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {daysList.length === 0 && (
                    <tr>
                      <td colSpan={6} className="text-center py-6 text-ink-muted text-xs">
                        Aucune donnée
                      </td>
                    </tr>
                  )}
                  {daysList.map((d) => (
                    <tr key={d.id} className="border-b border-surface-border/40">
                      <td className="py-2 text-xs">{fmtDate(d.date)}</td>
                      <td className="py-2 text-xs font-mono">{d.first_in ? fmtTime(d.first_in) : "—"}</td>
                      <td className="py-2 text-xs font-mono">{d.last_out ? fmtTime(d.last_out) : "—"}</td>
                      <td className="py-2 text-xs">
                        {d.worked_minutes
                          ? `${Math.floor(d.worked_minutes / 60)}h${(d.worked_minutes % 60).toString().padStart(2, "0")}`
                          : "—"}
                      </td>
                      <td className="py-2 text-xs text-warn">
                        {d.overtime_minutes ? `${Math.round(d.overtime_minutes / 60 * 10) / 10}h` : "—"}
                      </td>
                      <td className="py-2">
                        <Badge
                          tone={
                            d.status === "present"
                              ? "ok"
                              : d.status === "late"
                              ? "warn"
                              : d.status === "absent"
                              ? "danger"
                              : "muted"
                          }
                        >
                          {d.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
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
      <dt className="flex items-center gap-2 text-xs text-ink-muted">
        {icon}
        {label}
      </dt>
      <dd className="text-right min-w-0">{value}</dd>
    </div>
  );
}

function StatBlock({
  label, value, icon, accent = "brand",
}: {
  label: string;
  value: React.ReactNode;
  icon: React.ReactNode;
  accent?: "brand" | "warn" | "info";
}) {
  const accentClass = {
    brand: "text-brand-400 bg-brand-500/10",
    warn: "text-warn bg-warn/10",
    info: "text-info bg-info/10",
  }[accent];
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card/70 p-4">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-wider text-ink-soft">{label}</div>
        <div className={`w-7 h-7 rounded-lg grid place-items-center ${accentClass}`}>
          {icon}
        </div>
      </div>
      <div className="mt-2 text-lg font-bold text-ink">{value}</div>
    </div>
  );
}
