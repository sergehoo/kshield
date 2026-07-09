import { ButtonHTMLAttributes, forwardRef, ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "ghost" | "danger" | "outline" | "secondary";
type Size = "sm" | "md" | "lg";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
};

const variantMap: Record<Variant, string> = {
  primary: "bg-brand-500 hover:bg-brand-600 text-white shadow-lg shadow-brand-500/20",
  ghost: "border border-surface-border text-ink hover:bg-surface-soft",
  danger: "bg-danger/90 hover:bg-danger text-white",
  outline: "border border-brand-500/40 text-brand-400 hover:bg-brand-500/10",
  secondary: "bg-surface-soft hover:bg-surface-hover text-ink border border-surface-border",
};

const sizeMap: Record<Size, string> = {
  sm: "px-2.5 py-1.5 text-xs",
  md: "px-3.5 py-2 text-sm",
  lg: "px-5 py-3 text-base",
};

export const Button = forwardRef<HTMLButtonElement, Props>(
  (
    {
      variant = "primary",
      size = "md",
      loading,
      leftIcon,
      rightIcon,
      className,
      children,
      disabled,
      ...rest
    },
    ref,
  ) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center gap-2 rounded-lg font-medium transition-all",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        variantMap[variant],
        sizeMap[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : leftIcon}
      {children}
      {rightIcon}
    </button>
  ),
);
Button.displayName = "Button";
