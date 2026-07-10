package cmd

import (
	"fmt"

	"github.com/spf13/cobra"

	"github.com/sergehoo/kshield/agent-go/internal/config"
)

var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "Affiche l'état de la gateway (config chargée + connectivité)",
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := config.Load(cfgFile)
		if err != nil {
			fmt.Printf("✗ Config invalide : %v\n", err)
			return err
		}

		fmt.Println("═══════════════════════════════════════════════════════════════")
		fmt.Println("  Kaydan Edge Gateway — Statut")
		fmt.Println("═══════════════════════════════════════════════════════════════")
		fmt.Printf("  Config       : %s\n", cfg.SourcePath)
		fmt.Printf("  Gateway ID   : %s\n", cfg.Gateway.ID)
		fmt.Printf("  Label        : %s\n", cfg.Gateway.Label)
		fmt.Printf("  Tenant       : %s\n", cfg.Gateway.TenantID)
		fmt.Printf("  Site         : %s\n", cfg.Gateway.SiteID)
		fmt.Println()
		fmt.Printf("  Cloud URL    : %s\n", cfg.Cloud.ServerURL)
		fmt.Printf("  Activated    : %v\n", cfg.IsActivated())
		if !cfg.IsActivated() {
			fmt.Printf("  Activation   : token présent (%d chars)\n",
				len(cfg.Cloud.ActivationToken))
		}
		fmt.Println()
		fmt.Printf("  MQTT host    : %s:%d (TLS=%v)\n",
			cfg.MQTT.Host, cfg.MQTT.Port, cfg.MQTT.UseTLS)
		fmt.Printf("  MQTT user    : %s\n", cfg.MQTT.Username)
		fmt.Println()
		fmt.Printf("  Version      : %s\n", cfg.Agent.Version)
		fmt.Printf("  Heartbeat    : %ds\n", cfg.Agent.HeartbeatIntervalSeconds)
		fmt.Printf("  Auto-update  : %v (check every %dh)\n",
			cfg.Agent.AutoUpdateEnabled, cfg.Agent.AutoUpdateCheckIntervalHours)
		fmt.Println()
		fmt.Println("  Drivers activés :")
		if cfg.Devices.EnableZKTeco    { fmt.Println("    ✓ ZKTeco")     }
		if cfg.Devices.EnableHikvision { fmt.Println("    ✓ Hikvision")  }
		if cfg.Devices.EnableSuprema   { fmt.Println("    ✓ Suprema")    }
		if cfg.Devices.EnableHID       { fmt.Println("    ✓ HID")        }
		if cfg.Devices.EnableDahua     { fmt.Println("    ✓ Dahua")      }
		if cfg.Devices.EnableAxis      { fmt.Println("    ✓ Axis")       }
		if cfg.Devices.EnableONVIF     { fmt.Println("    ✓ ONVIF")      }
		fmt.Println()
		return nil
	},
}
