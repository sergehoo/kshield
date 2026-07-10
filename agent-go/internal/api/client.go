// Package api — Client HTTP pour parler au backend Django Kaydan Shield.
//
// Endpoints utilisés :
//
//	POST /api/v1/devices/edge-gateway/activate/     (première activation)
//	POST /api/v1/devices/edge-gateway/heartbeat/    (heartbeat régulier)
//	POST /api/v1/agent/events/                       (push d'events)
//	GET  /api/v1/edge-gateway/updates/check/         (auto-update)
//
// Le HMAC est calculé sur les requêtes après activation.
package api

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Client encapsule l'accès au backend cloud.
type Client struct {
	baseURL    string
	apiToken   string
	hmacSecret string
	http       *http.Client
	userAgent  string
}

// New crée un client. baseURL sans slash final.
func New(baseURL, apiToken, hmacSecret string) *Client {
	return &Client{
		baseURL:    strings.TrimRight(baseURL, "/"),
		apiToken:   apiToken,
		hmacSecret: hmacSecret,
		userAgent:  "kshield-edge-go/1.0",
		http: &http.Client{
			Timeout: 15 * time.Second,
			Transport: &http.Transport{
				MaxIdleConns:        10,
				MaxIdleConnsPerHost: 5,
				IdleConnTimeout:     90 * time.Second,
			},
		},
	}
}

// SetCredentials met à jour les credentials en runtime (après activation).
func (c *Client) SetCredentials(apiToken, hmacSecret string) {
	c.apiToken = apiToken
	c.hmacSecret = hmacSecret
}

// ─────────────────────────────────────────────────────────────────
// Activation (première fois — échange activation_token → api_token)
// ─────────────────────────────────────────────────────────────────

type ActivateRequest struct {
	ActivationToken string            `json:"activation_token"`
	GatewayID       string            `json:"gateway_id"`
	SystemInfo      map[string]string `json:"system_info"`
}

type ActivateResponse struct {
	Success       bool   `json:"success"`
	APIToken      string `json:"api_token"`
	HMACSecret    string `json:"hmac_secret"`
	MQTTUsername  string `json:"mqtt_username"`
	MQTTPassword  string `json:"mqtt_password"`
	MQTTHost      string `json:"mqtt_host"`
	MQTTPort      int    `json:"mqtt_port"`
	MQTTUseTLS    bool   `json:"mqtt_use_tls"`
	GatewayLabel  string `json:"gateway_label"`
	TenantID      string `json:"tenant_id"`
	SiteID        string `json:"site_id"`
	Message       string `json:"message,omitempty"`
	Error         string `json:"error,omitempty"`
}

// Activate échange le activation_token contre les credentials permanents.
// Appelé uniquement au premier boot (ou après un reset de la gateway).
func (c *Client) Activate(ctx context.Context, req ActivateRequest) (*ActivateResponse, error) {
	url := c.baseURL + "/api/v1/devices/edge-gateway/activate/"
	body, _ := json.Marshal(req)

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("User-Agent", c.userAgent)

	resp, err := c.http.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("HTTP: %w", err)
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("activate failed (HTTP %d): %s",
			resp.StatusCode, string(respBody))
	}

	var out ActivateResponse
	if err := json.Unmarshal(respBody, &out); err != nil {
		return nil, fmt.Errorf("parse response: %w — body: %s", err, string(respBody))
	}
	if !out.Success {
		return &out, fmt.Errorf("activate rejected: %s", out.Error)
	}
	return &out, nil
}

// ─────────────────────────────────────────────────────────────────
// Heartbeat (régulier, toutes les 30s par défaut)
// ─────────────────────────────────────────────────────────────────

type HeartbeatRequest struct {
	GatewayID      string             `json:"gateway_id"`
	Version        string             `json:"version"`
	OSInfo         string             `json:"os_info"`
	IPLocal        string             `json:"ip_local"`
	UptimeSeconds  int64              `json:"uptime_seconds"`
	EventsPending  int                `json:"events_pending"`
	MQTTStatus     string             `json:"mqtt_status"`     // ok / degraded / down
	WSStatus       string             `json:"ws_status"`
	CloudStatus    string             `json:"cloud_status"`
	DevicesDiscovered []DeviceSummary `json:"devices_discovered,omitempty"`
	// Optional metrics
	CPUPercent    float64 `json:"cpu_percent,omitempty"`
	MemoryPercent float64 `json:"memory_percent,omitempty"`
}

type DeviceSummary struct {
	IP       string `json:"ip"`
	MAC      string `json:"mac,omitempty"`
	Vendor   string `json:"vendor,omitempty"`
	Model    string `json:"model,omitempty"`
	Protocol string `json:"protocol,omitempty"`
	Firmware string `json:"firmware,omitempty"`
	Online   bool   `json:"online"`
}

type HeartbeatResponse struct {
	OK             bool           `json:"ok"`
	ServerTime     string         `json:"server_time"`
	PendingActions []PendingAction `json:"pending_actions,omitempty"`
}

type PendingAction struct {
	Type    string                 `json:"type"`   // restart / sync / update / scan
	Payload map[string]interface{} `json:"payload,omitempty"`
	ID      string                 `json:"id"`
}

