// Package hikvision — Driver pour caméras + contrôleurs Hikvision (ISAPI).
//
// ISAPI = Intelligent Security API. HTTP + Digest auth par défaut.
//
// Endpoints utilisés :
//
//   GET /ISAPI/System/deviceInfo        → getInfo / getStatus
//   GET /ISAPI/Event/notification/alertStream  → long-poll event stream (multipart)
//   PUT /ISAPI/AccessControl/RemoteControl/door/1  → unlock door
//
// Le event stream retourne un multipart continu, chaque part contient un
// XML event (access.granted / tamper / motion / etc.).
package hikvision

import (
	"bufio"
	"context"
	"crypto/md5"
	"encoding/hex"
	"encoding/xml"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/sergehoo/kshield/agent-go/internal/drivers"
)

const vendorName = "hikvision"

func init() {
	drivers.Register(vendorName, func(t drivers.Target) (drivers.Driver, error) {
		if t.IP == "" {
			return nil, fmt.Errorf("hikvision: target.IP requis")
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

// Driver implémente drivers.Driver pour Hikvision.
type Driver struct {
	target   drivers.Target
	baseURL  string
	username string
	password string
	client   *http.Client

	mu       sync.Mutex
	realm    string
	nonce    string
	qop      string
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

// Connect fait un getStatus pour valider IP + credentials.
func (d *Driver) Connect(ctx context.Context) error {
	res := d.GetStatus(ctx)
	if !res.OK {
		return fmt.Errorf("hikvision connect: %s", res.Error)
	}
	return nil
}

func (d *Driver) Disconnect() error {
	// HTTP stateless — rien à fermer explicitement.
	return nil
}

func (d *Driver) Ping(ctx context.Context) error {
	res := d.GetStatus(ctx)
	if !res.OK {
		return fmt.Errorf("ping: %s", res.Error)
	}
	return nil
}

// GetStatus récupère /ISAPI/System/deviceInfo (auth Digest).
func (d *Driver) GetStatus(ctx context.Context) drivers.Result {
	start := time.Now()
	body, err := d.doRequest(ctx, "GET", "/ISAPI/System/deviceInfo", nil)
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error(), Duration: time.Since(start)}
	}

	// Parse XML minimal — extrait deviceName + firmwareVersion
	var info struct {
		DeviceName      string `xml:"deviceName"`
		FirmwareVersion string `xml:"firmwareVersion"`
		Model           string `xml:"model"`
		SerialNumber    string `xml:"serialNumber"`
		MACAddress      string `xml:"macAddress"`
	}
	_ = xml.Unmarshal(body, &info)

	return drivers.Result{
		OK: true,
		Data: map[string]interface{}{
			"device_name":      info.DeviceName,
			"model":            info.Model,
			"firmware":         info.FirmwareVersion,
			"serial_number":    info.SerialNumber,
			"mac_address":      info.MACAddress,
		},
		Duration: time.Since(start),
	}
}

// DoorUnlock envoie un PUT sur /ISAPI/AccessControl/RemoteControl/door/<id>.
func (d *Driver) DoorUnlock(ctx context.Context, doorID string) drivers.Result {
	if doorID == "" {
		doorID = "1"
	}
	body := []byte(`<?xml version="1.0" encoding="UTF-8"?>
<RemoteControlDoor>
    <cmd>open</cmd>
</RemoteControlDoor>`)
	start := time.Now()
	_, err := d.doRequest(ctx, "PUT",
		"/ISAPI/AccessControl/RemoteControl/door/"+doorID, body)
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error(), Duration: time.Since(start)}
	}
	return drivers.Result{OK: true, Duration: time.Since(start),
		Data: map[string]interface{}{"door_id": doorID}}
}

// Sync — placeholder.
func (d *Driver) Sync(ctx context.Context) drivers.Result {
	return drivers.Result{OK: false, Error: "Sync pas encore implémenté"}
}

// Restart via /ISAPI/System/reboot.
func (d *Driver) Restart(ctx context.Context) drivers.Result {
	start := time.Now()
	_, err := d.doRequest(ctx, "PUT", "/ISAPI/System/reboot", nil)
	if err != nil {
		return drivers.Result{OK: false, Error: err.Error(), Duration: time.Since(start)}
	}
	return drivers.Result{OK: true, Duration: time.Since(start)}
}

// PushUser — placeholder (POST /ISAPI/AccessControl/UserInfo/Record).
func (d *Driver) PushUser(ctx context.Context, user map[string]interface{}) drivers.Result {
	return drivers.Result{OK: false, Error: "PushUser pas encore implémenté"}
}

// ═══════════════════════════════════════════════════════════════════
// ReadEvents — long-poll multipart sur /ISAPI/Event/notification/alertStream
// ═══════════════════════════════════════════════════════════════════
func (d *Driver) ReadEvents(ctx context.Context, sink drivers.EventSink) error {
	url := d.baseURL + "/ISAPI/Event/notification/alertStream"

	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return err
	}

	// Auth Digest sur premier round-trip
	// Note : ce driver simplifie en utilisant Basic auth quand possible.
	// Hikvision moderne accepte Basic par défaut si "Digest" désactivé.
	req.SetBasicAuth(d.username, d.password)

	// Long-polling — timeout très long pour laisser le stream ouvert
	longClient := &http.Client{Timeout: 24 * time.Hour}

	resp, err := longClient.Do(req)
	if err != nil {
		return fmt.Errorf("alertStream connect: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == 401 {
		return fmt.Errorf("alertStream: 401 Unauthorized (credentials Hikvision)")
	}
	if resp.StatusCode != 200 {
		return fmt.Errorf("alertStream: HTTP %d", resp.StatusCode)
	}

	// Parse multipart continu
	return d.parseAlertStream(ctx, resp.Body, sink)
}

// parseAlertStream lit le multipart stream et emit chaque event XML.
func (d *Driver) parseAlertStream(ctx context.Context, r io.Reader, sink drivers.EventSink) error {
	// Format multipart Hikvision — sépare avec "--MIME_boundary"
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

		// Détection début XML
		if strings.HasPrefix(line, "<?xml") || strings.HasPrefix(line, "<EventNotificationAlert") {
			inXML = true
			xmlBuf.Reset()
			xmlBuf.WriteString(line)
			xmlBuf.WriteByte('\n')
			continue
		}

		if inXML {
			xmlBuf.WriteString(line)
			xmlBuf.WriteByte('\n')

			// Fin du XML détectée
			if strings.HasSuffix(strings.TrimSpace(line), "</EventNotificationAlert>") {
				d.emitXMLEvent(ctx, xmlBuf.String(), sink)
				inXML = false
				xmlBuf.Reset()
			}
		}
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("scanner: %w", err)
	}
	return nil
}

