package actions

import (
	"context"
	"encoding/json"
	"testing"
)

func TestDispatcher_UnknownActionReturnsError(t *testing.T) {
	d := New()
	res := d.Dispatch(context.Background(), Action{
		ID:   "test-1",
		Type: "does-not-exist",
	})
	if res.Success {
		t.Error("expected Success=false pour action inconnue")
	}
	if res.Error == "" {
		t.Error("expected Error non-vide")
	}
}

func TestDispatcher_RegisterAndDispatch(t *testing.T) {
	d := New()
	called := false
	d.Register("my-action", func(_ context.Context, a Action) Result {
		called = true
		return Result{Success: true, Output: map[string]interface{}{"echo": a.Payload["msg"]}}
	})

	res := d.Dispatch(context.Background(), Action{
		ID:   "id-1",
		Type: "my-action",
		Payload: map[string]interface{}{
			"msg": "hello",
		},
	})
	if !called {
		t.Fatal("handler pas appelé")
	}
	if !res.Success {
		t.Error("Success expected true")
	}
	if res.ActionID != "id-1" {
		t.Errorf("ActionID lost: got %q, want id-1", res.ActionID)
	}
	if res.Output["echo"] != "hello" {
		t.Errorf("output echo bad: %v", res.Output)
	}
}

func TestDispatcher_DispatchJSON(t *testing.T) {
	d := New()
	d.Register("json-test", func(_ context.Context, a Action) Result {
		return Result{Success: true, Output: map[string]interface{}{"type": a.Type}}
	})

	raw := []byte(`{"id":"j1","type":"json-test","payload":{"foo":"bar"}}`)
	res := d.DispatchJSON(context.Background(), "mqtt:test-topic", raw)
	if !res.Success {
		t.Errorf("Success expected true, got err=%s", res.Error)
	}
}

func TestDispatcher_DispatchInvalidJSON(t *testing.T) {
	d := New()
	res := d.DispatchJSON(context.Background(), "mqtt", []byte("not json"))
	if res.Success {
		t.Error("expected Success=false pour JSON invalide")
	}
}

func TestDispatcher_OnResultCallback(t *testing.T) {
	d := New()
	captured := 0
	d.OnResult = func(res Result) { captured++ }
	d.Register("cb-test", func(_ context.Context, _ Action) Result {
		return Result{Success: true}
	})

	d.Dispatch(context.Background(), Action{ID: "a", Type: "cb-test"})
	d.Dispatch(context.Background(), Action{ID: "b", Type: "cb-test"})
	if captured != 2 {
		t.Errorf("OnResult appelé %d fois, want 2", captured)
	}
}

func TestResult_JSONShape(t *testing.T) {
	res := Result{
		ActionID: "x1",
		Success:  false,
		Error:    "boom",
	}
	b, err := json.Marshal(res)
	if err != nil {
		t.Fatal(err)
	}
	// Vérifie que "action_id" et "success" sont bien snake_case
	if !contains(b, `"action_id":"x1"`) || !contains(b, `"success":false`) {
		t.Errorf("bad JSON: %s", string(b))
	}
}

func contains(b []byte, sub string) bool {
	return string(b) != "" && indexOf(string(b), sub) >= 0
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}