// Heartbeat push l'état de la gateway au cloud et récupère les actions en attente.
func (c *Client) Heartbeat(ctx context.Context, req HeartbeatRequest) (*HeartbeatResponse, error) {
	url := c.baseURL + "/api/v1/devices/edge-gateway/heartbeat/"
	body, _ := json.Marshal(req)

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	c.setAuthHeaders(httpReq, body)

	resp, err := c.http.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("HTTP heartbeat: %w", err)
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)

	if resp.StatusCode == http.StatusUnauthorized {
		return nil, ErrRevoked
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("heartbeat failed (HTTP %d): %s",
			resp.StatusCode, string(respBody))
	}

	var out HeartbeatResponse
	if err := json.Unmarshal(respBody, &out); err != nil {
		return nil, fmt.Errorf("parse heartbeat response: %w", err)
	}
	return &out, nil
}

// ─────────────────────────────────────────────────────────────────
// Events push (batch)
// ─────────────────────────────────────────────────────────────────

type EventBatch struct {
	GatewayID string           `json:"gateway_id"`
	Events    []AgentEvent     `json:"events"`
}

type AgentEvent struct {
	Type        string                 `json:"type"`
	OccurredAt  string                 `json:"occurred_at"` // ISO8601
	Payload     map[string]interface{} `json:"payload"`
	SourceIP    string                 `json:"source_ip,omitempty"`
	SourceMAC   string                 `json:"source_mac,omitempty"`
	Signature   string                 `json:"signature,omitempty"`
}

func (c *Client) PushEvents(ctx context.Context, batch EventBatch) error {
	url := c.baseURL + "/api/v1/agent/events/"
	body, _ := json.Marshal(batch)

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	c.setAuthHeaders(httpReq, body)

	resp, err := c.http.Do(httpReq)
	if err != nil {
		return fmt.Errorf("HTTP push events: %w", err)
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)

	if resp.StatusCode == http.StatusUnauthorized {
		return ErrRevoked
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("push events failed (HTTP %d): %s",
			resp.StatusCode, string(respBody))
	}
	return nil
}

// ─────────────────────────────────────────────────────────────────
// Action result push (fire-and-forget)
// ─────────────────────────────────────────────────────────────────
type ActionResultPayload struct {
	ActionID   string                 `json:"action_id"`
	Success    bool                   `json:"success"`
	Error      string                 `json:"error,omitempty"`
	Output     map[string]interface{} `json:"output,omitempty"`
	FinishedAt string                 `json:"finished_at"`
}

// PushActionResult envoie le résultat d'une action exécutée au cloud.
// Utilisé par le dispatcher via callback OnResult.
func (c *Client) PushActionResult(ctx context.Context, res ActionResultPayload) error {
	url := c.baseURL + "/api/v1/devices/edge-gateway/action-result/"
	body, _ := json.Marshal(res)

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	c.setAuthHeaders(httpReq, body)

	resp, err := c.http.Do(httpReq)
	if err != nil {
		return fmt.Errorf("HTTP action-result: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusUnauthorized {
		return ErrRevoked
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("action-result failed (HTTP %d): %s",
			resp.StatusCode, string(respBody))
	}
	return nil
}

// ─────────────────────────────────────────────────────────────────
// Auto-update check
// ─────────────────────────────────────────────────────────────────

type UpdateCheckResponse struct {
	HasUpdate       bool   `json:"has_update"`
	LatestVersion   string `json:"latest_version"`
	CurrentVersion  string `json:"current_version"`
	DownloadURL     string `json:"download_url,omitempty"`
	ChecksumSHA256  string `json:"checksum_sha256,omitempty"`
	SignatureURL    string `json:"signature_url,omitempty"`
	ReleaseNotesURL string `json:"release_notes_url,omitempty"`
	Mandatory       bool   `json:"mandatory,omitempty"`
}

func (c *Client) CheckUpdate(ctx context.Context, currentVersion, platform string) (*UpdateCheckResponse, error) {
	url := fmt.Sprintf("%s/api/v1/edge-gateway/updates/check/?version=%s&platform=%s",
		c.baseURL, currentVersion, platform)

	httpReq, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, err
	}
	c.setAuthHeaders(httpReq, nil)

	resp, err := c.http.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("HTTP update check: %w", err)
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("update check failed (HTTP %d): %s",
			resp.StatusCode, string(respBody))
	}

	var out UpdateCheckResponse
	if err := json.Unmarshal(respBody, &out); err != nil {
		return nil, fmt.Errorf("parse update check: %w", err)
	}
	return &out, nil
}

// ─────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────

// ErrRevoked est retourné quand le serveur répond 401 = gateway révoquée.
// L'agent doit alors s'arrêter proprement au lieu de retry en boucle.
var ErrRevoked = fmt.Errorf("gateway revoked by cloud")

// setAuthHeaders ajoute Bearer token + HMAC signature + User-Agent + Content-Type.
func (c *Client) setAuthHeaders(req *http.Request, body []byte) {
	req.Header.Set("User-Agent", c.userAgent)
	req.Header.Set("Content-Type", "application/json")
	if c.apiToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.apiToken)
	}
	if c.hmacSecret != "" && body != nil {
		// Signature HMAC-SHA256 sur (timestamp + body) — anti-rejeu
		ts := fmt.Sprintf("%d", time.Now().Unix())
		mac := hmac.New(sha256.New, []byte(c.hmacSecret))
		mac.Write([]byte(ts))
		mac.Write([]byte("\n"))
		mac.Write(body)
		sig := hex.EncodeToString(mac.Sum(nil))
		req.Header.Set("X-Kshield-Timestamp", ts)
		req.Header.Set("X-Kshield-Signature", sig)
	}
}
