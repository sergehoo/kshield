package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"syscall"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/spf13/cobra"

	"github.com/sergehoo/kshield/agent-go/internal/actions"
	"github.com/sergehoo/kshield/agent-go/internal/api"
	"github.com/sergehoo/kshield/agent-go/internal/config"
	"github.com/sergehoo/kshield/agent-go/internal/drivers"
	"github.com/sergehoo/kshield/agent-go/internal/metrics"
	"github.com/sergehoo/kshield/agent-go/internal/mqtt"
	"github.com/sergehoo/kshield/agent-go/internal/notify"
	"github.com/sergehoo/kshield/agent-go/internal/queue"
	"github.com/sergehoo/kshield/agent-go/internal/scanner"
	"github.com/sergehoo/kshield/agent-go/internal/updater"
	"github.com/sergehoo/kshield/agent-go/internal/ws"
)

var runCmd = &cobra.Command{
	Use:   "run",
	Short: "Démarre l'agent en boucle (mode service)",
	Long: `Lance l'agent Kaydan Edge Gateway en mode service.

Boucles concurrentes lancées :

  • heartbeatLoop      (30s)    — HTTP POST heartbeat + pull actions
  • flushQueueLoop     (5s)     — SQLite queue → HTTP push events batch
  • mqtt.Client        (paho)   — sub cmd/# + pub events (temps réel)
  • ws.Client          (WS)     — canal bi-directionnel push cloud → agent
  • scanNetworkLoop    (6h)     — ARP + ONVIF + mDNS probes
  • autoUpdateLoop     (6h)     — check + download + swap binaire

Sortie propre sur SIGTERM / SIGINT (Ctrl+C).`,
	RunE: runAgent,
}

