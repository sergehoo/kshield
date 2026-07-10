// Package metrics — Compteurs internes + endpoint Prometheus opt-in.
//
// N'utilise volontairement pas prometheus/client_golang pour minimiser
// les deps et le binaire. Format Prometheus exposé "à la main" — c'est
// simple, un scrape/min suffit.
//
// Activation : dans config TOML, section [metrics], listen = "127.0.0.1:9090"
// (par défaut désactivé — pas d'exposition réseau).
package metrics

import (
	"fmt"
	"net/http"
	"sync/atomic"
	"time"

	"github.com/rs/zerolog/log"
)

// Counters expose des compteurs atomiques.
type Counters struct {
	// Events
	EventsEnqueued   atomic.Int64
	EventsPushed     atomic.Int64
	EventsDropped    atomic.Int64
	EventsRetried    atomic.Int64

	// HTTP
	HeartbeatOK      atomic.Int64
	HeartbeatFail    atomic.Int64
	HttpBytesSent    atomic.Int64

	// MQTT
	MQTTConnects     atomic.Int64
	MQTTDisconnects  atomic.Int64
	MQTTPublished    atomic.Int64
	MQTTReceived     atomic.Int64

	// WebSocket
	WSConnects       atomic.Int64
	WSDisconnects    atomic.Int64
	WSMessagesRecv   atomic.Int64

	// Actions
	ActionsDispatched atomic.Int64
	ActionsSucceeded  atomic.Int64
	ActionsFailed     atomic.Int64

	// Scans
	ScansCompleted   atomic.Int64
	DevicesDiscoveredTotal atomic.Int64

	// Uptime
	StartedAt        time.Time
}

// Global est le singleton exposé.
var Global = &Counters{StartedAt: time.Now()}

// ═══════════════════════════════════════════════════════════════════
// Endpoint HTTP format Prometheus
// ═══════════════════════════════════════════════════════════════════

// StartServer démarre un HTTP server local pour l'endpoint /metrics.
// listenAddr = "" désactive l'exposition. Bind sur 127.0.0.1 recommandé.
func StartServer(listenAddr string) *http.Server {
	if listenAddr == "" {
		return nil
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/metrics", handleMetrics)
	mux.HandleFunc("/health", handleHealth)

	srv := &http.Server{
		Addr:         listenAddr,
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
	}

	go func() {
		log.Info().Str("addr", listenAddr).Msg("Metrics server démarré (/metrics)")
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Warn().Err(err).Msg("Metrics server error")
		}
	}()
	return srv
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain")
	fmt.Fprintln(w, "ok")
}

func handleMetrics(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")

	uptime := time.Since(Global.StartedAt).Seconds()

	fmt.Fprintln(w, "# HELP kshield_edge_uptime_seconds Uptime of the agent in seconds.")
	fmt.Fprintln(w, "# TYPE kshield_edge_uptime_seconds gauge")
	fmt.Fprintf(w, "kshield_edge_uptime_seconds %f\n\n", uptime)

	writeCounter(w, "kshield_edge_events_enqueued_total",
		"Total events enqueued into offline SQLite queue",
		Global.EventsEnqueued.Load())
	writeCounter(w, "kshield_edge_events_pushed_total",
		"Total events successfully pushed to cloud",
		Global.EventsPushed.Load())
	writeCounter(w, "kshield_edge_events_dropped_total",
		"Total events dropped (queue full or purged)",
		Global.EventsDropped.Load())
	writeCounter(w, "kshield_edge_events_retried_total",
		"Total events retried after push failure",
		Global.EventsRetried.Load())

	writeCounter(w, "kshield_edge_heartbeat_ok_total",
		"Total successful heartbeats to cloud",
		Global.HeartbeatOK.Load())
	writeCounter(w, "kshield_edge_heartbeat_fail_total",
		"Total failed heartbeats",
		Global.HeartbeatFail.Load())
	writeCounter(w, "kshield_edge_http_bytes_sent_total",
		"Total HTTP bytes sent to cloud",
		Global.HttpBytesSent.Load())

	writeCounter(w, "kshield_edge_mqtt_connects_total",
		"Total MQTT (re)connections",
		Global.MQTTConnects.Load())
	writeCounter(w, "kshield_edge_mqtt_disconnects_total",
		"Total MQTT disconnections",
		Global.MQTTDisconnects.Load())
	writeCounter(w, "kshield_edge_mqtt_published_total",
		"Total MQTT messages published",
		Global.MQTTPublished.Load())
	writeCounter(w, "kshield_edge_mqtt_received_total",
		"Total MQTT messages received (commands)",
		Global.MQTTReceived.Load())

	writeCounter(w, "kshield_edge_ws_connects_total",
		"Total WebSocket connections",
		Global.WSConnects.Load())
	writeCounter(w, "kshield_edge_ws_disconnects_total",
		"Total WebSocket disconnections",
		Global.WSDisconnects.Load())
	writeCounter(w, "kshield_edge_ws_messages_recv_total",
		"Total WebSocket messages received",
		Global.WSMessagesRecv.Load())

	writeCounter(w, "kshield_edge_actions_dispatched_total",
		"Total actions dispatched",
		Global.ActionsDispatched.Load())
	writeCounter(w, "kshield_edge_actions_succeeded_total",
		"Total actions succeeded",
		Global.ActionsSucceeded.Load())
	writeCounter(w, "kshield_edge_actions_failed_total",
		"Total actions failed",
		Global.ActionsFailed.Load())

	writeCounter(w, "kshield_edge_scans_completed_total",
		"Total network scans completed",
		Global.ScansCompleted.Load())
	writeCounter(w, "kshield_edge_devices_discovered_total",
		"Total devices discovered on network (all scans cumulated)",
		Global.DevicesDiscoveredTotal.Load())
}

func writeCounter(w http.ResponseWriter, name, help string, value int64) {
	fmt.Fprintf(w, "# HELP %s %s\n", name, help)
	fmt.Fprintf(w, "# TYPE %s counter\n", name)
	fmt.Fprintf(w, "%s %d\n\n", name, value)
}
