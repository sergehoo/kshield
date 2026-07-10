// Package hid — Driver pour contrôleurs HID Global VertX / EDGE.
//
// Protocole HID VertX v2 :
//   - HTTP + Basic auth (souvent admin/admin par défaut)
//   - Events : polling /cgi-bin/status.cgi?event=1  (long-poll bounded)
//   - Commands : POST /cgi-bin/action.cgi
//
// Ce driver couvre le cas standard VertX/EDGE. Les modèles plus récents
// (Aero X1000, Signo) utilisent une API différente et nécessiteront un
// sous-package dédié.
package hid

import (
	"context"
	"encoding/xml"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/sergehoo/kshield/agent-go/internal/drivers"
)

const vendorName = "hid"

func init() {
	drivers.Register(vendorName, func(t drivers.Target) (drivers.Driver, error) {
		if t.IP == "" {
			return nil, fmt.Errorf("hid: target.IP requis")
		}
		port := t.Port
		if port == 0 {
			port = 80
		}
		return &Driver{
			target:   t,
			baseURL:  fmt.Sprintf("http://%s:%d", t.IP, port),
			username: t.Username,
			password: t.Password,
			client:   &http.Client{Timeout: 30 * time.Second},
		}, nil
	})
}

type Driver struct {
	target   drivers.Target
	baseURL  string
	username string
	password string
	client   *http.Client
}

func (d *Driver) Vendor() string { return vendorName }
func (d *Driver) Capabilities() []drivers.Capability {
	return []drivers.Capability{
		drivers.CapReadEvents,
		drivers.CapDoorUnlock,
		drivers.CapGetStatus,
	}
}

func (d *Driver) Connect(ctx context.Context) error {
	res := d.GetStatus(ctx)
	if !res.OK {
		return fmt.Errorf("hid connect: %s", res.Error)
	}
	return nil
}

func (d *Driver) Disconnect() error {
	return nil
}

func (d *Driver) Ping(ctx context.Context) error {
	res := d.GetStatus(ctx)
	if !res.OK {
		return fmt.Errorf("ping: %s", res.Error)
	}
	return nil
}

// GetStatus interroge /cgi-bin/status.cgi.
func (d *Driver) GetStatus(ctx context.Context) drivers.Result {
	start := time.Now()
	body, err := d.get(ctx, "/cgi-bin/status.cgi")
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error(), Duration: time.Since(start)}
	}
	var status struct {
		DeviceID   string `xml:"device_id"`
		Firmware   string `xml:"firmware"`
		Uptime     string `xml:"uptime"`
	}
	_ = xml.Unmarshal(body, &status)
	return drivers.Result{
		OK: true,
		Data: map[string]interface{}{
			"device_id": status.DeviceID,
			"firmware":  status.Firmware,
			"uptime":    status.Uptime,
			"raw":       string(body[:min(len(body), 500)]),
		},
		Duration: time.Since(start),
	}
}

// DoorUnlock — POST /cgi-bin/action.cgi?door=<id>&action=unlock
func (d *Driver) DoorUnlock(ctx context.Context, doorID string) drivers.Result {
	if doorID == "" {
		doorID = "1"
	}
	start := time.Now()
	path := fmt.Sprintf("/cgi-bin/action.cgi?door=%s&action=unlock", doorID)
	_, err := d.get(ctx, path)
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error(), Duration: time.Since(start)}
	}
	return drivers.Result{
		OK:       true,
		Data:     map[string]interface{}{"door_id": doorID},
		Duration: time.Since(start),
	}
}

func (d *Driver) Sync(ctx context.Context) drivers.Result {
	return drivers.Result{OK: false, Error: "Sync pas encore implémenté"}
}

func (d *Driver) Restart(ctx context.Context) drivers.Result {
	start := time.Now()
	_, err := d.get(ctx, "/cgi-bin/action.cgi?action=reboot")
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error(), Duration: time.Since(start)}
	}
	return drivers.Result{OK: true, Duration: time.Since(start)}
}

func (d *Driver) PushUser(ctx context.Context, user map[string]interface{}) drivers.Result {
	return drivers.Result{OK: false, Error: "PushUser pas encore implémenté"}
}

// ReadEvents — polling GET /cgi-bin/status.cgi?event=1
// L'endpoint bloque jusqu'à un event ou timeout (long-poll).
func (d *Driver) ReadEvents(ctx context.Context, sink drivers.EventSink) error {
	backoff := 2 * time.Second
	maxBackoff := 30 * time.Second

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		body, err := d.get(ctx, "/cgi-bin/status.cgi?event=1")
		if err != nil {
			log.Warn().Err(err).Msg("hid event poll failed")
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

		// Parse XML event
		d.parseEvent(ctx, body, sink)
	}
}

func (d *Driver) parseEvent(ctx context.Context, body []byte, sink drivers.EventSink) {
	var ev struct {
		Type       string `xml:"type,attr"`
		Timestamp  string `xml:"timestamp"`
		CardNumber string `xml:"card_number"`
		DoorID     string `xml:"door_id"`
		ReaderID   string `xml:"reader_id"`
		AccessResult string `xml:"result"`
	}
	if err := xml.Unmarshal(body, &ev); err != nil {
		return
	}
	if ev.Type == "" {
		return
	}

	ts := time.Now().UTC()
	if t, err := time.Parse("2006-01-02T15:04:05", ev.Timestamp); err == nil {
		ts = t
	}

	_ = sink.Emit(ctx, drivers.Event{
		Type:       mapHIDEvent(ev.Type, ev.AccessResult),
		OccurredAt: ts,
		DeviceID:   d.target.ID,
		Payload: map[string]interface{}{
			"vendor":       vendorName,
			"card_number":  ev.CardNumber,
			"door_id":      ev.DoorID,
			"reader_id":    ev.ReaderID,
			"access_result": ev.AccessResult,
			"raw_type":     ev.Type,
		},
	})
}

func mapHIDEvent(evType, result string) string {
	evType = strings.ToLower(evType)
	result = strings.ToLower(result)

	if strings.Contains(evType, "access") {
		if result == "granted" || result == "success" {
			return "access.granted"
		}
		return "access.denied"
	}
	if strings.Contains(evType, "tamper") {
		return "device.tamper"
	}
	if strings.Contains(evType, "door") {
		if strings.Contains(evType, "open") {
			return "door.open"
		}
		if strings.Contains(evType, "close") {
			return "door.close"
		}
	}
	return "device.event"
}

// ═══════════════════════════════════════════════════════════════════
// HTTP helpers
// ═══════════════════════════════════════════════════════════════════
func (d *Driver) get(ctx context.Context, path string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", d.baseURL+path, nil)
	if err != nil {
		return nil, err
	}
	req.SetBasicAuth(d.username, d.password)
	resp, err := d.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return body, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}
	return body, nil
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
