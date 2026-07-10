package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/sergehoo/kshield/agent-go/internal/scanner"
)

var (
	scanTimeout time.Duration
	scanJSON    bool
)

var scanCmd = &cobra.Command{
	Use:   "scan",
	Short: "Lance un scan réseau on-demand (ARP + ONVIF + mDNS)",
	Long: `Découvre les équipements présents sur le LAN de la gateway.

Sondes exécutées en parallèle :
  - ARP     : parse la table ARP de l'OS
  - ONVIF   : WS-Discovery UDP multicast (caméras IP)
  - mDNS    : Bonjour/Zeroconf sur port 5353

Affiche un tableau IP + MAC + Vendor + Model + Source.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		ctx, cancel := context.WithTimeout(context.Background(), scanTimeout+5*time.Second)
		defer cancel()

		s := scanner.New(scanTimeout)
		res, err := s.Scan(ctx)
		if err != nil {
			return fmt.Errorf("scan: %w", err)
		}

		if scanJSON {
			enc := json.NewEncoder(os.Stdout)
			enc.SetIndent("", "  ")
			return enc.Encode(res)
		}

		// Rendu tableau lisible
		fmt.Println()
		fmt.Println("═══════════════════════════════════════════════════════════════════════════════")
		fmt.Printf("  Scan réseau — %d équipements détectés en %s\n",
			len(res.Devices), res.Duration.Round(time.Millisecond))
		fmt.Printf("  Sondes actives : %s\n", strings.Join(res.ProbesRun, ", "))
		fmt.Println("═══════════════════════════════════════════════════════════════════════════════")
		fmt.Printf("  %-16s %-18s %-20s %-20s  %s\n",
			"IP", "MAC", "VENDOR", "MODEL", "SRC")
		fmt.Println("  ────────────────────────────────────────────────────────────────────────────")
		for _, d := range res.Devices {
			fmt.Printf("  %-16s %-18s %-20s %-20s  %s\n",
				truncate(d.IP, 16),
				truncate(d.MAC, 18),
				truncate(d.Vendor, 20),
				truncate(d.Model, 20),
				strings.Join(d.Sources, "+"),
			)
		}
		fmt.Println()
		return nil
	},
}

func init() {
	scanCmd.Flags().DurationVar(&scanTimeout, "timeout", 30*time.Second,
		"Timeout global du scan (chaque sonde tourne en parallèle)")
	scanCmd.Flags().BoolVar(&scanJSON, "json", false,
		"Sortie JSON structurée (pour scripting)")
	rootCmd.AddCommand(scanCmd)
}

func truncate(s string, n int) string {
	if s == "" {
		return "—"
	}
	if len(s) <= n {
		return s
	}
	return s[:n-1] + "…"
}
