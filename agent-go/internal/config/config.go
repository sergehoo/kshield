// Package config — Chargement + validation de la configuration TOML.
//
// La config est générée côté serveur Django par le PackageGenerator et
// embarquée dans le ZIP téléchargé. Ce package la lit au boot de l'agent.
//
// Emplacements par défaut selon plateforme :
//
//	Linux   : /etc/kshield-edge/kshield-agent.toml
//	macOS   : /etc/kshield-edge/kshield-agent.toml
//	Windows : C:\ProgramData\KaydanEdge\kshield-agent.toml
//
// Peut être surchargé via variable d'env KSHIELD_CONFIG_FILE ou flag CLI.
package config

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"

	"github.com/BurntSushi/toml"
)

// Config est le shape complet de kshield-agent.toml.
// Les tags `toml:"..."` doivent matcher exactement les clés du fichier
// généré par devices/services/package_generator.py.
type Config struct {
	Gateway  GatewaySection  `toml:"gateway"`
	Cloud    CloudSection    `toml:"cloud"`
	MQTT     MQTTSection     `toml:"mqtt"`
	Agent    AgentSection    `toml:"agent"`
	Logging  LoggingSection  `toml:"logging"`
	Devices  DevicesSection  `toml:"devices"`
	Advanced AdvancedSection `toml:"advanced"`
	Metrics  MetricsSection  `toml:"metrics"`

	// Targets : équipements vendors pilotés par cette gateway.
	// Alimenté depuis Kaydan Shield admin lors du download personnalisé,
	// mis à jour ensuite via commandes MQTT ou heartbeat pull.
	Targets []TargetSection `toml:"targets"`

	// Path d'où la config a été chargée — utile pour les logs et l'écriture
	// de tokens rotatés.
	SourcePath string `toml:"-"`
}

// TargetSection déclare un équipement vendor à connecter.
type TargetSection struct {
	ID       string            `toml:"id"`
	Vendor   string            `toml:"vendor"`     // "zkteco" / "hikvision" / ...
	IP       string            `toml:"ip"`
	Port     int               `toml:"port"`
	Username string            `toml:"username"`
	Password string            `toml:"password"`
	Extra    map[string]string `toml:"extra"`
}

// MetricsSection configure l'endpoint Prometheus opt-in.
type MetricsSection struct {
	Enabled    bool   `toml:"enabled"`
	ListenAddr string `toml:"listen_addr"` // ex: "127.0.0.1:9090"
}

type GatewaySection struct {
	ID       string `toml:"id"`
	Label    string `toml:"label"`
	TenantID string `toml:"tenant_id"`
	SiteID   string `toml:"site_id"`
}

type CloudSection struct {
	ServerURL          string `toml:"server_url"`
	ActivationToken    string `toml:"activation_token"`
	APIToken           string `toml:"api_token,omitempty"` // écrit après activation
	ActivationTTLHours int    `toml:"activation_ttl_hours"`
	HMACSecret         string `toml:"hmac_secret,omitempty"` // écrit après activation
}

type MQTTSection struct {
	Host        string `toml:"host"`
	Port        int    `toml:"port"`
	UseTLS      bool   `toml:"use_tls"`
	Username    string `toml:"username"`
	Password    string `toml:"password,omitempty"` // écrit après activation
	VerifyCert  bool   `toml:"verify_cert"`
	CAFile      string `toml:"ca_file"`
}

type AgentSection struct {
	Version                     string `toml:"version"`
	HeartbeatIntervalSeconds    int    `toml:"heartbeat_interval_seconds"`
	OfflineQueueMaxEvents       int    `toml:"offline_queue_max_events"`
	ScanNetworkEnabled          bool   `toml:"scan_network_enabled"`
	ScanNetworkIntervalHours    int    `toml:"scan_network_interval_hours"`
	AutoUpdateEnabled           bool   `toml:"auto_update_enabled"`
	AutoUpdateCheckIntervalHours int   `toml:"auto_update_check_interval_hours"`
}

type LoggingSection struct {
	Level       string `toml:"level"`
	File        string `toml:"file"`
	MaxSizeMB   int    `toml:"max_size_mb"`
	BackupCount int    `toml:"backup_count"`
}

type DevicesSection struct {
	EnableZKTeco    bool `toml:"enable_zkteco"`
	EnableHikvision bool `toml:"enable_hikvision"`
	EnableSuprema   bool `toml:"enable_suprema"`
	EnableHID       bool `toml:"enable_hid"`
	EnableDahua     bool `toml:"enable_dahua"`
	EnableAxis      bool `toml:"enable_axis"`
	EnableONVIF     bool `toml:"enable_onvif"`
}

