// Package mqtt — Client MQTT pour l'agent Kaydan Edge Gateway.
//
// Topics utilisés :
//
//	Publish (agent → cloud) :
//	  kshield/edge/<gateway_id>/events        — batch d'events métier
//	  kshield/edge/<gateway_id>/status        — heartbeat compact
//	  kshield/edge/<gateway_id>/scan          — résultat scan réseau
//
//	Subscribe (cloud → agent) :
//	  kshield/cmd/edge/<gateway_id>/#         — commandes admin
//	                                             (restart, sync, unlock, etc.)
//	  kshield/cmd/broadcast/#                 — broadcast à toutes les gateways
//
// La reconnexion est automatique avec backoff exponentiel via l'option
// AutoReconnect de paho.
package mqtt

import (
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"os"
	"time"

	pahomqtt "github.com/eclipse/paho.mqtt.golang"
	"github.com/rs/zerolog/log"
)

// Config regroupe les paramètres de connexion.
type Config struct {
	Host      string // ex: "mqtt.kaydanshield.com" ou "shieldmqtt"
	Port      int    // 1883 (clair) ou 8883 (TLS)
	Username  string
	Password  string
	UseTLS    bool
	CAFile    string // path vers CA custom (optionnel)
	VerifyCert bool
	GatewayID string // pour namespacer les topics + client_id
}

// MessageHandler reçoit les messages entrants sur les topics souscrits.
// topic = topic complet (ex: "kshield/cmd/edge/xxxx/restart"),
// payload = bytes du message.
type MessageHandler func(topic string, payload []byte)

// Client encapsule un client MQTT avec les topics Kaydan Shield.
type Client struct {
	cfg      Config
	mqtt     pahomqtt.Client
	handler  MessageHandler
	topicIn  string // topic subscribed (cmd)
	topicOut string // topic publié (events)
}

// New crée un client. Ne connecte pas immédiatement — appeler Connect().
func New(cfg Config, handler MessageHandler) *Client {
	if handler == nil {
		handler = func(topic string, payload []byte) {
			log.Debug().Str("topic", topic).Int("bytes", len(payload)).
				Msg("MQTT msg (no handler)")
		}
	}
	return &Client{
		cfg:      cfg,
		handler:  handler,
		topicIn:  fmt.Sprintf("kshield/cmd/edge/%s/#", cfg.GatewayID),
		topicOut: fmt.Sprintf("kshield/edge/%s/events", cfg.GatewayID),
	}
}

// Connect établit la connexion au broker + subscribe.
func (c *Client) Connect() error {
	broker := fmt.Sprintf("tcp://%s:%d", c.cfg.Host, c.cfg.Port)
	if c.cfg.UseTLS {
		broker = fmt.Sprintf("ssl://%s:%d", c.cfg.Host, c.cfg.Port)
	}

	opts := pahomqtt.NewClientOptions()
	opts.AddBroker(broker)
	opts.SetClientID(fmt.Sprintf("kshield-edge-%s", c.cfg.GatewayID))
	opts.SetUsername(c.cfg.Username)
	opts.SetPassword(c.cfg.Password)
	opts.SetKeepAlive(60 * time.Second)
	opts.SetPingTimeout(10 * time.Second)
	opts.SetConnectTimeout(15 * time.Second)
	opts.SetAutoReconnect(true)
	opts.SetMaxReconnectInterval(2 * time.Minute)
	opts.SetCleanSession(false) // conserver la subscription cross-reconnect
	opts.SetOrderMatters(false)

	// TLS config
	if c.cfg.UseTLS {
		tlsCfg := &tls.Config{
			InsecureSkipVerify: !c.cfg.VerifyCert,
		}
		if c.cfg.CAFile != "" {
			caBytes, err := os.ReadFile(c.cfg.CAFile)
			if err != nil {
				return fmt.Errorf("read CA file %s: %w", c.cfg.CAFile, err)
			}
			pool := x509.NewCertPool()
			if !pool.AppendCertsFromPEM(caBytes) {
				return fmt.Errorf("invalid CA cert in %s", c.cfg.CAFile)
			}
			tlsCfg.RootCAs = pool
		}
		opts.SetTLSConfig(tlsCfg)
	}

	// Callbacks
	opts.SetOnConnectHandler(func(client pahomqtt.Client) {
		log.Info().Str("broker", broker).Msg("MQTT connecté")
		// (Re)subscribe à chaque connexion (même après reconnexion)
		token := client.Subscribe(c.topicIn, 1, func(_ pahomqtt.Client, msg pahomqtt.Message) {
			log.Debug().
				Str("topic", msg.Topic()).
				Int("bytes", len(msg.Payload())).
				Msg("MQTT message reçu")
			c.handler(msg.Topic(), msg.Payload())
		})
		if token.WaitTimeout(5*time.Second) && token.Error() != nil {
			log.Error().Err(token.Error()).Msg("MQTT subscribe échoué")
		} else {
			log.Info().Str("topic", c.topicIn).Msg("MQTT subscribed")
		}
	})

	opts.SetConnectionLostHandler(func(_ pahomqtt.Client, err error) {
		log.Warn().Err(err).Msg("MQTT déconnecté — reconnexion en cours...")
	})

	c.mqtt = pahomqtt.NewClient(opts)
	token := c.mqtt.Connect()
	if !token.WaitTimeout(20 * time.Second) {
		return fmt.Errorf("MQTT connect timeout après 20s")
	}
	if err := token.Error(); err != nil {
		return fmt.Errorf("MQTT connect: %w", err)
	}
	return nil
}

// Disconnect ferme proprement la connexion.
func (c *Client) Disconnect() {
	if c.mqtt != nil && c.mqtt.IsConnected() {
		c.mqtt.Disconnect(1000) // 1s pour flush les in-flight
	}
}

// IsConnected retourne l'état actuel de la connexion.
func (c *Client) IsConnected() bool {
	return c.mqtt != nil && c.mqtt.IsConnected()
}

// Publish envoie un message sur un topic donné (QoS 1 par défaut).
func (c *Client) Publish(topic string, payload []byte) error {
	if !c.IsConnected() {
		return fmt.Errorf("MQTT non connecté")
	}
	token := c.mqtt.Publish(topic, 1, false, payload)
	if !token.WaitTimeout(5 * time.Second) {
		return fmt.Errorf("MQTT publish timeout")
	}
	return token.Error()
}

// PublishEvents envoie un batch d'events sur le topic dédié events.
func (c *Client) PublishEvents(payload []byte) error {
	return c.Publish(c.topicOut, payload)
}

// PublishStatus envoie un heartbeat compact via MQTT (complémentaire HTTP).
func (c *Client) PublishStatus(payload []byte) error {
	topic := fmt.Sprintf("kshield/edge/%s/status", c.cfg.GatewayID)
	return c.Publish(topic, payload)
}

// Status retourne un des trois états attendus par le heartbeat HTTP.
func (c *Client) Status() string {
	if c == nil || c.mqtt == nil {
		return "down"
	}
	if c.mqtt.IsConnected() {
		return "ok"
	}
	return "degraded" // en cours de reconnexion
}
