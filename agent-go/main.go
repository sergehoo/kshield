// Kaydan Edge Gateway — Point d'entrée binaire Go.
//
// Ce fichier délègue immédiatement à Cobra. Toute la logique CLI est dans
// cmd/. L'agent principal (boucle event) est démarré via `kshield-agent run`.
package main

import (
	"os"

	"github.com/sergehoo/kshield/agent-go/cmd"
)

func main() {
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
