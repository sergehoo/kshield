import { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Loader2, InboxIcon } from "lucide-react";

export type Column<T> = {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  className?: string;
  width?: string;
};

type Props<T> = {
  columns: Column<T>[];
  rows?: T[];
  loading?: boolean;
  emptyLabel?: string;
  rowKey: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  className?: string;
};

export function DataTable<T>({
  columns,
  rows = [],
  loading,
  emptyLabel = "Aucune donnée",
  rowKey,
  onRowClick,
  className,
}: Props<T>) {
  return (
    <div className={cn("overflow-x-auto rounded-xl border border-surface-border", className)}>
      <table className="table w-full">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                style={c.width ? { width: c.width } : undefined}
                className={c.className}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={columns.length} className="py-8 text-center text-ink-muted">
                <Loader2 className="w-5 h-5 animate-spin mx-auto" />
              </td>
            </tr>
          )}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="py-10 text-center text-ink-muted">
                <InboxIcon className="w-6 h-6 mx-auto mb-2 opacity-50" />
                <div className="text-sm">{emptyLabel}</div>
              </td>
            </tr>
          )}
          {!loading &&
            rows.map((row) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={onRowClick ? "cursor-pointer" : undefined}
              >
                {columns.map((c) => (
                  <td key={c.key} className={c.className}>
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}