// emitXMLEvent parse un XML alert et push vers le sink.
func (d *Driver) emitXMLEvent(ctx context.Context, xmlBody string, sink drivers.EventSink) {
	var alert struct {
		IPAddress     string `xml:"ipAddress"`
		DeviceID      string `xml:"channelID"`
		EventType     string `xml:"eventType"`
		EventState    string `xml:"eventState"`
		EventDesc     string `xml:"eventDescription"`
		ActivePost    string `xml:"activePostCount"`
		DateTime      string `xml:"dateTime"`
		AccessEvent   struct {
			CardNo    string `xml:"cardNo"`
			EmployeeID string `xml:"employeeNoString"`
			DoorNo    string `xml:"doorNo"`
			VerifyMode string `xml:"currentVerifyMode"`
		} `xml:"AccessControllerEvent"`
	}

	if err := xml.Unmarshal([]byte(xmlBody), &alert); err != nil {
		log.Debug().Err(err).Msg("hikvision: XML unmarshal failed")
		return
	}

	ts, _ := time.Parse(time.RFC3339, alert.DateTime)
	if ts.IsZero() {
		ts = time.Now().UTC()
	}

	payload := map[string]interface{}{
		"vendor":       vendorName,
		"event_type":   alert.EventType,
		"event_state":  alert.EventState,
		"event_desc":   alert.EventDesc,
		"channel_id":   alert.DeviceID,
	}
	if alert.AccessEvent.CardNo != "" {
		payload["card"] = alert.AccessEvent.CardNo
		payload["employee_id"] = alert.AccessEvent.EmployeeID
		payload["door"] = alert.AccessEvent.DoorNo
		payload["verify_mode"] = alert.AccessEvent.VerifyMode
	}

	_ = sink.Emit(ctx, drivers.Event{
		Type:       mapEventType(alert.EventType),
		OccurredAt: ts,
		DeviceID:   d.target.ID,
		SourceIP:   alert.IPAddress,
		Payload:    payload,
	})
}

