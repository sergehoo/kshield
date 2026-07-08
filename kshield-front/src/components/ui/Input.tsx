import { forwardRef, InputHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
  error?: string;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
};

export const Input = forwardRef<HTMLInputElement, Props>(
  ({ label, hint, error, leftIcon, rightIcon, className, ...rest }, ref) => (
    <label className="flex flex-col gap-1.5">
      {label && (
        <span className="text-xs font-medium text-ink-muted">{label}</span>
      )}
      <span className="relative flex items-center">
        {leftIcon && (
          <span className="absolute left-3 text-ink-soft pointer-events-none">
            {leftIcon}
          </span>
        )}
        <input
          ref={ref}
          className={cn(
            "w-full px-3.5 py-2.5 rounded-lg bg-surface-soft border text-ink placeholder-ink-soft",
            "focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500/60",
            "transition-all",
            error ? "border-danger/40" : "border-surface-border",
            leftIcon && "pl-10",
            rightIcon && "pr-10",
            className,
          )}
          {...rest}
        />
        {rightIcon && (
          <span className="absolute right-3 text-ink-soft">{rightIcon}</span>
        )}
      </span>
      {(error || hint) && (
        <span
          className={cn(
            "text-xs",
            error ? "text-danger" : "text-ink-soft",
          )}
        >
          {error || hint}
        </span>
      )}
    </label>
  ),
);
Input.displayName = "Input";
