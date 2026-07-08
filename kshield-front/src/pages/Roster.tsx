import { useState, useMemo } from "react";
import { format, addDays, startOfWeek } from "date-fns";
import { fr } from "date-fns/locale";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { rosterService, sitesService } from "@/services";
import { ChevronLeft, ChevronRight, Calendar as CalIcon } from "lucide-react";

/**
 * Planning hebdomadaire (roster) — vue grille jour x ouvriers.
 */
export function RosterPage() {
  const [weekStart, setWeekStart] = useState<Date>(
    startOfWeek(new Date(), { weekStartsOn: 1 }),
  );
  const [siteId, setSiteId] = useState<number | undefined>();

  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)),
    [weekStart],
  );

  const { data: sites } = useQuery({
    queryKey: ["sites", "for-roster"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
  });

  const { data, isLoading } = useQuery({
    queryKey: [
      "roster",
      format(weekStart, "yyyy-MM-dd"),
      format(addDays(weekStart, 6), "yyyy-MM-dd"),
      siteId,
    ],
    queryFn: async () =>
      (
        await rosterService.list({
          date__gte: format(weekStart, "yyyy-MM-dd"),
          date__lte: format(addDays(weekStart, 6), "yyyy-MM-dd"),
          site: siteId,
          page_size: 500,
        })
      ).data,
  });

  // Group by (worker/employee, date)
  const grid = useMemo(() => {
    const map = new Map<
      string,
      { name: string; days: Record<string, any> }
    >();
    (data?.results || []).forEach((r: any) => {
      const holder =
        r.worker_name || r.employee_name || r.worker || r.employee || "—";
      const dateKey = r.date;
      if (!map.has(holder))
        map.set(holder, { name: holder, days: {} });
      map.get(holder)!.days[dateKey] = r;
    });
    return Array.from(map.values());
  }, [data]);

  return (
    <div>
      <PageHeader
        title="Planning hebdomadaire"
        subtitle={`Semaine du ${format(weekStart, "d MMMM yyyy", { locale: fr })}`}
        actions={
          <div className="flex items-center gap-2">
            <select
              value={siteId ?? ""}
              onChange={(e) => setSiteId(e.target.value ? Number(e.target.value) : undefined)}
              className="field w-48"
            >
              <option value="">Tous chantiers</option>
              {sites?.results?.map((s: any) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setWeekStart((w) => addDays(w, -7))}
              leftIcon={<ChevronLeft className="w-4 h-4" />}
            >
              Précédente
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                setWeekStart(startOfWeek(new Date(), { weekStartsOn: 1 }))
              }
              leftIcon={<CalIcon className="w-4 h-4" />}
            >
              Cette semaine
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setWeekStart((w) => addDays(w, 7))}
              rightIcon={<ChevronRight className="w-4 h-4" />}
            >
              Suivante
            </Button>
          </div>
        }
      />

      <Card padded={false}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border">
                <th className="text-left px-4 py-3 text-xs uppercase tracking-wider text-ink-muted sticky left-0 bg-surface-card">
                  Ouvrier / Employé
                </th>
                {days.map((d) => (
                  <th
                    key={d.toISOString()}
                    className="px-3 py-3 text-xs uppercase tracking-wider text-ink-muted text-center"
                  >
                    {format(d, "EEE d/M", { locale: fr })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={8} className="text-center py-10 text-ink-muted">
                    Chargement…
                  </td>
                </tr>
              )}
              {!isLoading && grid.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center py-10 text-ink-muted">
                    Aucun planning pour cette semaine
                  </td>
                </tr>
              )}
              {grid.map((row) => (
                <tr key={row.name} className="border-b border-surface-border/50 hover:bg-surface-soft/40">
                  <td className="px-4 py-3 text-sm font-medium text-ink sticky left-0 bg-surface-card">
                    {row.name}
                  </td>
                  {days.map((d) => {
                    const cell = row.days[format(d, "yyyy-MM-dd")];
                    return (
                      <td key={d.toISOString()} className="px-3 py-2 text-center">
                        {cell ? (
                          <Badge tone={cell.type === "off" ? "muted" : "brand"}>
                            {cell.type === "off"
                              ? "Repos"
                              : cell.shift_label || "Présent"}
                          </Badge>
                        ) : (
                          <span className="text-ink-soft text-xs">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
