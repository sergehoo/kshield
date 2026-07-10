package config

import (
	"os"
	"path/filepath"
	"testing"
)

const validTOML = `
[gateway]
id = "abc123"
label = "Gateway Test"
tenant_id = "t1"
site_id = "s1"

[cloud]
server_url = "https://kaydanshield.com"
activation_token = "TOK1234567890"
activation_ttl_hours = 72

[mqtt]
host = "mqtt.kaydanshield.com"
port = 8883
use_tls = true
username = "kshield-edge-abc"
verify_cert = true
ca_file = "certs/ca.crt"

[agent]
version = "1.0.0"
heartbeat_interval_seconds = 30
offline_queue_max_events = 10000
scan_network_enabled = true
scan_network_interval_hours = 6
auto_update_enabled = true
auto_update_check_interval_hours = 6

[logging]
level = "INFO"
file = "logs/agent.log"
max_size_mb = 50
backup_count = 5

[devices]
enable_zkteco = true
enable_hikvision = true

[advanced]
hmac_signature_enabled = true
websocket_reconnect_delay_seconds = 5
websocket_max_reconnect_attempts = 100
`

func TestConfig_LoadValid(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "agent.toml")
	if err := os.WriteFile(path, []byte(validTOML), 0600); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.Gateway.ID != "abc123" {
		t.Errorf("gateway.id = %q", cfg.Gateway.ID)
	}
	if cfg.MQTT.Port != 8883 {
		t.Errorf("mqtt.port = %d", cfg.MQTT.Port)
	}
	if !cfg.MQTT.UseTLS {
		t.Error("mqtt.use_tls devrait être true")
	}
	if cfg.Devices.EnableZKTeco != true {
		t.Error("devices.enable_zkteco devrait être true")
	}
}

func TestConfig_IsActivated(t *testing.T) {
	c := &Config{}
	c.Cloud.APIToken = ""
	if c.IsActivated() {
		t.Error("IsActivated devrait être false avec api_token vide")
	}
	c.Cloud.APIToken = "TOK_XYZ"
	if !c.IsActivated() {
		t.Error("IsActivated devrait être true avec api_token présent")
	}
}

func TestConfig_ValidateMissingFields(t *testing.T) {
	// gateway.id manquant
	c := &Config{}
	c.Cloud.ServerURL = "https://x"
	c.Cloud.ActivationToken = "tok"
	c.MQTT.Host = "h"
	c.MQTT.Port = 1883
	if err := c.Validate(); err == nil {
		t.Error("Validate devrait échouer sans gateway.id")
	}

	// server_url manquant
	c2 := &Config{}
	c2.Gateway.ID = "x"
	c2.MQTT.Host = "h"
	c2.MQTT.Port = 1883
	if err := c2.Validate(); err == nil {
		t.Error("Validate devrait échouer sans server_url")
	}

	// mqtt.port invalide
	c3 := &Config{}
	c3.Gateway.ID = "x"
	c3.Cloud.ServerURL = "https://x"
	c3.Cloud.ActivationToken = "tok"
	c3.MQTT.Host = "h"
	c3.MQTT.Port = 99999
	if err := c3.Validate(); err == nil {
		t.Error("Validate devrait échouer avec port 99999")
	}
}

func TestConfig_SaveAtomic(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "agent.toml")
	if err := os.WriteFile(path, []byte(validTOML), 0600); err != nil {
		t.Fatal(err)
	}
	cfg, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}

	if err := cfg.SaveActivationCredentials("api-abc", "hmac-xyz", "mqtt-pw"); err != nil {
		t.Fatalf("Save: %v", err)
	}

	// Reload et vérifie
	cfg2, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if cfg2.Cloud.APIToken != "api-abc" {
		t.Errorf("api_token pas persisté: %q", cfg2.Cloud.APIToken)
	}
	if cfg2.MQTT.Password != "mqtt-pw" {
		t.Errorf("mqtt.password pas persisté: %q", cfg2.MQTT.Password)
	}
	// activation_token doit être vidé après save
	if cfg2.Cloud.ActivationToken != "" {
		t.Errorf("activation_token devrait être vidé, got %q", cfg2.Cloud.ActivationToken)
	}
}
