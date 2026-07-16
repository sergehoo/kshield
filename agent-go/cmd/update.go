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
	"github.com/sergehoo/kshield/agent-go/internal/updater"
)

var (
	updateDryRun bool
)

var updateCmd = &cobra.Command{
	Use:   "update",
	Short: "Vérifie + télécharge + installe une nouvelle version",
	Long: `Force une vérification manuelle d'update indépendamment de l'auto-check.

Flow :
  1. GET /api/v1/devices/edge-gateway/updates/check/
  2. Si has_update:
     - Télécharge le nouveau binaire
     - Vérifie le SHA256
     - Smoke test (--version)
     - Backup .old du binaire courant
     - Swap atomique
     - Retourne exit 0 (systemd relance)

Utiliser --dry-run pour juste voir si une update est disponible sans swap.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := config.Load(cfgFile)
		if err != nil {
			return err
		}
		if !cfg.IsActivated() {
			return fmt.Errorf("gateway non activée")
		}

		client := api.New(cfg.Cloud.ServerURL, cfg.Cloud.APIToken, cfg.Cloud.HMACSecret)

		platform := fmt.Sprintf("%s_%s", runtime.GOOS, runtime.GOARCH)
		switch platform {
		case "linux_amd64":
			platform = "linux_deb"
		case "linux_arm64", "linux_arm":
			platform = "raspberry_pi"
		case "windows_amd64":
			platform = "windows_exe"
		case "darwin_amd64", "darwin_arm64":
			platform = "macos_pkg"
		}

		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
		defer cancel()

		if updateDryRun {
			info, err := client.CheckUpdate(ctx, Version, platform)
			if err != nil {
				return err
			}
			if info.HasUpdate {
				fmt.Printf("Update disponible : %s → %s\n", info.CurrentVersion, info.LatestVersion)
				fmt.Printf("  Download   : %s\n", info.DownloadURL)
				fmt.Printf("  SHA256     : %s\n", info.ChecksumSHA256)
				fmt.Printf("  Mandatory  : %v\n", info.Mandatory)
			} else {
				fmt.Printf("Aucune update. Version courante : %s\n", info.CurrentVersion)
			}
			return nil
		}

		upd, err := updater.New(client, Version, platform)
		if err != nil {
			return err
		}
		updated, err := upd.CheckAndApply(ctx)
		if err != nil {
			return err
		}
		if !updated {
			fmt.Println("Aucune update — vous êtes à jour.")
			return nil
		}
		fmt.Println("✓ Update appliquée — le service va redémarrer dans 3s...")
		log.Info().Msg("Update terminée — exit pour relance service manager")
		time.Sleep(3 * time.Second)
		os.Exit(0)
		return nil
	},
}

func init() {
	updateCmd.Flags().BoolVar(&updateDryRun, "dry-run", false,
		"N'installe pas — affiche uniquement les infos si une update est dispo")
	rootCmd.AddCommand(updateCmd)
}
