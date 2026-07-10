// Package zkteco — Driver pour terminaux ZKTeco (RFID, biométrie, contrôle d'accès).
//
// Deux modes de fonctionnement supportés :
//
//   1. PUSH HTTP (recommandé)
//      Le terminal push ses events vers l'agent sur `/iclock/cdata`.
//      Configurer côté terminal : Server=<agent_ip>:<port> Type=HTTP
//      Ce driver démarre un HTTP server local et parse le format ZK ATTLOG.
//
//   2. PULL SDK (fallback pour firmwares anciens)
//      Non implémenté ici — nécessite protocole binaire ZK propriétaire.
//      Utiliser le driver Python legacy si nécessaire.
//
// Format ATTLOG typique reçu :
//   POST /iclock/cdata?SN=XXXX&table=ATTLOG&Stamp=YYYY
//   Content-Type: application/x-www-form-urlencoded
//
//   <user_id>\t<timestamp>\t<punch_type>\t<verify_mode>\t<work_code>
//   1234    2026-07-10 12:34:56    0    1    0
//
// Chaque ligne = un événement badge scan.
package zkteco

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/sergehoo/kshield/agent-go/internal/drivers"
)

const vendorName = "zkteco"

// Init : s'enregistre auprès du registry global.
func init() {
	drivers.Register(vendorName, func(t drivers.Target) (drivers.Driver, error) {
		port := t.Port
		if port == 0 {
			port = 8080 // port HTTP default pour le push server
		}
		return &Driver{
			target:     t,
			listenAddr: fmt.Sprintf("0.0.0.0:%d", port),
			events:     make(chan zkEvent, 100),
		}, nil
	})
}

// Driver implémente drivers.Driver pour ZKTeco.
type Driver struct {
	target     drivers.Target
	listenAddr string

	mu       sync.Mutex
	server   *http.Server
	events   chan zkEvent
	stopping bool
}

type zkEvent struct {
	SerialNumber string
	UserID       string
	Timestamp    time.Time
	PunchType    string
	VerifyMode   string
	Raw          string
	ClientIP     string
}

// Vendor implémente drivers.Driver.
func (d *Driver) Vendor() string { return vendorName }

// Capabilities implémente drivers.Driver.
func (d *Driver) Capabilities() []drivers.Capability {
	return []drivers.Capability{
		drivers.CapReadEvents,
		drivers.CapGetStatus,
		// TODO : DoorUnlock via commande push /iclock/getrequest
	}
}

// Connect démarre le HTTP server local pour recevoir les pushs.
func (d *Driver) Connect(ctx context.Context) error {
	d.mu.Lock()
	defer d.mu.Unlock()

	if d.server != nil {
		return nil // déjà connecté
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/iclock/cdata", d.handleCdata)
	mux.HandleFunc("/iclock/getrequest", d.handleGetrequest)
	mux.HandleFunc("/iclock/ping", d.handlePing)

	d.server = &http.Server{
		Addr:         d.listenAddr,
		Handler:      mux,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Test que le port est libre avant de démarrer
	listener, err := net.Listen("tcp", d.listenAddr)
	if err != nil {
		return fmt.Errorf("bind %s: %w", d.listenAddr, err)
	}

	go func() {
		if err := d.server.Serve(listener); err != nil && err != http.ErrServerClosed {
			log.Error().Err(err).Str("addr", d.listenAddr).Msg("ZKTeco server error")
		}
	}()

	log.Info().Str("addr", d.listenAddr).
		Msg("Driver ZKTeco : serveur push démarré. Configurer les terminaux avec Server=<agent_ip>")
	return nil
}

// Disconnect ferme le serveur HTTP.
func (d *Driver) Disconnect() error {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.stopping = true
	if d.server != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = d.server.Shutdown(ctx)
		d.server = nil
	}
	return nil
}

// Ping vérifie que le serveur écoute.
func (d *Driver) Ping(ctx context.Context) error {
	d.mu.Lock()
	up := d.server != nil
	d.mu.Unlock()
	if !up {
		return fmt.Errorf("server pas démarré")
	}
	return nil
}

// ReadEvents attend les events poussés par les terminaux ZKTeco et
// les émet vers le sink. Bloque jusqu'à annulation du context.
func (d *Driver) ReadEvents(ctx context.Context, sink drivers.EventSink) error {
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case ev, ok := <-d.events:
			if !ok {
				return fmt.Errorf("events channel fermé")
			}
			if err := sink.Emit(ctx, drivers.Event{
				Type:       eventTypeFromPunch(ev.PunchType),
				OccurredAt: ev.Timestamp,
				DeviceID:   ev.SerialNumber,
				SourceIP:   ev.ClientIP,
				Payload: map[string]interface{}{
					"user_id":     ev.UserID,
					"punch_type":  ev.PunchType,
					"verify_mode": ev.VerifyMode,
					"vendor":      vendorName,
					"raw":         ev.Raw,
				},
			}); err != nil {
				log.Warn().Err(err).Msg("ZKTeco sink emit failed")
			}
		}
	}
}

