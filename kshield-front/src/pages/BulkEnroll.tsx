import { useState, useRef, useEffect } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { LivePulse } from "@/components/LivePulse";
import { badgesService, helmetsService, scanInboxService } from "@/services";
import { toApiError } from "@/lib/api";
import {
  Upload, Plus, CreditCard, HardHat, ClipboardList, Radar, Trash2, CheckCircle2, X,
  FileUp,
} from "lucide-react";
import toast from "react-hot-toast";
import { cn } from "@/lib/cn";

type Mode = "batch" | "csv" | "live";
type Kind = "badges" | "helmets";

/**
 * Enrôlement en masse — 3 modes :
 *  - batch   : coller une liste d'UIDs (un par ligne)
 *  - csv     : uploader un fichier CSV (uid,tech ou uid,ble_uid pour casques)
 *  - live    : poll toutes les 2s le scan inbox Redis, chaque scan physique
 *              apparaît dans la liste et peut être validé
 */
export function BulkEnrollPage() {
  const [kind, setKind] = useState<Kind>("badges");
  const [mode, setMode] = useState<Mode>("batch");
  const [tech, setTech] = useState<"nfc" | "uhf" | "qr" | "ble">("nfc");
  const [batchText, setBatchText] = useState("");
  const [items, setItems] = useState<
    { uid: string; ble_uid?: string; ok?: boolean; error?: string }[]
  >([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ─── Mode live : poll scan inbox toutes les 2s ─────────
  const seenUids = useRef<Set<string>>(new Set());
  const { data: inbox } = useQuery({
    queryKey: ["scan-inbox", mode, kind, tech],
    queryFn: async () =>
      (await scanInboxService.drain({ kind: tech })).data,
    refetchInterval: mode === "live" ? 2_000 : false,
    refetchIntervalInBackground: false,
    enabled: mode === "live",
  });

  useEffect(() => {
    if (mode !== "live" || !inbox?.scans) return;
    const fresh = inbox.scans.filter((s: any) => {
      const uid = s.uid || s.badge_uid;
      if (!uid || seenUids.current.has(uid)) return false;
      seenUids.current.add(uid);
      return true;
    });
    if (fresh.length > 0) {
      setItems((prev) => [
        ...fresh.map((s: any) => ({ uid: s.uid || s.badge_uid })),
        ...prev,
      ]);
      toast.success(`${fresh.length} scan(s) capturé(s)`);
    }
  }, [inbox, mode]);

  // ─── Mutation enrôlement ───────────────────────────────
  const enrollMut = useMutation({
    mutationFn: async () => {
      const service = kind === "badges" ? badgesService : helmetsService;
      const body: any = { items };
      if (kind === "badges") body.tech = tech;
      const r = await service.bulkEnroll(body);
      return r.data;
    },
    onSuccess: (r: any) => {
      const created = r?.created_count ?? r?.created ?? items.length;
      const errors = r?.errors ?? [];
      toast.success(`${created} ${kind} créé(s)`);
      if (errors.length > 0) {
        toast.error(`${errors.length} erreur(s)`, { duration: 5000 });
      }
      // Marque les items OK
      setItems((prev) =>
        prev.map((it) => ({
          ...it,
          ok: !errors.find((e: any) => e.uid === it.uid),
          error: errors.find((e: any) => e.uid === it.uid)?.error,
        })),
      );
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const applyBatch = () => {
    const lines = batchText
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    if (lines.length === 0) return toast.error("Aucun UID à ajouter");
    const parsed = lines.map((line) => {
      const parts = line.split(/[,;\t]/).map((p) => p.trim());
      return kind === "helmets"
        ? { uid: parts[0], ble_uid: parts[1] || "" }
        : { uid: parts[0] };
    });
    setItems((prev) => {
      const existing = new Set(prev.map((p) => p.uid));
      const fresh = parsed.filter((p) => !existing.has(p.uid));
      return [...fresh, ...prev];
    });
    setBatchText("");
    toast.success(`${parsed.length} UID(s) ajouté(s)`);
  };

  const onCsvSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      const rows = text.split(/\r?\n/).filter(Boolean).slice(1); // skip header
      const parsed = rows
        .map((r) => {
          const cells = r.split(/[,;]/).map((c) => c.trim().replace(/^"|"$/g, ""));
          return kind === "helmets"
            ? { uid: cells[0], ble_uid: cells[1] }
            : { uid: cells[0] };
        })
        .filter((p) => p.uid);
      setItems((prev) => [...parsed, ...prev]);
      toast.success(`${parsed.length} ligne(s) importée(s)`);
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  const removeItem = (uid: string) =>
    setItems((prev) => prev.filter((i) => i.uid !== uid));

  const clearAll = () => {
    setItems([]);
    seenUids.current.clear();
  };

  return (
    <div>
      <PageHeader
        title="Enrôlement en masse"
        subtitle="Enregistrer plusieurs badges ou casques d'un coup — 3 modes disponibles"
      />

      {/* Sélecteur kind + tech */}
      <Card className="mb-4">
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <div className="text-xs text-ink-muted mb-1.5">Type d'équipement</div>
            <div className="inline-flex rounded-lg bg-surface-soft p-0.5 border border-surface-border">
              <button
                onClick={() => setKind("badges")}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium",
                  kind === "badges" ? "bg-brand-500 text-white" : "text-ink-muted",
                )}
              >
                <CreditCard className="w-3.5 h-3.5" /> Badges
              </button>
              <button
                onClick={() => setKind("helmets")}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium",
                  kind === "helmets" ? "bg-warn text-white" : "text-ink-muted",
                )}
              >
                <HardHat className="w-3.5 h-3.5" /> Casques
              </button>
            </div>
          </div>

          {kind === "badges" && (
            <div>
              <div className="text-xs text-ink-muted mb-1.5">Technologie</div>
              <select
                value={tech}
                onChange={(e) => setTech(e.target.value as any)}
                className="field w-40"
              >
                <option value="nfc">NFC (13.56 MHz)</option>
                <option value="uhf">UHF (860-960 MHz)</option>
                <option value="qr">QR code</option>
                <option value="ble">BLE (beacon)</option>
              </select>
            </div>
          )}
        </div>
      </Card>

      {/* Sélecteur mode */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        <ModeCard
          active={mode === "batch"}
          onClick={() => setMode("batch")}
          icon={<ClipboardList className="w-5 h-5" />}
          title="Coller une liste"
          desc="Un UID par ligne, séparé par virgule/tab pour les casques (uid, ble_uid)"
        />
        <ModeCard
          active={mode === "csv"}
          onClick={() => setMode("csv")}
          icon={<FileUp className="w-5 h-5" />}
          title="Fichier CSV"
          desc="Import avec entête : uid ou uid,ble_uid"
        />
        <ModeCard
          active={mode === "live"}
          onClick={() => setMode("live")}
          icon={<Radar className="w-5 h-5" />}
          title="Capture en direct"
          desc="Scan physique sur un lecteur — les UIDs apparaissent en temps réel"
          badge={mode === "live" ? <LivePulse label="ON" /> : undefined}
        />
      </div>

      {/* Zone de saisie selon mode */}
      {mode === "batch" && (
        <Card title="Coller les UIDs" className="mb-4">
          <textarea
            value={batchText}
            onChange={(e) => setBatchText(e.target.value)}
            rows={6}
            className="field w-full font-mono text-xs"
            placeholder={
              kind === "helmets"
                ? "HLM-001, BLE-AC:BC:32:...\nHLM-002, BLE-AC:BC:33:..."
                : "04:A1:B2:C3\n04:A1:B2:C4\n04:A1:B2:C5"
            }
          />
          <div className="mt-3 flex justify-between items-center">
            <div className="text-xs text-ink-soft">
              {batchText.split(/\r?\n/).filter((l) => l.trim()).length} ligne(s) prête(s)
            </div>
            <Button
              leftIcon={<Plus className="w-4 h-4" />}
              onClick={applyBatch}
              disabled={!batchText.trim()}
            >
              Ajouter à la liste
            </Button>
          </div>
        </Card>
      )}

      {mode === "csv" && (
        <Card title="Importer un fichier CSV" className="mb-4">
          <p className="text-xs text-ink-muted mb-3">
            Format attendu : première ligne = header, puis un UID par ligne.
            Séparateur virgule ou point-virgule. Encodage UTF-8.
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.txt"
            onChange={onCsvSelect}
            className="hidden"
          />
          <Button
            variant="ghost"
            leftIcon={<Upload className="w-4 h-4" />}
            onClick={() => fileInputRef.current?.click()}
          >
            Choisir un fichier CSV…
          </Button>
        </Card>
      )}

      {mode === "live" && (
        <Card
          title="Capture en direct depuis un lecteur"
          actions={<LivePulse />}
          className="mb-4"
        >
          <p className="text-sm text-ink-muted">
            Scannez maintenant un badge ({kind === "badges" ? tech.toUpperCase() : "casque"})
            sur n'importe quel lecteur configuré en mode enrôlement. L'UID apparaîtra
            automatiquement dans la liste ci-dessous.
          </p>
          <div className="mt-3 text-xs text-ink-soft">
            📡 Écoute active — polling toutes les 2 secondes de l'inbox Redis
          </div>
        </Card>
      )}

      {/* Liste des items */}
      <Card
        padded={false}
        title={`Liste à enrôler (${items.length})`}
        actions={
          items.length > 0 && (
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<Trash2 className="w-3.5 h-3.5" />}
                onClick={clearAll}
              >
                Vider
              </Button>
              <Button
                size="sm"
                onClick={() => enrollMut.mutate()}
                loading={enrollMut.isPending}
                disabled={items.length === 0}
              >
                Enrôler les {items.length} {kind === "badges" ? "badges" : "casques"}
              </Button>
            </div>
          )
        }
      >
        {items.length === 0 && (
          <div className="p-8 text-center text-ink-muted text-sm">
            Aucun UID dans la liste. Utilisez un mode ci-dessus pour en ajouter.
          </div>
        )}
        {items.length > 0 && (
          <ul className="divide-y divide-surface-border/50 max-h-[50vh] overflow-y-auto">
            {items.map((it) => (
              <li
                key={it.uid}
                className={cn(
                  "flex items-center gap-3 px-4 py-2.5",
                  it.ok && "bg-ok/5",
                  it.error && "bg-danger/5",
                )}
              >
                {kind === "badges" ? (
                  <CreditCard className="w-4 h-4 text-brand-400 shrink-0" />
                ) : (
                  <HardHat className="w-4 h-4 text-warn shrink-0" />
                )}
                <code className="text-sm font-mono text-ink flex-1 truncate">
                  {it.uid}
                  {it.ble_uid && (
                    <span className="ml-2 text-ink-soft">+ BLE {it.ble_uid}</span>
                  )}
                </code>
                {it.ok && (
                  <Badge tone="ok" dot>
                    <CheckCircle2 className="w-3 h-3" /> Créé
                  </Badge>
                )}
                {it.error && (
                  <span className="text-xs text-danger">{it.error}</span>
                )}
                {!it.ok && !it.error && (
                  <button
                    onClick={() => removeItem(it.uid)}
                    className="p-1 rounded hover:bg-danger/10 text-ink-soft hover:text-danger"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function ModeCard({
  active,
  onClick,
  icon,
  title,
  desc,
  badge,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  desc: string;
  badge?: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "text-left p-4 rounded-2xl border transition-all",
        active
          ? "border-brand-500 bg-brand-500/5 shadow-lg shadow-brand-500/10"
          : "border-surface-border bg-surface-card/60 hover:border-brand-500/40",
      )}
    >
      <div className="flex items-start justify-between">
        <div
          className={cn(
            "w-9 h-9 rounded-xl grid place-items-center",
            active ? "bg-brand-500/20 text-brand-400" : "bg-surface-soft text-ink-muted",
          )}
        >
          {icon}
        </div>
        {badge}
      </div>
      <div className="mt-3 text-sm font-semibold text-ink">{title}</div>
      <div className="mt-1 text-xs text-ink-muted">{desc}</div>
    </button>
  );
}
