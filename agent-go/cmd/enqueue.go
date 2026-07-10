package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/spf13/cobra"

	"github.com/sergehoo/kshield/agent-go/internal/config"
	"github.com/sergehoo/kshield/agent-go/internal/queue"
)

var enqueueCmd = &cobra.Command{
	Use:   "enqueue [type] [payload_json]",
	Short: "Push un event dans la queue offline (test manuel)",
	Long: `Utile pour tester la queue offline sans avoir un device connecté.

Exemple :
  kshield-agent enqueue access.granted '{"card":"1234","door":"main"}'
  kshield-agent enqueue device.tamper  '{"device_id":"dev-42"}'

Après enqueue, la boucle flushQueueLoop de 'run' pushera vers le cloud
au prochain tick (5s).`,
	Args: cobra.ExactArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := config.Load(cfgFile)
		if err != nil {
			return err
		}

		eventType := args[0]
		payloadStr := args[1]

		var payload map[string]interface{}
		if err := json.Unmarshal([]byte(payloadStr), &payload); err != nil {
			return fmt.Errorf("payload JSON invalide: %w", err)
		}

		q, err := queue.New(queueDBPath(cfg), cfg.Agent.OfflineQueueMaxEvents)
		if err != nil {
			return err
		}
		defer q.Close()

		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		if err := q.Enqueue(ctx, queue.Event{
			Type:       eventType,
			OccurredAt: time.Now().UTC(),
			Payload:    payload,
		}); err != nil {
			return fmt.Errorf("enqueue: %w", err)
		}

		n, _ := q.CountPending(ctx)
		fmt.Printf("✓ Event '%s' enqueué. Queue pending: %d\n", eventType, n)
		fmt.Fprintf(os.Stderr, "  DB: %s\n", q.Path())
		return nil
	},
}

func init() {
	rootCmd.AddCommand(enqueueCmd)
}
