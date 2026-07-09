import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import {
  workersService, accessEventsService, attendanceService, badgesService,
  helmetsService, workerCertsService, workerAssignmentsService,
} from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDate, fmtTime, fmtRelative, initials, fmtDateTime } from "@/lib/format";
import { WorkerFormModal, workerToForm } from "@/components/WorkerFormModal";
import {
  ArrowLeft, HardHat, CreditCard, MapPin, Briefcase, Calendar, TrendingUp, Ban,
  Phone, Mail, User, Home, Flag, Cake, Users as UsersIcon, CreditCard as IdCard, FileText,
  Edit3, Trash2, PauseCircle, PlayCircle, Link as LinkIcon,
  Award, Plus, CheckCircle2, XCircle, ArrowDownToLine, ArrowUpFromLine,
  Radio, Battery, AlertTriangle,
} from "lucide-react";
import toast from "react-hot-toast";
import { cn } from "@/lib/cn";

export function WorkerDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const id = Number(params.id);

  const [tab, setTab] = useState<"profile" | "equipement" | "certifs" | "presence" | "events">("profile");
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [linkBadgeOpen, setLinkBadgeOpen] = useState(false);
  const [linkHelmetOpen, setLinkHelmetOpen] = useState(false);
  const [addCertOpen, setAddCertOpen] = useState(false);
  const [certForm, setCertForm] = useState({ code: "", label: "", issued_at: "", valid_until: "" });
  const [selectedBadgeId, setSelectedBadgeId] = useState<number | "">("");
  const [selectedHelmetId, setSelectedHelmetId] = useState<number | "">("");

  const worker = useQuery({
    queryKey: ["worker", id],
    queryFn: async (): Promise<any> => (await workersService.get(id)).data,
    enabled: !!id,
  });

  const events = useLive(
    ["worker", id, "events"],
    async () => (await accessEventsService.list({
      holder_object_id: id, holder_kind: "worker",
      page_size: 30, ordering: "-timestamp",
    })).data,
    { intervalMs: 15_000, enabled: !!id && tab === "events" },
  );

  const days = useQuery({
    queryKey: ["worker", id, "days"],
    queryFn: async () =>
      (await attendanceService.daysList({ worker: id, page_size: 90, ordering: "-date" })).data,
    enabled: !!id && tab === "presence",
  });

  const certs = useQuery({
    queryKey: ["worker", id, "certs"],
    queryFn: async () =>
      (await workerCertsService.list({ worker: id, page_size: 50 })).data,
    enabled: !!id && tab === "certifs",
  });

  const assignments = useQuery({
    queryKey: ["worker", id, "assignments"],
    queryFn: async () =>
      (await workerAssignmentsService.list({ worker: id, page_size: 20 })).data,
    enabled: !!id,
  });

  // ─── Mutations CRUD ─────────────────────────
  const deleteMut = useMutation({
    mutationFn: () => workersService.remove(id),
    onSuccess: () => { toast.success("Ouvrier supprimé"); navigate("/workers"); },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const suspendMut = useMutation({
    mutationFn: () => workersService.update(id, { status: "suspended" as any }),
    onSuccess: () => { toast.success("Ouvrier suspendu"); qc.invalidateQueries({ queryKey: ["worker", id] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const reactivateMut = useMutation({
    mutationFn: () => workersService.update(id, { status: "active" }),
    onSuccess: () => { toast.success("Ouvrier réactivé"); qc.invalidateQueries({ queryKey: ["worker", id] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const blacklistMut = useMutation({
    mutationFn: () => workersService.update(id, { status: "blacklisted" }),
    onSuccess: () => { toast.success("Ajouté en liste rouge"); qc.invalidateQueries({ queryKey: ["worker", id] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const pairBadgeMut = useMutation({
    mutationFn: (badgeId: number) => workersService.pairBadge(id, badgeId),
    onSuccess: () => {
      toast.success("Badge associé");
      setLinkBadgeOpen(false);
      qc.invalidateQueries({ queryKey: ["worker", id] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const pairHelmetMut = useMutation({
    mutationFn: (helmetId: number) => workersService.pairHelmet(id, helmetId),
    onSuccess: () => {
      toast.success("Casque associé");
      setLinkHelmetOpen(false);
      qc.invalidateQueries({ queryKey: ["worker", id] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const addCertMut = useMutation({
    mutationFn: () => workerCertsService.create({ ...certForm, worker: id }),
    onSuccess: () => {
      toast.success("Certification ajoutée");
      setAddCertOpen(false);
      setCertForm({ code: "", label: "", issued_at: "", valid_until: "" });
      qc.invalidateQueries({ queryKey: ["worker", id, "certs"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  // ─── Data pour dropdowns ─────────────────
  const badgesAvailable = useQuery({
    queryKey: ["badges", "available", "uhf"],
    queryFn: async () => (await badgesService.list({ status: "available", tech: "uhf", page_size: 100 })).data,
    enabled: linkBadgeOpen,
  });
  const helmetsAvailable = useQuery({
    queryKey: ["helmets", "available"],
    queryFn: async () => (await helmetsService.list({ status: "active", page_size: 100 })).data,
    enabled: linkHelmetOpen,
  });

  const w = worker.data;
  if (!w && worker.isLoading)
    return <div className="text-center py-16 text-ink-muted">Chargement…</div>;
  if (!w)
    return (
      <div className="text-center py-16">
        <p className="text-ink-muted mb-3">Ouvrier introuvable</p>
        <Link to="/workers" className="btn-ghost inline-flex">
          <ArrowLeft className="w-4 h-4" /> Retour
        </Link>
      </div>
    );

  const badge = typeof w.badge === "object" ? w.badge : null;
  const helmet = typeof badge?.paired_helmet === "object" ? badge?.paired_helmet : null;

  // Stats journalier
  const daysList = days.data?.results || [];
  const worked = daysList.reduce((s: number, d: any) => s + (d.worked_minutes || 0), 0);
  const overtime = daysList.reduce((s: number, d: any) => s + (d.overtime_minutes || 0), 0);
  const present = daysList.filter((d: any) => d.status === "present" || d.status === "partial").length;

  return (
    <div>
      <PageHeader
        title={`${w.first_name} ${w.last_name}`}
        subtitle={
          <div className="flex items-center gap-2 text-xs">
            <code className="font-mono">{w.matricule}</code>
            {w.trade && (typeof w.trade === "object" ? w.trade.name : `Trade #${w.trade}`) && (
              <>
                <span className="text-ink-soft">·</span>
                <span>{typeof w.trade === "object" ? w.trade.name : ""}</span>
              </>
            )}
            {w.age != null && (
              <>
                <span className="text-ink-soft">·</span>
                <span>{w.age} ans</span>
              </>
            )}
            {w.nationality && (
              <>
                <span className="text-ink-soft">·</span>
                <span>🇮 {w.nationality}</span>
              </>
            )}
          </div>
        }
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="w-3.5 h-3.5" />}
                    onClick={() => navigate("/workers")}>
              Retour
            </Button>
            <Button size="sm" leftIcon={<Edit3 className="w-3.5 h-3.5" />}
                    onClick={() => setEditModalOpen(true)}>
              Modifier KYC
            </Button>
            {w.status === "active" && (
              <Button variant="ghost" size="sm" leftIcon={<PauseCircle className="w-3.5 h-3.5" />}
                      onClick={() => confirm(`Suspendre ${w.first_name} ${w.last_name} ?`) && suspendMut.mutate()}>
                Suspendre
              </Button>
            )}
            {w.status === "suspended" && (
              <Button variant="ghost" size="sm" leftIcon={<PlayCircle className="w-3.5 h-3.5" />}
                      onClick={() => reactivateMut.mutate()}>
                Réactiver
              </Button>
            )}
            {w.status !== "blacklisted" && (
              <Button variant="ghost" size="sm" leftIcon={<Ban className="w-3.5 h-3.5" />}
                      onClick={() => confirm("Ajouter cet ouvrier en LISTE ROUGE ?") && blacklistMut.mutate()}>
                Liste rouge
              </Button>
            )}
            <Button variant="danger" size="sm" leftIcon={<Trash2 className="w-3.5 h-3.5" />}
                    onClick={() => confirm(`Supprimer définitivement ${w.first_name} ${w.last_name} ?`) && deleteMut.mutate()}>
              Supprimer
            </Button>
          </div>
        }
      />

      {/* Bandeau récap : photo + status + KPIs rapides */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-4">
        {/* Photo & identité */}
        <Card className="lg:col-span-1">
          <div className="flex flex-col items-center text-center">
            {w.photo ? (
              <img src={w.photo} alt="" className="w-28 h-28 rounded-2xl object-cover border-2 border-warn/30" />
            ) : (
              <div className="w-28 h-28 rounded-2xl bg-warn/20 text-warn grid place-items-center text-3xl font-bold border-2 border-warn/30">
                {initials(`${w.first_name} ${w.last_name}`)}
              </div>
            )}
            <div className="mt-3">
              <Badge tone={
                w.status === "active" ? "ok" :
                w.status === "suspended" ? "warn" :
                w.status === "blacklisted" ? "danger" : "muted"
              } dot>
                {w.status || "actif"}
              </Badge>
            </div>
          </div>
        </Card>

        {/* Badge & casque — mis en avant */}
        <Card className="lg:col-span-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Badge RFID */}
            <div className="p-4 rounded-xl border border-info/20 bg-info/5">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-info font-semibold">
                  <CreditCard className="w-4 h-4" /> Badge RFID
                </div>
                {badge ? (
                  <Badge tone="ok" dot>Actif</Badge>
                ) : (
                  <Button size="sm" variant="ghost" leftIcon={<LinkIcon className="w-3 h-3" />}
                          onClick={() => setLinkBadgeOpen(true)}>
                    Associer
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
              ) : (
                <div className="text-sm text-ink-soft">Aucun badge attribué</div>
              )}
            </div>

            {/* Casque BLE */}
            <div className="p-4 rounded-xl border border-warn/20 bg-warn/5">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-warn font-semibold">
                  <HardHat className="w-4 h-4" /> Casque BLE
                </div>
                {helmet ? (
                  <Badge tone="ok" dot>Apparié</Badge>
                ) : (
                  <Button size="sm" variant="ghost" leftIcon={<LinkIcon className="w-3 h-3" />}
                          onClick={() => setLinkHelmetOpen(true)}>
                    Apparier
                  </Button>
                )}
              </div>
              {helmet ? (
                <>
                  <div className="text-lg font-mono text-ink">{helmet.serial_number || helmet.uid}</div>
                  <div className="mt-1 text-xs text-ink-muted flex items-center gap-2 flex-wrap">
                    {helmet.ble_beacon_uid && (
                      <span className="flex items-center gap-1">
                        <Radio className="w-3 h-3" /> BLE {helmet.ble_beacon_uid}
                      </span>
                    )}
                    {helmet.uhf_tag_uid && (<><span>·</span><span>UHF {helmet.uhf_tag_uid}</span></>)}
                    {helmet.battery_pct != null && (<><span>·</span>
                      <span className="flex items-center gap-1">
                        <Battery className={cn("w-3 h-3", helmet.battery_pct < 20 && "text-danger")} />
                        {helmet.battery_pct}%
                      </span></>)}
                  </div>
                </>
              ) : (
                <div className="text-sm text-ink-soft">
                  Aucun casque apparié{" "}
                  {w.helmet_size && <span className="text-ink-muted">(taille {w.helmet_size})</span>}
                </div>
              )}
            </div>
          </div>

          {/* Stats rapides */}
          <div className="mt-3 grid grid-cols-3 gap-2">
            <MiniKpi label="Ancienneté" value={
              w.seniority_days != null
                ? `${Math.floor(w.seniority_days / 30)} mois`
                : w.hired_at ? fmtRelative(w.hired_at) : "—"
            } icon={<Calendar className="w-3.5 h-3.5" />} />
            <MiniKpi label="Chantier actuel" value={
              typeof w.site === "object" ? w.site?.name :
              assignments.data?.results?.[0]?.site_name || "—"
            } icon={<MapPin className="w-3.5 h-3.5" />} />
            <MiniKpi label="Sous-traitant" value={
              typeof w.subcontractor === "object" ? w.subcontractor?.name : "Interne"
            } icon={<Briefcase className="w-3.5 h-3.5" />} />
          </div>
        </Card>
      </div>

      {/* Tabs */}
      <div className="mb-4 border-b border-surface-border flex gap-1 overflow-x-auto">
        {([
          { key: "profile",     label: "Profil KYC" },
          { key: "equipement",  label: `Équipement (${badge ? "1" : "0"}/2)` },
          { key: "certifs",     label: `Certifications HSE (${certs.data?.count ?? 0})` },
          { key: "presence",    label: "Présence & heures" },
          { key: "events",      label: "Événements récents" },
        ] as const).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "px-4 py-2 text-sm whitespace-nowrap",
              tab === t.key
                ? "font-medium text-brand-500 border-b-2 border-brand-500 -mb-px"
                : "text-ink-muted hover:text-ink",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "profile" && <ProfileTab worker={w} onEdit={() => setEditModalOpen(true)} />}
      {tab === "equipement" && (
        <EquipementTab worker={w} badge={badge} helmet={helmet} assignments={assignments.data?.results || []}
                       onLinkBadge={() => setLinkBadgeOpen(true)}
                       onLinkHelmet={() => setLinkHelmetOpen(true)} />
      )}
      {tab === "certifs" && (
        <CertifsTab certs={certs.data?.results || []} loading={certs.isLoading}
                    onAdd={() => setAddCertOpen(true)} />
      )}
      {tab === "presence" && (
        <PresenceTab days={daysList} worked={worked} overtime={overtime} present={present} />
      )}
      {tab === "events" && (
        <EventsTab events={events.data?.results || []} />
      )}

      {/* ─── Modal associer badge ─── */}
      <Modal open={linkBadgeOpen} onClose={() => setLinkBadgeOpen(false)} title="Associer un badge RFID"
        footer={<>
          <Button variant="ghost" onClick={() => setLinkBadgeOpen(false)}>Annuler</Button>
          <Button onClick={() => selectedBadgeId && pairBadgeMut.mutate(Number(selectedBadgeId))}
                  loading={pairBadgeMut.isPending} disabled={!selectedBadgeId}>
            Associer
          </Button>
        </>}
      >
        <label className="block">
          <span className="text-xs font-medium text-ink-muted">Badge disponible (UHF)</span>
          <select value={selectedBadgeId}
                  onChange={(e) => setSelectedBadgeId(e.target.value ? Number(e.target.value) : "")}
                  className="field w-full mt-1.5">
            <option value="">— Choisir un badge —</option>
            {badgesAvailable.data?.results?.map((b: any) => (
              <option key={b.id} value={b.id}>{b.uid} · {(b.type || b.tech || "").toUpperCase()}</option>
            ))}
          </select>
        </label>
      </Modal>

      {/* ─── Modal associer casque ─── */}
      <Modal open={linkHelmetOpen} onClose={() => setLinkHelmetOpen(false)} title="Apparier un casque BLE"
        footer={<>
          <Button variant="ghost" onClick={() => setLinkHelmetOpen(false)}>Annuler</Button>
          <Button onClick={() => selectedHelmetId && pairHelmetMut.mutate(Number(selectedHelmetId))}
                  loading={pairHelmetMut.isPending} disabled={!selectedHelmetId}>
            Apparier
          </Button>
        </>}
      >
        <label className="block">
          <span className="text-xs font-medium text-ink-muted">Casque disponible</span>
          <select value={selectedHelmetId}
                  onChange={(e) => setSelectedHelmetId(e.target.value ? Number(e.target.value) : "")}
                  className="field w-full mt-1.5">
            <option value="">— Choisir un casque —</option>
            {helmetsAvailable.data?.results?.map((h: any) => (
              <option key={h.id} value={h.id}>
                {h.serial_number || h.uid} {h.ble_beacon_uid && `· BLE ${h.ble_beacon_uid}`}
              </option>
            ))}
          </select>
        </label>
      </Modal>

      {/* ─── Modal ajouter certification ─── */}
      <Modal open={addCertOpen} onClose={() => setAddCertOpen(false)} title="Nouvelle certification HSE"
        footer={<>
          <Button variant="ghost" onClick={() => setAddCertOpen(false)}>Annuler</Button>
          <Button onClick={() => certForm.code && certForm.label && addCertMut.mutate()}
                  loading={addCertMut.isPending} disabled={!certForm.code || !certForm.label}>
            Ajouter
          </Button>
        </>}
      >
        <div className="space-y-3">
          <Input label="Code *" placeholder="CACES-R482" value={certForm.code}
                 onChange={(e) => setCertForm({ ...certForm, code: e.target.value })} />
          <Input label="Libellé *" placeholder="CACES engin de chantier R482" value={certForm.label}
                 onChange={(e) => setCertForm({ ...certForm, label: e.target.value })} />
          <div className="grid grid-cols-2 gap-3">
            <Input label="Délivrée le *" type="date" value={certForm.issued_at}
                   onChange={(e) => setCertForm({ ...certForm, issued_at: e.target.value })} />
            <Input label="Valide jusqu'au" type="date" value={certForm.valid_until}
                   onChange={(e) => setCertForm({ ...certForm, valid_until: e.target.value })} />
          </div>
        </div>
      </Modal>

      {/* ─── Modal édition KYC complète ─── */}
      <WorkerFormModal
        open={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        workerId={id}
        initialValues={workerToForm(w)}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Tabs
// ─────────────────────────────────────────────────────────────────
function ProfileTab({ worker: w, onEdit }: { worker: any; onEdit: () => void }) {
  const editBtn = (
    <button onClick={onEdit}
            className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-brand-400"
            title="Modifier cette section">
      <Edit3 className="w-3.5 h-3.5" />
    </button>
  );
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card title={<span className="flex items-center gap-2"><User className="w-4 h-4" /> Identité</span>}
            actions={editBtn}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row icon={<User className="w-3.5 h-3.5" />} label="Prénom" value={w.first_name} />
          <Row icon={<User className="w-3.5 h-3.5" />} label="Nom" value={w.last_name} />
          <Row icon={<IdCard className="w-3.5 h-3.5" />} label="Matricule" value={w.matricule} mono />
          <Row icon={<Cake className="w-3.5 h-3.5" />} label="Date naissance"
               value={w.date_of_birth ? `${fmtDate(w.date_of_birth)} (${w.age ?? "?"} ans)` : "—"} />
          <Row icon={<UsersIcon className="w-3.5 h-3.5" />} label="Sexe"
               value={{ male: "Homme", female: "Femme", other: "Autre" }[w.gender as string] || "—"} />
          <Row icon={<UsersIcon className="w-3.5 h-3.5" />} label="État civil"
               value={{ single: "Célibataire", married: "Marié(e)", divorced: "Divorcé(e)", widowed: "Veuf/veuve" }[w.marital_status as string] || "—"} />
          <Row icon={<Flag className="w-3.5 h-3.5" />} label="Nationalité" value={w.nationality} />
          <Row icon={<Flag className="w-3.5 h-3.5" />} label="Pays résidence" value={w.country_of_residence} />
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><IdCard className="w-4 h-4" /> Pièce d'identité</span>}
            actions={editBtn}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row icon={<IdCard className="w-3.5 h-3.5" />} label="Type"
               value={{ cni: "CNI", passport: "Passeport", driver: "Permis", cedeao: "CEDEAO", other: "Autre" }[w.id_type as string] || "—"} />
          <Row icon={<IdCard className="w-3.5 h-3.5" />} label="Numéro" value={w.id_document_number} mono />
          <Row icon={<Calendar className="w-3.5 h-3.5" />} label="Délivrée le"
               value={w.id_issue_date ? fmtDate(w.id_issue_date) : "—"} />
          <Row icon={<Calendar className="w-3.5 h-3.5" />} label="Expire le"
               value={w.id_expiry_date ? fmtDate(w.id_expiry_date) : "—"} />
          {w.id_document_file && (
            <div className="col-span-2 pt-2 mt-2 border-t border-surface-border/60">
              <a href={w.id_document_file} target="_blank" rel="noopener"
                 className="text-xs text-brand-500 hover:underline flex items-center gap-1">
                <FileText className="w-3.5 h-3.5" /> Télécharger la pièce jointe
              </a>
            </div>
          )}
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Phone className="w-4 h-4" /> Contact</span>}
            actions={editBtn}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row icon={<Phone className="w-3.5 h-3.5" />} label="Téléphone" value={w.phone} mono />
          <Row icon={<Mail className="w-3.5 h-3.5" />} label="Email" value={w.email} />
          <div className="col-span-2 pt-2 mt-1 border-t border-surface-border/60 text-xs text-ink-soft font-semibold uppercase tracking-wider">
            Contact d'urgence
          </div>
          <Row icon={<User className="w-3.5 h-3.5" />} label="Nom" value={w.emergency_contact_name} />
          <Row icon={<Phone className="w-3.5 h-3.5" />} label="Téléphone" value={w.emergency_contact_phone} mono />
          <Row icon={<UsersIcon className="w-3.5 h-3.5" />} label="Relation" value={w.emergency_contact_relation} />
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Home className="w-4 h-4" /> Résidence</span>}
            actions={editBtn}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row icon={<Home className="w-3.5 h-3.5" />} label="Ville" value={w.city} />
          <Row icon={<Home className="w-3.5 h-3.5" />} label="Quartier / commune" value={w.neighborhood} />
          <Row icon={<Home className="w-3.5 h-3.5" />} label="Adresse" value={w.address} span={2} />
        </dl>
      </Card>
    </div>
  );
}

function EquipementTab({ worker: w, badge, helmet, assignments, onLinkBadge, onLinkHelmet }:
  { worker: any; badge: any; helmet: any; assignments: any[]; onLinkBadge: () => void; onLinkHelmet: () => void }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title={<span className="flex items-center gap-2"><CreditCard className="w-4 h-4 text-info" /> Badge RFID</span>}
              actions={badge && <Badge tone="ok" dot>Actif</Badge>}>
          {badge ? (
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <Row icon={<IdCard className="w-3.5 h-3.5" />} label="UID" value={badge.uid} mono />
              <Row icon={<CreditCard className="w-3.5 h-3.5" />} label="Type"
                   value={(badge.type || badge.tech || "").toUpperCase()} />
              <Row icon={<Calendar className="w-3.5 h-3.5" />} label="Émis le"
                   value={badge.issued_at ? fmtDate(badge.issued_at) : "—"} />
              <Row icon={<Calendar className="w-3.5 h-3.5" />} label="Expire le"
                   value={badge.valid_until ? fmtDate(badge.valid_until) : "—"} />
              <Row label="Statut" value={<Badge tone={badge.status === "active" ? "ok" : "muted"} dot>{badge.status}</Badge>} />
              <Row label="Dernier scan"
                   value={badge.last_scan_at ? fmtRelative(badge.last_scan_at) : "Jamais"} />
            </dl>
          ) : (
            <div className="text-center py-8">
              <CreditCard className="w-8 h-8 mx-auto text-ink-soft mb-2" />
              <div className="text-sm text-ink-muted mb-3">Aucun badge attribué</div>
              <Button leftIcon={<LinkIcon className="w-4 h-4" />} onClick={onLinkBadge}>
                Associer un badge
              </Button>
            </div>
          )}
        </Card>

        <Card title={<span className="flex items-center gap-2"><HardHat className="w-4 h-4 text-warn" /> Casque BLE</span>}
              actions={helmet && <Badge tone="ok" dot>Apparié</Badge>}>
          {helmet ? (
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <Row icon={<IdCard className="w-3.5 h-3.5" />} label="Numéro série"
                   value={helmet.serial_number || helmet.uid} mono />
              <Row icon={<Radio className="w-3.5 h-3.5" />} label="Tag BLE"
                   value={helmet.ble_beacon_uid} mono />
              <Row icon={<Radio className="w-3.5 h-3.5" />} label="Tag UHF"
                   value={helmet.uhf_tag_uid} mono />
              <Row icon={<Battery className="w-3.5 h-3.5" />} label="Batterie"
                   value={helmet.battery_pct != null
                     ? <Badge tone={helmet.battery_pct > 30 ? "ok" : helmet.battery_pct > 15 ? "warn" : "danger"}>
                         {helmet.battery_pct}%</Badge>
                     : "—"} />
              <Row label="Taille casque" value={w.helmet_size || "—"} />
              <Row label="Dernière détection"
                   value={helmet.last_seen_at ? fmtRelative(helmet.last_seen_at) : "Jamais"} />
            </dl>
          ) : (
            <div className="text-center py-8">
              <HardHat className="w-8 h-8 mx-auto text-ink-soft mb-2" />
              <div className="text-sm text-ink-muted mb-3">Aucun casque apparié</div>
              <Button leftIcon={<LinkIcon className="w-4 h-4" />} onClick={onLinkHelmet}>
                Apparier un casque
              </Button>
            </div>
          )}
        </Card>
      </div>

      {/* Affectations */}
      <Card title="Affectations aux chantiers" padded={false}>
        {assignments.length === 0 ? (
          <div className="p-6 text-center text-ink-muted text-sm">Aucune affectation</div>
        ) : (
          <ul className="divide-y divide-surface-border/50">
            {assignments.map((a: any) => (
              <li key={a.id} className="px-4 py-3 flex items-center gap-3">
                <MapPin className="w-4 h-4 text-brand-500" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium">{a.site_name || `Site #${a.site}`}</div>
                  <div className="text-xs text-ink-soft">
                    Du {fmtDate(a.started_at)} {a.ended_at ? `au ${fmtDate(a.ended_at)}` : "· en cours"}
                  </div>
                </div>
                {!a.ended_at && <Badge tone="ok" dot>En cours</Badge>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function CertifsTab({ certs, loading, onAdd }: { certs: any[]; loading: boolean; onAdd: () => void }) {
  return (
    <Card title={<span className="flex items-center gap-2"><Award className="w-4 h-4" /> Certifications HSE</span>}
          actions={<Button size="sm" leftIcon={<Plus className="w-3.5 h-3.5" />} onClick={onAdd}>Ajouter</Button>}
          padded={false}>
      {loading && <div className="p-6 text-center text-ink-muted">Chargement…</div>}
      {!loading && certs.length === 0 && (
        <div className="p-6 text-center">
          <Award className="w-8 h-8 mx-auto text-ink-soft mb-2" />
          <div className="text-sm text-ink-muted">Aucune certification HSE enregistrée</div>
          <Button className="mt-3" size="sm" onClick={onAdd}>Ajouter la première</Button>
        </div>
      )}
      <ul className="divide-y divide-surface-border/50">
        {certs.map((c: any) => {
          const days = c.valid_until
            ? Math.floor((new Date(c.valid_until).getTime() - Date.now()) / 86400000)
            : null;
          const expired = days != null && days < 0;
          const warning = days != null && days >= 0 && days < 30;
          return (
            <li key={c.id} className="px-4 py-3 flex items-center gap-3">
              <div className={cn("w-9 h-9 rounded-lg grid place-items-center shrink-0",
                expired ? "bg-danger/10 text-danger" :
                warning ? "bg-warn/10 text-warn" : "bg-ok/10 text-ok")}>
                {expired ? <XCircle className="w-4 h-4" /> :
                 warning ? <AlertTriangle className="w-4 h-4" /> :
                 <CheckCircle2 className="w-4 h-4" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium">{c.label}</div>
                <div className="text-xs text-ink-soft flex items-center gap-2">
                  <code className="font-mono">{c.code}</code>
                  <span>·</span>
                  <span>Émise {fmtDate(c.issued_at)}</span>
                </div>
              </div>
              {c.valid_until ? (
                <Badge tone={expired ? "danger" : warning ? "warn" : "ok"}>
                  {expired ? `Expirée ${fmtDate(c.valid_until)}` : `${days}j restants`}
                </Badge>
              ) : <Badge tone="muted">Sans échéance</Badge>}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function PresenceTab({ days, worked, overtime, present }:
  { days: any[]; worked: number; overtime: number; present: number }) {
  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        <MiniKpi label="Jours présent (90j)" value={present} icon={<Calendar className="w-3.5 h-3.5" />} large />
        <MiniKpi label="Total heures"
                 value={`${Math.floor(worked / 60)}h${(worked % 60).toString().padStart(2, "0")}`}
                 icon={<Calendar className="w-3.5 h-3.5" />} large />
        <MiniKpi label="Heures supp"
                 value={`${Math.round(overtime / 60)}h`}
                 icon={<TrendingUp className="w-3.5 h-3.5" />} large />
      </div>

      <Card title="Journal 90 derniers jours" padded={false}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-surface-border">
              <tr className="text-xs text-ink-muted">
                <th className="text-left px-4 py-2 font-medium">Date</th>
                <th className="text-left px-4 py-2 font-medium">Entrée</th>
                <th className="text-left px-4 py-2 font-medium">Sortie</th>
                <th className="text-left px-4 py-2 font-medium">Travaillé</th>
                <th className="text-left px-4 py-2 font-medium">Supp</th>
                <th className="text-left px-4 py-2 font-medium">Statut</th>
              </tr>
            </thead>
            <tbody>
              {days.length === 0 && (
                <tr><td colSpan={6} className="text-center py-6 text-ink-muted text-xs">Aucune donnée</td></tr>
              )}
              {days.map((d: any) => (
                <tr key={d.id} className="border-b border-surface-border/40">
                  <td className="px-4 py-2 text-xs">{fmtDate(d.date)}</td>
                  <td className="px-4 py-2 text-xs font-mono">{d.first_in ? fmtTime(d.first_in) : "—"}</td>
                  <td className="px-4 py-2 text-xs font-mono">{d.last_out ? fmtTime(d.last_out) : "—"}</td>
                  <td className="px-4 py-2 text-xs">
                    {d.worked_minutes
                      ? `${Math.floor(d.worked_minutes / 60)}h${(d.worked_minutes % 60).toString().padStart(2, "0")}`
                      : "—"}
                  </td>
                  <td className="px-4 py-2 text-xs text-warn">
                    {d.overtime_minutes ? `${Math.round(d.overtime_minutes / 60 * 10) / 10}h` : "—"}
                  </td>
                  <td className="px-4 py-2">
                    <Badge tone={
                      d.status === "present" ? "ok" :
                      d.status === "late" ? "warn" :
                      d.status === "absent" ? "danger" : "muted"
                    }>{d.status}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

function EventsTab({ events }: { events: any[] }) {
  return (
    <Card title="Événements récents" padded={false}>
      {events.length === 0 && (
        <div className="p-6 text-center text-ink-muted text-sm">Aucun événement récent</div>
      )}
      <ul className="divide-y divide-surface-border/50">
        {events.map((e: any) => (
          <li key={e.id} className="px-4 py-2.5 flex items-center gap-3">
            <div className={cn("w-8 h-8 rounded-lg grid place-items-center shrink-0",
              e.decision === "granted" ? "bg-ok/10 text-ok" : "bg-danger/10 text-danger")}>
              {e.decision === "granted" ? <CheckCircle2 className="w-4 h-4" /> : <Ban className="w-4 h-4" />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <Badge tone={e.direction === "in" ? "info" : "muted"}>
                  {e.direction === "in" ? <><ArrowDownToLine className="w-3 h-3" /> Entrée</>
                                        : <><ArrowUpFromLine className="w-3 h-3" /> Sortie</>}
                </Badge>
                <span className="text-xs text-ink-muted truncate">
                  {typeof e.device === "object" ? e.device?.name : `Device #${e.device}`}
                </span>
              </div>
            </div>
            <div className="text-right text-xs">
              <div className="font-mono">{fmtTime(e.timestamp)}</div>
              <div className="text-ink-soft">{fmtRelative(e.timestamp)}</div>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// Helpers
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

function MiniKpi({ label, value, icon, large }:
  { label: string; value: React.ReactNode; icon?: React.ReactNode; large?: boolean }) {
  return (
    <div className={cn("rounded-xl border border-surface-border bg-surface-card/60",
      large ? "p-4" : "p-2.5")}>
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-ink-soft font-semibold">
        {icon}{label}
      </div>
      <div className={cn("mt-0.5 font-bold text-ink truncate",
        large ? "text-xl" : "text-sm")}>{value || "—"}</div>
    </div>
  );
}

