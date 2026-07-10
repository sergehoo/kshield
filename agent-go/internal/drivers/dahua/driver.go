// Package dahua — Driver pour caméras + contrôleurs Dahua.
//
// Protocole HTTP CGI standard Dahua :
//   - Auth : HTTP Digest (obligatoire depuis firmware 2018+)
//   - Events : GET /cgi-bin/eventManager.cgi?action=attach&codes=[All]
//              (long-poll multipart/x-mixed-replace)
//   - Info : GET /cgi-bin/magicBox.cgi?action=getSystemInfo
//   - Reboot : GET /cgi-bin/magicBox.cgi?action=reboot
//
// Le protocole partage beaucoup avec Hikvision mais avec des chemins CGI
// différents. On réutilise le helper Digest local.
package dahua

import (
	"bufio"
	"context"
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/sergehoo/kshield/agent-go/internal/drivers"
)

const vendorName = "dahua"

func init() {
	drivers.Register(vendorName, func(t drivers.Target) (drivers.Driver, error) {
		if t.IP == "" {
			return nil, fmt.Errorf("dahua: target.IP requis")
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

	mu    sync.Mutex
	nc    int
}

func (d *Driver) Vendor() string { return vendorName }
func (d *Driver) Capabilities() []drivers.Capability {
	return []drivers.Capability{
		drivers.CapReadEvents,
		drivers.CapDoorUnlock,
		drivers.CapGetStatus,
		drivers.CapRestart,
	}
}

func (d *Driver) Connect(ctx context.Context) error {
	res := d.GetStatus(ctx)
	if !res.OK {
		return fmt.Errorf("dahua connect: %s", res.Error)
	}
	return nil
}

func (d *Driver) Disconnect() error { return nil }

func (d *Driver) Ping(ctx context.Context) error {
	if !d.GetStatus(ctx).OK {
		return fmt.Errorf("ping failed")
	}
	return nil
}

func (d *Driver) GetStatus(ctx context.Context) drivers.Result {
	start := time.Now()
	body, err := d.get(ctx, "/cgi-bin/magicBox.cgi?action=getSystemInfo")
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error(), Duration: time.Since(start)}
	}
	info := parseKeyValueBody(string(body))
	return drivers.Result{
		OK:       true,
		Data:     mapifyInfo(info),
		Duration: time.Since(start),
	}
}

// DoorUnlock via /cgi-bin/accessControl.cgi?action=openDoor&channel=1
func (d *Driver) DoorUnlock(ctx context.Context, doorID string) drivers.Result {
	if doorID == "" {
		doorID = "1"
	}
	start := time.Now()
	path := fmt.Sprintf("/cgi-bin/accessControl.cgi?action=openDoor&channel=%s", doorID)
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
	_, err := d.get(ctx, "/cgi-bin/magicBox.cgi?action=reboot")
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error(), Duration: time.Since(start)}
	}
	return drivers.Result{OK: true, Duration: time.Since(start)}
}

func (d *Driver) PushUser(ctx context.Context, user map[string]interface{}) drivers.Result {
	return drivers.Result{OK: false, Error: "PushUser pas encore implémenté"}
}

// ReadEvents via long-poll multipart /cgi-bin/eventManager.cgi?action=attach
func (d *Driver) ReadEvents(ctx context.Context, sink drivers.EventSink) error {
	url := d.baseURL + "/cgi-bin/eventManager.cgi?action=attach&codes=[All]"
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return err
	}
	req.SetBasicAuth(d.username, d.password)

	// Long-poll : timeout très long
	longClient := &http.Client{Timeout: 24 * time.Hour}

	resp, err := longClient.Do(req)
	if err != nil {
		return fmt.Errorf("dahua attach: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == 401 {
		// Retry avec Digest
		return d.readEventsDigest(ctx, sink, resp.Header.Get("WWW-Authenticate"))
	}
	if resp.StatusCode != 200 {
		return fmt.Errorf("attach HTTP %d", resp.StatusCode)
	}

	return d.parseEventStream(ctx, resp.Body, sink)
}

// readEventsDigest retente avec un challenge digest calculé.
func (d *Driver) readEventsDigest(ctx context.Context, sink drivers.EventSink, wwwAuth string) error {
	realm, nonce, qop := parseDigestChallenge(wwwAuth)
	if realm == "" || nonce == "" {
		return fmt.Errorf("digest challenge invalide")
	}

	d.mu.Lock()
	d.nc++
	nc := d.nc
	d.mu.Unlock()

	uri := "/cgi-bin/eventManager.cgi?action=attach&codes=[All]"
	ha1 := md5hex(fmt.Sprintf("%s:%s:%s", d.username, realm, d.password))
	ha2 := md5hex(fmt.Sprintf("%s:%s", "GET", uri))
	cnonce := fmt.Sprintf("%x", time.Now().UnixNano())
	ncHex := fmt.Sprintf("%08x", nc)
	var response string
	if qop != "" {
		response = md5hex(fmt.Sprintf("%s:%s:%s:%s:%s:%s",
			ha1, nonce, ncHex, cnonce, qop, ha2))
	} else {
		response = md5hex(fmt.Sprintf("%s:%s:%s", ha1, nonce, ha2))
	}
	auth := fmt.Sprintf(
		`Digest username="%s", realm="%s", nonce="%s", uri="%s", response="%s"`,
		d.username, realm, nonce, uri, response,
	)
	if qop != "" {
		auth += fmt.Sprintf(`, qop=%s, nc=%s, cnonce="%s"`, qop, ncHex, cnonce)
	}

	req, err := http.NewRequestWithContext(ctx, "GET", d.baseURL+uri, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", auth)

	longClient := &http.Client{Timeout: 24 * time.Hour}
	resp, err := longClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return fmt.Errorf("attach digest HTTP %d", resp.StatusCode)
	}
	return d.parseEventStream(ctx, resp.Body, sink)
}

