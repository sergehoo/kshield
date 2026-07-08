import { useState } from "react";
import { format } from "date-fns";
import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { DataTable, Column } from "@/components/ui/DataTable";
import { KpiCard } from "@/components/KpiCard";
import { attendanceService } from "@/services";
import { fmtDate, fmtTime, fmtNumber } from "@/lib/format";
import type { AttendanceDay } from "@/types/api";
import { Users, Clock, AlertTriangle, TrendingUp } from "lucide-react";

export function AttendancePage() {
  const [date, setDate] = useState(format(new Date(), "yyyy-MM-dd"));

  const days = useLive(
    ["attendance", "days", date],
    async () =>
      (
        await attendanceService.daysList({
          date,
          page_size: 500,
          ordering: "-first_in",
        })
      ).data,
    { intervalMs: 30_000 },
  );

  const summary = useLive(
    ["attendance", "summary", date],
    async () => (await attendanceService.todaySummary()).data,
    { intervalMs: 30_000 },
  );

  const columns: Column<AttendanceDay>[] = [
    {
      key: "worker",
      header: "Ouvrier",
      render: (d) =>
        typeof d.worker === "object" ? (
          <span className="text-sm font-medium text-ink">
            {d.worker?.full_name}
          </span>
        ) : (
          `#${d.worker}`
        ),
    },
    {
      key: "first_in",
      header: "Entrée",
      render: (d) => (
        <span className="text-sm font-mono">{d.first_in ? fmtTime(d.first_in) : "—"}</span>
      ),
    },
    {
      key: "last_out",
      header: "Sortie",
      render: (d) => (
        <span className="text-sm font-mono">{d.last_out ? fmtTime(d.last_out) : "—"}</span>
      ),
    },
    {
      key: "worked",
      header: "Temps travaillé",
      render: (d) => {
        const h = Math.floor((d.worked_minutes || 0) / 60);
        const m = (d.worked_minutes || 0) % 60;
        return <span className="text-sm">{h}h{m.toString().padStart(2, "0")}</span>;
      },
    },
    {
      key: "overtime",
      header: "Heures supp",
      render: (d) =>
        d.overtime_minutes ? (
          <span className="text-sm text-warn">{Math.round(d.overtime_minutes / 60 * 10) / 10}h</span>
        ) : (
          <span className="text-ink-soft">—</span>
        ),
    },
    {
      key: "status",
      header: "Statut",
      render: (d) => (
        <Badge
          tone={
            d.status === "present"
              ? "ok"
              : d.status === "late"
              ? "warn"
              : d.status === "absent"
              ? "danger"
              : "muted"
          }
          dot
        >
          {d.status || "—"}
        </Badge>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Feuille de présence"
        subtitle={`Journée du ${fmtDate(date)}`}
        live
        actions={
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="field w-auto"
          />
        }
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <KpiCard
          label="Présents"
          value={fmtNumber(summary.data?.present_count)}
          icon={<Users className="w-5 h-5" />}
          accent="ok"
          loading={summary.isLoading}
        />
        <KpiCard
          label="Retards"
          value={fmtNumber(summary.data?.late_count)}
          icon={<AlertTriangle className="w-5 h-5" />}
          accent="warn"
          loading={summary.isLoading}
        />
        <KpiCard
          label="Absents"
          value={fmtNumber(summary.data?.absent_count)}
          icon={<Clock className="w-5 h-5" />}
          accent="danger"
          loading={summary.isLoading}
        />
        <KpiCard
          label="Heures supp"
          value={
            summary.data?.total_overtime_minutes
              ? `${Math.round(summary.data.total_overtime_minutes / 60)}h`
              : "0h"
          }
          icon={<TrendingUp className="w-5 h-5" />}
          accent="info"
          loading={summary.isLoading}
        />
      </div>

      <Card padded={false}>
        <DataTable
          columns={columns}
          rows={days.data?.results || []}
          loading={days.isLoading}
          rowKey={(d) => d.id}
          emptyLabel="Aucune donnée pour cette date"
        />
      </Card>
    </div>
  );
}
