/**
 * Parsing et traduction des erreurs Django REST Framework en messages humains,
 * organisés par champ pour affichage sous chaque input.
 *
 * DRF renvoie généralement :
 *   400 { "field_name": ["Erreur 1", "Erreur 2"], "other_field": [...] }
 *   ou   { "detail": "Message général" }
 *   ou   { "non_field_errors": ["..."] }
 */
import axios from "axios";

export type FieldErrors = Record<string, string>;

/** Map des messages DRF vers du français plus humain */
const HUMAN_MAP: Array<[RegExp | string, string]> = [
  [/Ce champ ne peut être nul\.?/i,                          "Ce champ ne peut pas être vide."],
  [/Ce champ est requis\.?/i,                                "Ce champ est obligatoire."],
  [/This field is required\.?/i,                             "Ce champ est obligatoire."],
  [/This field may not be blank\.?/i,                        "Ce champ ne peut pas être vide."],
  [/This field may not be null\.?/i,                         "Ce champ ne peut pas être vide."],
  [/Enter a valid email address\.?/i,                        "Adresse email invalide."],
  [/Saisissez une adresse email valide\.?/i,                 "Adresse email invalide."],
  [/Enter a valid URL\.?/i,                                  "URL invalide."],
  [/Enter a valid date\.?/i,                                 "Date invalide (format attendu : AAAA-MM-JJ)."],
  [/Saisissez une date valide\.?/i,                          "Date invalide (format attendu : AAAA-MM-JJ)."],
  [/A valid integer is required\.?/i,                        "Ce champ doit être un nombre entier."],
  [/A valid number is required\.?/i,                         "Ce champ doit être un nombre."],
  [/already exists/i,                                        "Cette valeur existe déjà — elle doit être unique."],
  [/must make a unique set/i,                                "Cette combinaison de champs existe déjà."],
  [/Ensure this field has no more than (\d+) characters/i,   "Trop long — maximum $1 caractères."],
  [/Assurez-vous que ce champ ne comporte pas plus de (\d+) caractère/i, "Trop long — maximum $1 caractères."],
  [/Ensure this value is greater than or equal to (\S+)/i,   "Valeur doit être ≥ $1."],
  [/Ensure this value is less than or equal to (\S+)/i,      "Valeur doit être ≤ $1."],
  [/Object with .+ does not exist/i,                         "Référence introuvable — l'élément lié n'existe pas."],
  [/Incorrect type\. Expected pk value, received/i,          "Type de valeur incorrect (ID attendu)."],
  [/The fields .+ must make a unique set/i,                  "Cette combinaison existe déjà."],
];

/** Traduit un message brut DRF en français humain. */
export function humanizeError(msg: string): string {
  if (!msg) return "";
  for (const [pattern, replacement] of HUMAN_MAP) {
    if (typeof pattern === "string") {
      if (msg.toLowerCase().includes(pattern.toLowerCase())) return replacement;
    } else {
      if (pattern.test(msg)) return msg.replace(pattern, replacement);
    }
  }
  return msg;
}

/**
 * Extrait les erreurs d'une AxiosError DRF sous forme { field: humanMessage }.
 * Les erreurs top-level (detail, non_field_errors) sont mappées à `__global__`.
 */
