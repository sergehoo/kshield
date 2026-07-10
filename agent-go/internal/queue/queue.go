// Package queue — File d'attente offline persistante pour les events.
//
// Stockage : SQLite via modernc.org/sqlite (pure Go, no CGO required —
// permet cross-compile Linux/Windows/macOS/ARM sans toolchain C).
//
// Contrat :
//   - Enqueue : ajoute un event (durable, survit au reboot)
//   - DequeueBatch : lit les N plus anciens events non-ack (pour push cloud)
//   - Ack : supprime définitivement les events transmis avec succès
//   - CountPending : nombre d'events en attente
//   - Purge : garde-fou, drop les events > MaxEvents (FIFO)
package queue

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	_ "modernc.org/sqlite"
)

// Event est un event métier persisté dans la queue.
type Event struct {
	ID         int64                  // Auto-increment SQLite
	Type       string                 // ex: "access.granted", "device.tamper"
	OccurredAt time.Time              // Timestamp d'origine
	Payload    map[string]interface{} // Payload JSON quelconque
	SourceIP   string
	SourceMAC  string
	Signature  string // HMAC calculé au moment du push
	CreatedAt  time.Time
	Attempts   int // Nombre de tentatives d'envoi
}

// Queue est thread-safe (SQLite gère la sérialisation interne).
type Queue struct {
	db        *sql.DB
	path      string
	maxEvents int
}

// New ouvre (ou crée) la base SQLite au chemin donné.
// maxEvents est la limite au-delà de laquelle on drop les plus anciens.
func New(path string, maxEvents int) (*Queue, error) {
	if maxEvents <= 0 {
		maxEvents = 10_000
	}

	// Crée le dossier parent si nécessaire
	if dir := filepath.Dir(path); dir != "." && dir != "" {
		if err := os.MkdirAll(dir, 0755); err != nil {
			return nil, fmt.Errorf("mkdir queue: %w", err)
		}
	}

	// WAL mode = meilleure concurrence + résiste aux crashes
	dsn := path + "?_pragma=journal_mode(WAL)&_pragma=synchronous(NORMAL)&_pragma=busy_timeout(5000)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("open sqlite: %w", err)
	}

	// SQLite en Go standard : limite le pool à 1 pour éviter les locks
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)

	q := &Queue{db: db, path: path, maxEvents: maxEvents}
	if err := q.migrate(); err != nil {
		db.Close()
		return nil, fmt.Errorf("migrate: %w", err)
	}
	return q, nil
}

// Close libère la connexion DB.
func (q *Queue) Close() error {
	return q.db.Close()
}

// migrate crée la table events si absente. Idempotent.
func (q *Queue) migrate() error {
	schema := `
	CREATE TABLE IF NOT EXISTS events (
		id           INTEGER PRIMARY KEY AUTOINCREMENT,
		type         TEXT NOT NULL,
		occurred_at  TEXT NOT NULL,
		payload      TEXT NOT NULL,
		source_ip    TEXT,
		source_mac   TEXT,
		signature    TEXT,
		created_at   TEXT NOT NULL DEFAULT (datetime('now')),
		attempts     INTEGER NOT NULL DEFAULT 0
	);
	CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
	`
	_, err := q.db.Exec(schema)
	return err
}

// Enqueue persiste un event dans la queue. Purge les plus anciens si dépasse max.
func (q *Queue) Enqueue(ctx context.Context, ev Event) error {
	payloadJSON, err := json.Marshal(ev.Payload)
	if err != nil {
		return fmt.Errorf("marshal payload: %w", err)
	}
	occurred := ev.OccurredAt
	if occurred.IsZero() {
		occurred = time.Now().UTC()
	}

	_, err = q.db.ExecContext(ctx, `
		INSERT INTO events (type, occurred_at, payload, source_ip, source_mac, signature)
		VALUES (?, ?, ?, ?, ?, ?)`,
		ev.Type, occurred.UTC().Format(time.RFC3339Nano), string(payloadJSON),
		ev.SourceIP, ev.SourceMAC, ev.Signature,
	)
	if err != nil {
		return fmt.Errorf("insert event: %w", err)
	}

	// Auto-purge des plus anciens si on dépasse maxEvents
	return q.purge(ctx)
}