// mapEventType convertit un event Hikvision vers le taxonomie Kaydan Shield.
func mapEventType(hikType string) string {
	switch strings.ToLower(hikType) {
	case "accessgranted", "cardgranted":
		return "access.granted"
	case "accessdenied", "carddenied":
		return "access.denied"
	case "duress":
		return "access.duress"
	case "tamperalarm", "opencasealarm":
		return "device.tamper"
	case "motiondetection":
		return "camera.motion"
	case "linedetection":
		return "camera.line_crossed"
	default:
		return "device.event"
	}
}

// ═══════════════════════════════════════════════════════════════════
// HTTP request helper avec Digest auth fallback → Basic
// ═══════════════════════════════════════════════════════════════════
func (d *Driver) doRequest(ctx context.Context, method, path string, body []byte) ([]byte, error) {
	url := d.baseURL + path

	var reqBody io.Reader
	if body != nil {
		reqBody = strings.NewReader(string(body))
	}

	req, err := http.NewRequestWithContext(ctx, method, url, reqBody)
	if err != nil {
		return nil, err
	}
	req.SetBasicAuth(d.username, d.password)
	if body != nil {
		req.Header.Set("Content-Type", "application/xml")
	}

	resp, err := d.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)

	if resp.StatusCode == 401 && resp.Header.Get("WWW-Authenticate") != "" {
		// Retry avec Digest si Basic refusé
		return d.retryWithDigest(ctx, method, path, body, resp.Header.Get("WWW-Authenticate"))
	}
	if resp.StatusCode >= 400 {
		return respBody, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(respBody))
	}
	return respBody, nil
}

// retryWithDigest calcule un header Digest simple et retry.
// N'implémente que le cas MD5 le plus courant Hikvision.
func (d *Driver) retryWithDigest(ctx context.Context, method, path string,
	body []byte, wwwAuth string) ([]byte, error) {

	realm, nonce, qop := parseDigestChallenge(wwwAuth)
	if realm == "" || nonce == "" {
		return nil, fmt.Errorf("digest challenge invalide: %s", wwwAuth)
	}

	d.mu.Lock()
	d.nc++
	nc := d.nc
	d.mu.Unlock()

	// HA1 = MD5(user:realm:pass)
	ha1 := md5hex(fmt.Sprintf("%s:%s:%s", d.username, realm, d.password))
	// HA2 = MD5(method:path)
	ha2 := md5hex(fmt.Sprintf("%s:%s", method, path))
	// cnonce arbitraire
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

	var reqBody io.Reader
	if body != nil {
		reqBody = strings.NewReader(string(body))
	}
	req, err := http.NewRequestWithContext(ctx, method, d.baseURL+path, reqBody)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", auth)
	if body != nil {
		req.Header.Set("Content-Type", "application/xml")
	}

	resp, err := d.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return respBody, fmt.Errorf("digest HTTP %d: %s", resp.StatusCode, string(respBody))
	}
	return respBody, nil
}

// parseDigestChallenge extrait realm/nonce/qop d'un header WWW-Authenticate.
func parseDigestChallenge(header string) (realm, nonce, qop string) {
	if !strings.HasPrefix(strings.TrimSpace(header), "Digest") {
		return
	}
	fields := header[6:]
	for _, part := range strings.Split(fields, ",") {
		part = strings.TrimSpace(part)
		if strings.HasPrefix(part, "realm=") {
			realm = strings.Trim(part[6:], `"`)
		} else if strings.HasPrefix(part, "nonce=") {
			nonce = strings.Trim(part[6:], `"`)
		} else if strings.HasPrefix(part, "qop=") {
			qop = strings.Trim(part[4:], `"`)
			// Certains serveurs listent "auth,auth-int" → on prend le premier
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