func runAgent(cmd *cobra.Command, args []string) error {
	cfg, err := config.Load(cfgFile)
	if err != nil {
		return fmt.Errorf("load config: %w", err)
	}
	if !cfg.IsActivated() {
		return fmt.Errorf("gateway non activée — lancer d'abord: kshield-agent activate")
	}

	log.Info().
		Str("gateway_id", cfg.Gateway.ID).
		Str("label", cfg.Gateway.Label).
		Str("server", cfg.Cloud.ServerURL).
		Str("version", Version).
		Msg("Kaydan Edge Gateway démarré")

	// ─── Queue offline ──────────────────────────────────────────
	queuePath := queueDBPath(cfg)
	q, err := queue.New(queuePath, cfg.Agent.OfflineQueueMaxEvents)
	if err != nil {
		return fmt.Errorf("init queue: %w", err)
	}
	defer q.Close()
	log.Info().Str("path", q.Path()).Msg("Queue offline prête")

	// ─── Metrics endpoint Prometheus (opt-in) ───────────────────
	if cfg.Metrics.Enabled && cfg.Metrics.ListenAddr != "" {
		metrics.StartServer(cfg.Metrics.ListenAddr)
	}

	// ─── Desktop notifier (best-effort, silent si headless) ─────
	notifier := notify.New("Kaydan Edge Gateway")

	// ─── Client cloud HTTP ──────────────────────────────────────
	cloudClient := api.New(cfg.Cloud.ServerURL, cfg.Cloud.APIToken, cfg.Cloud.HMACSecret)
	_ = notifier // évite unused warning — on l'utilise plus bas

	// ─── Dispatcher d'actions ───────────────────────────────────
	dispatcher := actions.New()
	dispatcher.OnResult = func(res actions.Result) {
		if res.ActionID == "" {
			return
		}
		// Envoie le résultat au cloud (fire-and-forget)
		go func(r actions.Result) {
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			payload := api.ActionResultPayload{
				ActionID:   r.ActionID,
				Success:    r.Success,
				Error:      r.Error,
				Output:     r.Output,
				FinishedAt: r.FinishedAt.Format(time.RFC3339Nano),
			}
			if err := cloudClient.PushActionResult(ctx, payload); err != nil {
				log.Debug().Err(err).Str("action_id", r.ActionID).
					Msg("Push action result échoué")
			}
		}(res)
	}

	// Handler force_sync = flush la queue vers cloud immédiatement
	dispatcher.Register("force_sync", func(ctx context.Context, _ actions.Action) actions.Result {
		n, err := flushQueue(ctx, q, cloudClient, cfg)
		if err != nil {
			return actions.Result{Success: false, Error: err.Error()}
		}
		return actions.Result{
			Success: true,
			Output:  map[string]interface{}{"events_flushed": n},
		}
	})

	// ─── Drivers manager (targets vendors ZKTeco/Hikvision/etc.) ─
	driverSink := &queueEventSink{q: q}
	driverMgr := drivers.NewManager(driverSink)
	for _, t := range cfg.Targets {
		if t.Vendor == "" {
			continue
		}
		target := drivers.Target{
			ID:       t.ID,
			IP:       t.IP,
			Port:     t.Port,
			Vendor:   t.Vendor,
			Username: t.Username,
			Password: t.Password,
			Extra:    t.Extra,
		}
		if err := driverMgr.Start(ctx, target); err != nil {
			log.Warn().Err(err).
				Str("vendor", t.Vendor).
				Str("id", t.ID).
				Msg("Driver start échoué — ignoré")
		} else {
			log.Info().
				Str("vendor", t.Vendor).
				Str("id", t.ID).
				Str("ip", t.IP).
				Msg("Driver démarré")
		}
	}
	defer driverMgr.StopAll()

	// Handler door_unlock via drivers manager
	dispatcher.Register("door_unlock", func(ctx context.Context, a actions.Action) actions.Result {
		targetID, _ := a.Payload["target_id"].(string)
		doorID, _ := a.Payload["door_id"].(string)
		if targetID == "" {
			return actions.Result{Success: false, Error: "target_id manquant"}
		}
		drv, ok := driverMgr.GetDriver(targetID)
		if !ok {
			return actions.Result{Success: false,
				Error: fmt.Sprintf("driver introuvable pour target %s", targetID)}
		}
		res := drv.DoorUnlock(ctx, doorID)
		return actions.Result{
			Success: res.OK,
			Error:   res.Error,
			Output:  res.Data,
		}
	})

	// Handler scan_network = utilise le scanner intégré
	dispatcher.Register("scan_network", func(ctx context.Context, a actions.Action) actions.Result {
		timeout := 30 * time.Second
		if v, ok := a.Payload["timeout_seconds"].(float64); ok && v > 0 {
			timeout = time.Duration(v) * time.Second
		}
		s := scanner.New(timeout)
		res, err := s.Scan(ctx)
		if err != nil {
			return actions.Result{Success: false, Error: err.Error()}
		}
		return actions.Result{
			Success: true,
			Output: map[string]interface{}{
				"devices_count": len(res.Devices),
				"devices":       res.Devices,
				"duration_ms":   res.Duration.Milliseconds(),
				"probes_run":    res.ProbesRun,
			},
		}
	})

	// ─── Signal handling ────────────────────────────────────────
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		s := <-sig
		log.Info().Str("signal", s.String()).Msg("Signal reçu — arrêt en cours...")
		cancel()
	}()

	// ─── Client MQTT ────────────────────────────────────────────
	mqttCli := mqtt.New(mqtt.Config{
		Host:       cfg.MQTT.Host,
		Port:       cfg.MQTT.Port,
		Username:   cfg.MQTT.Username,
		Password:   cfg.MQTT.Password,
		UseTLS:     cfg.MQTT.UseTLS,
		CAFile:     cfg.MQTT.CAFile,
		VerifyCert: cfg.MQTT.VerifyCert,
		GatewayID:  cfg.Gateway.ID,
	}, func(topic string, payload []byte) {
		go dispatcher.DispatchJSON(ctx, "mqtt:"+topic, payload)
	})
	if err := mqttCli.Connect(); err != nil {
		log.Warn().Err(err).Msg("MQTT connect initial échoué — retry en arrière-plan")
	}
	defer mqttCli.Disconnect()

	// ─── Client WebSocket ───────────────────────────────────────
	wsCli := ws.New(ws.Config{
		ServerURL: cfg.Cloud.ServerURL,
		GatewayID: cfg.Gateway.ID,
		APIToken:  cfg.Cloud.APIToken,
	}, func(payload []byte) {
		go dispatcher.DispatchJSON(ctx, "ws", payload)
	})
	wsCli.Start(ctx)
	defer wsCli.Stop()

	// ─── Boucles background ─────────────────────────────────────
	go heartbeatLoop(ctx, cfg, cloudClient, q, mqttCli, wsCli, dispatcher, driverMgr)
	go flushQueueLoop(ctx, q, cloudClient, cfg, mqttCli)

	if cfg.Agent.ScanNetworkEnabled {
		go scanNetworkLoop(ctx, cfg, cloudClient, mqttCli)
	}
	if cfg.Agent.AutoUpdateEnabled {
		go autoUpdateLoop(ctx, cfg, cloudClient)
	}

	<-ctx.Done()

	// Grace period pour flush les derniers events
	log.Info().Msg("Flush final de la queue avant arrêt...")
	flushCtx, flushCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer flushCancel()
	if _, err := flushQueue(flushCtx, q, cloudClient, cfg); err != nil {
		log.Warn().Err(err).Msg("Flush final incomplet")
	}

	log.Info().Msg("Agent arrêté proprement")
	return nil
}

