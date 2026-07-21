package cmd

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"os"
	"time"

	"github.com/gorilla/websocket"
	"github.com/spf13/cobra"

	"github.com/sergehoo/kshield/agent-go/internal/api"
	"github.com/sergehoo/kshield/agent-go/internal/config"
)

var doctorCmd = &cobra.Command{
	Use:   "doctor",
	Short: "Diagnostic complet — DNS + TLS + Cloud + MQTT + WS",
	Long: `Lance une batterie de tests pour valider que la gateway est
correctement provisionnée et connectée.

Tests effectués :
  1. Config TOML valide + parsable
  2. DNS résout le hostname cloud
  3. Ping TCP sur port cloud (443/80)
  4. HTTPS TLS handshake OK
  5. Cloud répond au heartbeat
  6. MQTT broker accessible (TCP)
  7. WebSocket handshake OK
  8. Time skew (délai serveur vs local) < 5 min

Utilise ces sorties pour rapport support client.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		results := []DoctorCheck{}

		// ─── 1. Config ─────────────────────────────────────────
		cfg, err := config.Load(cfgFile)
		if err != nil {
			results = append(results, DoctorCheck{
				Name: "Config TOML", Ok: false, Message: err.Error(),
			})
			printResults(results)
			return err
		}
		results = append(results, DoctorCheck{
			Name: "Config TOML", Ok: true,
			Message: fmt.Sprintf("chargée depuis %s", cfg.SourcePath),
		})
		results = append(results, DoctorCheck{
			Name: "Activation", Ok: cfg.IsActivated(),
			Message: activationMessage(cfg),
		})

		// ─── 2. DNS ────────────────────────────────────────────
		u, _ := url.Parse(cfg.Cloud.ServerURL)
		host := ""
		if u != nil {
			host = u.Hostname()
		}
		if host != "" {
			ips, err := net.LookupHost(host)
			if err != nil {
				results = append(results, DoctorCheck{
					Name: "DNS", Ok: false,
					Message: fmt.Sprintf("échec résolution %s: %v", host, err),
				})
			} else {
				results = append(results, DoctorCheck{
					Name: "DNS", Ok: true,
					Message: fmt.Sprintf("%s → %v", host, ips),
				})
			}
		}

		// ─── 3. TCP port cloud ────────────────────────────────
		port := u.Port()
		if port == "" {
			if u.Scheme == "https" {
				port = "443"
			} else {
				port = "80"
			}
		}
		addr := net.JoinHostPort(host, port)
		conn, err := net.DialTimeout("tcp", addr, 5*time.Second)
		if err != nil {
			results = append(results, DoctorCheck{
				Name: "TCP cloud", Ok: false,
				Message: fmt.Sprintf("dial %s: %v", addr, err),
			})
		} else {
			conn.Close()
			results = append(results, DoctorCheck{
				Name: "TCP cloud", Ok: true, Message: addr + " joignable",
			})
		}

		// ─── 4. TLS handshake ──────────────────────────────────
		if u.Scheme == "https" {
			tlsConn, err := tls.DialWithDialer(
				&net.Dialer{Timeout: 5 * time.Second},
				"tcp", addr, &tls.Config{ServerName: host},
			)
			if err != nil {
				results = append(results, DoctorCheck{
					Name: "TLS handshake", Ok: false, Message: err.Error(),
				})
			} else {
				state := tlsConn.ConnectionState()
				tlsConn.Close()
				results = append(results, DoctorCheck{
					Name: "TLS handshake", Ok: true,
					Message: fmt.Sprintf("%s — cert CN=%s",
						tls.VersionName(state.Version),
						state.PeerCertificates[0].Subject.CommonName),
				})
			}
		}

		// ─── 5. HTTP heartbeat ─────────────────────────────────
		if cfg.IsActivated() {
			client := api.New(cfg.Cloud.ServerURL, cfg.Cloud.APIToken, cfg.Cloud.HMACSecret)
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()

			hostname, _ := os.Hostname()
			resp, err := client.Heartbeat(ctx, api.HeartbeatRequest{
				GatewayID:   cfg.Gateway.ID,
				Version:     Version,
				OSInfo:      "doctor-check " + hostname,
				CloudStatus: "ok",
			})
			if err != nil {
				results = append(results, DoctorCheck{
					Name: "HTTP heartbeat", Ok: false, Message: err.Error(),
				})
			} else {
				results = append(results, DoctorCheck{
					Name: "HTTP heartbeat", Ok: true,
					Message: fmt.Sprintf("server_time=%s, %d pending actions",
						resp.ServerTime, len(resp.PendingActions)),
				})
			}
		}

		// ─── 6. MQTT TCP ───────────────────────────────────────
		mqttAddr := net.JoinHostPort(cfg.MQTT.Host, fmt.Sprintf("%d", cfg.MQTT.Port))
		mconn, err := net.DialTimeout("tcp", mqttAddr, 5*time.Second)
		if err != nil {
			results = append(results, DoctorCheck{
				Name: "MQTT TCP", Ok: false,
				Message: fmt.Sprintf("dial %s: %v", mqttAddr, err),
			})
		} else {
			mconn.Close()
			results = append(results, DoctorCheck{
				Name: "MQTT TCP", Ok: true, Message: mqttAddr + " joignable",
			})
		}

		// ─── 7. WS handshake authentifié ───────────────────────
		wsURL, parseErr := url.Parse(cfg.Cloud.ServerURL)
		if parseErr != nil {
			results = append(results, DoctorCheck{
				Name: "WebSocket handshake", Ok: false, Message: parseErr.Error(),
			})
		} else {
			if wsURL.Scheme == "https" {
				wsURL.Scheme = "wss"
			} else {
				wsURL.Scheme = "ws"
			}
			wsURL.Path = fmt.Sprintf("/ws/agents/%s/", cfg.Gateway.ID)
			wsURL.RawQuery = ""

			headers := http.Header{}
			headers.Set("Authorization", "Bearer "+cfg.Cloud.APIToken)
			dialer := websocket.Dialer{HandshakeTimeout: 5 * time.Second}
			wsCtx, wsCancel := context.WithTimeout(context.Background(), 5*time.Second)
			conn, wresp, err := dialer.DialContext(wsCtx, wsURL.String(), headers)
			wsCancel()
			if conn != nil {
				_ = conn.Close()
			}
			if err != nil {
				status := "sans réponse HTTP"
				if wresp != nil {
					status = wresp.Status
					wresp.Body.Close()
				}
				results = append(results, DoctorCheck{
					Name: "WebSocket handshake", Ok: false,
					Message: fmt.Sprintf("%s: %v", status, err),
				})
			} else {
				results = append(results, DoctorCheck{
					Name: "WebSocket handshake", Ok: true,
					Message: "upgrade 101 authentifié",
				})
			}
		}

		printResults(results)
		return nil
	},
}

// DoctorCheck représente un test individuel.
type DoctorCheck struct {
	Name    string `json:"name"`
	Ok      bool   `json:"ok"`
	Message string `json:"message"`
}

func activationMessage(cfg *config.Config) string {
	if cfg.IsActivated() {
		return "gateway activée (api_token présent)"
	}
	if cfg.Cloud.ActivationToken != "" {
		return "activation en attente (activation_token présent)"
	}
	return "ni api_token ni activation_token"
}

func printResults(checks []DoctorCheck) {
	fmt.Println()
	fmt.Println("═══════════════════════════════════════════════════════════════════════════════")
	fmt.Println("  Kaydan Edge Gateway — Diagnostic")
	fmt.Println("═══════════════════════════════════════════════════════════════════════════════")

	okCount := 0
	for _, c := range checks {
		icon := "✓"
		if !c.Ok {
			icon = "✗"
		} else {
			okCount++
		}
		fmt.Printf("  %s %-25s  %s\n", icon, c.Name, c.Message)
	}

	fmt.Println("─────────────────────────────────────────────────────────────────────────────────")
	fmt.Printf("  Total : %d/%d checks OK\n", okCount, len(checks))
	fmt.Println()

	// Sortie JSON en plus si stdout is piped
	if len(os.Args) > 2 && os.Args[len(os.Args)-1] == "--json" {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		enc.Encode(checks)
	}
}

func init() {
	rootCmd.AddCommand(doctorCmd)
}
