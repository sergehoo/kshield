// Package tray — Icône barre système (System Tray) cross-platform.
//
// Utilise github.com/getlantern/systray qui gère :
//   - macOS Status Bar (NSStatusItem)
//   - Linux (AppIndicator / GTK)
//   - Windows (NotifyIcon)
//
// Le tray fait tourner sa boucle sur le thread principal (getlantern/systray
// requires this). Pour cette raison, l'agent lance le tray dans main() et
// le service en goroutine, PAS l'inverse.
//
// Nouvelle commande CLI : `kshield-agent tray` — lance le tray + le service.
package tray

import (
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"sync/atomic"
	"time"

	"github.com/getlantern/systray"
	"github.com/rs/zerolog/log"
)

// Status représente l'état affiché.
type Status int

const (
	StatusUnknown Status = iota
	StatusConnected
	StatusDegraded
	StatusDisconnected
)

// Controller expose une API pour piloter le tray depuis l'app.
// Les setters sont thread-safe (atomic + Channel dans systray).
type Controller struct {
	title       string
	setStatus   chan Status
	stop        chan struct{}
	currentSt   atomic.Int32
	openConfig  func()
	openLogs    func()
	openWebURL  string   // URL admin Kaydan Shield à ouvrir
}

// NewController crée un controller. openConfig/openLogs sont des callbacks
// invoqués au clic sur le menu correspondant.
func NewController(title string, adminURL string) *Controller {
	return &Controller{
		title:      title,
		setStatus:  make(chan Status, 10),
		stop:       make(chan struct{}),
		openWebURL: adminURL,
	}
}

// Run bloque le thread appelant (systray requiert main-thread).
// L'appelant doit lancer son service en goroutine séparée AVANT Run().
func (c *Controller) Run() {
	systray.Run(c.onReady, c.onExit)
}

// SetStatus met à jour l'icône + tooltip depuis n'importe quelle goroutine.
func (c *Controller) SetStatus(s Status) {
	select {
	case c.setStatus <- s:
	default:
		// Channel plein — le tray n'est pas prêt, on met à jour atomiquement
		c.currentSt.Store(int32(s))
	}
}

// Stop demande la fermeture propre du tray.
func (c *Controller) Stop() {
	close(c.stop)
	systray.Quit()
}

// ═══════════════════════════════════════════════════════════════════
// Callbacks systray
// ═══════════════════════════════════════════════════════════════════

func (c *Controller) onReady() {
	systray.SetTemplateIcon(iconUnknown, iconUnknown) // fallback si couleurs KO
	systray.SetTitle("")
	systray.SetTooltip(c.title + " — état: initialisation")

	mStatus := systray.AddMenuItem("État : inconnu", "État de la gateway")
	mStatus.Disable()
	systray.AddSeparator()

	mOpen := systray.AddMenuItem("Ouvrir Kaydan Shield", "Ouvre l'admin web")
	mConfig := systray.AddMenuItem("Ouvrir dossier config", "Explorer /etc/kshield-edge")
	mLogs := systray.AddMenuItem("Voir les logs", "Tail des logs récents")
	systray.AddSeparator()

	mRestart := systray.AddMenuItem("Redémarrer service", "Redémarre kshield-edge")
	systray.AddSeparator()

	mAbout := systray.AddMenuItem("À propos", "Kaydan Edge Gateway")
	mAbout.Disable()
	mQuit := systray.AddMenuItem("Quitter", "Ferme le tray uniquement (le service continue)")

	// Boucle status + interactions
	go func() {
		for {
			select {
			case <-c.stop:
				return

			case s := <-c.setStatus:
				c.currentSt.Store(int32(s))
				icon, tooltip, label := statusMeta(s)
				systray.SetIcon(icon)
				systray.SetTooltip(c.title + " — " + tooltip)
				mStatus.SetTitle(label)

			case <-mOpen.ClickedCh:
				openBrowser(c.openWebURL)
			case <-mConfig.ClickedCh:
				openConfigDir()
			case <-mLogs.ClickedCh:
				openLogsDir()
			case <-mRestart.ClickedCh:
				restartService()
			case <-mQuit.ClickedCh:
				log.Info().Msg("Tray quit demandé — le service continue")
				systray.Quit()
				return
			}
		}
	}()

	// Initial status
	c.SetStatus(Status(c.currentSt.Load()))
}

func (c *Controller) onExit() {
	log.Info().Msg("Tray fermé")
}

