import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { FormErrorBanner } from "@/components/FormErrorBanner";
import { employeesService, companiesService } from "@/services";
import { parseApiErrors, omitEmpty, FieldErrors } from "@/lib/formErrors";
import { Edit3, Plus } from "lucide-react";
import toast from "react-hot-toast";

export type EmployeeFormValues = {
  matricule: string; first_name: string; last_name: string;
  email: string; phone: string;
  company: number | ""; department: string; job_title: string;
  contract_type: string; work_location: string; status: string;
  hired_at: string;
  // KYC étendus (backend a été mis à jour)
  date_of_birth: string; gender: string; marital_status: string;
  nationality: string; country_of_residence: string;
  city: string; neighborhood: string; address: string;
  id_type: string; id_number: string; id_issue_date: string; id_expiry_date: string;
  emergency_contact_name: string; emergency_contact_phone: string; emergency_contact_relation: string;
};

export const EMPTY_EMPLOYEE_FORM: EmployeeFormValues = {
  matricule: "", first_name: "", last_name: "",
  email: "", phone: "",
  company: "", department: "", job_title: "",
  contract_type: "cdi", work_location: "office", status: "active",
  hired_at: "",
  date_of_birth: "", gender: "", marital_status: "",
  nationality: "Ivoirien", country_of_residence: "Côte d'Ivoire",
  city: "", neighborhood: "", address: "",
  id_type: "cni", id_number: "", id_issue_date: "", id_expiry_date: "",
  emergency_contact_name: "", emergency_contact_phone: "", emergency_contact_relation: "",
};

export function employeeToForm(e: any): EmployeeFormValues {
  return {
    matricule: e.matricule || "", first_name: e.first_name || "", last_name: e.last_name || "",
    email: e.email || "", phone: e.phone || "",
    company: typeof e.company === "object" ? e.company?.id : (e.company || ""),
    department: typeof e.department === "object" ? e.department?.name : (e.department || ""),
    job_title: e.job_title || "",
    contract_type: e.contract_type || "cdi",
    work_location: e.work_location || "office",
    status: e.status || "active",
    hired_at: e.hired_at || "",
    date_of_birth: e.date_of_birth || "", gender: e.gender || "", marital_status: e.marital_status || "",
    nationality: e.nationality || "", country_of_residence: e.country_of_residence || "Côte d'Ivoire",
    city: e.city || "", neighborhood: e.neighborhood || "", address: e.address || "",
    id_type: e.id_type || "cni", id_number: e.id_number || "",
    id_issue_date: e.id_issue_date || "", id_expiry_date: e.id_expiry_date || "",
    emergency_contact_name: e.emergency_contact_name || "",
    emergency_contact_phone: e.emergency_contact_phone || "",
    emergency_contact_relation: e.emergency_contact_relation || "",
  };
}

type Props = {
  open: boolean;
  onClose: () => void;
  employeeId?: number | null;
  initialValues?: EmployeeFormValues;
  onSaved?: (employee: any) => void;
};

