import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { KpiCard } from "@/components/KpiCard";
import { companiesService, sitesService, employeesService } from "@/services";
import { fmtDate } from "@/lib/format";
import { ArrowLeft, Building2, MapPin, Users, FileText } from "lucide-react";

export function CompanyDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const id = Number(params.id);

  const company = useQuery({
    queryKey: ["company", id],
    queryFn: async () => (await (companiesService as any).get(id)).data,
    enabled: !!id,
  });

  const sites = useQuery({
    queryKey: ["company", id, "sites"],
    queryFn: async () =>
      (await sitesService.list({ company: id, page_size: 100 })).data,
    enabled: !!id,
  });

  const employees = useQuery({
    queryKey: ["company", id, "employees"],
    queryFn: async () =>
      (await employeesService.list({ company: id, page_size: 100 })).data,
    enabled: !!id,
  });

  const c = company.data;
  if (!c && company.isLoading)
    return <div className="text-center py-16 text-ink-muted">Chargement…</div>;
  if (!c)
    return (
      <div className="text-center py-16">
        <p className="text-ink-muted mb-3">Société introuvable</p>
        <Link to="/companies" className="btn-ghost inline-flex">
          <ArrowLeft className="w-4 h-4" /> Retour
        </Link>
      </div>
    );

  return (
    <div>
      <PageHeader
        title={c.name}
        subtitle={c.legal_form ? `Forme juridique : ${c.legal_form}` : ""}
        actions={
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<ArrowLeft className="w-3.5 h-3.5" />}
            onClick={() => navigate("/companies")}
          >
            Retour
          </Button>
        }
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <KpiCard
          label="Sites"
          value={sites.data?.count ?? 0}
          icon={<MapPin className="w-5 h-5" />}
          accent="brand"
        />
        <KpiCard
          label="Employés"
          value={employees.data?.count ?? 0}
          icon={<Users className="w-5 h-5" />}
          accent="info"
        />
        <KpiCard
          label="Statut"
          value={
            <Badge tone={c.is_active !== false ? "ok" : "muted"}>
              {c.is_active !== false ? "Active" : "Inactive"}
            </Badge>
          }
          icon={<Building2 className="w-5 h-5" />}
          accent={c.is_active !== false ? "ok" : "danger"}
        />
        <KpiCard
          label="N° Contribuable"
          value={c.ncc || "—"}
          icon={<FileText className="w-5 h-5" />}
          accent="warn"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card
          title={
            <span className="flex items-center gap-2">
              <MapPin className="w-4 h-4" /> Sites du groupe
            </span>
          }
          padded={false}
        >
          {sites.data?.results?.length === 0 && (
            <div className="p-6 text-center text-ink-muted text-sm">Aucun site</div>
          )}
          <ul className="divide-y divide-surface-border/50">
            {sites.data?.results?.map((s: any) => (
              <li key={s.id} className="px-4 py-2.5">
                <Link
                  to={`/sites/${s.id}`}
                  className="flex items-center justify-between hover:bg-surface-soft/40 -mx-4 px-4 py-1"
                >
                  <div>
                    <div className="text-sm font-medium text-ink">{s.name}</div>
                    <div className="text-xs text-ink-soft">{s.address || s.code || "—"}</div>
                  </div>
                  <Badge tone={s.is_active !== false ? "ok" : "muted"}>
                    {s.is_active !== false ? "Actif" : "Inactif"}
                  </Badge>
                </Link>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Informations légales">
          <dl className="space-y-3 text-sm">
            <Row label="Nom" value={c.name} />
            <Row label="Code" value={c.code} mono />
            <Row label="Forme juridique" value={c.legal_form} />
            <Row label="N° CC" value={c.ncc} mono />
            <Row label="Créée le" value={c.created_at ? fmtDate(c.created_at) : "—"} />
          </dl>
        </Card>
      </div>
    </div>
  );
}

function Row({
  label, value, mono,
}: {
  label: string;
  value?: string | null;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-xs uppercase tracking-wider text-ink-soft">{label}</dt>
      <dd className={mono ? "text-xs font-mono text-ink" : "text-sm text-ink"}>
        {value || <span className="text-ink-soft">—</span>}
      </dd>
    </div>
  );
}
