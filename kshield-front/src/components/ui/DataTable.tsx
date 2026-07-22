import { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { InboxIcon, ChevronLeft, ChevronRight } from "lucide-react";

export type Column<T> = {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  className?: string;
  width?: string;
  sortable?: boolean;
};

type PaginationProps = {
  count: number;
  pageSize: number;
  page: number;
  onPageChange: (page: number) => void;
};

type Props<T> = {
  columns: Column<T>[];
  rows?: T[];
  loading?: boolean;
  emptyLabel?: string;
  emptyIcon?: ReactNode;
  rowKey: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  className?: string;
  pagination?: PaginationProps;
  skeletonRows?: number;
};

export function DataTable<T>({
  columns,
  rows = [],
  loading,
  emptyLabel = "Aucune donnée",
  emptyIcon,
  rowKey,
  onRowClick,
  className,
  pagination,
  skeletonRows = 6,
}: Props<T>) {
  return (
    <div className={cn("rounded-xl border border-surface-border bg-surface-card overflow-hidden", className)}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-soft/55">
              {columns.map((c) => (
                <th
                  key={c.key}
                  style={c.width ? { width: c.width } : undefined}
                  className={cn(
                    "text-left font-medium text-ink-muted px-4 py-3 text-xs uppercase tracking-wider border-b border-surface-border",
                    c.className,
                  )}
                >
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* Skeleton rows pendant loading */}
            {loading &&
              Array.from({ length: skeletonRows }).map((_, i) => (
                <tr key={`skel-${i}`} className="border-b border-surface-border/40">
                  {columns.map((c) => (
                    <td key={c.key} className="px-4 py-3">
                      <div
                        className="h-3 rounded bg-surface-soft animate-pulse"
                        style={{ width: `${40 + ((i + c.key.length) % 5) * 12}%` }}
                      />
                    </td>
                  ))}
                </tr>
              ))}

            {/* Empty state */}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="py-12 text-center text-ink-muted">
                  {emptyIcon || (
                    <InboxIcon className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  )}
                  <div className="text-sm">{emptyLabel}</div>
                </td>
              </tr>
            )}

            {/* Rows */}
            {!loading &&
              rows.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={cn(
                    "border-b border-surface-border/40 transition-colors",
                    onRowClick && "cursor-pointer hover:bg-surface-soft/40",
                  )}
                >
                  {columns.map((c) => (
                    <td key={c.key} className={cn("px-4 py-3", c.className)}>
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pagination && pagination.count > pagination.pageSize && (
        <Pagination {...pagination} />
      )}
    </div>
  );
}

function Pagination({ count, pageSize, page, onPageChange }: PaginationProps) {
  const totalPages = Math.ceil(count / pageSize);
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, count);

  const canPrev = page > 1;
  const canNext = page < totalPages;

  return (
    <div className="flex items-center justify-between px-4 py-2.5 border-t border-surface-border text-xs">
      <div className="text-ink-muted">
        <strong>{from}</strong>–<strong>{to}</strong> sur <strong>{count}</strong>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => canPrev && onPageChange(page - 1)}
          disabled={!canPrev}
          className={cn(
            "p-1.5 rounded-md",
            canPrev ? "hover:bg-surface-soft text-ink" : "text-ink-soft cursor-not-allowed",
          )}
          aria-label="Précédent"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="tabular-nums text-ink-muted">
          {page} / {totalPages}
        </span>
        <button
          onClick={() => canNext && onPageChange(page + 1)}
          disabled={!canNext}
          className={cn(
            "p-1.5 rounded-md",
            canNext ? "hover:bg-surface-soft text-ink" : "text-ink-soft cursor-not-allowed",
          )}
          aria-label="Suivant"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
