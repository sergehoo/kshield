import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { format, subDays } from "date-fns";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { reportsService, sitesService } from "@/services";
import { toApiError } from "@/lib/api";
import {
  FileSpreadsheet, FileText, Download, Calendar, MapPin, Clock,
  TrendingUp, ScrollText,
} from "lucide-react";
import toast from "react-hot-toast";

/**
 * Page Reports — exports Excel/PDF des principales données métier.
 * Chaque rapport est un composant `ReportCard` avec ses propres filtres.
 */
export function ReportsPage() {
  return (
    <div>
      <PageHeader
        title="Rapports & exports"
        subtitle="Exports Excel / PDF des données présence, heures supplémentaires, événements"
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <AttendanceReport />
        <OvertimeReport />
        <EventsReport />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function SiteSelect({
  value, onChange,
}: {
  value: number | undefined;
  onChange: (v: number | undefined) => void;
}) {
  const { data } = useQuery({
    queryKey: ["sites", "all"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
  });
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : undefined)}
      className="field"
    >
      <option value="">Tous les sites</option>
      {data?.results?.map((s: any) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </select>
  );
}

// ─────────────────────────────────────────────────────────────
// Attendance report — feuille de présence Excel/PDF
// ─────────────────────────────────────────────────────────────
function AttendanceReport() {
  const [from, setFrom] = useState(format(subDays(new Date(), 7), "yyyy-MM-dd"));
  const [to, setTo] = useState(format(new Date(), "yyyy-MM-dd"));
  const [site, setSite] = useState<number | undefined>();

  const excelMut = useMutation({
    mutationFn: () =>
      reportsService.attendanceExcel({ date_from: from, date_to: to, site }),
    onSuccess: (r) => {
      downloadBlob(r.data, `presence_${from}_${to}.xlsx`);
      toast.success("Export Excel généré");
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const pdfMut = useMutation({
    mutationFn: () =>
      reportsService.attendancePdf({ date_from: from, date_to: to, site }),
    onSuccess: (r) => {
      downloadBlob(r.data, `presence_${from}_${to}.pdf`);
      toast.success("Export PDF généré");
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-brand-500" /> Feuille de présence
        </span>
      }
      subtitle="Détail journalier par ouvrier — Excel ou PDF"
    >
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Du"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
          <Input
            label="Au"
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>
        <label className="block">
          <span className="text-xs font-medium text-ink-muted">Chantier</span>
          <div className="mt-1.5">
            <SiteSelect value={site} onChange={setSite} />
          </div>
        </label>

        <div className="flex gap-2 pt-2">
          <Button
            variant="primary"
            className="flex-1 justify-center"
            leftIcon={<FileSpreadsheet className="w-4 h-4" />}
            onClick={() => excelMut.mutate()}
            loading={excelMut.isPending}
          >
            Export Excel
          </Button>
          <Button
            variant="ghost"
            className="flex-1 justify-center"
            leftIcon={<FileText className="w-4 h-4" />}
            onClick={() => pdfMut.mutate()}
            loading={pdfMut.isPending}
          >
            Export PDF
          </Button>
        </div>
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────
// Overtime report — heures supp hebdo
// ─────────────────────────────────────────────────────────────
function OvertimeReport() {
  const [weekStart, setWeekStart] = useState(
    format(subDays(new Date(), 7), "yyyy-MM-dd"),
  );
  const [site, setSite] = useState<number | undefined>();

  const excelMut = useMutation({
    mutationFn: () => reportsService.overtimeExcel({ week_start: weekStart, site }),
    onSuccess: (r) => {
      downloadBlob(r.data, `heures_supp_${weekStart}.xlsx`);
      toast.success("Export généré");
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-warn" /> Heures supplémentaires
        </span>
      }
      subtitle="Calcul hebdomadaire par ouvrier (règles overtime)"
    >
      <div className="space-y-3">
        <Input
          label="Début de semaine"
          type="date"
          value={weekStart}
          onChange={(e) => setWeekStart(e.target.value)}
        />
        <label className="block">
          <span className="text-xs font-medium text-ink-muted">Chantier</span>
          <div className="mt-1.5">
            <SiteSelect value={site} onChange={setSite} />
          </div>
        </label>
        <Button
          className="w-full justify-center"
          leftIcon={<Download className="w-4 h-4" />}
          onClick={() => excelMut.mutate()}
          loading={excelMut.isPending}
        >
          Télécharger Excel
        </Button>
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────
// Events report — journal des scans
// ─────────────────────────────────────────────────────────────
function EventsReport() {
  const [from, setFrom] = useState(format(subDays(new Date(), 1), "yyyy-MM-dd"));
  const [to, setTo] = useState(format(new Date(), "yyyy-MM-dd"));
  const [site, setSite] = useState<number | undefined>();

  const mut = useMutation({
    mutationFn: () =>
      reportsService.eventsExcel({
        timestamp__gte: from,
        timestamp__lte: to,
        site,
      }),
    onSuccess: (r) => {
      downloadBlob(r.data, `events_${from}_${to}.xlsx`);
      toast.success("Export généré");
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <ScrollText className="w-4 h-4 text-info" /> Journal des événements
        </span>
      }
      subtitle="Tous les scans (badge, face, RFID) avec décision entrée/sortie"
    >
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Du" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          <Input label="Au" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <label className="block">
          <span className="text-xs font-medium text-ink-muted">Chantier</span>
          <div className="mt-1.5">
            <SiteSelect value={site} onChange={setSite} />
          </div>
        </label>
        <Button
          className="w-full justify-center"
          leftIcon={<Download className="w-4 h-4" />}
          onClick={() => mut.mutate()}
          loading={mut.isPending}
        >
          Télécharger Excel
        </Button>
      </div>
    </Card>
  );
}
