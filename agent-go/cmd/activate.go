package cmd

import (
	"context"
	"fmt"
	"os"
	"runtime"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/spf13/cobra"

	"github.com/sergehoo/kshield/agent-go/internal/api"
	"github.com/sergehoo/kshield/agent-go/internal/config"
)

var (
	flagServerURL string
	flagToken     string
)

var activateCmd = &cobra.Command{
	Use:   "activate",
	Short: "Appaire la gateway avec le Cloud (échange activation_token → api_token)",
	Long: `Effectue l'échange initial du activation_token contre les credentials
permanents (api_token, hmac_secret, mqtt password).

Cette commande est appelée UNE FOIS par l'installateur. Si la gateway est
déjà activée, la commande no-op.

Les credentials sont écrits dans le fichier de config TOML de manière
atomique (fichier temporaire + rename).`,
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := config.Load(cfgFile)
		if err != nil {
			return fmt.Errorf("load config: %w", err)
		}

		// Idempotent : si déjà activé, on ne refait rien.
		if cfg.IsActivated() {
			log.Info().Msg("Gateway déjà activée — aucune action")
			return nil
		}

		// Surcharge éventuelle par les flags CLI
		serverURL := cfg.Cloud.ServerURL
		if flagServerURL != "" {
			serverURL = flagServerURL
		}
		activationToken := cfg.Cloud.ActivationToken
		if flagToken != "" {
			activationToken = flagToken
		}
		if serverURL == "" || activationToken == "" {
			return fmt.Errorf("server URL et activation token requis (ni dans config, ni en CLI)")
		}

		log.Info().
			Str("server", serverURL).
			Str("gateway_id", cfg.Gateway.ID).
			Msg("Appairage avec le Cloud...")

		client := api.New(serverURL, "", "")
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()

		hostname, _ := os.Hostname()
		resp, err := client.Activate(ctx, api.ActivateRequest{
			ActivationToken: activationToken,
			GatewayID:       cfg.Gateway.ID,
			SystemInfo: map[string]string{
				"os":         runtime.GOOS,
				"arch":       runtime.GOARCH,
				"hostname":   hostname,
				"go_version": runtime.Version(),
				"agent_version": Version,
			},
		})
		if err != nil {
			return fmt.Errorf("activation échouée: %w", err)
		}

		// Écriture des credentials dans le TOML
		if err := cfg.SaveActivationCredentials(
			resp.APIToken, resp.HMACSecret, resp.MQTTPassword,
		); err != nil {
			return fmt.Errorf("sauvegarde credentials: %w", err)
		}

		log.Info().
			Str("label", resp.GatewayLabel).
			Str("tenant", resp.TenantID).
			Msg("✓ Activation réussie — credentials enregistrés")

		fmt.Println()
		fmt.Println("═══════════════════════════════════════════════════════════════")
		fmt.Println("  ✓ Gateway appairée avec succès")
		fmt.Println("═══════════════════════════════════════════════════════════════")
		fmt.Printf("  Label     : %s\n", resp.GatewayLabel)
		fmt.Printf("  Tenant    : %s\n", resp.TenantID)
		fmt.Printf("  MQTT user : %s\n", resp.MQTTUsername)
		fmt.Printf("  MQTT host : %s:%d (TLS=%v)\n",
			resp.MQTTHost, resp.MQTTPort, resp.MQTTUseTLS)
		fmt.Println()
		fmt.Println("  Prochaine étape : démarrer le service")
		fmt.Println("    Linux   : sudo systemctl enable --now kshield-edge")
		fmt.Println("    Windows : Start-Service KaydanEdgeGateway")
		fmt.Println("    macOS   : sudo launchctl load /Library/LaunchDaemons/com.kaydangroupe.kshield-edge.plist")
		fmt.Println()

		return nil
	},
}

func init() {
	activateCmd.Flags().StringVar(&flagServerURL, "server-url", "",
		"URL du serveur Kaydan Shield (surcharge la config)")
	activateCmd.Flags().StringVar(&flagToken, "token", "",
		"Token d'activation (surcharge la config)")
}
