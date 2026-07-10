package cmd

import (
	"fmt"

	"github.com/spf13/cobra"

	"github.com/sergehoo/kshield/agent-go/internal/drivers"
)

var driversCmd = &cobra.Command{
	Use:   "drivers",
	Short: "Liste les drivers vendors enregistrés",
	Long: `Affiche tous les drivers plugins disponibles dans ce binaire.

Un driver est chargé si son package est importé via internal/drivers/all/
(chargement automatique via import blank dans main.go).

Chaque driver déclare ses capacités (read_events, door_unlock, sync_users,
etc.) — voir la colonne CAPABILITIES.`,
	Run: func(cmd *cobra.Command, args []string) {
		list := drivers.List()
		if len(list) == 0 {
			fmt.Println("Aucun driver enregistré. Vérifier import blank dans main.go.")
			return
		}
		fmt.Println()
		fmt.Println("═══════════════════════════════════════════════════════════════════")
		fmt.Printf("  Drivers vendors disponibles : %d\n", len(list))
		fmt.Println("═══════════════════════════════════════════════════════════════════")
		fmt.Printf("  %-15s %-40s\n", "VENDOR", "CAPABILITIES")
		fmt.Println("  ─────────────────────────────────────────────────────────────")

		for _, vendor := range list {
			// Construit un driver "dry" juste pour lister ses capabilities
			factory, _ := drivers.Get(vendor)
			drv, err := factory(drivers.Target{Vendor: vendor, IP: "0.0.0.0"})
			if err != nil {
				fmt.Printf("  %-15s (init error: %v)\n", vendor, err)
				continue
			}
			caps := drv.Capabilities()
			capsStr := ""
			for i, c := range caps {
				if i > 0 {
					capsStr += ", "
				}
				capsStr += string(c)
			}
			fmt.Printf("  %-15s %s\n", vendor, capsStr)
		}
		fmt.Println()
	},
}

func init() {
	rootCmd.AddCommand(driversCmd)
}
