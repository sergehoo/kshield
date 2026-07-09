import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { FormErrorBanner } from "@/components/FormErrorBanner";
import { workersService, subcontractorsService, tradesService } from "@/services";
import { parseApiErrors, omitEmpty, FieldErrors } from "@/lib/formErrors";
import { Edit3, Plus } from "lucide-react";
import toast from "react-hot-toast";

export type WorkerFormValues = {
  matricule: string; first_name: string; last_name: string;
  date_of_birth: string; gender: string; marital_status: string;
  nationality: string; country_of_residence: string;
  city: string; neighborhood: string; address: string;
  id_type: string; id_document_number: string; id_issue_date: string; id_expiry_date: string;
  phone: string; email: string;
  emergency_contact_name: string; emergency_contact_phone: string; emergency_contact_relation: string;
  trade: number | ""; subcontractor: number | "";
  helmet_size: string; hired_at: string; status: string;
};

export const EMPTY_WORKER_FORM: WorkerFormValues = {
  matricule: "", first_name: "", last_name: "",
  date_of_birth: "", gender: "", marital_status: "",
  nationality: "Ivoirien", country_of_residence: "Côte d'Ivoire",
  city: "", neighborhood: "", address: "",
  id_type: "cni", id_document_number: "", id_issue_date: "", id_expiry_date: "",
  phone: "", email: "",
  emergency_contact_name: "", emergency_contact_phone: "", emergency_contact_relation: "",
  trade: "", subcontractor: "",
  helmet_size: "M", hired_at: "",
  status: "active",
};

/** Convertit une fiche worker API → valeurs du formulaire (préremplissage). */
export function workerToForm(w: any): WorkerFormValues {
  return {
    matricule: w.matricule || "", first_name: w.first_name || "", last_name: w.last_name || "",
    date_of_birth: w.date_of_birth || "", gender: w.gender || "", marital_status: w.marital_status || "",
    nationality: w.nationality || "", country_of_residence: w.country_of_residence || "Côte d'Ivoire",
    city: w.city || "", neighborhood: w.neighborhood || "", address: w.address || "",
    id_type: w.id_type || "cni", id_document_number: w.id_document_number || "",
    id_issue_date: w.id_issue_date || "", id_expiry_date: w.id_expiry_date || "",
    phone: w.phone || "", email: w.email || "",
    emergency_contact_name: w.emergency_contact_name || "",
    emergency_contact_phone: w.emergency_contact_phone || "",
    emergency_contact_relation: w.emergency_contact_relation || "",
    trade: typeof w.trade === "object" ? w.trade?.id : (w.trade || ""),
    subcontractor: typeof w.subcontractor === "object" ? w.subcontractor?.id : (w.subcontractor || ""),
    helmet_size: w.helmet_size || "M", hired_at: w.hired_at || "",
    status: w.status || "active",
  };
}

type Props = {
  open: boolean;
  onClose: () => void;
  /** Si fourni, mode édition (PATCH) ; sinon création (POST). */
  workerId?: number | null;
  /** Valeurs initiales du form (pour préremplir en édition) */
  initialValues?: WorkerFormValues;
  /** Callback après succès (list refresh externe si besoin) */
  onSaved?: (worker: any) => void;
  /** Focus initial sur une section (identity, id, contact, address, work) */
  focusSection?: "identity" | "id" | "contact" | "address" | "work";
};

/**
 * Modale d'édition complète d'un Worker — 5 sections KYC.
 * Réutilisable depuis Workers.tsx (création) et WorkerDetail.tsx (édition).
 */
