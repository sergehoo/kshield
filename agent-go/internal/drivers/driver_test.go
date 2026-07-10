package drivers

import (
	"context"
	"testing"
)

// fakeDriver est un driver test qui n'a besoin d'aucune ressource réseau.
type fakeDriver struct {
	vendor string
}

func (f *fakeDriver) Vendor() string { return f.vendor }
func (f *fakeDriver) Capabilities() []Capability {
	return []Capability{CapReadEvents, CapGetStatus}
}
func (f *fakeDriver) Connect(_ context.Context) error    { return nil }
func (f *fakeDriver) Disconnect() error                  { return nil }
func (f *fakeDriver) Ping(_ context.Context) error       { return nil }
func (f *fakeDriver) ReadEvents(ctx context.Context, sink EventSink) error {
	<-ctx.Done()
	return ctx.Err()
}
func (f *fakeDriver) GetStatus(_ context.Context) Result { return Result{OK: true} }
func (f *fakeDriver) DoorUnlock(_ context.Context, _ string) Result { return Result{OK: true} }
func (f *fakeDriver) Sync(_ context.Context) Result                 { return Result{OK: true} }
func (f *fakeDriver) Restart(_ context.Context) Result              { return Result{OK: true} }
func (f *fakeDriver) PushUser(_ context.Context, _ map[string]interface{}) Result {
	return Result{OK: true}
}

func TestRegistry_RegisterAndBuild(t *testing.T) {
	// Reset registry pour ce test
	registryMu.Lock()
	registry = make(map[string]Factory)
	registryMu.Unlock()

	Register("test-vendor", func(t Target) (Driver, error) {
		return &fakeDriver{vendor: "test-vendor"}, nil
	})

	drv, err := BuildDriver(Target{Vendor: "test-vendor", ID: "d1"})
	if err != nil {
		t.Fatal(err)
	}
	if drv.Vendor() != "test-vendor" {
		t.Errorf("wrong vendor: %s", drv.Vendor())
	}
}

func TestRegistry_UnknownVendorReturnsError(t *testing.T) {
	// Reset
	registryMu.Lock()
	registry = make(map[string]Factory)
	registryMu.Unlock()

	_, err := BuildDriver(Target{Vendor: "does-not-exist"})
	if err == nil {
		t.Error("expected error pour vendor inconnu")
	}
}

func TestRegistry_DoubleRegisterPanics(t *testing.T) {
	registryMu.Lock()
	registry = make(map[string]Factory)
	registryMu.Unlock()

	factory := func(_ Target) (Driver, error) {
		return &fakeDriver{}, nil
	}
	Register("dup", factory)

	defer func() {
		if r := recover(); r == nil {
			t.Error("expected panic sur double register")
		}
	}()
	Register("dup", factory)
}

func TestRegistry_List(t *testing.T) {
	registryMu.Lock()
	registry = make(map[string]Factory)
	registryMu.Unlock()

	Register("v1", func(_ Target) (Driver, error) { return &fakeDriver{}, nil })
	Register("v2", func(_ Target) (Driver, error) { return &fakeDriver{}, nil })

	list := List()
	if len(list) != 2 {
		t.Errorf("expected 2 vendors, got %d: %v", len(list), list)
	}
}

func TestCapability_Contains(t *testing.T) {
	drv := &fakeDriver{vendor: "test"}
	caps := drv.Capabilities()
	hasEvents := false
	for _, c := range caps {
		if c == CapReadEvents {
			hasEvents = true
		}
	}
	if !hasEvents {
		t.Error("expected CapReadEvents dans capabilities")
	}
}
