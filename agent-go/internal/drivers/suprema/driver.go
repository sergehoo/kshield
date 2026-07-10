// Package suprema — Driver pour Suprema BioStar 2 API.
//
// Suprema propose plusieurs API — ce driver cible **BioStar 2 Cloud/Server REST API**
// (HTTPS avec session cookie). Documentation :
//   https://api.biostar2.com/docs/
//
// Auth flow :
//   1. POST /api/login  {"login_id":..., "password":...}  → cookie "bs-session-id"
//   2. Toutes les requêtes ultérieures utilisent ce cookie
//
// Events : long-poll GET /api/events → array JSON de events
// Le protocole diffère de la BioStation Air (BSA-01) — voir sub-package si besoin.
package suprema

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/sergehoo/kshield/agent-go/internal/drivers"
)

const vendorName = "suprema"

func init() {
	drivers.Register(vendorName, func(t drivers.Target) (drivers.Driver, error) {
		if t.IP == "" {
			return nil, fmt.Errorf("suprema: target.IP requis")
		}
		port := t.Port
		if port == 0 {
			port = 443 // BioStar 2 default HTTPS
		}
		jar, _ := cookiejar.New(nil)
		return &Driver{
			target:   t,
			baseURL:  fmt.Sprintf("https://%s:%d", t.IP, port),
			username: t.Username,
			password: t.Password,
			client: &http.Client{
				Timeout: 30 * time.Second,
				Jar:     jar,
				Transport: &http.Transport{
					// BioStar 2 utilise souvent un cert self-signed
					TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
				},
			},
		}, nil
	})
}

// Driver implémente drivers.Driver.
type Driver struct {
	target   drivers.Target
	baseURL  string
	username string
	password string
	client   *http.Client

	mu         sync.Mutex
	loggedIn   bool
	sessionID  string
	lastLoginAt time.Time
}

func (d *Driver) Vendor() string { return vendorName }

func (d *Driver) Capabilities() []drivers.Capability {
	return []drivers.Capability{
		drivers.CapReadEvents,
		drivers.CapDoorUnlock,
		drivers.CapGetStatus,
		drivers.CapSyncUsers,
	}
}

// Connect fait le login BioStar 2 et stocke le cookie de session.
func (d *Driver) Connect(ctx context.Context) error {
	return d.login(ctx)
}

func (d *Driver) Disconnect() error {
	// BioStar 2 : POST /api/logout — best-effort
	d.mu.Lock()
	d.loggedIn = false
	d.sessionID = ""
	d.mu.Unlock()
	return nil
}

func (d *Driver) Ping(ctx context.Context) error {
	// GET /api/info (public, pas d'auth requise)
	req, err := http.NewRequestWithContext(ctx, "GET", d.baseURL+"/api/info", nil)
	if err != nil {
		return err
	}
	resp, err := d.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	return nil
}

// login POST /api/login → cookie
func (d *Driver) login(ctx context.Context) error {
	body := map[string]interface{}{
		"User": map[string]string{
			"login_id": d.username,
			"password": d.password,
		},
	}
	jsonBody, _ := json.Marshal(body)

	req, err := http.NewRequestWithContext(ctx, "POST",
		d.baseURL+"/api/login", bytes.NewReader(jsonBody))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := d.client.Do(req)
	if err != nil {
		return fmt.Errorf("login connect: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("login HTTP %d: %s", resp.StatusCode, string(respBody))
	}

	// Cookie stocké dans le jar automatiquement
	// Extrait aussi bs-session-id du header
	for _, c := range resp.Cookies() {
		if c.Name == "bs-session-id" {
			d.mu.Lock()
			d.sessionID = c.Value
			d.loggedIn = true
			d.lastLoginAt = time.Now()
			d.mu.Unlock()
			break
		}
	}
	log.Info().Msg("Suprema BioStar 2 login OK")
	return nil
}

// authGet fait un GET authentifié + relogin si expire session.
func (d *Driver) authGet(ctx context.Context, path string) ([]byte, error) {
	if !d.isSessionFresh() {
		if err := d.login(ctx); err != nil {
			return nil, fmt.Errorf("re-login: %w", err)
		}
	}
	req, err := http.NewRequestWithContext(ctx, "GET", d.baseURL+path, nil)
	if err != nil {
		return nil, err
	}
	resp, err := d.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == 401 {
		// Session expirée — 1 retry
		if err := d.login(ctx); err != nil {
			return nil, err
		}
		return d.authGet(ctx, path)
	}
	return io.ReadAll(resp.Body)
}

func (d *Driver) isSessionFresh() bool {
	d.mu.Lock()
	defer d.mu.Unlock()
	if !d.loggedIn {
		return false
	}
	// Session BioStar 2 : 1h de validité par défaut, on relogin toutes les 30 min
	return time.Since(d.lastLoginAt) < 30*time.Minute
}

// GetStatus retourne l'état des devices via /api/devices.
func (d *Driver) GetStatus(ctx context.Context) drivers.Result {
	start := time.Now()
	body, err := d.authGet(ctx, "/api/devices")
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error(), Duration: time.Since(start)}
	}
	var out struct {
		Records []map[string]interface{} `json:"records"`
		Total   int                      `json:"total"`
	}
	_ = json.Unmarshal(body, &out)
	return drivers.Result{
		OK: true,
		Data: map[string]interface{}{
			"devices_count": out.Total,
			"devices":       out.Records,
		},
		Duration: time.Since(start),
	}
}