// ═══════════════════════════════════════════════════════════════════
// Boucle heartbeat
// ═══════════════════════════════════════════════════════════════════
func heartbeatLoop(ctx context.Context, cfg *config.Config, client *api.Client,
	q *queue.Queue, mqttCli *mqtt.Client, wsCli *ws.Client,
	disp *actions.Dispatcher, driverMgr *drivers.Manager) {

	interval := time.Duration(cfg.Agent.HeartbeatIntervalSeconds) * time.Second
	if interval == 0 {
		interval = 30 * time.Second
	}

	startedAt := time.Now()
	hostname, _ := os.Hostname()

	sendHeartbeat(ctx, cfg, client, q, mqttCli, wsCli, disp, driverMgr, startedAt, hostname)

	tick := time.NewTicker(interval)
	defer tick.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-tick.C:
			sendHeartbeat(ctx, cfg, client, q, mqttCli, wsCli, disp, driverMgr, startedAt, hostname)
		}
	}
}

func sendHeartbeat(ctx context.Context, cfg *config.Config, client *api.Client,
	q *queue.Queue, mqttCli *mqtt.Client, wsCli *ws.Client,
	disp *actions.Dispatcher, driverMgr *drivers.Manager,
	startedAt time.Time, hostname string) {

	hbCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	uptime := int64(time.Since(startedAt).Seconds())
	osInfo := fmt.Sprintf("%s/%s %s", runtime.GOOS, runtime.GOARCH, hostname)
	pending, _ := q.CountPending(hbCtx)

	// Collecte les statuses des targets depuis le driver manager
	var targetStatuses []api.TargetStatus
	if driverMgr != nil {
		for _, ds := range driverMgr.Status() {
			targetStatuses = append(targetStatuses, api.TargetStatus{
				ID:          ds.ID,
				Vendor:      ds.Vendor,
				IP:          ds.IP,
				Connected:   ds.Status == "connected",
				EventsCount: ds.Events,
				LastError:   ds.Error,
			})
		}
	}

	req := api.HeartbeatRequest{
		GatewayID:      cfg.Gateway.ID,
		Version:        Version,
		OSInfo:         osInfo,
		UptimeSeconds:  uptime,
		EventsPending:  pending,
		MQTTStatus:     mqttCli.Status(),
		WSStatus:       wsCli.Status(),
		CloudStatus:    "ok",
		TargetStatuses: targetStatuses,
	}

	resp, err := client.Heartbeat(hbCtx, req)
	if err != nil {
		if err == api.ErrRevoked {
			log.Fatal().Msg("Gateway révoquée par le cloud — arrêt définitif")
		}
		log.Warn().Err(err).Msg("Heartbeat échoué — retry au prochain tick")
		return
	}

	log.Debug().
		Int("actions", len(resp.PendingActions)).
		Int("pending_events", pending).
		Str("mqtt", mqttCli.Status()).
		Str("ws", wsCli.Status()).
		Msg("Heartbeat OK")

	for _, action := range resp.PendingActions {
		go disp.Dispatch(ctx, actions.Action{
			ID:      action.ID,
			Type:    action.Type,
			Payload: action.Payload,
			Source:  "heartbeat",
		})
	}
}