type AdvancedSection struct {
	HMACSignatureEnabled           bool `toml:"hmac_signature_enabled"`
	WebSocketReconnectDelaySeconds int  `toml:"websocket_reconnect_delay_seconds"`
	WebSocketMaxReconnectAttempts  int  `toml:"websocket_max_reconnect_attempts"`
}

// DefaultPath retourne le chemin standard de config par OS.
func DefaultPath() string {
	if runtime.GOOS == "windows" {
		programData := os.Getenv("ProgramData")
		if programData == "" {
			programData = `C:\ProgramData`
		}
		return filepath.Join(programData, "KaydanEdge", "kshield-agent.toml")
	}
	// Linux + macOS
	return "/etc/kshield-edge/kshield-agent.toml"
}

// Load lit + parse le fichier TOML au chemin donné.
// Si path == "", utilise DefaultPath() ou la var d'env KSHIELD_CONFIG_FILE.
func Load(path string) (*Config, error) {
	if path == "" {
		path = os.Getenv("KSHIELD_CONFIG_FILE")
	}
	if path == "" {
		path = DefaultPath()
	}

	// Résout les paths relatifs
	if !filepath.IsAbs(path) {
		abs, err := filepath.Abs(path)
		if err == nil {
			path = abs
		}
	}

	if _, err := os.Stat(path); err != nil {
		return nil, fmt.Errorf("config file not found at %s: %w", path, err)
	}

	var cfg Config
	if _, err := toml.DecodeFile(path, &cfg); err != nil {
		return nil, fmt.Errorf("parse TOML %s: %w", path, err)
	}
	cfg.SourcePath = path

	if err := cfg.Validate(); err != nil {
		return nil, fmt.Errorf("invalid config: %w", err)
	}

	return &cfg, nil
}

// Validate vérifie les invariants critiques. Retourne une erreur si un
// champ requis manque ou est invalide.
func (c *Config) Validate() error {
	if c.Gateway.ID == "" {
		return fmt.Errorf("gateway.id required")
	}
	if c.Cloud.ServerURL == "" {
		return fmt.Errorf("cloud.server_url required")
	}
	// Doit avoir soit un activation_token (première activation)
	// soit un api_token (déjà activé)
	if c.Cloud.ActivationToken == "" && c.Cloud.APIToken == "" {
		return fmt.Errorf("cloud.activation_token OR cloud.api_token required")
	}
	if c.MQTT.Host == "" {
		return fmt.Errorf("mqtt.host required")
	}
	if c.MQTT.Port <= 0 || c.MQTT.Port > 65535 {
		return fmt.Errorf("mqtt.port invalid: %d", c.MQTT.Port)
	}
	if c.Agent.HeartbeatIntervalSeconds <= 0 {
		c.Agent.HeartbeatIntervalSeconds = 30 // default
	}
	return nil
}

// IsActivated retourne true si la gateway a déjà été appairée (api_token présent).
func (c *Config) IsActivated() bool {
	return c.Cloud.APIToken != ""
}

// SaveActivationCredentials écrit dans le TOML les credentials permanents
// reçus lors de l'activation (api_token, hmac_secret, mqtt password).
// Réécrit le fichier de config de manière atomique.
func (c *Config) SaveActivationCredentials(apiToken, hmacSecret, mqttPassword string) error {
	c.Cloud.APIToken = apiToken
	c.Cloud.HMACSecret = hmacSecret
	c.MQTT.Password = mqttPassword
	// L'activation_token est one-shot, on le vide pour éviter réutilisation
	c.Cloud.ActivationToken = ""

	if c.SourcePath == "" {
		return fmt.Errorf("cannot save: SourcePath empty")
	}

	// Écriture atomique via fichier temporaire + rename
	tmp := c.SourcePath + ".tmp"
	f, err := os.OpenFile(tmp, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0600)
	if err != nil {
		return fmt.Errorf("open tmp: %w", err)
	}

	enc := toml.NewEncoder(f)
	if err := enc.Encode(c); err != nil {
		f.Close()
		os.Remove(tmp)
		return fmt.Errorf("encode TOML: %w", err)
	}
	if err := f.Close(); err != nil {
		os.Remove(tmp)
		return fmt.Errorf("close tmp: %w", err)
	}

	if err := os.Rename(tmp, c.SourcePath); err != nil {
		os.Remove(tmp)
		return fmt.Errorf("rename tmp → %s: %w", c.SourcePath, err)
	}
	return nil
}
