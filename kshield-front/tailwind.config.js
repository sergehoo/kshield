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
        ok:     "#22c55e",
        warn:   "#f59e0b",
        danger: "#f87171",
        info:   "#38bdf8",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 6px 24px rgb(0 0 0 / var(--shadow-strength, 0.35))",
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
