package cmd

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/rs/zerolog/log"
	"github.com/spf13/cobra"

	"github.com/sergehoo/kshield/agent-go/internal/config"
	"github.com/sergehoo/kshield/agent-go/internal/tray"
)

var trayCmd = &cobra.Command{
	Use:   "tray",
	Short: "Lance le tray icon (mode desktop)",
	Long: `Démarre l'agent AVEC une icône dans la barre système.

Le tray affiche l'état de connexion (vert/orange/rouge) et permet à
l'admin de :
  - Ouvrir l'admin Kaydan Shield dans le navigateur
  - Voir les logs
  - Redémarrer le service
  - Ouvrir le dossier de config

Note : le service peut tourner sans tray (mode headless). Cette commande
est utile sur les postes admin, pas sur les serveurs de site.

Attention : sur Linux, nécessite un environnement graphique (X11/Wayland +
appindicator). Sur Windows/macOS c'est natif.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := config.Load(cfgFile)
		if err != nil {
			return fmt.Errorf("load config: %w", err)
		}

		// URL admin pour "Ouvrir dans le navigateur"
		adminURL := cfg.Cloud.ServerURL + "/edge-gateway"

		title := "Kaydan Edge Gateway"
		if cfg.Gateway.Label != "" {
			title = title + " · " + cfg.Gateway.Label
		}

		controller := tray.NewController(title, adminURL)

		// Signal handling — SIGTERM ferme proprement le tray
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()

		sig := make(chan os.Signal, 1)
		signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
		go func() {
			<-sig
			log.Info().Msg("Signal reçu — arrêt du tray")
			controller.Stop()
			cancel()
		}()

		// Lance l'agent en background (comme `run`)
		go func() {
			if err := runAgent(cmd, args); err != nil {
				log.Fatal().Err(err).Msg("Agent failed")
			}
		}()

		// Le tray doit tourner sur le thread principal
		controller.Run()
		return nil
	},
}

func init() {
	rootCmd.AddCommand(trayCmd)
}
