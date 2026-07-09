import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Modal } from "@/components/ui/Modal";
import { StatsRow } from "@/components/StatsRow";
import { fraudInvestigationsService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDateTime, fmtRelative } from "@/lib/format";
import { Search, ShieldCheck, ShieldX, FileSearch, AlertTriangle } from "lucide-react";
import toast from "react-hot-toast";

export function FraudInvestigationsPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("open");
  const [closing, setClosing] = useState<any | null>(null);
  const [verdict, setVerdict] = useState<"confirmed" | "false_positive">("confirmed");
  const [note, setNote] = useState("");
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["fraud-investigations", status, q],
    queryFn: async () =>
      (
        await fraudInvestigationsService.list({
          status: status || undefined,
          search: q || undefined,
          page_size: 100,
          ordering: "-created_at",
        })
      ).data,
  });

  const { data: allInv } = useQuery({
    queryKey: ["fraud-investigations", "all-stats"],
    queryFn: async () => (await fraudInvestigationsService.list({ page_size: 300 })).data,
    staleTime: 30_000,
  });

  const stats = useMemo(() => {
    const list = allInv?.results || [];
    return {
      total:    allInv?.count || 0,
      open:     list.filter((i: any) => i.status === "open").length,
      inProg:   list.filter((i: any) => i.status === "in_progress").length,
      closed:   list.filter((i: any) => i.status === "closed").length,
      confirmed: list.filter((i: any) => i.verdict === "confirmed").length,
      critical: list.filter((i: any) => i.severity === "critical").length,
    };
  }, [allInv]);

  const closeMut = useMutation({
    mutationFn: () => {
      if (!closing) throw new Error("no target");
      return fraudInvestigationsService.close(closing.id, verdict, note);
    },
    onSuccess: () => {
      toast.success("Investigation clôturée");
      setClosing(null);
      setNote("");
      qc.invalidateQueries({ queryKey: ["fraud-investigations"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const columns: Column<any>[] = [
    {
      key: "title",
      header: "Investigation",
      render: (i) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-danger/10 text-danger grid place-items-center">
            <FileSearch className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium truncate">{i.title || `Investigation #${i.id}`}</div>
            <div className="text-xs text-ink-soft">
              Ouverte {fmtRelative(i.created_at)} par {i.opened_by_name || "—"}
            </div>
          </div>
        </div>
      ),
    },
    {
      key: "severity",
      header: "Sévérité",
      render: (i) => (
        <Badge
          tone={
            i.severity === "critical" ? "danger" :
            i.severity === "high" ? "warn" :
            i.severity === "medium" ? "info" : "muted"
          }
        >
          {i.severity || "info"}
        </Badge>
      ),
    },
    { key: "alerts_count", header: "Alertes liées", render: (i) => i.alerts_count ?? 0 },
    {
      key: "status",
      header: "Statut",
      render: (i) => {
        const tone =
          i.status === "closed" ? (i.verdict === "confirmed" ? "danger" : "ok") :
          i.status === "in_progress" ? "warn" : "info";
        return <Badge tone={tone} dot>{i.status || "open"}</Badge>;
      },
    },
    { key: "assignee", header: "Assigné", render: (i) => i.assignee_name || "—" },
    {
      key: "actions",
      header: "",
      className: "text-right",
      render: (i) =>
        i.status !== "closed" && (
          <div className="inline-flex gap-1">
            <button
              onClick={() => {
                setClosing(i);
                setVerdict("confirmed");
                setNote("");
              }}
              className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
              title="Confirmer fraude"
            >
              <ShieldX className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => {
                setClosing(i);
                setVerdict("false_positive");
                setNote("");
              }}
              className="p-1.5 rounded-md hover:bg-ok/10 text-ink-muted hover:text-ok"
              title="Faux positif"
            >
              <ShieldCheck className="w-3.5 h-3.5" />
            </button>
          </div>
        ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Investigations anti-fraude"
        subtitle={`${data?.count ?? 0} investigations`}
      />

      <StatsRow stats={[
        { label: "Total",       value: stats.total,     icon: <FileSearch className="w-4 h-4" />,    tone: "brand" },
        { label: "Ouvertes",    value: stats.open,      icon: <AlertTriangle className="w-4 h-4" />, tone: "warn",
          onClick: () => setStatus("open") },
        { label: "En cours",    value: stats.inProg,    icon: <FileSearch className="w-4 h-4" />,    tone: "info",
          onClick: () => setStatus("in_progress") },
        { label: "Clôturées",   value: stats.closed,    icon: <ShieldCheck className="w-4 h-4" />,   tone: "muted",
          onClick: () => setStatus("closed") },
        { label: "Fraudes",     value: stats.confirmed, icon: <ShieldX className="w-4 h-4" />,       tone: "danger" },
        { label: "Critiques",   value: stats.critical,  icon: <AlertTriangle className="w-4 h-4" />, tone: "danger" },
      ]} />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border flex gap-2">
          <div className="flex-1">
            <Input
              placeholder="Rechercher…"
              leftIcon={<Search className="w-4 h-4" />}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="field w-48">
            <option value="open">Ouvertes</option>
            <option value="in_progress">En cours</option>
            <option value="closed">Clôturées</option>
            <option value="">Toutes</option>
          </select>
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(i) => i.id}
        />
      </Card>

      <Modal
        open={!!closing}
        onClose={() => setClosing(null)}
        title={`Clôturer : ${verdict === "confirmed" ? "Fraude confirmée" : "Faux positif"}`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setClosing(null)}>Annuler</Button>
            <Button
              variant={verdict === "confirmed" ? "danger" : "primary"}
              onClick={() => closeMut.mutate()}
              loading={closeMut.isPending}
            >
              Confirmer et clôturer
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="text-sm text-ink">
            Investigation : <strong>{closing?.title || `#${closing?.id}`}</strong>
          </div>
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Verdict</span>
            <select
              value={verdict}
              onChange={(e) => setVerdict(e.target.value as any)}
              className="field w-full mt-1.5"
            >
              <option value="confirmed">Fraude confirmée</option>
              <option value="false_positive">Faux positif</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Note (obligatoire)</span>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={4}
              className="field w-full mt-1.5"
              placeholder="Résumé de l'investigation, preuves, actions prises…"
            />
          </label>
        </div>
      </Modal>
    </div>
  );
}
