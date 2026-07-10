// Kaydan Edge Gateway — Point d'entrée binaire Go.
//
// Ce fichier délègue immédiatement à Cobra. Toute la logique CLI est dans
// cmd/. L'agent principal (boucle event) est démarré via `kshield-agent run`.
package main

import (
	"os"

	"github.com/sergehoo/kshield/agent-go/cmd"

	// Import blank : enregistre tous les drivers vendors (ZKTeco, Hikvision,
	// Suprema, HID, Dahua, Axis) auprès du registry via leur init().
	_ "github.com/sergehoo/kshield/agent-go/internal/drivers/all"
)

func main() {
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