// ═══════════════════════════════════════════════════════════════════
// Flush queue → cloud
// ═══════════════════════════════════════════════════════════════════
func flushQueueLoop(ctx context.Context, q *queue.Queue, client *api.Client,
	cfg *config.Config, mqttCli *mqtt.Client) {
	tick := time.NewTicker(5 * time.Second)
	defer tick.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-tick.C:
			n, err := flushQueue(ctx, q, client, cfg)
			if err != nil {
				log.Debug().Err(err).Msg("Flush queue tick — retry plus tard")
				continue
			}
			if n > 0 {
				log.Info().Int("count", n).Msg("Events flushed vers cloud")
			}
		}
	}
}

func flushQueue(ctx context.Context, q *queue.Queue, client *api.Client,
	cfg *config.Config) (int, error) {

	batch, err := q.DequeueBatch(ctx, 100)
	if err != nil {
		return 0, fmt.Errorf("dequeue: %w", err)
	}
	if len(batch) == 0 {
		return 0, nil
	}

	apiBatch := api.EventBatch{GatewayID: cfg.Gateway.ID}
	ids := make([]int64, 0, len(batch))
	for _, ev := range batch {
		apiBatch.Events = append(apiBatch.Events, api.AgentEvent{
			Type:       ev.Type,
			OccurredAt: ev.OccurredAt.UTC().Format(time.RFC3339Nano),
			Payload:    ev.Payload,
			SourceIP:   ev.SourceIP,
			SourceMAC:  ev.SourceMAC,
			Signature:  ev.Signature,
		})
		ids = append(ids, ev.ID)
	}

	if err := client.PushEvents(ctx, apiBatch); err != nil {
		_ = q.IncrementAttempts(ctx, ids)
		return 0, fmt.Errorf("push events: %w", err)
	}

	if err := q.Ack(ctx, ids); err != nil {
		return len(batch), fmt.Errorf("ack: %w", err)
	}
	return len(batch), nil
}

// ═══════════════════════════════════════════════════════════════════
// Scan réseau périodique
// ═══════════════════════════════════════════════════════════════════
func scanNetworkLoop(ctx context.Context, cfg *config.Config,
	client *api.Client, mqttCli *mqtt.Client) {

	interval := time.Duration(cfg.Agent.ScanNetworkIntervalHours) * time.Hour
	if interval == 0 {
		interval = 6 * time.Hour
	}
	// Premier scan après 30s de démarrage
	firstScan := time.NewTimer(30 * time.Second)
	defer firstScan.Stop()

	tick := time.NewTicker(interval)
	defer tick.Stop()

	doScan := func() {
		s := scanner.New(30 * time.Second)
		res, err := s.Scan(ctx)
		if err != nil {
			log.Warn().Err(err).Msg("Scan réseau échoué")
			return
		}
		log.Info().
			Int("devices", len(res.Devices)).
			Dur("duration", res.Duration).
			Msg("Scan réseau terminé")

		// Push le résultat via MQTT (temps réel) si connecté
		if mqttCli.IsConnected() {
			payload, _ := json.Marshal(res)
			if err := mqttCli.Publish(
				fmt.Sprintf("kshield/edge/%s/scan", cfg.Gateway.ID),
				payload,
			); err != nil {
				log.Debug().Err(err).Msg("Push scan MQTT échoué")
			}
		}
	}

	for {
		select {
		case <-ctx.Done():
			return
		case <-firstScan.C:
			doScan()
		case <-tick.C:
			doScan()
		}
	}
}