export function EmployeeFormModal({ open, onClose, employeeId, initialValues, onSaved }: Props) {
  const [form, setForm] = useState<EmployeeFormValues>(initialValues || EMPTY_EMPLOYEE_FORM);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [globalError, setGlobalError] = useState("");
  const qc = useQueryClient();

  useEffect(() => {
    if (open) {
      setForm(initialValues || EMPTY_EMPLOYEE_FORM);
      setFieldErrors({});
      setGlobalError("");
    }
  }, [open, initialValues]);

  const { data: companies } = useQuery({
    queryKey: ["companies", "for-emp-form"],
    queryFn: async () => (await companiesService.list({ page_size: 200 })).data,
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
    mutationFn: () => employeeId
      ? employeesService.update(employeeId, omitEmpty(form))
      : employeesService.create(omitEmpty(form)),
    onSuccess: (r: any) => {
      toast.success(employeeId ? "Employé mis à jour" : "Employé créé");
      qc.invalidateQueries({ queryKey: ["employees"] });
      qc.invalidateQueries({ queryKey: ["employee", employeeId] });
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
  const set = (k: keyof EmployeeFormValues, v: any) => setForm({ ...form, [k]: v });

  return (
    <Modal open={open} onClose={onClose} size="xl"
      title={employeeId ? "Modifier les données KYC" : "Nouvel employé"}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Annuler</Button>
        <Button onClick={submit} loading={saveMut.isPending}
                leftIcon={employeeId ? <Edit3 className="w-4 h-4" /> : <Plus className="w-4 h-4" />}>
          {employeeId ? "Enregistrer les modifications" : "Créer l'employé"}
        </Button>
      </>}>
      <div className="space-y-5 max-h-[70vh] overflow-y-auto pr-2">
        <FormErrorBanner message={globalError} fieldErrors={fieldErrors} />
        <p className="text-[11px] text-ink-soft">
          Les champs marqués <span className="text-danger">*</span> sont obligatoires.
        </p>

        <Sec title="Identité">
          <div className="grid grid-cols-2 gap-3">
            <Input label="Matricule" requiredMark placeholder="EMP-001" value={form.matricule}
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
        </Sec>

        <Sec title="Résidence & origine">
          <div className="grid grid-cols-2 gap-3">
            <Input label="Nationalité" value={form.nationality}
                   onChange={(e) => set("nationality", e.target.value)} error={err("nationality")} />
            <Input label="Pays de résidence" value={form.country_of_residence}
                   onChange={(e) => set("country_of_residence", e.target.value)} error={err("country_of_residence")} />
            <Input label="Ville" placeholder="Abidjan" value={form.city}
                   onChange={(e) => set("city", e.target.value)} error={err("city")} />
            <Input label="Quartier" placeholder="Cocody" value={form.neighborhood}
                   onChange={(e) => set("neighborhood", e.target.value)} error={err("neighborhood")} />
            <div className="col-span-2">
              <Input label="Adresse complète" value={form.address}
                     onChange={(e) => set("address", e.target.value)} error={err("address")} />
            </div>
          </div>
        </Sec>

        <Sec title="Pièce d'identité">
          <div className="grid grid-cols-2 gap-3">
            <Select label="Type" value={form.id_type} onChange={(v) => set("id_type", v)}
                    options={[{v:"cni",l:"CNI"},{v:"passport",l:"Passeport"},{v:"driver",l:"Permis"},{v:"cedeao",l:"CEDEAO"},{v:"other",l:"Autre"}]}
                    error={err("id_type")} />
            <Input label="Numéro" value={form.id_number}
                   onChange={(e) => set("id_number", e.target.value)} error={err("id_number")} />
            <Input label="Date de délivrance" type="date" value={form.id_issue_date}
                   onChange={(e) => set("id_issue_date", e.target.value)} error={err("id_issue_date")} />
            <Input label="Date d'expiration" type="date" value={form.id_expiry_date}
                   onChange={(e) => set("id_expiry_date", e.target.value)} error={err("id_expiry_date")} />
          </div>
        </Sec>

        <Sec title="Contact">
          <div className="grid grid-cols-2 gap-3">
            <Input label="Email" type="email" value={form.email}
                   onChange={(e) => set("email", e.target.value)} error={err("email")} />
            <Input label="Téléphone" placeholder="+225 07 00 00 00 00" value={form.phone}
                   onChange={(e) => set("phone", e.target.value)} error={err("phone")} />
            <Input label="Contact d'urgence (nom)" value={form.emergency_contact_name}
                   onChange={(e) => set("emergency_contact_name", e.target.value)} error={err("emergency_contact_name")} />
            <Input label="Contact d'urgence (téléphone)" value={form.emergency_contact_phone}
                   onChange={(e) => set("emergency_contact_phone", e.target.value)} error={err("emergency_contact_phone")} />
            <Input label="Relation" placeholder="Épouse, frère…" value={form.emergency_contact_relation}
                   onChange={(e) => set("emergency_contact_relation", e.target.value)} error={err("emergency_contact_relation")} />
          </div>
        </Sec>

        <Sec title="Poste & rattachement">
          <div className="grid grid-cols-2 gap-3">
            <Select label="Filiale" value={form.company ? String(form.company) : ""}
                    onChange={(v) => set("company", v ? Number(v) : "")}
                    options={[{v:"",l:"— Sélectionner —"}, ...(companies?.results || []).map((c: any) => ({v: String(c.id), l: c.name}))]}
                    error={err("company")} />
            <Input label="Département" placeholder="RH, Finance, Tech…" value={form.department}
                   onChange={(e) => set("department", e.target.value)} error={err("department")} />
            <Input label="Poste" placeholder="Chef de projet…" value={form.job_title}
                   onChange={(e) => set("job_title", e.target.value)} error={err("job_title")} />
            <Select label="Type de contrat" value={form.contract_type} onChange={(v) => set("contract_type", v)}
                    options={[{v:"cdi",l:"CDI"},{v:"cdd",l:"CDD"},{v:"internship",l:"Stage"},{v:"freelance",l:"Indépendant"},{v:"temp",l:"Intérim"}]}
                    error={err("contract_type")} />
            <Select label="Lieu de travail" value={form.work_location} onChange={(v) => set("work_location", v)}
                    options={[{v:"office",l:"Bureau (badge seul)"},{v:"field",l:"Chantier (badge + casque)"},{v:"both",l:"Bureau + chantiers"}]}
                    error={err("work_location")} />
            <Input label="Date d'embauche" type="date" value={form.hired_at}
                   onChange={(e) => set("hired_at", e.target.value)} error={err("hired_at")} />
            <Select label="Statut" value={form.status} onChange={(v) => set("status", v)}
                    options={[{v:"active",l:"Actif"},{v:"on_leave",l:"En congé"},{v:"suspended",l:"Suspendu"},{v:"terminated",l:"Sorti"}]}
                    error={err("status")} />
          </div>
        </Sec>
      </div>
    </Modal>
  );
}

function Sec({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
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
