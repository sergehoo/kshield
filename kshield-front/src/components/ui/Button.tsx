import { ButtonHTMLAttributes, forwardRef, ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "ghost" | "danger" | "outline" | "secondary" | "dark" | "invert";
type Size = "sm" | "md" | "lg";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
};

// Style Dappr : boutons noirs pleins, coins arrondis prononcés (rounded-xl)
const variantMap: Record<Variant, string> = {
  primary:   "bg-brand-500 hover:bg-brand-600 text-white",
  dark:      "bg-ink hover:bg-ink/85 text-white",
  invert:    "bg-white hover:bg-white/90 text-ink",
  ghost:     "bg-transparent text-ink hover:bg-ink/5",
  secondary: "bg-surface-soft hover:bg-surface-soft/70 text-ink",
  outline:   "border-2 border-ink/10 text-ink hover:bg-ink/5",
  danger:    "bg-danger/90 hover:bg-danger text-white",
};

const sizeMap: Record<Size, string> = {
  sm: "px-3 py-1.5 text-xs rounded-lg",
  md: "px-4 py-2.5 text-sm rounded-xl",
  lg: "px-6 py-3.5 text-base rounded-2xl",
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
        "inline-flex items-center gap-2 font-medium transition-all",
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