// ═══════════════════════════════════════════════════════════════════
// Auto-update
// ═══════════════════════════════════════════════════════════════════
func autoUpdateLoop(ctx context.Context, cfg *config.Config, client *api.Client) {
	interval := time.Duration(cfg.Agent.AutoUpdateCheckIntervalHours) * time.Hour
	if interval == 0 {
		interval = 6 * time.Hour
	}
	platform := fmt.Sprintf("%s_%s", runtime.GOOS, runtime.GOARCH)
	// Normaliser platform pour matcher les keys EdgeGatewayPackage backend
	switch platform {
	case "linux_amd64":
		platform = "linux_deb"
	case "linux_arm64", "linux_arm":
		platform = "raspberry_pi"
	case "windows_amd64":
		platform = "windows_exe"
	case "darwin_amd64", "darwin_arm64":
		platform = "macos_pkg"
	}

	upd, err := updater.New(client, Version, platform)
	if err != nil {
		log.Warn().Err(err).Msg("Auto-updater init échoué — désactivé")
		return
	}

	// Ne pas check au boot immédiat (attend 1h — évite l'update pile après install)
	first := time.NewTimer(1 * time.Hour)
	defer first.Stop()

	tick := time.NewTicker(interval)
	defer tick.Stop()

	doCheck := func() {
		updated, err := upd.CheckAndApply(ctx)
		if err != nil {
			log.Warn().Err(err).Msg("Update check échoué")
			return
		}
		if updated {
			log.Info().Msg("Mise à jour appliquée — redémarrage dans 5s")
			time.Sleep(5 * time.Second)
			os.Exit(0)
		}
	}

	for {
		select {
		case <-ctx.Done():
			return
		case <-first.C:
			doCheck()
		case <-tick.C:
			doCheck()
		}
	}
}

// ═══════════════════════════════════════════════════════════════════
// queueEventSink — adapte drivers.EventSink vers queue offline
// ═══════════════════════════════════════════════════════════════════
// Chaque event émis par un driver (badge scan, tamper, motion, ...) est
// enqueué en local. La boucle flushQueueLoop se charge ensuite du push.
type queueEventSink struct {
	q *queue.Queue
}

func (s *queueEventSink) Emit(ctx context.Context, ev drivers.Event) error {
	metrics.Global.EventsEnqueued.Add(1)
	payload := ev.Payload
	if payload == nil {
		payload = map[string]interface{}{}
	}
	if ev.DeviceID != "" {
		payload["device_id"] = ev.DeviceID
	}
	return s.q.Enqueue(ctx, queue.Event{
		Type:       ev.Type,
		OccurredAt: ev.OccurredAt,
		Payload:    payload,
		SourceIP:   ev.SourceIP,
	})
}

// ═══════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════
func queueDBPath(cfg *config.Config) string {
	if p := os.Getenv("KSHIELD_QUEUE_PATH"); p != "" {
		return p
	}
	if runtime.GOOS == "windows" {
		programData := os.Getenv("ProgramData")
		if programData == "" {
			programData = `C:\ProgramData`
		}
		return filepath.Join(programData, "KaydanEdge", "queue.db")
	}
	return "/var/lib/kshield-edge/queue.db"
}
