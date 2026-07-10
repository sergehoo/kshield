// Package drivers — Manager : orchestrateur des drivers actifs.
package drivers

import (
	"context"
	"sync"
	"time"

	"github.com/rs/zerolog/log"
)

// Manager pilote la vie des drivers actifs :
//   - Lifecycle : Connect → ReadEvents → Restart auto si crash
//   - Route les events entrants vers le sink global (queue offline + MQTT)
//   - Expose GetDriver(id) pour envoyer des commandes runtime
type Manager struct {
	sink    EventSink
	mu      sync.RWMutex
	active  map[string]*managedDriver
}

type managedDriver struct {
	Target Target
	Driver Driver
	cancel context.CancelFunc
	status string // "connected" / "connecting" / "error"
	lastErr error
	events  int64
}

// NewManager crée un manager avec le sink partagé.
func NewManager(sink EventSink) *Manager {
	return &Manager{
		sink:   sink,
		active: make(map[string]*managedDriver),
	}
}

// Start lance un driver pour un Target donné. Non-bloquant.
// L'agent doit appeler Start() pour chaque équipement configuré.
func (m *Manager) Start(ctx context.Context, target Target) error {
	drv, err := BuildDriver(target)
	if err != nil {
		return err
	}

	dctx, cancel := context.WithCancel(ctx)
	md := &managedDriver{
		Target: target,
		Driver: drv,
		cancel: cancel,
		status: "connecting",
	}

	m.mu.Lock()
	if existing, ok := m.active[target.ID]; ok {
		// Remplace le driver existant (redémarrage)
		existing.cancel()
	}
	m.active[target.ID] = md
	m.mu.Unlock()

	go m.runDriver(dctx, md)
	return nil
}

// Stop arrête un driver identifié par ID.
func (m *Manager) Stop(id string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if md, ok := m.active[id]; ok {
		md.cancel()
		if err := md.Driver.Disconnect(); err != nil {
			log.Debug().Err(err).Str("id", id).Msg("driver disconnect")
		}
		delete(m.active, id)
	}
}

// StopAll arrête tous les drivers actifs (shutdown).
func (m *Manager) StopAll() {
	m.mu.Lock()
	defer m.mu.Unlock()
	for id, md := range m.active {
		md.cancel()
		_ = md.Driver.Disconnect()
		delete(m.active, id)
	}
}

// GetDriver retourne le driver actif d'un ID pour exécuter une commande.
func (m *Manager) GetDriver(id string) (Driver, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	md, ok := m.active[id]
	if !ok {
		return nil, false
	}
	return md.Driver, true
}

// Status retourne un snapshot des drivers actifs.
type DriverStatus struct {
	ID     string `json:"id"`
	Vendor string `json:"vendor"`
	IP     string `json:"ip"`
	Status string `json:"status"`
	Error  string `json:"error,omitempty"`
	Events int64  `json:"events"`
}

func (m *Manager) Status() []DriverStatus {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := make([]DriverStatus, 0, len(m.active))
	for id, md := range m.active {
		ds := DriverStatus{
			ID:     id,
			Vendor: md.Target.Vendor,
			IP:     md.Target.IP,
			Status: md.status,
			Events: md.events,
		}
		if md.lastErr != nil {
			ds.Error = md.lastErr.Error()
		}
		out = append(out, ds)
	}
	return out
}

// ═══════════════════════════════════════════════════════════════════
// Boucle interne — connect + read events + auto-restart
// ═══════════════════════════════════════════════════════════════════
func (m *Manager) runDriver(ctx context.Context, md *managedDriver) {
	logger := log.With().
		Str("driver", md.Target.Vendor).
		Str("id", md.Target.ID).
		Str("ip", md.Target.IP).
		Logger()

	logger.Info().Msg("Démarrage driver")

	// Boucle de reconnexion — restart auto sur crash
	backoff := 5 * time.Second
	maxBackoff := 5 * time.Minute

	for {
		select {
		case <-ctx.Done():
			logger.Info().Msg("Driver arrêté (context annulé)")
			return
		default:
		}

		// Connect
		md.status = "connecting"
		connectCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
		if err := md.Driver.Connect(connectCtx); err != nil {
			cancel()
			md.status = "error"
			md.lastErr = err
			logger.Warn().Err(err).Dur("retry_in", backoff).
				Msg("Connect échoué — retry")
			select {
			case <-ctx.Done():
				return
			case <-time.After(backoff):
			}
			backoff = min(backoff*2, maxBackoff)
			continue
		}
		cancel()

		md.status = "connected"
		md.lastErr = nil
		backoff = 5 * time.Second
		logger.Info().Msg("Driver connecté — lecture events...")

		// ReadEvents (bloquant — dure jusqu'à erreur ou ctx annulé)
		sinkWrap := &countingSink{
			inner:   m.sink,
			counter: &md.events,
		}
		err := md.Driver.ReadEvents(ctx, sinkWrap)

		// Cleanup
		_ = md.Driver.Disconnect()

		if ctx.Err() != nil {
			return
		}
		md.status = "error"
		md.lastErr = err
		logger.Warn().Err(err).Dur("retry_in", backoff).
			Msg("ReadEvents s'est arrêté — reconnexion")
		select {
		case <-ctx.Done():
			return
		case <-time.After(backoff):
		}
		backoff = min(backoff*2, maxBackoff)
	}
}

// countingSink wrappe un EventSink pour incrémenter un compteur.
type countingSink struct {
	inner   EventSink
	counter *int64
}

func (c *countingSink) Emit(ctx context.Context, ev Event) error {
	if err := c.inner.Emit(ctx, ev); err != nil {
		return err
	}
	*c.counter++
	return nil
}

func min(a, b time.Duration) time.Duration {
	if a < b {
		return a
	}
	return b
}
