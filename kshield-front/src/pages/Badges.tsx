import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge as UIBadge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { badgesService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Badge as ApiBadge } from "@/types/api";
import { Search, CreditCard, Ban, PauseCircle, PlayCircle } from "lucide-react";
import toast from "react-hot-toast";

function techTone(t?: string | null) {
  const v = (t || "").toLowerCase();
  return v === "nfc" ? "info" : v === "uhf" ? "brand" : v === "qr" ? "warn" : "muted";
}
function statusTone(s?: string | null) {
  const v = (s || "").toLowerCase();
  return v === "active" ? "ok" : v === "suspended" ? "warn" : v === "revoked" ? "danger" : "muted";
}

export function BadgesPage() {
  const [q, setQ] = useState("");
  const [tech, setTech] = useState("");
  const [status, setStatus] = useState("");
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["badges", q, tech, status],
    queryFn: async () =>
      (
        await badgesService.list({
          page_size: 300,
          search: q || undefined,
          tech: tech || undefined,
          status: status || undefined,
        })
      ).data,
  });

  const suspendMut = useMutation({
    mutationFn: (id: number) => badgesService.suspend(id),
    onSuccess: () => {
      toast.success("Badge suspendu");
      qc.invalidateQueries({ queryKey: ["badges"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const revokeMut = useMutation({
    mutationFn: (id: number) => badgesService.revoke(id),
    onSuccess: () => {
      toast.success("Badge révoqué");
      qc.invalidateQueries({ queryKey: ["badges"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const reactivateMut = useMutation({
    mutationFn: (id: number) => badgesService.reactivate(id),
    onSuccess: () => {
      toast.success("Badge réactivé");
      qc.invalidateQueries({ queryKey: ["badges"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const columns: Column<ApiBadge>[] = [
    {
      key: "uid",
      header: "UID",
      render: (b) => (
        <div className="flex items-center gap-2">
          <CreditCard className="w-4 h-4 text-brand-400" />
          <code className="text-xs font-mono text-ink">{b.uid}</code>
        </div>
      ),
    },
    {
      key: "tech",
      header: "Techno",
      render: (b) => (
        <UIBadge tone={techTone(b.tech)}>
          {(b.tech || "—").toUpperCase()}
        </UIBadge>
      ),
    },
    { key: "holder", header: "Porteur", render: (b) => b.holder_name || "—" },
    {
      key: "status",
      header: "Statut",
      render: (b) => (
        <UIBadge tone={statusTone(b.status)} dot>
          {b.status || "—"}
        </UIBadge>
      ),
    },
    { key: "issued", header: "Émis le", render: (b) => fmtDate(b.issued_at) },
    {
      key: "actions",
      header: "",
      className: "text-right",
      render: (b) => (
        <div className="inline-flex gap-1">
          {b.status === "active" && (
            <button
              onClick={() => suspendMut.mutate(b.id)}
              className="p-1.5 rounded-md hover:bg-warn/10 text-ink-muted hover:text-warn"
              title="Suspendre"
            >
              <PauseCircle className="w-3.5 h-3.5" />
            </button>
          )}
          {b.status === "suspended" && (
            <button
              onClick={() => reactivateMut.mutate(b.id)}
              className="p-1.5 rounded-md hover:bg-ok/10 text-ink-muted hover:text-ok"
              title="Réactiver"
            >
              <PlayCircle className="w-3.5 h-3.5" />
            </button>
          )}
          {b.status !== "revoked" && (
            <button
              onClick={() => {
                if (confirm(`Révoquer définitivement ${b.uid} ?`)) revokeMut.mutate(b.id);
              }}
              className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
              title="Révoquer"
            >
              <Ban className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Badges"
        subtitle={`${data?.count ?? 0} badges enregistrés (NFC / UHF / QR / BLE)`}
      />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border flex flex-col sm:flex-row gap-2">
          <div className="flex-1">
            <Input
              placeholder="Rechercher par UID, porteur…"
              leftIcon={<Search className="w-4 h-4" />}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <select value={tech} onChange={(e) => setTech(e.target.value)} className="field sm:w-32">
            <option value="">Tous techs</option>
            <option value="nfc">NFC</option>
            <option value="uhf">UHF</option>
            <option value="qr">QR</option>
            <option value="ble">BLE</option>
          </select>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="field sm:w-40"
          >
            <option value="">Tous statuts</option>
            <option value="active">Actifs</option>
            <option value="suspended">Suspendus</option>
            <option value="revoked">Révoqués</option>
            <option value="lost">Perdus</option>
          </select>
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(b) => b.id}
        />
      </Card>
    </div>
  );
}