export function WorkerFormModal({ open, onClose, workerId, initialValues, onSaved, focusSection }: Props) {
  const [form, setForm] = useState<WorkerFormValues>(initialValues || EMPTY_WORKER_FORM);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [globalError, setGlobalError] = useState("");
  const qc = useQueryClient();

  // Reset form quand la modale s'ouvre avec de nouvelles valeurs
  useEffect(() => {
    if (open) {
      setForm(initialValues || EMPTY_WORKER_FORM);
      setFieldErrors({});
      setGlobalError("");
    }
  }, [open, initialValues]);

  const { data: trades } = useQuery({
    queryKey: ["trades", "for-form"],
    queryFn: async () => (await tradesService.list({ page_size: 100 })).data,
    enabled: open,
  });
  const { data: subs } = useQuery({
    queryKey: ["subs", "for-form"],
    queryFn: async () => (await subcontractorsService.list({ page_size: 100 })).data,
    enabled: open,
  });

  const handleErr = (e: unknown) => {
    const parsed = parseApiErrors(e);
    setFieldErrors(parsed.fieldErrors);
    setGlobalError(parsed.globalMessage);
    const nb = Object.keys(parsed.fieldErrors).length;
    toast.error(nb > 0 ? `${nb} champ(s) à corriger` : parsed.globalMessage);
  };

  const saveMut = useMutation({
    mutationFn: () => workerId
      ? workersService.update(workerId, omitEmpty(form))
      : workersService.create(omitEmpty(form)),
    onSuccess: (r: any) => {
      toast.success(workerId ? "Ouvrier mis à jour" : "Ouvrier créé");
      qc.invalidateQueries({ queryKey: ["workers"] });
      qc.invalidateQueries({ queryKey: ["worker", workerId] });
      onSaved?.(r.data);
      onClose();
    },
    onError: handleErr,
  });

  const submit = () => {
    const missing: string[] = [];
    if (!form.matricule) missing.push("Matricule");
    if (!form.first_name) missing.push("Prénom");
    if (!form.last_name) missing.push("Nom");
    if (missing.length > 0) {
      const fe: FieldErrors = {};
      if (!form.matricule) fe.matricule = "Ce champ est obligatoire.";
      if (!form.first_name) fe.first_name = "Ce champ est obligatoire.";
      if (!form.last_name) fe.last_name = "Ce champ est obligatoire.";
      setFieldErrors(fe);
      setGlobalError(`Merci de compléter : ${missing.join(", ")}.`);
      return;
    }
    setFieldErrors({}); setGlobalError("");
    saveMut.mutate();
  };

  const err = (k: string) => fieldErrors?.[k];
  const set = (k: keyof WorkerFormValues, v: any) => setForm({ ...form, [k]: v });

  return (
    <Modal open={open} onClose={onClose} size="xl"
      title={workerId ? "Modifier les données KYC" : "Nouvel ouvrier"}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Annuler</Button>
        <Button onClick={submit} loading={saveMut.isPending}
                leftIcon={workerId ? <Edit3 className="w-4 h-4" /> : <Plus className="w-4 h-4" />}>
          {workerId ? "Enregistrer les modifications" : "Créer l'ouvrier"}
        </Button>
      </>}>
      <div className="space-y-5 max-h-[70vh] overflow-y-auto pr-2">
        <FormErrorBanner message={globalError} fieldErrors={fieldErrors} />
        <p className="text-[11px] text-ink-soft">
          Les champs marqués <span className="text-danger">*</span> sont obligatoires.
        </p>

        <Section id="identity" title="Identité" focused={focusSection === "identity"}>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Matricule" requiredMark placeholder="OV-001" value={form.matricule}
                   onChange={(e) => set("matricule", e.target.value)} error={err("matricule")} />
            <Input label="Date de naissance" type="date" value={form.date_of_birth}
                   onChange={(e) => set("date_of_birth", e.target.value)} error={err("date_of_birth")} />
            <Input label="Prénom" requiredMark value={form.first_name}
                   onChange={(e) => set("first_name", e.target.value)} error={err("first_name")} />
            <Input label="Nom" requiredMark value={form.last_name}
                   onChange={(e) => set("last_name", e.target.value)} error={err("last_name")} />
            <Select label="Sexe" value={form.gender} onChange={(v) => set("gender", v)}
                    options={[{v:"",l:"—"},{v:"male",l:"Homme"},{v:"female",l:"Femme"},{v:"other",l:"Autre"}]}
                    error={err("gender")} />
            <Select label="État civil" value={form.marital_status} onChange={(v) => set("marital_status", v)}
                    options={[{v:"",l:"—"},{v:"single",l:"Célibataire"},{v:"married",l:"Marié(e)"},{v:"divorced",l:"Divorcé(e)"},{v:"widowed",l:"Veuf/veuve"}]}
                    error={err("marital_status")} />
          </div>
        </Section>

        <Section id="address" title="Résidence & origine" focused={focusSection === "address"}>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Nationalité" placeholder="Ivoirien" value={form.nationality}
                   onChange={(e) => set("nationality", e.target.value)} error={err("nationality")} />
            <Input label="Pays de résidence" value={form.country_of_residence}
                   onChange={(e) => set("country_of_residence", e.target.value)} error={err("country_of_residence")} />
            <Input label="Ville" placeholder="Abidjan" value={form.city}
                   onChange={(e) => set("city", e.target.value)} error={err("city")} />
            <Input label="Quartier / commune" placeholder="Yopougon" value={form.neighborhood}
                   onChange={(e) => set("neighborhood", e.target.value)} error={err("neighborhood")} />
            <div className="col-span-2">
              <Input label="Adresse complète" value={form.address}
                     onChange={(e) => set("address", e.target.value)} error={err("address")} />
            </div>
          </div>
        </Section>

        <Section id="id" title="Pièce d'identité" focused={focusSection === "id"}>
          <div className="grid grid-cols-2 gap-3">
            <Select label="Type" value={form.id_type} onChange={(v) => set("id_type", v)}
                    options={[{v:"cni",l:"CNI"},{v:"passport",l:"Passeport"},{v:"driver",l:"Permis"},{v:"cedeao",l:"CEDEAO"},{v:"other",l:"Autre"}]}
                    error={err("id_type")} />
            <Input label="Numéro" value={form.id_document_number}
                   onChange={(e) => set("id_document_number", e.target.value)} error={err("id_document_number")} />
            <Input label="Date de délivrance" type="date" value={form.id_issue_date}
                   onChange={(e) => set("id_issue_date", e.target.value)} error={err("id_issue_date")} />
            <Input label="Date d'expiration" type="date" value={form.id_expiry_date}
                   onChange={(e) => set("id_expiry_date", e.target.value)} error={err("id_expiry_date")} />
          </div>
        </Section>

        <Section id="contact" title="Contact" focused={focusSection === "contact"}>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Téléphone" placeholder="+225 07 00 00 00 00" value={form.phone}
                   onChange={(e) => set("phone", e.target.value)} error={err("phone")} />
            <Input label="Email" type="email" value={form.email}
                   onChange={(e) => set("email", e.target.value)} error={err("email")} />
            <Input label="Contact d'urgence (nom)" value={form.emergency_contact_name}
                   onChange={(e) => set("emergency_contact_name", e.target.value)} error={err("emergency_contact_name")} />
            <Input label="Contact d'urgence (téléphone)" value={form.emergency_contact_phone}
                   onChange={(e) => set("emergency_contact_phone", e.target.value)} error={err("emergency_contact_phone")} />
            <Input label="Relation" placeholder="Épouse, frère, mère…" value={form.emergency_contact_relation}
                   onChange={(e) => set("emergency_contact_relation", e.target.value)} error={err("emergency_contact_relation")} />
          </div>
        </Section>

        <Section id="work" title="Métier & emploi" focused={focusSection === "work"}>
          <div className="grid grid-cols-2 gap-3">
            <Select label="Métier" value={form.trade ? String(form.trade) : ""}
                    onChange={(v) => set("trade", v ? Number(v) : "")}
                    options={[{v:"",l:"— Sélectionner —"}, ...(trades?.results || []).map((t: any) => ({v: String(t.id), l: t.name}))]}
                    error={err("trade")} />
            <Select label="Sous-traitant" value={form.subcontractor ? String(form.subcontractor) : ""}
                    onChange={(v) => set("subcontractor", v ? Number(v) : "")}
                    options={[{v:"",l:"Interne KAYDAN"}, ...(subs?.results || []).map((s: any) => ({v: String(s.id), l: s.name}))]}
                    error={err("subcontractor")} />
            <Select label="Taille casque" value={form.helmet_size} onChange={(v) => set("helmet_size", v)}
                    options={[{v:"S",l:"S"},{v:"M",l:"M"},{v:"L",l:"L"},{v:"XL",l:"XL"}]}
                    error={err("helmet_size")} />
            <Input label="Date d'embauche" type="date" value={form.hired_at}
                   onChange={(e) => set("hired_at", e.target.value)} error={err("hired_at")} />
            <Select label="Statut" value={form.status} onChange={(v) => set("status", v)}
                    options={[{v:"active",l:"Actif"},{v:"suspended",l:"Suspendu"},{v:"blacklisted",l:"Liste rouge"},{v:"terminated",l:"Sorti"}]}
                    error={err("status")} />
          </div>
        </Section>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────
function Section({ id, title, children, focused }: {
  id: string; title: string; children: React.ReactNode; focused?: boolean;
}) {
  return (
    <div id={`section-${id}`} className={focused ? "ring-2 ring-brand-500/40 rounded-lg p-2 -m-2" : ""}>
      <div className="text-xs uppercase tracking-wider text-ink-soft font-semibold mb-2">{title}</div>
      {children}
    </div>
  );
}

function Select({ label, value, onChange, options, error, required }: {
  label: string; value: string; onChange: (v: string) => void;
  options: { v: string; l: string }[]; error?: string; required?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-ink-muted flex items-center gap-0.5">
        {label}
        {required && <span className="text-danger">*</span>}
      </span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
              className={`field w-full mt-1.5 ${error ? "border-danger/60" : ""}`}>
        {options.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
      </select>
      {error && (
        <span className="text-xs text-danger mt-1 flex items-start gap-1">
          <span className="w-1 h-1 rounded-full bg-danger mt-1.5 shrink-0" />
          {error}
        </span>
      )}
    </label>
  );
}
