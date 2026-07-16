package notify

import (
	"testing"
	"time"
)

func TestNotifier_ThrottleSameKey(t *testing.T) {
	n := New("Test")
	n.MinInterval = 10 * time.Second

	// Deux notifs successives avec la même clé → la seconde doit être throttled
	// Le call n'est pas observable directement (beeep échoue silencieusement
	// en env headless), mais on peut vérifier que la map lastAt a un timestamp.
	n.Notify(LevelInfo, "Test", "msg1", "key1")

	before := n.lastAt["key1"]
	if before.IsZero() {
		t.Fatal("premier call n'a pas enregistré timestamp")
	}

	n.Notify(LevelInfo, "Test", "msg2", "key1")
	after := n.lastAt["key1"]

	if !after.Equal(before) {
		t.Error("second call devrait être throttled (timestamp inchangé)")
	}
}

func TestNotifier_NoThrottleEmptyKey(t *testing.T) {
	n := New("Test")
	n.MinInterval = 100 * time.Millisecond

	// Sans throttleKey, les 2 notifs passent
	n.Notify(LevelInfo, "T", "m1", "")
	n.Notify(LevelInfo, "T", "m2", "")

	if len(n.lastAt) > 0 {
		t.Errorf("empty key ne devrait rien enregistrer, got %d entries", len(n.lastAt))
	}
}

func TestNotifier_ThrottleExpires(t *testing.T) {
	n := New("Test")
	n.MinInterval = 20 * time.Millisecond

	n.Notify(LevelInfo, "T", "m1", "expiring")
	first := n.lastAt["expiring"]

	// Attend > MinInterval
	time.Sleep(30 * time.Millisecond)

	n.Notify(LevelInfo, "T", "m2", "expiring")
	second := n.lastAt["expiring"]

	if !second.After(first) {
		t.Error("après expiration, second call doit mettre à jour timestamp")
	}
}

func TestNotifier_ConvenienceWrappers(t *testing.T) {
	n := New("Test")
	// Just verifie que les wrappers ne panic pas
	n.Info("t", "m")
	n.Warn("t", "m")
	n.Error("t", "m")
	n.Success("t", "m")

	// Warn utilise le title comme throttle key
	if _, ok := n.lastAt["t"]; !ok {
		t.Error("Warn devrait throttle par title")
	}
}
