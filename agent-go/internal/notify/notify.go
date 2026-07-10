// Package notify — Notifications desktop cross-platform.
//
// Utilise gen2brain/beeep pour :
//   - macOS  : UserNotifications (bundle native)
//   - Windows: Toast notifications (Windows 10+)
//   - Linux  : libnotify (notify-osd, dunst, mako, etc.)
//
// Ces notifications servent à alerter l'admin sur des événements critiques
// depuis l'agent tournant sur son poste local :
//   - Cloud déconnecté depuis > 5 min
//   - Device tamper détecté
//   - Update mandatory disponible
//   - Erreur d'auth (token invalide)
package notify

import (
	"sync"
	"time"

	"github.com/gen2brain/beeep"
	"github.com/rs/zerolog/log"
)

// Level détermine la sévérité + icône affichée.
type Level int

const (
	LevelInfo Level = iota
	LevelWarning
	LevelError
	LevelSuccess
)

// Notifier expose l'API de notification avec throttling (évite le spam).
type Notifier struct {
	appName string
	mu      sync.Mutex
	lastAt  map[string]time.Time
	// MinInterval : intervalle minimum entre deux notifications avec le
	// même throttleKey. Défaut 60s.
	MinInterval time.Duration
}

// New crée un Notifier.
func New(appName string) *Notifier {
	return &Notifier{
		appName:     appName,
		lastAt:      make(map[string]time.Time),
		MinInterval: 60 * time.Second,
	}
}

// Notify émet une notification. throttleKey est utilisé pour dédupliquer :
// si une notif avec cette clé a été émise récemment, on skippe.
// Passer "" pour désactiver le throttling.
func (n *Notifier) Notify(level Level, title, message, throttleKey string) {
	if throttleKey != "" {
		n.mu.Lock()
		last, exists := n.lastAt[throttleKey]
		if exists && time.Since(last) < n.MinInterval {
			n.mu.Unlock()
			log.Debug().Str("key", throttleKey).Msg("Notify throttled")
			return
		}
		n.lastAt[throttleKey] = time.Now()
		n.mu.Unlock()
	}

	// Formatage titre avec préfixe app
	fullTitle := n.appName
	if title != "" {
		fullTitle = n.appName + " — " + title
	}

	var err error
	switch level {
	case LevelError:
		err = beeep.Alert(fullTitle, message, "")
	case LevelSuccess:
		err = beeep.Notify(fullTitle, "✓ "+message, "")
	case LevelWarning:
		err = beeep.Notify(fullTitle, "⚠ "+message, "")
	default:
		err = beeep.Notify(fullTitle, message, "")
	}
	if err != nil {
		log.Debug().Err(err).Msg("Notify failed (support desktop?)")
	}
}

// Convenience wrappers ─────────────────────────────────────────────
func (n *Notifier) Info(title, msg string) {
	n.Notify(LevelInfo, title, msg, "")
}

func (n *Notifier) Warn(title, msg string) {
	n.Notify(LevelWarning, title, msg, title)
}

func (n *Notifier) Error(title, msg string) {
	n.Notify(LevelError, title, msg, title)
}

func (n *Notifier) Success(title, msg string) {
	n.Notify(LevelSuccess, title, msg, "")
}

// Alerts métier prédéfinies ────────────────────────────────────────
func (n *Notifier) CloudDisconnected(duration time.Duration) {
	n.Notify(LevelError,
		"Cloud déconnecté",
		"Aucune connexion depuis "+duration.Round(time.Second).String()+
			". Les events sont mis en file locale.",
		"cloud_disconnected",
	)
}

func (n *Notifier) DeviceTamper(deviceID string) {
	n.Notify(LevelError,
		"Sabotage détecté",
		"Le device "+deviceID+" signale une tentative de sabotage.",
		"tamper_"+deviceID,
	)
}

func (n *Notifier) UpdateAvailable(currentVer, newVer string, mandatory bool) {
	msg := "Version " + newVer + " disponible (actuel: " + currentVer + ")"
	level := LevelInfo
	if mandatory {
		msg = "⚡ Mise à jour OBLIGATOIRE : " + msg
		level = LevelWarning
	}
	n.Notify(level, "Update disponible", msg, "update_"+newVer)
}

func (n *Notifier) AuthFailed() {
	n.Notify(LevelError,
		"Authentification refusée",
		"Le cloud a rejeté les credentials. Vérifier config ou révocation.",
		"auth_failed",
	)
}

func (n *Notifier) Reconnected() {
	n.Notify(LevelSuccess,
		"Cloud reconnecté",
		"La connexion est rétablie.",
		"reconnected",
	)
}
