package queue

import (
	"context"
	"path/filepath"
	"testing"
	"time"
)

func newTestQueue(t *testing.T) *Queue {
	t.Helper()
	path := filepath.Join(t.TempDir(), "test-queue.db")
	q, err := New(path, 1000)
	if err != nil {
		t.Fatalf("New failed: %v", err)
	}
	t.Cleanup(func() { q.Close() })
	return q
}

func TestQueue_EnqueueDequeueAck(t *testing.T) {
	ctx := context.Background()
	q := newTestQueue(t)

	// Enqueue 3 events
	for i := 0; i < 3; i++ {
		err := q.Enqueue(ctx, Event{
			Type:       "test.event",
			OccurredAt: time.Now(),
			Payload:    map[string]interface{}{"n": i},
		})
		if err != nil {
			t.Fatalf("Enqueue: %v", err)
		}
	}

	// Count
	n, err := q.CountPending(ctx)
	if err != nil || n != 3 {
		t.Fatalf("CountPending: got %d err=%v, want 3", n, err)
	}

	// Dequeue batch
	batch, err := q.DequeueBatch(ctx, 10)
	if err != nil {
		t.Fatalf("DequeueBatch: %v", err)
	}
	if len(batch) != 3 {
		t.Fatalf("DequeueBatch: got %d events, want 3", len(batch))
	}
	if batch[0].Type != "test.event" {
		t.Errorf("bad type: %s", batch[0].Type)
	}

	// Ack tous
	var ids []int64
	for _, ev := range batch {
		ids = append(ids, ev.ID)
	}
	if err := q.Ack(ctx, ids); err != nil {
		t.Fatalf("Ack: %v", err)
	}
	n, _ = q.CountPending(ctx)
	if n != 0 {
		t.Errorf("Après ack: got %d pending, want 0", n)
	}
}

func TestQueue_PurgeMaxEvents(t *testing.T) {
	ctx := context.Background()
	path := filepath.Join(t.TempDir(), "purge.db")
	q, err := New(path, 5) // limite volontairement basse
	if err != nil {
		t.Fatal(err)
	}
	defer q.Close()

	// Enqueue 10 events → auto-purge doit garder les 5 plus récents
	for i := 0; i < 10; i++ {
		if err := q.Enqueue(ctx, Event{
			Type:    "test.spam",
			Payload: map[string]interface{}{"i": i},
		}); err != nil {
			t.Fatal(err)
		}
	}
	n, _ := q.CountPending(ctx)
	if n > 5 {
		t.Errorf("purge FIFO failed: got %d, want <= 5", n)
	}
}

func TestQueue_IncrementAttempts(t *testing.T) {
	ctx := context.Background()
	q := newTestQueue(t)

	_ = q.Enqueue(ctx, Event{Type: "x", Payload: map[string]interface{}{"a": 1}})
	batch, _ := q.DequeueBatch(ctx, 10)
	if len(batch) != 1 {
		t.Fatal("expected 1 event")
	}
	if batch[0].Attempts != 0 {
		t.Errorf("initial attempts = %d, want 0", batch[0].Attempts)
	}

	// Increment 2x
	_ = q.IncrementAttempts(ctx, []int64{batch[0].ID})
	_ = q.IncrementAttempts(ctx, []int64{batch[0].ID})

	batch2, _ := q.DequeueBatch(ctx, 10)
	if batch2[0].Attempts != 2 {
		t.Errorf("after 2 inc: got %d, want 2", batch2[0].Attempts)
	}
}

func TestQueue_PersistenceAcrossReopen(t *testing.T) {
	ctx := context.Background()
	dir := t.TempDir()
	path := filepath.Join(dir, "persist.db")

	// Session 1 : enqueue puis close
	q1, err := New(path, 100)
	if err != nil {
		t.Fatal(err)
	}
	_ = q1.Enqueue(ctx, Event{Type: "durable", Payload: map[string]interface{}{"k": "v"}})
	q1.Close()

	// Session 2 : reopen → l'event doit encore être là
	q2, err := New(path, 100)
	if err != nil {
		t.Fatal(err)
	}
	defer q2.Close()

	n, _ := q2.CountPending(ctx)
	if n != 1 {
		t.Errorf("après reopen: got %d, want 1 (durabilité perdue)", n)
	}
}