export function parseApiErrors(err: unknown): {
  fieldErrors: FieldErrors;
  globalMessage: string;
} {
  const fieldErrors: FieldErrors = {};
  let globalMessage = "";

  if (!axios.isAxiosError(err)) {
    return {
      fieldErrors: {},
      globalMessage: err instanceof Error ? err.message : String(err),
    };
  }

  const data = err.response?.data;
  const status = err.response?.status;

  if (status === 401) return { fieldErrors: {}, globalMessage: "Non authentifié. Veuillez vous reconnecter." };
  if (status === 403) return { fieldErrors: {}, globalMessage: "Permission refusée." };
  if (status === 404) return { fieldErrors: {}, globalMessage: "Ressource introuvable." };
  if (status === 500) return { fieldErrors: {}, globalMessage: "Erreur serveur — réessayez ou contactez l'admin." };
  if (status === 502 || status === 503 || status === 504)
    return { fieldErrors: {}, globalMessage: "Service temporairement indisponible." };

  if (!data) {
    return { fieldErrors: {}, globalMessage: err.message || "Erreur inconnue" };
  }

  // Format string simple
  if (typeof data === "string") {
    return { fieldErrors: {}, globalMessage: humanizeError(data) };
  }

  // Format DRF classique { field: [msg], detail: msg, non_field_errors: [...] }
  if (typeof data === "object" && !Array.isArray(data)) {
    for (const [key, value] of Object.entries(data)) {
      if (key === "detail" && typeof value === "string") {
        globalMessage = humanizeError(value);
        continue;
      }
      if (key === "non_field_errors") {
        const arr = Array.isArray(value) ? value : [value];
        globalMessage = arr.map((m: any) => humanizeError(String(m))).join(" ");
        continue;
      }
      // Field errors
      if (Array.isArray(value)) {
        fieldErrors[key] = value.map((m: any) => humanizeError(String(m))).join(" ");
      } else if (typeof value === "string") {
        fieldErrors[key] = humanizeError(value);
      } else if (typeof value === "object" && value) {
        // Nested (rare) — sérialise
        fieldErrors[key] = humanizeError(JSON.stringify(value));
      }
    }
  }

  // Si pas de message global mais qu'il y a des erreurs de champs, résumer
  if (!globalMessage && Object.keys(fieldErrors).length > 0) {
    const count = Object.keys(fieldErrors).length;
    globalMessage = count === 1
      ? "Merci de corriger le champ signalé ci-dessous."
      : `Merci de corriger les ${count} champs signalés ci-dessous.`;
  }

  return { fieldErrors, globalMessage: globalMessage || "Erreur de validation" };
}

/**
 * Nettoie un objet form avant POST :
 *  - retire les clés dont la valeur est "" (chaîne vide)
 *  - retire les clés dont la valeur est null ou undefined
 *  - laisse les booléens (false valide), les nombres (0 valide), et les strings non vides
 *
 * Évite d'envoyer null explicit à Django sur des champs blank=True/null=False.
 */
export function omitEmpty<T extends Record<string, any>>(obj: T): Partial<T> {
  const out: any = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v === "" || v === null || v === undefined) continue;
    out[k] = v;
  }
  return out;
}

/** Labels français des champs pour affichage dans les toasts */
export const FIELD_LABELS: Record<string, string> = {
  matricule: "Matricule",
  first_name: "Prénom",
  last_name: "Nom",
  email: "Email",
  phone: "Téléphone",
  date_of_birth: "Date de naissance",
  gender: "Sexe",
  marital_status: "État civil",
  nationality: "Nationalité",
  city: "Ville",
  neighborhood: "Quartier",
  address: "Adresse",
  id_type: "Type de pièce",
  id_number: "Numéro de pièce",
  id_document_number: "Numéro de pièce",
  id_issue_date: "Date de délivrance",
  id_expiry_date: "Date d'expiration",
  emergency_contact_name: "Nom du contact d'urgence",
  emergency_contact_phone: "Téléphone d'urgence",
  emergency_contact_relation: "Relation contact d'urgence",
  trade: "Métier",
  subcontractor: "Sous-traitant",
  helmet_size: "Taille casque",
  hired_at: "Date d'embauche",
  status: "Statut",
  company: "Filiale",
  department: "Département",
  job_title: "Poste",
  contract_type: "Type de contrat",
  work_location: "Lieu de travail",
  site: "Site",
  zone: "Zone",
  name: "Nom",
  code: "Code",
  country_of_residence: "Pays de résidence",
};

/** Renvoie un label humain pour un champ backend */
export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] || key.replace(/_/g, " ");
}
