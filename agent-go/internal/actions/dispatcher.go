// Package actions — Traite les commandes reçues du Cloud.
//
// Les commandes arrivent par 2 canaux :
//   1. Via pending_actions dans la réponse au heartbeat HTTP (polling 30s)
//   2. Via MQTT sur le topic kshield/cmd/edge/<gateway_id>/#  (temps réel)
//
// Chaque canal appelle le même Dispatcher.Dispatch(action) pour un
// traitement unifié.
//
// Types d'actions supportés :
//   - restart      : re-exec du binaire (le service manager relance)
//   - force_sync   : flush immédiat de la queue offline vers le cloud
//   - update       : télécharge + vérifie + swap le binaire
//   - scan_network : lance un scan LAN puis renvoie les résultats
//   - unlock_door  : commande vers un device via son driver
package actions

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"sync"
	"time"

	"github.com/rs/zerolog/log"
)

// Action représente une commande à exécuter.
type Action struct {
	ID      string                 `json:"id"`
	Type    string                 `json:"type"`
	Payload map[string]interface{} `json:"payload"`
	// Source indique d'où vient l'action (pour logs) : "heartbeat" ou "mqtt".
	Source string `json:"-"`
}

// Result est le retour d'exécution d'une action.
type Result struct {
	ActionID  string                 `json:"action_id"`
	Success   bool                   `json:"success"`
	Error     string                 `json:"error,omitempty"`
	Output    map[string]interface{} `json:"output,omitempty"`
	FinishedAt time.Time             `json:"finished_at"`
}

// Handler est la signature d'un traitement d'action.
type Handler func(ctx context.Context, action Action) Result

// Dispatcher route les actions vers leurs handlers respectifs.
type Dispatcher struct {
	mu       sync.RWMutex
	handlers map[string]Handler

	// Callback appelé après chaque exécution (pour ack cloud, log, etc.).
	OnResult func(res Result)
}

// New crée un dispatcher avec les handlers par défaut.
func New() *Dispatcher {
	d := &Dispatcher{
		handlers: make(map[string]Handler),
	}
	// Handlers built-in
	d.Register("restart", handleRestart)
	d.Register("force_sync", handleForceSync)
	d.Register("scan_network", handleScanNetwork)
	d.Register("update", handleUpdate)
	return d
}

// Register enregistre ou remplace un handler pour un type d'action.
func (d *Dispatcher) Register(actionType string, h Handler) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.handlers[actionType] = h
}

// Dispatch exécute l'action de manière synchrone. Retourne le résultat.
func (d *Dispatcher) Dispatch(ctx context.Context, action Action) Result {
	d.mu.RLock()
	h, ok := d.handlers[action.Type]
	d.mu.RUnlock()

	if !ok {
		return Result{
			ActionID:   action.ID,
			Success:    false,
			Error:      fmt.Sprintf("Aucun handler pour action type '%s'", action.Type),
			FinishedAt: time.Now().UTC(),
		}
	}

	log.Info().
		Str("action_id", action.ID).
		Str("type", action.Type).
		Str("source", action.Source).
		Msg("Exécution action")

	// Timeout de sécurité par action (5 min max)
	ctx, cancel := context.WithTimeout(ctx, 5*time.Minute)
	defer cancel()

	res := h(ctx, action)
	res.ActionID = action.ID
	if res.FinishedAt.IsZero() {
		res.FinishedAt = time.Now().UTC()
	}

	if d.OnResult != nil {
		d.OnResult(res)
	}

	logEvent := log.Info()
	if !res.Success {
		logEvent = log.Warn().Str("error", res.Error)
	}
	logEvent.
		Str("action_id", action.ID).
		Str("type", action.Type).
		Bool("success", res.Success).
		Msg("Action terminée")

	return res
}

// DispatchJSON parse un payload JSON MQTT (ex: {"type":"restart","id":"..."})
// et dispatch.
func (d *Dispatcher) DispatchJSON(ctx context.Context, source string, raw []byte) Result {
	var action Action
	if err := json.Unmarshal(raw, &action); err != nil {
		return Result{
			Success:    false,
			Error:      fmt.Sprintf("JSON invalide: %v", err),
			FinishedAt: time.Now().UTC(),
		}
	}
	action.Source = source
	return d.Dispatch(ctx, action)
}

// ═══════════════════════════════════════════════════════════════════
// Handlers built-in
// ═══════════════════════════════════════════════════════════════════

// handleRestart re-lance le binaire. Le service manager (systemd/Windows
// Service/launchd) le redémarrera automatiquement grâce à Restart=on-failure.
func handleRestart(ctx context.Context, _ Action) Result {
	log.Info().Msg("Restart demandé — arrêt du process (le service manager relancera)")
	// Fire-and-forget : on donne 1s au caller pour renvoyer le result,
	// puis on quitte proprement.
	go func() {
		time.Sleep(1 * time.Second)
		os.Exit(0) // le service manager voit exit=0 = clean restart
	}()
	return Result{Success: true, Output: map[string]interface{}{"restart": "scheduled"}}
}

// handleForceSync est un no-op au niveau dispatcher — la vraie sync est
// portée par le module queue qui écoute une notification.
// L'appelant doit brancher sa propre implémentation via Register().
func handleForceSync(_ context.Context, _ Action) Result {
	return Result{
		Success: false,
		Error:   "force_sync handler pas encore branché — cf. run.go",
	}
}

// handleUpdate est un placeholder pour Phase 2.3 (auto-update binaire).
func handleUpdate(_ context.Context, action Action) Result {
	log.Warn().
		Interface("payload", action.Payload).
		Msg("Update handler pas encore implémenté (Phase 2.3)")
	return Result{
		Success: false,
		Error:   "Auto-update pas encore supporté — mise à jour manuelle requise",
	}
}

// handleScanNetwork est un placeholder pour Phase 2.4 (network scanner).
func handleScanNetwork(ctx context.Context, action Action) Result {
	// En attendant l'orchestrator interne, on tente un arp -a via l'OS.
	timeout := 10 * time.Second
	if v, ok := action.Payload["timeout_seconds"].(float64); ok && v > 0 {
		timeout = time.Duration(v) * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, "arp", "-a")
	out, err := cmd.CombinedOutput()
	if err != nil {
		return Result{
			Success: false,
			Error:   fmt.Sprintf("arp -a échoué: %v", err),
		}
	}
	return Result{
		Success: true,
		Output:  map[string]interface{}{"arp_raw": string(out)},
	}
}
