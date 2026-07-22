/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Palette de marque (identique en light/dark)
        brand: {
          50: "#fff7ed",
          100: "#ffedd5",
          400: "#fb923c",
          500: "#f97316",
          600: "#ea580c",
          700: "#c2410c",
          ink: "rgb(var(--c-brand-ink) / <alpha-value>)",
        },
        // Surfaces & texte — pilotées par CSS variables (voir styles/index.css)
        // rgb(<var> / <alpha-value>) permet à Tailwind d'appliquer bg-surface/70 etc.
        surface: {
          DEFAULT: "rgb(var(--c-surface) / <alpha-value>)",
          soft:    "rgb(var(--c-surface-soft) / <alpha-value>)",
          card:    "rgb(var(--c-surface-card) / <alpha-value>)",
          border:  "rgb(var(--c-surface-border) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--c-ink) / <alpha-value>)",
          muted:   "rgb(var(--c-ink-muted) / <alpha-value>)",
          soft:    "rgb(var(--c-ink-soft) / <alpha-value>)",
        },
        // Sémantiques
        ok:      "rgb(var(--c-ok) / <alpha-value>)",
        warn:    "rgb(var(--c-warn) / <alpha-value>)",
        warning: "rgb(var(--c-warn) / <alpha-value>)",
        danger:  "rgb(var(--c-danger) / <alpha-value>)",
        info:    "rgb(var(--c-info) / <alpha-value>)",
        success: "rgb(var(--c-ok) / <alpha-value>)",
        "on-ok":     "rgb(var(--c-on-ok) / <alpha-value>)",
        "on-warn":   "rgb(var(--c-on-warn) / <alpha-value>)",
        "on-danger": "rgb(var(--c-on-danger) / <alpha-value>)",
        "on-info":   "rgb(var(--c-on-info) / <alpha-value>)",
        obsidian: {
          DEFAULT: "#111820",
          hover: "#202a36",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 6px 24px rgb(0 0 0 / var(--shadow-strength, 0.35))",
        // Ombre très légère style Dappr — juste un lift subtil
        dappr: "0 2px 12px rgb(0 0 0 / var(--shadow-strength, 0.08))",
      },
      borderRadius: {
        // Coins ultra-arrondis pour cards style Dappr
        "4xl": "2rem",
        "5xl": "2.5rem",
      },
      animation: {
        "pulse-dot": "pulse-dot 1.4s ease-in-out infinite",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.4", transform: "scale(0.85)" },
        },
      },
    },
  },
  plugins: [],
};
