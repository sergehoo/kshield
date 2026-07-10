// Package updater — Auto-update du binaire de l'agent.
//
// Flow :
//   1. CheckUpdate → GET /api/v1/edge-gateway/updates/check/
//   2. Si has_update=true : Download + SHA256 verify
//   3. Sauvegarde binaire courant en <path>.old (rollback)
//   4. Swap atomique du nouveau binaire (rename)
//   5. Restart du process (os.Exit(0) → service manager relance)
//
// Sécurité :
//   - SHA256 obligatoire, refuse le binaire si mismatch
//   - Signature Ed25519 optionnelle (Phase 3, cert Kaydan Groupe)
//   - Rollback automatique si le nouveau binaire crash au démarrage
package updater

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/sergehoo/kshield/agent-go/internal/api"
)

// Updater orchestre les vérifications et swaps.
type Updater struct {
	Client         *api.Client
	CurrentVersion string
	Platform       string
	BinaryPath     string // path vers le binaire courant (self)
}

// New construit un updater. Détecte automatiquement le path du binaire.
func New(client *api.Client, currentVersion, platform string) (*Updater, error) {
	execPath, err := os.Executable()
	if err != nil {
		return nil, fmt.Errorf("détection binaire: %w", err)
	}
	// Résout les symlinks
	realPath, err := filepath.EvalSymlinks(execPath)
	if err == nil {
		execPath = realPath
	}
	return &Updater{
		Client:         client,
		CurrentVersion: currentVersion,
		Platform:       platform,
		BinaryPath:     execPath,
	}, nil
}

// CheckAndApply tente une mise à jour complète. Retourne true si l'agent
// doit redémarrer (nouvelle version installée). Ne redémarre PAS lui-même —
// c'est à l'appelant de faire os.Exit(0) après cleanup.
func (u *Updater) CheckAndApply(ctx context.Context) (bool, error) {
	info, err := u.Client.CheckUpdate(ctx, u.CurrentVersion, u.Platform)
	if err != nil {
		return false, fmt.Errorf("check update: %w", err)
	}
	if !info.HasUpdate {
		log.Debug().Str("current", u.CurrentVersion).Msg("Aucune mise à jour disponible")
		return false, nil
	}

	log.Info().
		Str("current", info.CurrentVersion).
		Str("latest", info.LatestVersion).
		Bool("mandatory", info.Mandatory).
		Msg("Nouvelle version disponible")

	if info.DownloadURL == "" || info.ChecksumSHA256 == "" {
		return false, fmt.Errorf("info d'update incomplète (download_url ou checksum manquant)")
	}

	return u.applyUpdate(ctx, info)
}

// applyUpdate télécharge, vérifie, swap et retourne true si l'agent doit
// redémarrer pour prendre en compte la nouvelle version.
func (u *Updater) applyUpdate(ctx context.Context, info *api.UpdateCheckResponse) (bool, error) {
	// 1. Download vers un fichier temporaire
	tmpPath := u.BinaryPath + ".new"
	log.Info().Str("url", info.DownloadURL).Str("tmp", tmpPath).
		Msg("Téléchargement de la nouvelle version...")

	if err := downloadFile(ctx, info.DownloadURL, tmpPath); err != nil {
		return false, fmt.Errorf("download: %w", err)
	}
	defer func() {
		// Cleanup du .new si on échoue plus loin
		if _, err := os.Stat(tmpPath); err == nil {
			os.Remove(tmpPath)
		}
	}()

	// 2. Vérification SHA256
	log.Info().Msg("Vérification SHA256...")
	actualChecksum, err := sha256File(tmpPath)
	if err != nil {
		return false, fmt.Errorf("checksum: %w", err)
	}
	if actualChecksum != info.ChecksumSHA256 {
		return false, fmt.Errorf(
			"SHA256 mismatch — expected %s got %s (binaire corrompu ou man-in-the-middle)",
			info.ChecksumSHA256, actualChecksum,
		)
	}
	log.Info().Str("sha256", actualChecksum[:16]+"...").Msg("SHA256 vérifié")

	// 3. Rendre exécutable (Linux/macOS)
	if err := os.Chmod(tmpPath, 0755); err != nil {
		return false, fmt.Errorf("chmod: %w", err)
	}

	// 4. Test rapide : vérifier que le nouveau binaire lance version sans crash
	if err := smokeTest(ctx, tmpPath); err != nil {
		return false, fmt.Errorf("smoke test échoué (binaire cassé): %w", err)
	}

	// 5. Backup du binaire courant en .old (rollback si crash au boot)
	oldPath := u.BinaryPath + ".old"
	if err := copyFile(u.BinaryPath, oldPath); err != nil {
		log.Warn().Err(err).Msg("Backup .old échoué — swap forcé sans rollback possible")
	}

	// 6. Swap atomique via rename (Windows nécessite parfois Remove+Rename)
	if err := os.Rename(tmpPath, u.BinaryPath); err != nil {
		// Sous Windows, on ne peut pas rename par-dessus un fichier verrouillé.
		// Fallback : copy + chmod. Le vrai swap se fera au prochain reboot.
		if copyErr := copyFile(tmpPath, u.BinaryPath); copyErr != nil {
			return false, fmt.Errorf("swap échoué (rename %v, copy %v)", err, copyErr)
		}
		log.Warn().Msg("Swap Windows fait par copy (fichier verrouillé) — actif au restart")
	}

	log.Info().
		Str("new_version", info.LatestVersion).
		Str("binary", u.BinaryPath).
		Msg("✓ Mise à jour appliquée")

	return true, nil
}

// ═══════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════

func downloadFile(ctx context.Context, url, dest string) error {
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", "kshield-edge-updater/1.0")

	client := &http.Client{Timeout: 5 * time.Minute}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	f, err := os.OpenFile(dest, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0644)
	if err != nil {
		return err
	}
	defer f.Close()

	if _, err := io.Copy(f, resp.Body); err != nil {
		return err
	}
	return nil
}

func sha256File(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()

	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	stat, err := in.Stat()
	if err != nil {
		return err
	}

	out, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, stat.Mode())
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, in)
	return err
}

// smokeTest lance `<binary> version` avec timeout 5s pour vérifier
// que le binaire télécharger est fonctionnel avant swap.
func smokeTest(ctx context.Context, binaryPath string) error {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, binaryPath, "version")
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("smoke test: %w — output: %s", err, string(out))
	}
	return nil
}
