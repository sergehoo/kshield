package cmd

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/spf13/cobra"

	"github.com/sergehoo/kshield/agent-go/internal/api"
	"github.com/sergehoo/kshield/agent-go/internal/config"
)

var runCmd = &cobra.Command{
	Use:   "run",
	Short: "Démarre l'agent en boucle (mode service)",
	Long: `Lance l'agent Kaydan Edge Gateway en mode service.

Cette commande boucle en foreground et effectue :

  • Heartbeat périodique vers le Cloud (défaut: 30s)
  • Boucle MQTT pour publier events + recevoir commandes
  • WebSocket de commande temps réel
  • Scan réseau périodique (défaut: 6h)
  • Vérification auto-update (défaut: 6h)
  • Queue offline avec retransmission

Sortie propre sur SIGTERM / SIGINT (Ctrl+C).`,
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := config.Load(cfgFile)
		if err != nil {
			return fmt.Errorf("load config: %w", err)
		}
		if !cfg.IsActivated() {
			return fmt.Errorf("gateway non activée — lancer d'abord: kshield-agent activate")
		}

		log.Info().
			Str("gateway_id", cfg.Gateway.ID).
			Str("label", cfg.Gateway.Label).
			Str("server", cfg.Cloud.ServerURL).
			Str("version", Version).
			Msg("Kaydan Edge Gateway démarré")

		// Client cloud
		cloudClient := api.New(cfg.Cloud.ServerURL, cfg.Cloud.APIToken, cfg.Cloud.HMACSecret)

		// Contexte annulable par signal OS
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()

		sig := make(chan os.Signal, 1)
		signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
		go func() {
			s := <-sig
			log.Info().Str("signal", s.String()).Msg("Signal reçu — arrêt en cours...")
			cancel()
		}()

		// Boucle heartbeat
		go heartbeatLoop(ctx, cfg, cloudClient)

		// TODO Phase 2.2 : MQTT client + WS + scanner réseau + auto-update
		// Pour l'instant, on tourne juste le heartbeat.

		<-ctx.Done()
		log.Info().Msg("Agent arrêté proprement")
		return nil
	},
}

// heartbeatLoop envoie un heartbeat toutes les N secondes tant que ctx vit.
func heartbeatLoop(ctx context.Context, cfg *config.Config, client *api.Client) {
	interval := time.Duration(cfg.Agent.HeartbeatIntervalSeconds) * time.Second
	if interval == 0 {
		interval = 30 * time.Second
	}

	startedAt := time.Now()
	hostname, _ := os.Hostname()

	// Premier heartbeat immédiat
	sendHeartbeat(ctx, cfg, client, startedAt, hostname)

	tick := time.NewTicker(interval)
	defer tick.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-tick.C:
			sendHeartbeat(ctx, cfg, client, startedAt, hostname)
		}
	}
}

func sendHeartbeat(ctx context.Context, cfg *config.Config, client *api.Client,
	startedAt time.Time, hostname string) {

	hbCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	uptime := int64(time.Since(startedAt).Seconds())
	osInfo := fmt.Sprintf("%s/%s %s", runtime.GOOS, runtime.GOARCH, hostname)

	req := api.HeartbeatRequest{
		GatewayID:     cfg.Gateway.ID,
		Version:       Version,
		OSInfo:        osInfo,
		UptimeSeconds: uptime,
		EventsPending: 0, // TODO: brancher sur la queue offline
		MQTTStatus:    "unknown",
		WSStatus:      "unknown",
		CloudStatus:   "ok",
	}

	resp, err := client.Heartbeat(hbCtx, req)
	if err != nil {
		if err == api.ErrRevoked {
			log.Fatal().Msg("Gateway révoquée par le cloud — arrêt définitif")
		}
		log.Warn().Err(err).Msg("Heartbeat échoué — retry au prochain tick")
		return
	}

	log.Debug().
		Int("actions", len(resp.PendingActions)).
		Str("server_time", resp.ServerTime).
		Msg("Heartbeat OK")

	// Traite les actions pending
	for _, action := range resp.PendingActions {
		log.Info().Str("type", action.Type).Str("id", action.ID).
			Msg("Action pending reçue")
		// TODO Phase 2.2 : dispatch vers handlers (restart, sync, update, scan)
	}
}