// parseEventStream lit le multipart continu et emit un event par bloc.
// Format Dahua :
//   --myboundary
//   Content-Type: text/plain
//   Content-Length: N
//
//   Code=VideoMotion;action=Start;index=0;data={"..."}
func (d *Driver) parseEventStream(ctx context.Context, r io.Reader, sink drivers.EventSink) error {
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 64*1024), 512*1024)

	for scanner.Scan() {
		line := scanner.Text()
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		if !strings.HasPrefix(line, "Code=") {
			continue
		}
		event := parseEventLine(line)
		if event == nil {
			continue
		}

		_ = sink.Emit(ctx, drivers.Event{
			Type:       mapDahuaEvent(event["code"]),
			OccurredAt: time.Now().UTC(),
			DeviceID:   d.target.ID,
			Payload: map[string]interface{}{
				"vendor": vendorName,
				"code":   event["code"],
				"action": event["action"],
				"index":  event["index"],
				"data":   event["data"],
			},
		})
	}
	return scanner.Err()
}

// parseEventLine parse "Code=X;action=Y;index=Z;data={...}"
func parseEventLine(line string) map[string]string {
	out := make(map[string]string)
	for _, part := range strings.Split(line, ";") {
		kv := strings.SplitN(part, "=", 2)
		if len(kv) == 2 {
			out[strings.ToLower(kv[0])] = kv[1]
		}
	}
	if out["code"] == "" {
		return nil
	}
	return out
}

func mapDahuaEvent(code string) string {
	code = strings.ToLower(code)
	switch {
	case strings.Contains(code, "videomotion"):
		return "camera.motion"
	case strings.Contains(code, "crossline"):
		return "camera.line_crossed"
	case strings.Contains(code, "accessgranted"):
		return "access.granted"
	case strings.Contains(code, "accessdenied"):
		return "access.denied"
	case strings.Contains(code, "tamper"):
		return "device.tamper"
	case strings.Contains(code, "doorstatus"):
		return "door.status"
	default:
		return "device.event"
	}
}

// ═══════════════════════════════════════════════════════════════════
// HTTP helpers avec fallback Digest
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

	if resp.StatusCode == 401 && resp.Header.Get("WWW-Authenticate") != "" {
		return d.retryDigest(ctx, "GET", path, resp.Header.Get("WWW-Authenticate"))
	}
	if resp.StatusCode >= 400 {
		return body, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}
	return body, nil
}

func (d *Driver) retryDigest(ctx context.Context, method, path, wwwAuth string) ([]byte, error) {
	realm, nonce, qop := parseDigestChallenge(wwwAuth)
	if realm == "" || nonce == "" {
		return nil, fmt.Errorf("digest challenge invalide")
	}
	d.mu.Lock()
	d.nc++
	nc := d.nc
	d.mu.Unlock()

	ha1 := md5hex(fmt.Sprintf("%s:%s:%s", d.username, realm, d.password))
	ha2 := md5hex(fmt.Sprintf("%s:%s", method, path))
	cnonce := fmt.Sprintf("%x", time.Now().UnixNano())
	ncHex := fmt.Sprintf("%08x", nc)
	var response string
	if qop != "" {
		response = md5hex(fmt.Sprintf("%s:%s:%s:%s:%s:%s",
			ha1, nonce, ncHex, cnonce, qop, ha2))
	} else {
		response = md5hex(fmt.Sprintf("%s:%s:%s", ha1, nonce, ha2))
	}
	auth := fmt.Sprintf(
		`Digest username="%s", realm="%s", nonce="%s", uri="%s", response="%s"`,
		d.username, realm, nonce, path, response,
	)
	if qop != "" {
		auth += fmt.Sprintf(`, qop=%s, nc=%s, cnonce="%s"`, qop, ncHex, cnonce)
	}

	req, err := http.NewRequestWithContext(ctx, method, d.baseURL+path, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", auth)

	resp, err := d.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return body, fmt.Errorf("digest HTTP %d: %s", resp.StatusCode, string(body))
	}
	return body, nil
}

// ═══════════════════════════════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════════════════════════════
func parseDigestChallenge(header string) (realm, nonce, qop string) {
	if !strings.HasPrefix(strings.TrimSpace(header), "Digest") {
		return
	}
	for _, part := range strings.Split(header[6:], ",") {
		part = strings.TrimSpace(part)
		if strings.HasPrefix(part, "realm=") {
			realm = strings.Trim(part[6:], `"`)
		} else if strings.HasPrefix(part, "nonce=") {
			nonce = strings.Trim(part[6:], `"`)
		} else if strings.HasPrefix(part, "qop=") {
			qop = strings.Trim(part[4:], `"`)
			if i := strings.Index(qop, ","); i != -1 {
				qop = qop[:i]
			}
		}
	}
	return
}

func md5hex(s string) string {
	h := md5.Sum([]byte(s))
	return hex.EncodeToString(h[:])
}

// parseKeyValueBody parse "key1=value1\nkey2=value2" (Dahua-style responses).
func parseKeyValueBody(body string) map[string]string {
	out := make(map[string]string)
	for _, line := range strings.Split(body, "\n") {
		line = strings.TrimSpace(line)
		if kv := strings.SplitN(line, "=", 2); len(kv) == 2 {
			out[strings.TrimSpace(kv[0])] = strings.TrimSpace(kv[1])
		}
	}
	return out
}

func mapifyInfo(info map[string]string) map[string]interface{} {
	out := make(map[string]interface{}, len(info))
	for k, v := range info {
		out[k] = v
	}
	return out
}

// silence unused warning si personne n'appelle log dans ce package pour l'instant
var _ = log.Info
