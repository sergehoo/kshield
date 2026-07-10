// Package cmd — CLI Cobra pour Kaydan Edge Gateway.
package cmd

import (
	"os"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"github.com/spf13/cobra"
)

var (
	// Flags globaux
	cfgFile  string
	verbose  bool
	logJSON  bool
)

// Version définie à la compilation via -ldflags "-X ..."
var (
	Version   = "1.0.0-dev"
	Commit    = "unknown"
	BuildDate = "unknown"
)

var rootCmd = &cobra.Command{
	Use:   "kshield-agent",
	Short: "Kaydan Edge Gateway — passerelle temps réel entre les équipements du site et le Cloud Kaydan Shield.",
	Long: `Kaydan Edge Gateway
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Passerelle enterprise pour connecter automatiquement un site client
à la plateforme Kaydan Shield.

Fonctionnalités :
  • Découverte automatique des équipements (RFID, biométrie, caméras)
  • Communication MQTT + WebSocket + HTTPS avec le Cloud
  • File d'attente offline avec retransmission automatique
  • Auto-update avec signature vérifiée
  • Service système autonome (systemd / Windows Service / launchd)

Documentation : https://kaydanshield.com/docs/edge-gateway`,
	PersistentPreRun: func(cmd *cobra.Command, args []string) {
		// Init logger avant toute commande
		level := zerolog.InfoLevel
		if verbose {
			level = zerolog.DebugLevel
		}
		zerolog.SetGlobalLevel(level)

		if logJSON {
			log.Logger = zerolog.New(os.Stdout).With().Timestamp().Logger()
		} else {
			log.Logger = log.Output(zerolog.ConsoleWriter{
				Out:        os.Stdout,
				TimeFormat: "15:04:05",
			})
		}
	},
}

// Execute est le point d'entrée appelé par main().
func Execute() error {
	return rootCmd.Execute()
}

func init() {
	rootCmd.PersistentFlags().StringVarP(&cfgFile, "config", "c", "",
		"Path vers kshield-agent.toml (défaut: /etc/kshield-edge/kshield-agent.toml)")
	rootCmd.PersistentFlags().BoolVarP(&verbose, "verbose", "v", false,
		"Active les logs DEBUG")
	rootCmd.PersistentFlags().BoolVar(&logJSON, "log-json", false,
		"Émet les logs en JSON structuré (pour ingestion Loki/Elastic)")

	// Sous-commandes
	rootCmd.AddCommand(runCmd)
	rootCmd.AddCommand(activateCmd)
	rootCmd.AddCommand(statusCmd)
	rootCmd.AddCommand(versionCmd)
}
