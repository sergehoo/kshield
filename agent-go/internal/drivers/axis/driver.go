// Package axis — Driver pour caméras + contrôleurs Axis Communications (VAPIX).
//
// VAPIX = Video API for Axis. HTTP + Digest auth par défaut.
//
// Endpoints principaux :
//   GET /axis-cgi/basicdeviceinfo.cgi              → getInfo
//   GET /axis-cgi/eventstream.cgi                  → event stream (multipart)
//   POST /axis-cgi/param.cgi?action=list           → config
//   POST /axis-cgi/opentls/uploadcert.cgi          → cert mgmt
//
// Le protocole ressemble beaucoup à Hikvision — HTTP Digest + stream.
package axis

import (
	"bufio"
	"context"
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/sergehoo/kshield/agent-go/internal/drivers"
)

const vendorName = "axis"

func init() {
	drivers.Register(vendorName, func(t drivers.Target) (drivers.Driver, error) {
		if t.IP == "" {
			return nil, fmt.Errorf("axis: target.IP requis")
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
	mu       sync.Mutex
	nc       int
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
	if !d.GetStatus(ctx).OK {
		return fmt.Errorf("axis connect failed")
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

// GetStatus interroge basicdeviceinfo.cgi.
func (d *Driver) GetStatus(ctx context.Context) drivers.Result {
	start := time.Now()
	body, err := d.jsonPost(ctx, "/axis-cgi/basicdeviceinfo.cgi", map[string]interface{}{
		"apiVersion": "1.0",
		"context":    "kshield-edge",
		"method":     "getAllProperties",
	})
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error(), Duration: time.Since(start)}
	}
	var out struct {
		Data struct {
			PropertyList map[string]interface{} `json:"propertyList"`
		} `json:"data"`
	}
	_ = json.Unmarshal(body, &out)
	return drivers.Result{
		OK:       true,
		Data:     out.Data.PropertyList,
		Duration: time.Since(start),
	}
}

// DoorUnlock — POST /vapix/services (Access Control web service).
func (d *Driver) DoorUnlock(ctx context.Context, doorID string) drivers.Result {
	if doorID == "" {
		doorID = "1"
	}
	start := time.Now()
	soapBody := fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <ExitDoor xmlns="http://www.axis.com/vapix/access/2/">
      <DoorToken>%s</DoorToken>
    </ExitDoor>
  </soap:Body>
</soap:Envelope>`, doorID)

	_, err := d.postSOAP(ctx, "/vapix/services", []byte(soapBody))
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
	_, err := d.jsonPost(ctx, "/axis-cgi/systemready.cgi", map[string]interface{}{
		"apiVersion": "1.0", "method": "restart",
	})
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error(), Duration: time.Since(start)}
	}
	return drivers.Result{OK: true, Duration: time.Since(start)}
}

func (d *Driver) PushUser(ctx context.Context, user map[string]interface{}) drivers.Result {
	return drivers.Result{OK: false, Error: "PushUser pas encore implémenté"}
}

// ReadEvents — event stream via /axis-cgi/eventstream.cgi (multipart).
func (d *Driver) ReadEvents(ctx context.Context, sink drivers.EventSink) error {
	url := d.baseURL + "/axis-cgi/eventstream.cgi"
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return err
	}
	req.SetBasicAuth(d.username, d.password)

	longClient := &http.Client{Timeout: 24 * time.Hour}
	resp, err := longClient.Do(req)
	if err != nil {
		return fmt.Errorf("axis eventstream: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == 401 && resp.Header.Get("WWW-Authenticate") != "" {
		return d.readEventsDigest(ctx, sink, resp.Header.Get("WWW-Authenticate"))
	}
	if resp.StatusCode != 200 {
		return fmt.Errorf("eventstream HTTP %d", resp.StatusCode)
	}
	return d.parseStream(ctx, resp.Body, sink)
}

func (d *Driver) readEventsDigest(ctx context.Context, sink drivers.EventSink, wwwAuth string) error {
	realm, nonce, qop := parseDigestChallenge(wwwAuth)
	if realm == "" {
		return fmt.Errorf("digest challenge invalide")
	}
	d.mu.Lock()
	d.nc++
	nc := d.nc
	d.mu.Unlock()

	uri := "/axis-cgi/eventstream.cgi"
	ha1 := md5hex(fmt.Sprintf("%s:%s:%s", d.username, realm, d.password))
	ha2 := md5hex(fmt.Sprintf("GET:%s", uri))
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
		return fmt.Errorf("eventstream digest HTTP %d", resp.StatusCode)
	}
	return d.parseStream(ctx, resp.Body, sink)
}

func (d *Driver) parseStream(ctx context.Context, r io.Reader, sink drivers.EventSink) error {
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 64*1024), 512*1024)

	var xmlBuf strings.Builder
	inXML := false

	for scanner.Scan() {
		line := scanner.Text()
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		if strings.HasPrefix(line, "<?xml") || strings.HasPrefix(line, "<MetadataStream") {
			inXML = true
			xmlBuf.Reset()
			xmlBuf.WriteString(line)
			xmlBuf.WriteByte('\n')
			continue
		}
		if inXML {
			xmlBuf.WriteString(line)
			xmlBuf.WriteByte('\n')
			if strings.HasSuffix(strings.TrimSpace(line), "</MetadataStream>") {
				d.emitXMLEvent(ctx, xmlBuf.String(), sink)
				inXML = false
				xmlBuf.Reset()
			}
		}
	}
	return scanner.Err()
}

// emitXMLEvent parse un XML Axis event et push.
func (d *Driver) emitXMLEvent(ctx context.Context, xmlBody string, sink drivers.EventSink) {
	// Format simplifié : on regarde le topic (tt:VideoAnalytics, ...)
	topicIdx := strings.Index(xmlBody, "<wsnt:Topic")
	if topicIdx == -1 {
		return
	}
	topicEnd := strings.Index(xmlBody[topicIdx:], "</wsnt:Topic>")
	if topicEnd == -1 {
		return
	}
	topic := xmlBody[topicIdx : topicIdx+topicEnd]

	_ = sink.Emit(ctx, drivers.Event{
		Type:       mapAxisTopic(topic),
		OccurredAt: time.Now().UTC(),
		DeviceID:   d.target.ID,
		Payload: map[string]interface{}{
			"vendor": vendorName,
			"topic":  topic,
			"raw":    xmlBody[:min(len(xmlBody), 500)],
		},
	})
}

func mapAxisTopic(topic string) string {
	topic = strings.ToLower(topic)
	switch {
	case strings.Contains(topic, "motionalarm"), strings.Contains(topic, "videoanalytics"):
		return "camera.motion"
	case strings.Contains(topic, "accesscontrol"):
		return "access.granted"
	case strings.Contains(topic, "tampering"):
		return "device.tamper"
	case strings.Contains(topic, "input"):
		return "device.input_change"
	default:
		return "device.event"
	}
}

// ═══════════════════════════════════════════════════════════════════
// HTTP helpers
// ═══════════════════════════════════════════════════════════════════
func (d *Driver) jsonPost(ctx context.Context, path string, body map[string]interface{}) ([]byte, error) {
	jsonBody, _ := json.Marshal(body)
	req, err := http.NewRequestWithContext(ctx, "POST", d.baseURL+path, strings.NewReader(string(jsonBody)))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(d.username, d.password)

	resp, err := d.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return respBody, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(respBody))
	}
	return respBody, nil
}

func (d *Driver) postSOAP(ctx context.Context, path string, body []byte) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, "POST", d.baseURL+path, strings.NewReader(string(body)))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/soap+xml; charset=utf-8")
	req.SetBasicAuth(d.username, d.password)

	resp, err := d.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return respBody, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(respBody))
	}
	return respBody, nil
}

// Utilities dupliqués (compatibilité — devrait être un package util partagé)
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

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

var _ = log.Info
