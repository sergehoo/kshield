// Package ws — Client WebSocket vers Django Channels.
//
// Endpoint côté serveur : ws(s)://.../ws/agents/<gateway_id>/
//
// Utilité : recevoir des commandes temps réel qui ne peuvent pas attendre
// le tick heartbeat (30s) ni MQTT (potentiellement en cours de reconnexion).
// Exemples : unlock d'urgence, kill switch, révocation immédiate.
//
// Reconnexion automatique avec backoff exponentiel + max_attempts config.
package ws

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/rs/zerolog/log"
)

// Config regroupe les paramètres du client WS.
type Config struct {
	ServerURL string // ex: "https://kaydanshield.com"
	GatewayID string
	APIToken  string // Bearer pour auth

	// Reconnexion
	InitialReconnectDelay time.Duration // défaut 5s
	MaxReconnectDelay     time.Duration // défaut 2min
	MaxReconnectAttempts  int           // défaut 999999 (~jamais abandonner)
}

// MessageHandler reçoit les payloads WS entrants.
type MessageHandler func(payload []byte)

// Client encapsule la connexion WS + boucle de reconnexion.
type Client struct {
	cfg     Config
	handler MessageHandler

	mu        sync.Mutex
	conn      *websocket.Conn
	connected bool
	stopped   bool

	stopCh chan struct{}
}

// New construit un client. Ne connecte pas immédiatement — appeler Start().
func New(cfg Config, handler MessageHandler) *Client {
	if cfg.InitialReconnectDelay == 0 {
		cfg.InitialReconnectDelay = 5 * time.Second
	}
	if cfg.MaxReconnectDelay == 0 {
		cfg.MaxReconnectDelay = 2 * time.Minute
	}
	if cfg.MaxReconnectAttempts == 0 {
		cfg.MaxReconnectAttempts = 999999
	}
	if handler == nil {
		handler = func(p []byte) {
			log.Debug().Int("bytes", len(p)).Msg("WS msg (no handler)")
		}
	}
	return &Client{
		cfg:     cfg,
		handler: handler,
		stopCh:  make(chan struct{}),
	}
}

// wsURL dérive l'URL WebSocket depuis ServerURL (http→ws, https→wss).
func (c *Client) wsURL() (string, error) {
	u, err := url.Parse(c.cfg.ServerURL)
	if err != nil {
		return "", err
	}
	switch strings.ToLower(u.Scheme) {
	case "http":
		u.Scheme = "ws"
	case "https":
		u.Scheme = "wss"
	}
	u.Path = fmt.Sprintf("/ws/agents/%s/", c.cfg.GatewayID)
	return u.String(), nil
}

// Start lance la boucle connect-read-reconnect dans une goroutine.
// Ne bloque pas. Utiliser Stop() pour arrêter.
func (c *Client) Start(ctx context.Context) {
	go c.loop(ctx)
}

// Stop demande un arrêt propre.
func (c *Client) Stop() {
	c.mu.Lock()
	c.stopped = true
	if c.conn != nil {
		_ = c.conn.Close()
	}
	c.mu.Unlock()
	close(c.stopCh)
}

// IsConnected retourne l'état actuel de la connexion.
func (c *Client) IsConnected() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.connected
}

// Status retourne un des trois états attendus par le heartbeat HTTP.
func (c *Client) Status() string {
	if c == nil {
		return "down"
	}
	if c.IsConnected() {
		return "ok"
	}
	c.mu.Lock()
	stopped := c.stopped
	c.mu.Unlock()
	if stopped {
		return "down"
	}
	return "degraded" // en cours de reconnexion
}

// Send envoie un message JSON au serveur (write bloquant, thread-safe).
func (c *Client) Send(payload interface{}) error {
	c.mu.Lock()
	conn := c.conn
	c.mu.Unlock()
	if conn == nil {
		return fmt.Errorf("WS non connecté")
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	return conn.WriteMessage(websocket.TextMessage, data)
}

// loop est la boucle principale : connect → read → reconnect.
func (c *Client) loop(ctx context.Context) {
	attempts := 0
	delay := c.cfg.InitialReconnectDelay

	for {
		select {
		case <-ctx.Done():
			return
		case <-c.stopCh:
			return
		default:
		}

		c.mu.Lock()
		stopped := c.stopped
		c.mu.Unlock()
		if stopped {
			return
		}

		if err := c.connectAndRead(ctx); err != nil {
			attempts++
			if attempts > c.cfg.MaxReconnectAttempts {
				log.Error().
					Int("attempts", attempts).
					Msg("WS max reconnect attempts atteint — abandon")
				return
			}
			// Backoff exponentiel plafonné à MaxReconnectDelay
			delay = time.Duration(math.Min(
				float64(c.cfg.MaxReconnectDelay),
				float64(delay)*1.5,
			))
			log.Warn().
				Err(err).
				Int("attempt", attempts).
				Dur("retry_in", delay).
				Msg("WS déconnecté — reconnexion en cours")
			select {
			case <-ctx.Done():
				return
			case <-c.stopCh:
				return
			case <-time.After(delay):
			}
		} else {
			// Retour à un délai court après une connexion réussie
			attempts = 0
			delay = c.cfg.InitialReconnectDelay
		}
	}
}

// connectAndRead ouvre la WS et boucle en lecture jusqu'à erreur ou stop.
func (c *Client) connectAndRead(ctx context.Context) error {
	wsURL, err := c.wsURL()
	if err != nil {
		return fmt.Errorf("URL invalide: %w", err)
	}

	dialer := websocket.Dialer{
		HandshakeTimeout: 15 * time.Second,
	}
	headers := http.Header{}
	if c.cfg.APIToken != "" {
		headers.Set("Authorization", "Bearer "+c.cfg.APIToken)
	}
	headers.Set("User-Agent", "kshield-edge-go/1.0")

	dialCtx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()

	conn, resp, err := dialer.DialContext(dialCtx, wsURL, headers)
	if err != nil {
		status := "?"
		if resp != nil {
			status = resp.Status
			resp.Body.Close()
		}
		return fmt.Errorf("dial %s (%s): %w", wsURL, status, err)
	}

	c.mu.Lock()
	c.conn = conn
	c.connected = true
	c.mu.Unlock()

	log.Info().Str("url", wsURL).Msg("WS connecté")

	// Ping/pong pour détecter les déconnexions silencieuses
	conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	conn.SetPongHandler(func(string) error {
		conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		return nil
	})

	// Goroutine qui envoie un ping toutes les 25s
	pingDone := make(chan struct{})
	go func() {
		ticker := time.NewTicker(25 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-pingDone:
				return
			case <-ticker.C:
				if err := conn.WriteControl(websocket.PingMessage, nil,
					time.Now().Add(5*time.Second)); err != nil {
					return
				}
			}
		}
	}()

	// Boucle de lecture
	defer func() {
		close(pingDone)
		c.mu.Lock()
		c.conn = nil
		c.connected = false
		c.mu.Unlock()
		_ = conn.Close()
	}()

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-c.stopCh:
			return nil
		default:
		}

		msgType, payload, err := conn.ReadMessage()
		if err != nil {
			return fmt.Errorf("read: %w", err)
		}
		if msgType == websocket.TextMessage || msgType == websocket.BinaryMessage {
			c.handler(payload)
		}
	}
}