// purge supprime les events les plus anciens si la queue dépasse maxEvents.
// FIFO : "au moins ne rien perdre récent".
func (q *Queue) purge(ctx context.Context) error {
	count, err := q.CountPending(ctx)
	if err != nil {
		return err
	}
	if count <= q.maxEvents {
		return nil
	}
	toDelete := count - q.maxEvents
	_, err = q.db.ExecContext(ctx, `
		DELETE FROM events WHERE id IN (
			SELECT id FROM events ORDER BY id ASC LIMIT ?
		)`, toDelete)
	return err
}

// CountPending retourne le nombre d'events non ack.
func (q *Queue) CountPending(ctx context.Context) (int, error) {
	var n int
	err := q.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM events").Scan(&n)
	return n, err
}

// DequeueBatch récupère les N plus anciens events (sans les supprimer).
// L'appelant doit call Ack(ids) après push réussi, ou IncrementAttempts sinon.
func (q *Queue) DequeueBatch(ctx context.Context, limit int) ([]Event, error) {
	if limit <= 0 {
		limit = 100
	}
	rows, err := q.db.QueryContext(ctx, `
		SELECT id, type, occurred_at, payload, source_ip, source_mac,
		       signature, created_at, attempts
		FROM events
		ORDER BY id ASC
		LIMIT ?`, limit)
	if err != nil {
		return nil, fmt.Errorf("query events: %w", err)
	}
	defer rows.Close()

	var out []Event
	for rows.Next() {
		var ev Event
		var occurredStr, createdStr, payloadStr string
		if err := rows.Scan(&ev.ID, &ev.Type, &occurredStr, &payloadStr,
			&ev.SourceIP, &ev.SourceMAC, &ev.Signature, &createdStr, &ev.Attempts); err != nil {
			return nil, err
		}
		ev.OccurredAt, _ = time.Parse(time.RFC3339Nano, occurredStr)
		ev.CreatedAt, _ = time.Parse("2006-01-02 15:04:05", createdStr)
		if err := json.Unmarshal([]byte(payloadStr), &ev.Payload); err != nil {
			// Payload corrompu — on garde l'event mais avec payload vide
			ev.Payload = map[string]interface{}{"_corrupt": true, "_raw": payloadStr}
		}
		out = append(out, ev)
	}
	return out, rows.Err()
}

// Ack supprime définitivement les events transmis avec succès.
func (q *Queue) Ack(ctx context.Context, ids []int64) error {
	if len(ids) == 0 {
		return nil
	}
	// Construit la clause WHERE id IN (?,?,?,...)
	args := make([]interface{}, len(ids))
	placeholders := ""
	for i, id := range ids {
		if i > 0 {
			placeholders += ","
		}
		placeholders += "?"
		args[i] = id
	}
	query := fmt.Sprintf("DELETE FROM events WHERE id IN (%s)", placeholders)
	_, err := q.db.ExecContext(ctx, query, args...)
	return err
}

// IncrementAttempts incrémente le compteur d'essais pour un batch (utile pour
// détecter les events "poison" qu'on n'arrive jamais à transmettre).
func (q *Queue) IncrementAttempts(ctx context.Context, ids []int64) error {
	if len(ids) == 0 {
		return nil
	}
	args := make([]interface{}, len(ids))
	placeholders := ""
	for i, id := range ids {
		if i > 0 {
			placeholders += ","
		}
		placeholders += "?"
		args[i] = id
	}
	query := fmt.Sprintf(
		"UPDATE events SET attempts = attempts + 1 WHERE id IN (%s)",
		placeholders,
	)
	_, err := q.db.ExecContext(ctx, query, args...)
	return err
}

// Path retourne le chemin du fichier SQLite (utile pour debug/backup).
func (q *Queue) Path() string {
	return q.path
}

// DefaultPath retourne l'emplacement standard de la queue selon l'OS.
func DefaultPath() string {
	if p := os.Getenv("KSHIELD_QUEUE_PATH"); p != "" {
		return p
	}
	// Linux + macOS
	return "/var/lib/kshield-edge/queue.db"
}
