# ═══════════════════════════════════════════════════════════════════
# Kaydan Edge Gateway — Multi-stage Dockerfile
# ═══════════════════════════════════════════════════════════════════
#
# Build stage : compile le binaire statique Go
# Runtime stage : image debian slim minimale (~50 MB avec le binaire)
#
# Utilisation :
#   docker build -t kshield-edge:latest .
#   docker run -v $(pwd)/config:/etc/kshield-edge:ro kshield-edge:latest
# ═══════════════════════════════════════════════════════════════════

# ─── Stage 1 : build ─────────────────────────────────────────────
FROM golang:1.22-alpine AS builder

WORKDIR /build

# Cache-friendly : deps d'abord
COPY go.mod go.sum ./
RUN go mod download

# Sources
COPY . .

ARG VERSION=1.0.0-docker
ARG COMMIT=unknown
ARG BUILD_DATE=unknown

RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags "-s -w \
        -X 'github.com/sergehoo/kshield/agent-go/cmd.Version=${VERSION}' \
        -X 'github.com/sergehoo/kshield/agent-go/cmd.Commit=${COMMIT}' \
        -X 'github.com/sergehoo/kshield/agent-go/cmd.BuildDate=${BUILD_DATE}'" \
    -o /out/kshield-agent .

# ─── Stage 2 : runtime ───────────────────────────────────────────
FROM debian:bookworm-slim AS runtime

# arp + ca-certificates pour TLS + iputils pour ping
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    net-tools \
    iproute2 \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# User non-root pour les bonnes pratiques
RUN groupadd -r kshield-edge && \
    useradd -r -g kshield-edge -s /usr/sbin/nologin kshield-edge

# Dossiers standard
RUN mkdir -p /etc/kshield-edge /var/lib/kshield-edge /var/log/kshield-edge && \
    chown -R kshield-edge:kshield-edge /var/lib/kshield-edge /var/log/kshield-edge

COPY --from=builder /out/kshield-agent /usr/bin/kshield-agent
RUN chmod +x /usr/bin/kshield-agent

# Note : scan_network via ARP nécessite CAP_NET_RAW → docker run --cap-add=NET_RAW
USER kshield-edge
WORKDIR /var/lib/kshield-edge

ENV KSHIELD_CONFIG_FILE=/etc/kshield-edge/kshield-agent.toml
ENV KSHIELD_QUEUE_PATH=/var/lib/kshield-edge/queue.db

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD ["/usr/bin/kshield-agent", "status"]

ENTRYPOINT ["/usr/bin/kshield-agent"]
CMD ["run"]
