// Package drivers — Framework de drivers vendors (ZKTeco, Hikvision, Suprema, ...).
//
// Chaque driver implémente l'interface Driver pour standardiser :
//   - Découverte : Probe(target) tente d'identifier un équipement
//   - Connexion : Connect() ouvre une session (TCP/HTTP/UDP selon vendor)
//   - Lecture : ReadEvents(ctx, sink) push les events reçus (badge scan,
//     tamper, door open, etc.) au sink fourni par l'agent
//   - Commandes : DoorUnlock / Sync / Restart / PushUser
//
// L'agent Go boucle sur les drivers activés dans la config
// (devices.enable_zkteco = true, etc.) et démarre un goroutine par
// device managed.
package drivers

import (
	"context"
	"fmt"
	"sync"
	"time"
)

// Capability décrit ce qu'un driver sait faire.
type Capability string

const (
	CapReadEvents  Capability = "read_events"
	CapDoorUnlock  Capability = "door_unlock"
	CapSyncUsers   Capability = "sync_users"
	CapPushUser    Capability = "push_user"
	CapRestart     Capability = "restart"
	CapGetStatus   Capability = "get_status"
	CapUpdateFirm  Capability = "update_firmware"
	CapStartEnroll Capability = "start_enrollment"
)

// Event est un event métier produit par un driver.
type Event struct {
	Type       string                 // "access.granted" / "device.tamper" / ...
	OccurredAt time.Time
	DeviceID   string                 // ID interne agent (mac ou serial)
	Payload    map[string]interface{} // Données spécifiques
	SourceIP   string
}

// EventSink est le canal de sortie où le driver push ses events.
// L'agent implémente typiquement cette interface avec un fanout
// vers la queue offline + MQTT.
type EventSink interface {
	Emit(ctx context.Context, ev Event) error
}

// Target décrit un équipement à connecter.
type Target struct {
	ID       string            // ID unique agent-side
	IP       string
	Port     int
	Vendor   string
	Model    string
	Username string
	Password string
	Extra    map[string]string // free-form config
}

// Result standardise le retour d'une commande driver.
type Result struct {
	OK       bool                   `json:"ok"`
	Error    string                 `json:"error,omitempty"`
	Data     map[string]interface{} `json:"data,omitempty"`
	Duration time.Duration          `json:"duration"`
}

// Driver est l'interface implémentée par chaque vendor plugin.
//
// Contract :
//   - Connect() doit établir la session et rester non-bloquant (retour rapide)
//   - ReadEvents(ctx, sink) est LA méthode principale — bloquante, elle
//     tourne dans une goroutine dédiée et push les events tant que ctx vit
//   - Les commandes sync (DoorUnlock, PushUser) doivent retourner en < 10s
//   - Un driver doit être thread-safe pour la lecture (plusieurs goroutines
//     peuvent appeler GetStatus/DoorUnlock en parallèle)
type Driver interface {
	// Meta
	Vendor() string
	Capabilities() []Capability

	// Lifecycle
	Connect(ctx context.Context) error
	Disconnect() error
	Ping(ctx context.Context) error

	// Data (bloquant — tourne en goroutine dédiée)
	ReadEvents(ctx context.Context, sink EventSink) error

	// Commandes (sync)
	GetStatus(ctx context.Context) Result
	DoorUnlock(ctx context.Context, doorID string) Result
	Sync(ctx context.Context) Result
	Restart(ctx context.Context) Result
	PushUser(ctx context.Context, user map[string]interface{}) Result
}

// ═══════════════════════════════════════════════════════════════════
// Registry — équivalent Go du @register_driver Python
// ═══════════════════════════════════════════════════════════════════

// Factory construit un nouveau Driver pour un Target donné.
type Factory func(target Target) (Driver, error)

var (
	registryMu sync.RWMutex
	registry   = make(map[string]Factory)
)

// Register enregistre un factory sous une clé vendor.
// Appelé depuis l'init() de chaque package driver (zkteco, hikvision, ...).
func Register(vendor string, factory Factory) {
	registryMu.Lock()
	defer registryMu.Unlock()
	if _, exists := registry[vendor]; exists {
		panic(fmt.Sprintf("driver vendor déjà enregistré: %s", vendor))
	}
	registry[vendor] = factory
}

// Get récupère le factory d'un vendor.
func Get(vendor string) (Factory, bool) {
	registryMu.RLock()
	defer registryMu.RUnlock()
	f, ok := registry[vendor]
	return f, ok
}

// List retourne les vendors enregistrés (utile pour debug / status).
func List() []string {
	registryMu.RLock()
	defer registryMu.RUnlock()
	out := make([]string, 0, len(registry))
	for v := range registry {
		out = append(out, v)
	}
	return out
}

// BuildDriver construit un Driver pour un Target ou retourne erreur.
func BuildDriver(target Target) (Driver, error) {
	f, ok := Get(target.Vendor)
	if !ok {
		return nil, fmt.Errorf("driver inconnu pour vendor=%s (registered: %v)",
			target.Vendor, List())
	}
	return f(target)
}
