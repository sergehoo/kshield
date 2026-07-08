import { ReactNode, useEffect } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";

type Props = {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
};

const sizeMap = {
  sm: "max-w-md",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
};

export function Modal({ open, onClose, title, children, footer, size = "md" }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className={cn(
          "w-full rounded-2xl border border-surface-border bg-surface-card shadow-2xl",
          sizeMap[size],
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <header className="flex items-center justify-between px-5 py-4 border-b border-surface-border">
            <h3 className="text-sm font-semibold text-ink">{title}</h3>
            <button
              onClick={onClose}
              className="p-1 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink"
              aria-label="Fermer"
            >
              <X className="w-4 h-4" />
            </button>
          </header>
        )}
        <div className="p-5">{children}</div>
        {footer && (
          <footer className="px-5 py-3 border-t border-surface-border/60 flex justify-end gap-2">
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}
