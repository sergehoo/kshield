import { useState, useRef, useMemo } from "react";
import Papa from "papaparse";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { employeesService, workersService } from "@/services";
import { toApiError } from "@/lib/api";
import {
  Upload, FileSpreadsheet, CheckCircle2, XCircle, Users, HardHat,
  Download, RotateCw, AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/cn";
import toast from "react-hot-toast";

type Kind = "employees" | "workers";
type Row = Record<string, any>;
type RowStatus = "pending" | "creating" | "ok" | "error";

/**
 * Import en masse d'employés/ouvriers depuis un fichier CSV.
 *
 * Étapes :
 *  1. User choisit type (employé ou ouvrier)
 *  2. User upload CSV → Papa parse → aperçu
 *  3. Validation client (colonnes obligatoires)
 *  4. Import ligne par ligne avec progression + retry sur erreur
 */
export function BulkImportPage() {
  const [kind, setKind] = useState<Kind>("employees");
  const [rows, setRows] = useState<
    { data: Row; status: RowStatus; error?: string; id?: number }[]
  >([]);
  const [progress, setProgress] = useState({ done: 0, total: 0, errors: 0 });
  const [running, setRunning] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const columnsByKind = {
    employees: {
      required: ["full_name", "email"],
      optional: ["matricule", "phone", "job_title", "department", "company_id"],
      sample:
        "full_name,email,matricule,phone,job_title\n" +
        "Jean Kouassi,jean.kouassi@example.com,EMP-001,+225 07 00 00 00 01,Chef de chantier\n" +
        "Marie Yao,marie.yao@example.com,EMP-002,+225 07 00 00 00 02,Comptable",
    },
    workers: {
      required: ["full_name"],
      optional: ["matricule", "trade", "site_id", "company_id", "phone"],
      sample:
        "full_name,matricule,trade,phone,site_id\n" +
        "Adama Traoré,OUV-001,Maçon,+225 05 00 00 00 01,\n" +
        "Ismaël Bamba,OUV-002,Ferrailleur,+225 05 00 00 00 02,",
    },
  }[kind];

  const stats = useMemo(() => {
    const ok = rows.filter((r) => r.status === "ok").length;
    const err = rows.filter((r) => r.status === "error").length;
    const pending = rows.filter((r) => r.status === "pending").length;
    return { ok, err, pending, total: rows.length };
  }, [rows]);

  const onFile = (file: File) => {
    Papa.parse<Row>(file, {
      header: true,
      skipEmptyLines: true,
      transformHeader: (h) => h.trim().toLowerCase(),
      complete: (result) => {
        if (result.errors.length > 0) {
          toast.error(`${result.errors.length} erreur(s) de parsing CSV`);
        }
        // Validation colonnes obligatoires
        const firstRow = result.data[0] || {};
        const missing = columnsByKind.required.filter((c) => !(c in firstRow));
        if (missing.length > 0) {
          toast.error(`Colonnes manquantes : ${missing.join(", ")}`);
          return;
        }
        setRows(
          result.data.map((data) => ({
            data,
            status: "pending" as RowStatus,
          })),
        );
        setProgress({ done: 0, total: result.data.length, errors: 0 });
        toast.success(`${result.data.length} ligne(s) chargée(s)`);
      },
    });
  };

  const downloadSample = () => {
    const blob = new Blob([columnsByKind.sample], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${kind}_import_sample.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const runImport = async () => {
    if (rows.length === 0) return;
    setRunning(true);
    let done = 0;
    let errors = 0;

    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      if (row.status === "ok") {
        done++;
        continue;
      }
      // Marque en cours
      setRows((prev) => {
        const copy = [...prev];
        copy[i] = { ...copy[i], status: "creating" };
        return copy;
      });

      try {
        // Cast des ids en number
        const payload = { ...row.data };
        for (const k of ["site_id", "company_id"]) {
          if (payload[k]) payload[k] = Number(payload[k]);
        }
        // Remappe *_id → * (Django accepte site=X pas site_id=X sur les FK typiquement)
        if (payload.site_id) {
          payload.site = payload.site_id;
          delete payload.site_id;
        }
        if (payload.company_id) {
          payload.company = payload.company_id;
          delete payload.company_id;
        }

        const service = kind === "employees" ? employeesService : workersService;
        const r = await service.create(payload as any);
        setRows((prev) => {
          const copy = [...prev];
          copy[i] = { ...copy[i], status: "ok", id: r.data?.id };
          return copy;
        });
        done++;
      } catch (e) {
        const err = toApiError(e);
        setRows((prev) => {
          const copy = [...prev];
          copy[i] = { ...copy[i], status: "error", error: err.message };
          return copy;
        });
        errors++;
      }
      setProgress({ done, total: rows.length, errors });
    }

    setRunning(false);
    toast.success(`Import terminé : ${done - errors} OK, ${errors} erreurs`);
  };

  const retryErrors = () => {
    setRows((prev) =>
      prev.map((r) => (r.status === "error" ? { ...r, status: "pending", error: undefined } : r)),
    );
    runImport();
  };

  const reset = () => {
    setRows([]);
    setProgress({ done: 0, total: 0, errors: 0 });
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div>
      <PageHeader
        title="Import en masse"
        subtitle="Importer plusieurs employés ou ouvriers depuis un fichier CSV"
      />

      {/* Type + upload */}
      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <div className="text-xs text-ink-muted mb-1.5">Type d'entité</div>
            <div className="inline-flex rounded-lg bg-surface-soft p-0.5 border border-surface-border">
              <button
                onClick={() => setKind("employees")}
                disabled={running}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium",
                  kind === "employees" ? "bg-brand-500 text-white" : "text-ink-muted",
                )}
              >
                <Users className="w-3.5 h-3.5" /> Employés
              </button>
              <button
                onClick={() => setKind("workers")}
                disabled={running}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium",
                  kind === "workers" ? "bg-warn text-on-warn" : "text-ink-muted",
                )}
              >
                <HardHat className="w-3.5 h-3.5" /> Ouvriers
              </button>
            </div>
          </div>

          <div className="flex gap-2 ml-auto">
            <Button
              variant="ghost"
              leftIcon={<Download className="w-4 h-4" />}
              onClick={downloadSample}
            >
              Modèle CSV
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.txt"
              onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
              className="hidden"
            />
            <Button
              leftIcon={<Upload className="w-4 h-4" />}
              onClick={() => fileRef.current?.click()}
            >
              Charger un CSV
            </Button>
          </div>
        </div>

        <div className="mt-4 p-3 rounded-lg bg-info/5 border border-info/20 text-xs text-ink">
          <div className="flex items-center gap-2 font-medium mb-1">
            <FileSpreadsheet className="w-3.5 h-3.5 text-info" />
            Colonnes attendues pour <strong>{kind === "employees" ? "employés" : "ouvriers"}</strong>
          </div>
          <div className="text-ink-muted">
            Obligatoires :{" "}
            {columnsByKind.required.map((c) => (
              <code key={c} className="mx-0.5 px-1 py-0.5 rounded bg-surface-soft font-mono text-[10px]">
                {c}
              </code>
            ))}
            {"  ·  "}
            Optionnelles :{" "}
            {columnsByKind.optional.map((c) => (
              <code key={c} className="mx-0.5 px-1 py-0.5 rounded bg-surface-soft font-mono text-[10px]">
                {c}
              </code>
            ))}
          </div>
        </div>
      </Card>

      {/* Progression */}
      {rows.length > 0 && (
        <Card className="mb-4">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="text-sm">
              <strong>{stats.total}</strong> lignes ·{" "}
              <span className="text-ok">{stats.ok} OK</span> ·{" "}
              <span className="text-danger">{stats.err} erreurs</span> ·{" "}
              <span className="text-ink-muted">{stats.pending} en attente</span>
            </div>
            <div className="flex-1 min-w-40 h-2 rounded-full bg-surface-soft overflow-hidden">
              <div
                className="h-full bg-brand-500 transition-all"
                style={{
                  width: `${stats.total ? ((stats.ok + stats.err) / stats.total) * 100 : 0}%`,
                }}
              />
            </div>
            <div className="flex gap-2">
              {stats.err > 0 && !running && (
                <Button
                  variant="ghost"
                  size="sm"
                  leftIcon={<RotateCw className="w-3.5 h-3.5" />}
                  onClick={retryErrors}
                >
                  Réessayer erreurs
                </Button>
              )}
              <Button
                size="sm"
                onClick={runImport}
                loading={running}
                disabled={stats.pending === 0 && !running}
              >
                {stats.ok > 0 ? "Continuer l'import" : `Importer ${stats.total} lignes`}
              </Button>
              <Button variant="ghost" size="sm" onClick={reset}>
                Réinitialiser
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Aperçu + résultats */}
      {rows.length > 0 && (
        <Card padded={false}>
          <div className="max-h-[60vh] overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-surface-card border-b border-surface-border">
                <tr>
                  <th className="text-left px-3 py-2 text-ink-muted w-10">#</th>
                  <th className="text-left px-3 py-2 text-ink-muted w-24">Statut</th>
                  {Object.keys(rows[0].data).map((col) => (
                    <th key={col} className="text-left px-3 py-2 text-ink-muted">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr
                    key={i}
                    className={cn(
                      "border-b border-surface-border/40",
                      r.status === "ok" && "bg-ok/5",
                      r.status === "error" && "bg-danger/5",
                    )}
                  >
                    <td className="px-3 py-1.5 text-ink-soft font-mono">{i + 1}</td>
                    <td className="px-3 py-1.5">
                      {r.status === "ok" && (
                        <Badge tone="ok" dot>
                          <CheckCircle2 className="w-3 h-3" /> OK
                        </Badge>
                      )}
                      {r.status === "error" && (
                        <Badge tone="danger" dot>
                          <XCircle className="w-3 h-3" /> Erreur
                        </Badge>
                      )}
                      {r.status === "creating" && (
                        <Badge tone="info" dot>Création…</Badge>
                      )}
                      {r.status === "pending" && (
                        <Badge tone="muted">En attente</Badge>
                      )}
                    </td>
                    {Object.keys(rows[0].data).map((col) => (
                      <td key={col} className="px-3 py-1.5 text-ink truncate max-w-xs">
                        {r.data[col] || <span className="text-ink-soft">—</span>}
                      </td>
                    ))}
                    {r.error && (
                      <td className="px-3 py-1.5 text-danger text-[11px]">
                        <div className="flex items-start gap-1">
                          <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
                          {r.error}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
