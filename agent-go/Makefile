# ═══════════════════════════════════════════════════════════════════
# Kaydan Edge Gateway — Makefile
# ═══════════════════════════════════════════════════════════════════
#
# Cible principal : make release
#   → Cross-compile pour Linux (amd64+arm64), Windows, macOS (Intel+ARM)
#   → Génère des binaires dans dist/
#   → Calcule les SHA256
#
# Nécessite : Go 1.22+
# ═══════════════════════════════════════════════════════════════════

BINARY  := kshield-agent
VERSION := 1.0.0
COMMIT  := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
DATE    := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")

LDFLAGS := -s -w \
           -X 'github.com/sergehoo/kshield/agent-go/cmd.Version=$(VERSION)' \
           -X 'github.com/sergehoo/kshield/agent-go/cmd.Commit=$(COMMIT)' \
           -X 'github.com/sergehoo/kshield/agent-go/cmd.BuildDate=$(DATE)'

.PHONY: help
help:
	@echo "Cibles disponibles :"
	@echo "  make deps         — Installe les dépendances Go"
	@echo "  make build        — Build local (dev)"
	@echo "  make test         — Lance les tests unitaires"
	@echo "  make release      — Cross-compile toutes les plateformes"
	@echo "  make clean        — Supprime dist/"
	@echo "  make run          — Build + lance en dev"

.PHONY: deps
deps:
	go mod tidy
	go mod download

.PHONY: build
build:
	@echo "→ Build local (native)..."
	go build -ldflags "$(LDFLAGS)" -o dist/$(BINARY) .
	@echo "✓ dist/$(BINARY) — $$(du -h dist/$(BINARY) | cut -f1)"

.PHONY: test
test:
	go test -v -race ./...

.PHONY: run
run: build
	./dist/$(BINARY) --verbose status

# ─── Cross-compile toutes plateformes cibles ────────────────────
.PHONY: release
release: clean
	@echo "═══ Cross-compilation Kaydan Edge Gateway v$(VERSION) ═══"
	@mkdir -p dist

	@echo "→ Linux amd64..."
	@GOOS=linux   GOARCH=amd64 go build -ldflags "$(LDFLAGS)" -o dist/$(BINARY)-linux-amd64 .
	@echo "→ Linux arm64 (Raspberry Pi 4/5, ARM serveurs)..."
	@GOOS=linux   GOARCH=arm64 go build -ldflags "$(LDFLAGS)" -o dist/$(BINARY)-linux-arm64 .
	@echo "→ Linux arm (Raspberry Pi 3, 32-bit)..."
	@GOOS=linux   GOARCH=arm GOARM=7 go build -ldflags "$(LDFLAGS)" -o dist/$(BINARY)-linux-armv7 .

	@echo "→ Windows amd64..."
	@GOOS=windows GOARCH=amd64 go build -ldflags "$(LDFLAGS)" -o dist/$(BINARY)-windows-amd64.exe .

	@echo "→ macOS Intel..."
	@GOOS=darwin  GOARCH=amd64 go build -ldflags "$(LDFLAGS)" -o dist/$(BINARY)-darwin-amd64 .
	@echo "→ macOS Apple Silicon..."
	@GOOS=darwin  GOARCH=arm64 go build -ldflags "$(LDFLAGS)" -o dist/$(BINARY)-darwin-arm64 .

	@echo ""
	@echo "═══ Checksums SHA256 ═══"
	@cd dist && shasum -a 256 * | tee SHA256SUMS.txt

	@echo ""
	@echo "═══ Tailles ═══"
	@ls -lh dist/ | grep -v total | grep -v SHA

.PHONY: clean
clean:
	rm -rf dist/
	go clean -cache 2>/dev/null || true

# ─── Package .deb (Linux Debian/Ubuntu) ─────────────────────────
# Nécessite dpkg-deb (préinstallé sur Debian, apt install dpkg sur autres).
.PHONY: package-deb
package-deb: build
	@echo "→ Building .deb package..."
	@mkdir -p dist/deb/DEBIAN
	@mkdir -p dist/deb/usr/bin
	@mkdir -p dist/deb/etc/systemd/system
	@cp dist/$(BINARY) dist/deb/usr/bin/
	@cp build/linux/kshield-edge.service dist/deb/etc/systemd/system/
	@cp build/linux/DEBIAN-control dist/deb/DEBIAN/control
	@sed -i "s/__VERSION__/$(VERSION)/" dist/deb/DEBIAN/control 2>/dev/null || \
	 sed -i "" "s/__VERSION__/$(VERSION)/" dist/deb/DEBIAN/control
	@dpkg-deb --build dist/deb dist/kshield-edge_$(VERSION)_amd64.deb
	@rm -rf dist/deb
	@echo "✓ dist/kshield-edge_$(VERSION)_amd64.deb"