// DoorUnlock — POST /api/doors/{id}/open avec body {"open_duration":5}
func (d *Driver) DoorUnlock(ctx context.Context, doorID string) drivers.Result {
	if doorID == "" {
		doorID = "1"
	}
	start := time.Now()
	if !d.isSessionFresh() {
		if err := d.login(ctx); err != nil {
			return drivers.Result{OK: false, Error: err.Error()}
		}
	}
	body := []byte(`{"open_duration":5}`)
	req, err := http.NewRequestWithContext(ctx, "POST",
		fmt.Sprintf("%s/api/doors/%s/open", d.baseURL, doorID),
		bytes.NewReader(body))
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error()}
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := d.client.Do(req)
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error()}
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		respBody, _ := io.ReadAll(resp.Body)
		return drivers.Result{
			OK:       false,
			Error:    fmt.Sprintf("HTTP %d: %s", resp.StatusCode, string(respBody)),
			Duration: time.Since(start),
		}
	}
	return drivers.Result{
		OK:       true,
		Data:     map[string]interface{}{"door_id": doorID},
		Duration: time.Since(start),
	}
}

// Sync (placeholder)
func (d *Driver) Sync(ctx context.Context) drivers.Result {
	return drivers.Result{OK: false, Error: "Sync users pas encore implémenté"}
}

// Restart — pas d'endpoint standard BioStar 2 pour reboot serveur.
func (d *Driver) Restart(ctx context.Context) drivers.Result {
	return drivers.Result{OK: false, Error: "Restart pas supporté par BioStar 2 API"}
}

// PushUser — POST /api/users
func (d *Driver) PushUser(ctx context.Context, user map[string]interface{}) drivers.Result {
	return drivers.Result{OK: false, Error: "PushUser pas encore implémenté"}
}

// ═══════════════════════════════════════════════════════════════════
// ReadEvents — long-poll /api/events?last_id=...
// ═══════════════════════════════════════════════════════════════════
func (d *Driver) ReadEvents(ctx context.Context, sink drivers.EventSink) error {
	if err := d.login(ctx); err != nil {
		return fmt.Errorf("login initial: %w", err)
	}

	lastID := ""
	backoff := 2 * time.Second
	maxBackoff := 30 * time.Second

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		url := "/api/events"
		if lastID != "" {
			url += "?last_id=" + lastID
		}

		body, err := d.authGet(ctx, url)
		if err != nil {
			log.Warn().Err(err).Msg("suprema events poll failed")
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(backoff):
			}
			if backoff < maxBackoff {
				backoff *= 2
			}
			continue
		}
		backoff = 2 * time.Second

		var out struct {
			Records []map[string]interface{} `json:"records"`
			Total   int                      `json:"total"`
		}
		if err := json.Unmarshal(body, &out); err != nil {
			log.Debug().Err(err).Msg("suprema events unmarshal")
			continue
		}

		for _, ev := range out.Records {
			eventType := "device.event"
			if code, ok := ev["event_type_id"].(map[string]interface{}); ok {
				if name, ok := code["name"].(string); ok {
					eventType = mapSupremaEvent(name)
				}
			}
			ts := time.Now().UTC()
			if s, ok := ev["datetime"].(string); ok {
				if parsed, err := time.Parse("2006-01-02T15:04:05Z", s); err == nil {
					ts = parsed
				}
			}

			_ = sink.Emit(ctx, drivers.Event{
				Type:       eventType,
				OccurredAt: ts,
				DeviceID:   d.target.ID,
				Payload:    ev,
			})
			if id, ok := ev["id"].(string); ok {
				lastID = id
			}
		}

		// Polling toutes les 5s si pas d'events
		if out.Total == 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(5 * time.Second):
			}
		}
	}
}

// mapSupremaEvent convertit un code BioStar 2 vers taxonomie Kaydan Shield.
func mapSupremaEvent(name string) string {
	name = strings.ToLower(name)
	switch {
	case strings.Contains(name, "granted"):
		return "access.granted"
	case strings.Contains(name, "denied"):
		return "access.denied"
	case strings.Contains(name, "duress"):
		return "access.duress"
	case strings.Contains(name, "tamper"):
		return "device.tamper"
	case strings.Contains(name, "door open"):
		return "door.open"
	case strings.Contains(name, "door close"):
		return "door.close"
	default:
		return "device.event"
	}
}
