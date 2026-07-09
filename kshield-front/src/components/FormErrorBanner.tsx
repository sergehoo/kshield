import { AlertCircle } from "lucide-react";
import { FieldErrors, fieldLabel } from "@/lib/formErrors";

/**
 * Bannière d'erreur pour formulaires — affichée en haut de la modale quand
 * une soumission échoue. Résume le problème global + liste les champs concernés
 * pour que l'utilisateur voie tout de suite ce qui bloque.
 */
export function FormErrorBanner({
  message,
  fieldErrors,
}: {
  message?: string;
  fieldErrors?: FieldErrors;
}) {
  const fields = Object.keys(fieldErrors || {});
  if (!message && fields.length === 0) return null;

  return (
    <div className="mb-4 p-3 rounded-lg bg-danger/10 border border-danger/30 flex gap-2">
      <AlertCircle className="w-4 h-4 text-danger shrink-0 mt-0.5" />
      <div className="text-sm text-ink flex-1 min-w-0">
        {message && <div className="font-medium">{message}</div>}
        {fields.length > 0 && (
          <ul className="mt-1 text-xs text-ink-muted space-y-0.5">
            {fields.slice(0, 6).map((f) => (
              <li key={f}>
                <span className="font-medium text-danger">{fieldLabel(f)}</span>{" "}
                <span>— {fieldErrors![f]}</span>
              </li>
            ))}
            {fields.length > 6 && (
              <li className="text-ink-soft">…et {fields.length - 6} autres champs</li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
