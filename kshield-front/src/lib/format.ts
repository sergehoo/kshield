import { format, formatDistanceToNowStrict, parseISO } from "date-fns";
import { fr } from "date-fns/locale";

export function fmtDateTime(iso?: string | Date | null): string {
  if (!iso) return "—";
  try {
    const d = typeof iso === "string" ? parseISO(iso) : iso;
    return format(d, "dd/MM/yyyy HH:mm", { locale: fr });
  } catch {
    return "—";
  }
}

export function fmtDate(iso?: string | Date | null): string {
  if (!iso) return "—";
  try {
    const d = typeof iso === "string" ? parseISO(iso) : iso;
    return format(d, "dd/MM/yyyy", { locale: fr });
  } catch {
    return "—";
  }
}

export function fmtTime(iso?: string | Date | null): string {
  if (!iso) return "—";
  try {
    const d = typeof iso === "string" ? parseISO(iso) : iso;
    return format(d, "HH:mm:ss", { locale: fr });
  } catch {
    return "—";
  }
}

export function fmtRelative(iso?: string | Date | null): string {
  if (!iso) return "—";
  try {
    const d = typeof iso === "string" ? parseISO(iso) : iso;
    return formatDistanceToNowStrict(d, { addSuffix: true, locale: fr });
  } catch {
    return "—";
  }
}

export function fmtNumber(n?: number | null): string {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat("fr-FR").format(n);
}

export function fmtPercent(n?: number | null, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${n.toFixed(digits)}%`;
}

export function initials(name?: string | null): string {
  if (!name) return "?";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() || "")
    .join("");
}
