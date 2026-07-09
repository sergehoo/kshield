## KAYDAN SHIELD front — Vite + React
## Build multi-stage → nginx pour servir les assets statiques.

# ── Build ──────────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# ── Runtime ────────────────────────────────────────────────────
FROM nginx:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Écoute sur 80 (Docker direct) + 3000 (Dokploy / conventions PaaS)
EXPOSE 80 3000
# Healthcheck : busybox wget dans nginx:alpine (fiable), fallback nc si absent.
# On teste sur le port 80 uniquement — si nginx tourne, les 2 ports sont OK.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:80/ 2>/dev/null \
        || nc -z 127.0.0.1 80 \
        || exit 1
CMD ["nginx", "-g", "daemon off;"]
