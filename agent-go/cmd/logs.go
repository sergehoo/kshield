package cmd

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"time"

	"github.com/spf13/cobra"

	"github.com/sergehoo/kshield/agent-go/internal/config"
)

var (
	logsFollow bool
	logsLines  int
)

var logsCmd = &cobra.Command{
	Use:   "logs",
	Short: "Affiche les logs du service (journalctl / event log / fichier)",
	Long: `Selon l'OS :

  Linux (systemd) : journalctl -u kshield-edge -n <lines>
  macOS (launchd) : cat /usr/local/var/log/kshield-edge/stderr.log
  Windows         : Get-Content de %ProgramData%\KaydanEdge\logs\service-stderr.log
  Fallback        : lit le fichier configuré dans logging.file

Utiliser --follow pour un tail live.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, _ := config.Load(cfgFile) // OK si config manquante

		switch runtime.GOOS {
		case "linux":
			return tailLinux()
		case "darwin":
			return tailFile("/usr/local/var/log/kshield-edge/stderr.log")
		case "windows":
			path := filepath.Join(
				os.Getenv("ProgramData"), "KaydanEdge", "logs", "service-stderr.log",
			)
			return tailFile(path)
		default:
			if cfg != nil && cfg.Logging.File != "" {
				return tailFile(cfg.Logging.File)
			}
			return fmt.Errorf("logs: aucun emplacement standard sur %s", runtime.GOOS)
		}
	},
}

func tailLinux() error {
	args := []string{"-u", "kshield-edge"}
	if logsFollow {
		args = append(args, "-f")
	} else {
		args = append(args, "-n", fmt.Sprintf("%d", logsLines), "--no-pager")
	}
	c := exec.Command("journalctl", args...)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin
	return c.Run()
}

func tailFile(path string) error {
	if _, err := os.Stat(path); err != nil {
		return fmt.Errorf("log file introuvable: %s (le service tourne-t-il ?)", path)
	}

	// Affiche les N dernières lignes
	if !logsFollow {
		return printTail(path, logsLines)
	}

	// Follow mode — lit depuis la fin et attend
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	// Position à la fin du fichier
	if _, err := f.Seek(0, io.SeekEnd); err != nil {
		return err
	}
	fmt.Fprintf(os.Stderr, "→ Tail %s (Ctrl+C pour quitter)\n", path)

	reader := bufio.NewReader(f)
	for {
		line, err := reader.ReadString('\n')
		if err == io.EOF {
			time.Sleep(500 * time.Millisecond)
			continue
		}
		if err != nil {
			return err
		}
		fmt.Print(line)
	}
}

func printTail(path string, n int) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	// Lecture ligne à ligne dans un ring buffer
	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 1024*1024), 1024*1024)
	lines := make([]string, 0, n)
	for scanner.Scan() {
		if len(lines) == n {
			lines = lines[1:]
		}
		lines = append(lines, scanner.Text())
	}
	for _, l := range lines {
		fmt.Println(l)
	}
	return scanner.Err()
}

func init() {
	logsCmd.Flags().BoolVarP(&logsFollow, "follow", "f", false,
		"Tail live (bloquant, Ctrl+C pour arrêter)")
	logsCmd.Flags().IntVarP(&logsLines, "lines", "n", 50,
		"Nombre de lignes à afficher (défaut 50)")
	rootCmd.AddCommand(logsCmd)
}