// ═══════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════

// statusMeta retourne (icon_bytes, tooltip_text, menu_label) pour un état.
// Les icons sont des PNGs 32x32 embarqués (déclarés en bas du fichier).
func statusMeta(s Status) ([]byte, string, string) {
	switch s {
	case StatusConnected:
		return iconConnected, "connecté au Cloud", "État : ● Connecté"
	case StatusDegraded:
		return iconDegraded, "connexion dégradée", "État : ◐ Dégradé"
	case StatusDisconnected:
		return iconDisconnected, "hors-ligne", "État : ○ Hors ligne"
	default:
		return iconUnknown, "état inconnu", "État : ? Inconnu"
	}
}

func openBrowser(url string) {
	if url == "" {
		return
	}
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", url)
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	if err := cmd.Start(); err != nil {
		log.Warn().Err(err).Msg("open browser failed")
	}
}

func openConfigDir() {
	var path string
	switch runtime.GOOS {
	case "windows":
		path = fmt.Sprintf(`%s\KaydanEdge`, os.Getenv("ProgramData"))
	default:
		path = "/etc/kshield-edge"
	}
	openPath(path)
}

func openLogsDir() {
	var path string
	switch runtime.GOOS {
	case "windows":
		path = fmt.Sprintf(`%s\KaydanEdge\logs`, os.Getenv("ProgramData"))
	case "darwin":
		path = "/usr/local/var/log/kshield-edge"
	default:
		path = "/var/log/kshield-edge"
	}
	openPath(path)
}

func openPath(path string) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", path)
	case "windows":
		cmd = exec.Command("explorer", path)
	default:
		cmd = exec.Command("xdg-open", path)
	}
	_ = cmd.Start()
}

func restartService() {
	log.Info().Msg("Redémarrage service demandé depuis tray")
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "linux":
		cmd = exec.Command("systemctl", "restart", "kshield-edge")
	case "windows":
		cmd = exec.Command("net", "stop", "KaydanEdgeGateway")
		_ = cmd.Run()
		cmd = exec.Command("net", "start", "KaydanEdgeGateway")
	case "darwin":
		cmd = exec.Command("launchctl", "kickstart", "-k", "system/com.kaydangroupe.kshield-edge")
	}
	if cmd != nil {
		go func() {
			// Async — pas bloquant sur le tray thread
			time.Sleep(100 * time.Millisecond)
			if err := cmd.Run(); err != nil {
				log.Warn().Err(err).Msg("restart service failed")
			}
		}()
	}
}

// ═══════════════════════════════════════════════════════════════════
// Icons embarqués — PNG 32x32 avec couleur selon état
// ═══════════════════════════════════════════════════════════════════
// Ces bytes sont des PNGs minimaux — 32x32 circle avec la couleur.
// En Phase 3.2 on remplacera par les vrais logos Kaydan Shield.
//
// Génération temporaire via https://png-pixel.com ou ImageMagick :
//   convert -size 32x32 xc:'#22c55e' green.png     (connected)
//   convert -size 32x32 xc:'#f59e0b' orange.png    (degraded)
//   convert -size 32x32 xc:'#ef4444' red.png       (disconnected)
//   convert -size 32x32 xc:'#9ca3af' gray.png      (unknown)
//
// Placeholder : PNG 1x1 gris. À remplacer par vrais assets avant Phase 3 final.
var (
	// PNG 1x1 gris pour éviter que le tray ne montre rien.
	// Un vrai package doit embed des icônes 16x16 + 32x32 par couleur.
	pngPlaceholder = []byte{
		0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
		0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
		0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
		0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
		0xde, 0x00, 0x00, 0x00, 0x0c, 0x49, 0x44, 0x41,
		0x54, 0x08, 0xd7, 0x63, 0x60, 0x00, 0x00, 0x00,
		0x02, 0x00, 0x01, 0xe5, 0x27, 0xde, 0xfc, 0x00,
		0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44, 0xae,
		0x42, 0x60, 0x82,
	}
	iconConnected    = pngPlaceholder // TODO Phase 3.2 : vraie icône verte
	iconDegraded     = pngPlaceholder // TODO Phase 3.2 : vraie icône orange
	iconDisconnected = pngPlaceholder // TODO Phase 3.2 : vraie icône rouge
	iconUnknown      = pngPlaceholder // TODO Phase 3.2 : vraie icône grise
)
