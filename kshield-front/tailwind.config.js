/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // KAYDAN SHIELD palette (aligned with Django templates layout/base.html)
        brand: {
          50: "#fff7ed",
          100: "#ffedd5",
          400: "#fb923c",
          500: "#f97316",
          600: "#ea580c",
          700: "#c2410c",
        },
        surface: {
          DEFAULT: "#0b0f14",
          soft: "#111823",
          card: "#0f1620",
          border: "rgba(148,163,184,0.14)",
        },
        ink: {
          DEFAULT: "#e5e7eb",
          muted: "#94a3b8",
          soft: "#64748b",
        },
        ok: "#22c55e",
        warn: "#f59e0b",
        danger: "#f87171",
        info: "#38bdf8",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 6px 24px rgba(0,0,0,0.35)",
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
