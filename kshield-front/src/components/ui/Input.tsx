import { forwardRef, InputHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";
import { AlertCircle } from "lucide-react";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
  /** Message d'erreur — affiché en rouge sous l'input. */
  error?: string;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  /** Marque le label avec un astérisque rouge quand true (visuel obligatoire). */
  requiredMark?: boolean;
};

export const Input = forwardRef<HTMLInputElement, Props>(
  ({ label, hint, error, leftIcon, rightIcon, className, required, requiredMark, ...rest }, ref) => {
    const showRequired = required || requiredMark;
    return (
      <label className="flex flex-col gap-1.5">
        {label && (
          <span className="text-xs font-medium text-ink-muted flex items-center gap-0.5">
            {label}
            {showRequired && <span className="text-danger" aria-hidden>*</span>}
          </span>
        )}
        <span className="relative flex items-center">
          {leftIcon && (
            <span className="absolute left-3 text-ink-soft pointer-events-none">
              {leftIcon}
            </span>
          )}
          <input
            ref={ref}
            required={required}
            className={cn(
              // Style Dappr : rounded-2xl, fond soft, pas de bordure par défaut
              "w-full px-4 py-3 rounded-2xl bg-surface-soft text-ink placeholder-ink-soft",
              "focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:bg-surface-card",
              "transition-all border",
              error
                ? "border-danger/60 focus:ring-danger/30 focus:border-danger"
                : "border-transparent",
              leftIcon && "pl-11",
              rightIcon && "pr-11",
              className,
            )}
            {...rest}
          />
          {rightIcon && (
            <span className="absolute right-3 text-ink-soft">{rightIcon}</span>
          )}
        </span>
        {error && (
          <span className="text-xs text-danger flex items-start gap-1">
            <AlertCircle className="w-3 h-3 shrink-0 mt-0.5" />
            <span>{error}</span>
          </span>
        )}
        {!error && hint && (
          <span className="text-xs text-ink-soft">{hint}</span>
        )}
      </label>
    );
  },
);
Input.displayName = "Input";
