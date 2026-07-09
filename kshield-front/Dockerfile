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
# Healthcheck : vérif TCP simple sur le port 80 via /dev/tcp (bash) ou nc.
# Assez robuste — pas de dépendance à wget/curl, marche partout dans BusyBox.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD sh -c "netstat -tln 2>/dev/null | grep -q ':80 ' || exit 1"
CMD ["nginx", "-g", "daemon off;"]
