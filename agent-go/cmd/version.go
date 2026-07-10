package cmd

import (
	"fmt"
	"runtime"

	"github.com/spf13/cobra"
)

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Affiche la version du binaire",
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Printf("Kaydan Edge Gateway\n")
		fmt.Printf("  Version    : %s\n", Version)
		fmt.Printf("  Commit     : %s\n", Commit)
		fmt.Printf("  Build date : %s\n", BuildDate)
		fmt.Printf("  Go         : %s (%s/%s)\n", runtime.Version(), runtime.GOOS, runtime.GOARCH)
	},
}
