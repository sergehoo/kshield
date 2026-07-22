import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { employeesService, accessEventsService, badgesService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtTime, fmtRelative, initials, fmtDate } from "@/lib/format";
import { EmployeeFormModal, employeeToForm } from "@/components/EmployeeFormModal";
import {
  ArrowLeft, Mail, Phone, Briefcase, Building2, Zap, ScanFace, Edit3, Trash2,
  PauseCircle, PlayCircle, CreditCard, Link as LinkIcon, User, Home, Flag,
  Cake, Users as UsersIcon, CreditCard as IdCard, FileText, Calendar,
  ArrowDownToLine, ArrowUpFromLine, CheckCircle2, Ban,
} from "lucide-react";
import { cn } from "@/lib/cn";
import toast from "react-hot-toast";

export function EmployeeDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const id = Number(params.id);

  const [tab, setTab] = useState<"profile" | "equipement" | "events">("profile");
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [linkBadgeOpen, setLinkBadgeOpen] = useState(false);
  const [selectedBadge, setSelectedBadge] = useState<number | "">("");

  const emp = useQuery({
    queryKey: ["employee", id],
    queryFn: async (): Promise<any> => (await (employeesService as any).get(id)).data,
    enabled: !!id,
  });

  const events = useLive(
    ["employee", id, "events"],
    async () => (await accessEventsService.list({
      holder_object_id: id, holder_kind: "employee",
      page_size: 30, ordering: "-timestamp",
    })).data,
    { intervalMs: 15_000, enabled: !!id && tab === "events" },
  );

  const badgesAvailable = useQuery({
    queryKey: ["badges", "available", "nfc"],
    queryFn: async () => (await badgesService.list({ status: "available", tech: "nfc", page_size: 100 })).data,
    enabled: linkBadgeOpen,
  });

  const deleteMut = useMutation({
    mutationFn: () => employeesService.remove(id),
    onSuccess: () => { toast.success("Employé supprimé"); navigate("/employees"); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const suspendMut = useMutation({
    mutationFn: () => employeesService.update(id, { status: "suspended" }),
    onSuccess: () => { toast.success("Suspendu"); qc.invalidateQueries({ queryKey: ["employee", id] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const reactivateMut = useMutation({
    mutationFn: () => employeesService.update(id, { status: "active" }),
    onSuccess: () => { toast.success("Réactivé"); qc.invalidateQueries({ queryKey: ["employee", id] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const pushZkMut = useMutation({
    mutationFn: () => (employeesService as any).pushToZk(id),
    onSuccess: () => toast.success("Push vers terminaux ZK lancé"),
    onError: (e) => toast.error(toApiError(e).message),
  });

  const e = emp.data;
  if (!e && emp.isLoading)
    return <div className="text-center py-16 text-ink-muted">Chargement…</div>;
  if (!e)
    return (
      <div className="text-center py-16">
        <p className="text-ink-muted mb-3">Employé introuvable</p>
        <Link to="/employees" className="btn-ghost inline-flex">
          <ArrowLeft className="w-4 h-4" /> Retour
        </Link>
      </div>
    );

  const badge = typeof e.badge === "object" ? e.badge : null;

  return (
    <div>
      <PageHeader
        title={`${e.first_name} ${e.last_name}`}
        subtitle={
          <div className="flex items-center gap-2 text-xs">
            <code className="font-mono">{e.matricule}</code>
            {e.job_title && (<><span className="text-ink-soft">·</span><span>{e.job_title}</span></>)}
            {e.age != null && (<><span className="text-ink-soft">·</span><span>{e.age} ans</span></>)}
            {e.nationality && (<><span className="text-ink-soft">·</span><span>🇮 {e.nationality}</span></>)}
          </div>
        }
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="w-3.5 h-3.5" />}
                    onClick={() => navigate("/employees")}>Retour</Button>
            <Button size="sm" leftIcon={<Edit3 className="w-3.5 h-3.5" />}
                    onClick={() => setEditModalOpen(true)}>
              Modifier KYC
            </Button>
            {e.status === "active" && (
              <Button variant="ghost" size="sm" leftIcon={<PauseCircle className="w-3.5 h-3.5" />}
                      onClick={() => confirm(`Suspendre ${e.first_name} ${e.last_name} ?`) && suspendMut.mutate()}>
                Suspendre
              </Button>
            )}
            {e.status === "suspended" && (
              <Button variant="ghost" size="sm" leftIcon={<PlayCircle className="w-3.5 h-3.5" />}
                      onClick={() => reactivateMut.mutate()}>
                Réactiver
              </Button>
            )}
            <Button variant="ghost" size="sm" leftIcon={<Zap className="w-3.5 h-3.5" />}
                    onClick={() => pushZkMut.mutate()} loading={pushZkMut.isPending}>
              Push ZK
            </Button>
            <Button variant="danger" size="sm" leftIcon={<Trash2 className="w-3.5 h-3.5" />}
                    onClick={() => confirm(`Supprimer ${e.first_name} ${e.last_name} ?`) && deleteMut.mutate()}>
              Supprimer
            </Button>
          </div>
        }
      />

      {/* Bandeau photo + statut */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-4">
        <Card className="lg:col-span-1">
          <div className="flex flex-col items-center text-center">
            {e.photo ? (
              <img src={e.photo} alt="" className="w-28 h-28 rounded-2xl object-cover border-2 border-brand-500/30" />
            ) : (
              <div className="w-28 h-28 rounded-2xl bg-brand-500/20 text-brand-ink grid place-items-center text-3xl font-bold border-2 border-brand-500/30">
                {initials(`${e.first_name} ${e.last_name}`)}
              </div>
            )}
            <div className="mt-3">
              <Badge tone={
                e.status === "active" ? "ok" :
                e.status === "on_leave" ? "warn" :
                e.status === "suspended" ? "danger" : "muted"
              } dot>{e.status || "actif"}</Badge>
            </div>
          </div>
        </Card>

        <Card className="lg:col-span-3">
          <div className="p-4 rounded-xl border border-info/20 bg-info/5">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-info font-semibold">
                <CreditCard className="w-4 h-4" /> Badge RFID (NFC)
              </div>
              {badge ? <Badge tone="ok" dot>Actif</Badge> : (
                <Button size="sm" variant="ghost" leftIcon={<LinkIcon className="w-3 h-3" />}
                        onClick={() => setLinkBadgeOpen(true)}>
                  Associer un badge
                </Button>
              )}
            </div>
            {badge ? (
              <>
                <div className="text-lg font-mono text-ink">{badge.uid}</div>
                <div className="mt-1 text-xs text-ink-muted flex items-center gap-2 flex-wrap">
                  <span>{(badge.type || badge.tech || "?").toUpperCase()}</span>
                  <span>·</span>
                  <span>Émis {badge.issued_at ? fmtDate(badge.issued_at) : "—"}</span>
                  {badge.valid_until && (<><span>·</span><span>Valide jusqu'au {fmtDate(badge.valid_until)}</span></>)}
                </div>
              </>
            ) : <div className="text-sm text-ink-soft">Aucun badge attribué</div>}
          </div>

          <div className="mt-3 grid grid-cols-3 gap-2">
            <MiniKpi label="Ancienneté" value={
              e.seniority_days != null ? `${Math.floor(e.seniority_days / 30)} mois` :
              e.hired_at ? fmtRelative(e.hired_at) : "—"
            } icon={<Calendar className="w-3.5 h-3.5" />} />
            <MiniKpi label="Filiale" value={typeof e.company === "object" ? e.company?.name : "—"}
                     icon={<Building2 className="w-3.5 h-3.5" />} />
            <MiniKpi label="Face template"
                     value={e.has_face_template ? <Badge tone="ok">Enrôlée</Badge> : <Badge tone="muted">Non enrôlée</Badge>}
                     icon={<ScanFace className="w-3.5 h-3.5" />} />
          </div>
        </Card>
      </div>

      {/* Tabs */}
      <div className="mb-4 border-b border-surface-border flex gap-1 overflow-x-auto">
        {([
          { key: "profile",    label: "Profil KYC" },
          { key: "equipement", label: `Badge ${badge ? "(actif)" : "(absent)"}` },
          { key: "events",     label: "Événements récents" },
        ] as const).map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
                  className={cn("px-4 py-2 text-sm whitespace-nowrap",
                    tab === t.key
                      ? "font-medium text-brand-ink border-b-2 border-brand-500 -mb-px"
                      : "text-ink-muted hover:text-ink")}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "profile" && <ProfileTab e={e} onEdit={() => setEditModalOpen(true)} />}
      {tab === "equipement" && (
        <EquipTab e={e} badge={badge} onLink={() => setLinkBadgeOpen(true)} />
      )}
      {tab === "events" && (
        <EventsTab events={events.data?.results || []} />
      )}

      {/* Modal associer badge */}
      <Modal open={linkBadgeOpen} onClose={() => setLinkBadgeOpen(false)} title="Associer un badge NFC"
        footer={<>
          <Button variant="ghost" onClick={() => setLinkBadgeOpen(false)}>Annuler</Button>
          <Button onClick={() => selectedBadge && toast("Feature backend à implémenter")}
                  disabled={!selectedBadge}>
            Associer
          </Button>
        </>}>
        <label className="block">
          <span className="text-xs font-medium text-ink-muted">Badge NFC disponible</span>
          <select value={selectedBadge}
                  onChange={(e) => setSelectedBadge(e.target.value ? Number(e.target.value) : "")}
                  className="field w-full mt-1.5">
            <option value="">— Choisir —</option>
            {badgesAvailable.data?.results?.map((b: any) => (
              <option key={b.id} value={b.id}>{b.uid}</option>
            ))}
          </select>
        </label>
      </Modal>

      {/* ─── Modal édition KYC complète ─── */}
      <EmployeeFormModal
        open={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        employeeId={id}
        initialValues={employeeToForm(e)}
      />
    </div>
  );
}

function ProfileTab({ e, onEdit }: { e: any; onEdit: () => void }) {
  const editBtn = (
    <button onClick={onEdit}
            className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-brand-ink"
            title="Modifier cette section">
      <Edit3 className="w-3.5 h-3.5" />
    </button>
  );
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card title={<span className="flex items-center gap-2"><User className="w-4 h-4" /> Identité</span>}
            actions={editBtn}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row label="Prénom" value={e.first_name} />
          <Row label="Nom" value={e.last_name} />
          <Row label="Matricule" value={e.matricule} mono />
          <Row icon={<Cake className="w-3.5 h-3.5" />} label="Date naissance"
               value={e.date_of_birth ? `${fmtDate(e.date_of_birth)} (${e.age ?? "?"} ans)` : "—"} />
          <Row icon={<UsersIcon className="w-3.5 h-3.5" />} label="Sexe"
               value={{ male:"Homme", female:"Femme", other:"Autre" }[e.gender as string] || "—"} />
          <Row icon={<UsersIcon className="w-3.5 h-3.5" />} label="État civil"
               value={{ single:"Célibataire", married:"Marié(e)", divorced:"Divorcé(e)", widowed:"Veuf/veuve" }[e.marital_status as string] || "—"} />
          <Row icon={<Flag className="w-3.5 h-3.5" />} label="Nationalité" value={e.nationality} />
          <Row icon={<Flag className="w-3.5 h-3.5" />} label="Pays résidence" value={e.country_of_residence} />
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><IdCard className="w-4 h-4" /> Pièce d'identité</span>}
            actions={editBtn}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row label="Type" value={{ cni:"CNI", passport:"Passeport", driver:"Permis", cedeao:"CEDEAO", other:"Autre" }[e.id_type as string] || "—"} />
          <Row label="Numéro" value={e.id_number} mono />
          <Row label="Délivrée le" value={e.id_issue_date ? fmtDate(e.id_issue_date) : "—"} />
          <Row label="Expire le" value={e.id_expiry_date ? fmtDate(e.id_expiry_date) : "—"} />
          {e.id_document && (
            <div className="col-span-2 pt-2 mt-2 border-t border-surface-border/60">
              <a href={e.id_document} target="_blank" rel="noopener"
                 className="text-xs text-brand-ink hover:underline flex items-center gap-1">
                <FileText className="w-3.5 h-3.5" /> Pièce jointe
              </a>
            </div>
          )}
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Phone className="w-4 h-4" /> Contact</span>}
            actions={editBtn}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row icon={<Phone className="w-3.5 h-3.5" />} label="Téléphone" value={e.phone} mono />
          <Row icon={<Mail className="w-3.5 h-3.5" />} label="Email" value={e.email} />
          <div className="col-span-2 pt-2 mt-1 border-t border-surface-border/60 text-xs text-ink-soft font-semibold uppercase tracking-wider">
            Contact d'urgence
          </div>
          <Row label="Nom" value={e.emergency_contact_name} />
          <Row label="Téléphone" value={e.emergency_contact_phone} mono />
          <Row label="Relation" value={e.emergency_contact_relation} />
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Briefcase className="w-4 h-4" /> Poste & résidence</span>}
            actions={editBtn}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row icon={<Briefcase className="w-3.5 h-3.5" />} label="Poste" value={e.job_title} />
          <Row label="Département" value={typeof e.department === "object" ? e.department?.name : e.department} />
          <Row label="Type contrat" value={e.contract_type?.toUpperCase()} />
          <Row label="Date d'embauche" value={e.hired_at ? fmtDate(e.hired_at) : "—"} />
          <div className="col-span-2 pt-2 mt-1 border-t border-surface-border/60 text-xs text-ink-soft font-semibold uppercase tracking-wider">
            Résidence
          </div>
          <Row icon={<Home className="w-3.5 h-3.5" />} label="Ville" value={e.city} />
          <Row icon={<Home className="w-3.5 h-3.5" />} label="Quartier" value={e.neighborhood} />
          <Row icon={<Home className="w-3.5 h-3.5" />} label="Adresse" value={e.address} span={2} />
        </dl>
      </Card>
    </div>
  );
}

function EquipTab({ e, badge, onLink }: { e: any; badge: any; onLink: () => void }) {
  return (
    <Card title={<span className="flex items-center gap-2"><CreditCard className="w-4 h-4 text-info" /> Badge RFID (NFC)</span>}
          actions={badge && <Badge tone="ok" dot>Actif</Badge>}>
      {badge ? (
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row label="UID" value={badge.uid} mono />
          <Row label="Type" value={(badge.type || badge.tech || "").toUpperCase()} />
          <Row label="Émis le" value={badge.issued_at ? fmtDate(badge.issued_at) : "—"} />
          <Row label="Expire le" value={badge.valid_until ? fmtDate(badge.valid_until) : "—"} />
          <Row label="Dernier scan" value={badge.last_scan_at ? fmtRelative(badge.last_scan_at) : "Jamais"} />
          <Row label="Statut" value={<Badge tone={badge.status === "active" ? "ok" : "muted"} dot>{badge.status}</Badge>} />
        </dl>
      ) : (
        <div className="text-center py-8">
          <CreditCard className="w-8 h-8 mx-auto text-ink-soft mb-2" />
          <div className="text-sm text-ink-muted mb-3">Aucun badge NFC attribué à cet employé</div>
          <Button leftIcon={<LinkIcon className="w-4 h-4" />} onClick={onLink}>
            Associer un badge
          </Button>
        </div>
      )}

      <div className="mt-4 pt-3 border-t border-surface-border/60">
        <div className="text-xs uppercase tracking-wider text-ink-soft font-semibold mb-2">
          Reconnaissance faciale
        </div>
        {e.has_face_template ? (
          <div className="flex items-center gap-2 text-sm text-ok">
            <ScanFace className="w-4 h-4" /> Template facial enrôlé
          </div>
        ) : (
          <div className="text-xs text-ink-muted">Pas de template facial. Utiliser un terminal AI face pour enrôler.</div>
        )}
      </div>
    </Card>
  );
}

function EventsTab({ events }: { events: any[] }) {
  return (
    <Card title="Événements récents" padded={false}>
      {events.length === 0 && (
        <div className="p-6 text-center text-ink-muted text-sm">Aucun événement récent</div>
      )}
      <ul className="divide-y divide-surface-border/50">
        {events.map((ev: any) => (
          <li key={ev.id} className="px-4 py-2.5 flex items-center gap-3">
            <div className={cn("w-8 h-8 rounded-lg grid place-items-center",
              ev.decision === "granted" ? "bg-ok/10 text-ok" : "bg-danger/10 text-danger")}>
              {ev.decision === "granted" ? <CheckCircle2 className="w-4 h-4" /> : <Ban className="w-4 h-4" />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <Badge tone={ev.direction === "in" ? "info" : "muted"}>
                  {ev.direction === "in" ? <><ArrowDownToLine className="w-3 h-3" /> Entrée</>
                                          : <><ArrowUpFromLine className="w-3 h-3" /> Sortie</>}
                </Badge>
                <span className="text-xs text-ink-muted truncate">
                  {typeof ev.device === "object" ? ev.device?.name : `Device #${ev.device}`}
                </span>
              </div>
            </div>
            <div className="text-right text-xs">
              <div className="font-mono">{fmtTime(ev.timestamp)}</div>
              <div className="text-ink-soft">{fmtRelative(ev.timestamp)}</div>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Row({ icon, label, value, mono, span }: {
  icon?: React.ReactNode; label: string; value: React.ReactNode;
  mono?: boolean; span?: number;
}) {
  return (
    <div className={cn("py-1", span === 2 && "col-span-2")}>
      <dt className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-ink-soft font-semibold">
        {icon}{label}
      </dt>
      <dd className={cn("mt-0.5 text-ink truncate", mono && "font-mono text-xs")}>
        {value || <span className="text-ink-soft">—</span>}
      </dd>
    </div>
  );
}

function MiniKpi({ label, value, icon }:
  { label: string; value: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card/60 p-2.5">
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-ink-soft font-semibold">
        {icon}{label}
      </div>
      <div className="mt-0.5 text-sm font-bold text-ink truncate">{value || "—"}</div>
    </div>
  );
}