// GetStatus retourne un état basique.
func (d *Driver) GetStatus(ctx context.Context) drivers.Result {
	d.mu.Lock()
	up := d.server != nil
	d.mu.Unlock()
	return drivers.Result{
		OK: up,
		Data: map[string]interface{}{
			"listen_addr": d.listenAddr,
			"protocol":    "push_http",
		},
	}
}

// DoorUnlock — TODO : file la commande dans la file getrequest.
func (d *Driver) DoorUnlock(ctx context.Context, doorID string) drivers.Result {
	// Le protocole ZK Push permet à l'agent d'envoyer une commande au
	// prochain appel /iclock/getrequest du terminal. À implémenter avec
	// une queue de commandes par SN.
	return drivers.Result{
		OK:    false,
		Error: "DoorUnlock pas encore implémenté pour ZKTeco Push",
	}
}

// Sync — TODO : push USERINFO au terminal.
func (d *Driver) Sync(ctx context.Context) drivers.Result {
	return drivers.Result{OK: false, Error: "Sync pas encore implémenté"}
}

// Restart via commande C:<SN>:INFO Reboot.
func (d *Driver) Restart(ctx context.Context) drivers.Result {
	return drivers.Result{OK: false, Error: "Restart pas encore implémenté"}
}

// PushUser — TODO : USERINFO PIN=X Name=Y ...
func (d *Driver) PushUser(ctx context.Context, user map[string]interface{}) drivers.Result {
	return drivers.Result{OK: false, Error: "PushUser pas encore implémenté"}
}

// ═══════════════════════════════════════════════════════════════════
// HTTP handlers — protocole ZKTeco Push
// ═══════════════════════════════════════════════════════════════════

// handleCdata parse les données push envoyées par le terminal.
//
// Format URL : /iclock/cdata?SN=XXXX&table=ATTLOG&Stamp=YYYY
// Format body :
//     <user_id>\t<timestamp>\t<punch_type>\t<verify_mode>\t<work_code>
//     ... (une ligne par event)
func (d *Driver) handleCdata(w http.ResponseWriter, r *http.Request) {
	sn := r.URL.Query().Get("SN")
	table := r.URL.Query().Get("table")
	clientIP := clientIPFromRequest(r)

	if r.Method == "POST" {
		body, err := io.ReadAll(r.Body)
		if err != nil {
			log.Warn().Err(err).Msg("ZKTeco cdata: read body")
			http.Error(w, "read error", 500)
			return
		}
		d.parseCdataBody(sn, table, clientIP, string(body))
	}

	// La réponse doit être "OK" simple pour que le terminal considère
	// le push comme réussi.
	w.Header().Set("Content-Type", "text/plain")
	fmt.Fprintln(w, "OK")
}

// handleGetrequest — le terminal poll les commandes de l'agent.
// Pour l'instant on répond "OK" (pas de commande en attente).
func (d *Driver) handleGetrequest(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain")
	fmt.Fprintln(w, "OK")
}

// handlePing (endpoint interne — utile pour healthchecks).
func (d *Driver) handlePing(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain")
	fmt.Fprintln(w, "PONG")
}

// parseCdataBody parse le body du push et emit les events.
func (d *Driver) parseCdataBody(sn, table, clientIP, body string) {
	scanner := bufio.NewScanner(strings.NewReader(body))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		// Format ATTLOG : user_id \t timestamp \t punch_type \t verify_mode ...
		parts := strings.Split(line, "\t")
		if len(parts) < 3 {
			continue
		}

		ts, err := time.Parse("2006-01-02 15:04:05", parts[1])
		if err != nil {
			// Format alternatif ISO ou epoch
			ts = time.Now().UTC()
		}

		ev := zkEvent{
			SerialNumber: sn,
			UserID:       parts[0],
			Timestamp:    ts,
			Raw:          line,
			ClientIP:     clientIP,
		}
		if len(parts) > 2 {
			ev.PunchType = parts[2]
		}
		if len(parts) > 3 {
			ev.VerifyMode = parts[3]
		}

		select {
		case d.events <- ev:
			log.Debug().
				Str("sn", sn).
				Str("user", ev.UserID).
				Msg("ZKTeco event push")
		default:
			log.Warn().Msg("ZKTeco events channel plein — event dropped")
		}
	}
}

// eventTypeFromPunch mappe le punch_type ZK vers un type d'event Kaydan Shield.
// 0 = check-in, 1 = check-out, 4 = overtime-in, 5 = overtime-out
func eventTypeFromPunch(pt string) string {
	switch pt {
	case "0":
		return "access.check_in"
	case "1":
		return "access.check_out"
	case "4":
		return "access.overtime_in"
	case "5":
		return "access.overtime_out"
	default:
		return "access.granted"
	}
}

func clientIPFromRequest(r *http.Request) string {
	// X-Forwarded-For prioritaire si proxy devant
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		if i := strings.Index(xff, ","); i != -1 {
			return strings.TrimSpace(xff[:i])
		}
		return xff
	}
	// Sinon RemoteAddr
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}
