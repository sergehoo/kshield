// Package scanner — Découverte multi-protocole des équipements sur le LAN.
//
// Sondes disponibles :
//   - ARP     : parse la table ARP de l'OS (linux/mac/win)
//   - ONVIF   : WS-Discovery UDP multicast (caméras IP)
//   - mDNS    : Bonjour/Zeroconf sur port 5353 (imprimantes, appareils Apple, IoT)
//   - Ping    : ICMP sweep pour subnet complet (fallback)
//
// L'orchestrator exécute les sondes en parallèle et fusionne les résultats
// par IP + MAC.
package scanner

import (
	"context"
	"encoding/xml"
	"fmt"
	"net"
	"os/exec"
	"regexp"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog/log"
)

// Device est un équipement découvert sur le LAN.
type Device struct {
	IP       string   `json:"ip"`
	MAC      string   `json:"mac,omitempty"`
	Vendor   string   `json:"vendor,omitempty"`
	Model    string   `json:"model,omitempty"`
	Hostname string   `json:"hostname,omitempty"`
	Protocol string   `json:"protocol,omitempty"`   // onvif / mdns / arp / ping
	Ports    []int    `json:"ports,omitempty"`      // ports ouverts détectés
	Sources  []string `json:"sources"`              // lesquelles sondes l'ont vu
	Metadata map[string]string `json:"metadata,omitempty"`
	FoundAt  time.Time `json:"found_at"`
}

// Scanner exécute les sondes et fusionne les résultats.
type Scanner struct {
	Timeout time.Duration
}

// New crée un scanner avec le timeout global demandé.
func New(timeout time.Duration) *Scanner {
	if timeout == 0 {
		timeout = 30 * time.Second
	}
	return &Scanner{Timeout: timeout}
}

// Result est le retour d'un scan complet.
type Result struct {
	Devices    []Device      `json:"devices"`
	Duration   time.Duration `json:"duration"`
	ProbesRun  []string      `json:"probes_run"`
	StartedAt  time.Time     `json:"started_at"`
	FinishedAt time.Time     `json:"finished_at"`
}

// Scan lance toutes les sondes en parallèle et retourne la liste dédupliquée.
func (s *Scanner) Scan(ctx context.Context) (*Result, error) {
	start := time.Now()
	ctx, cancel := context.WithTimeout(ctx, s.Timeout)
	defer cancel()

	res := &Result{StartedAt: start}
	var mu sync.Mutex
	// Index par (IP+MAC) pour fusionner les résultats de plusieurs sondes.
	index := make(map[string]*Device)

	appendDevs := func(probeName string, devs []Device) {
		mu.Lock()
		defer mu.Unlock()
		res.ProbesRun = append(res.ProbesRun, probeName)
		for _, d := range devs {
			key := d.IP + "|" + d.MAC
			if existing, ok := index[key]; ok {
				// Merge — enrichir sans overwrite
				existing.Sources = append(existing.Sources, probeName)
				if d.Hostname != "" && existing.Hostname == "" {
					existing.Hostname = d.Hostname
				}
				if d.Vendor != "" && existing.Vendor == "" {
					existing.Vendor = d.Vendor
				}
				if d.Model != "" && existing.Model == "" {
					existing.Model = d.Model
				}
				if d.Protocol != "" && existing.Protocol == "" {
					existing.Protocol = d.Protocol
				}
				existing.Ports = append(existing.Ports, d.Ports...)
				for k, v := range d.Metadata {
					if _, exists := existing.Metadata[k]; !exists {
						if existing.Metadata == nil {
							existing.Metadata = make(map[string]string)
						}
						existing.Metadata[k] = v
					}
				}
			} else {
				d.Sources = []string{probeName}
				d.FoundAt = time.Now().UTC()
				dc := d
				index[key] = &dc
			}
		}
	}

	// Sondes en parallèle
	var wg sync.WaitGroup

	wg.Add(1)
	go func() {
		defer wg.Done()
		if devs, err := arpProbe(ctx); err != nil {
			log.Debug().Err(err).Msg("arp probe: erreur")
		} else {
			appendDevs("arp", devs)
		}
	}()

	wg.Add(1)
	go func() {
		defer wg.Done()
		if devs, err := onvifProbe(ctx); err != nil {
			log.Debug().Err(err).Msg("onvif probe: erreur")
		} else {
			appendDevs("onvif", devs)
		}
	}()

	wg.Add(1)
	go func() {
		defer wg.Done()
		if devs, err := mdnsProbe(ctx); err != nil {
			log.Debug().Err(err).Msg("mdns probe: erreur")
		} else {
			appendDevs("mdns", devs)
		}
	}()

	wg.Wait()

	// Extraction ordonnée
	for _, dev := range index {
		res.Devices = append(res.Devices, *dev)
	}
	res.FinishedAt = time.Now().UTC()
	res.Duration = res.FinishedAt.Sub(res.StartedAt)
	return res, nil
}

// ═══════════════════════════════════════════════════════════════════
// Probe : ARP (via commande OS)
// ═══════════════════════════════════════════════════════════════════
// La table ARP contient tous les hosts joignables sur le broadcast domain.
// C'est la sonde la plus fiable pour un premier inventaire.
func arpProbe(ctx context.Context) ([]Device, error) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.CommandContext(ctx, "arp", "-a")
	case "linux":
		// Sur Linux moderne, `ip neigh` est plus riche que `arp -a`.
		if _, err := exec.LookPath("ip"); err == nil {
			cmd = exec.CommandContext(ctx, "ip", "neigh")
		} else {
			cmd = exec.CommandContext(ctx, "arp", "-a")
		}
	default: // macOS et autres
		cmd = exec.CommandContext(ctx, "arp", "-a")
	}

	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("arp cmd: %w", err)
	}
	return parseArpOutput(string(out)), nil
}

var (
	// IPv4 + MAC — matche la plupart des formats OS (Linux, macOS, Windows).
	arpLineRegex = regexp.MustCompile(
		`(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}).*?([0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2})`,
	)
)

func parseArpOutput(raw string) []Device {
	var out []Device
	for _, line := range strings.Split(raw, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.Contains(strings.ToLower(line), "incomplete") {
			continue
		}
		m := arpLineRegex.FindStringSubmatch(line)
		if len(m) < 3 {
			continue
		}
		mac := strings.ToLower(strings.ReplaceAll(m[2], "-", ":"))
		// Ignore les MAC broadcast/multicast/incomplet
		if strings.HasPrefix(mac, "ff:ff:") || strings.HasPrefix(mac, "01:00:5e") {
			continue
		}
		out = append(out, Device{
			IP:       m[1],
			MAC:      mac,
			Vendor:   vendorFromMAC(mac),
			Protocol: "arp",
		})
	}
	return out
}

// vendorFromMAC lookup rapide sur les 3 premiers octets (OUI).
// Version simplifiée avec un mini-dictionnaire — enrichissable via base IEEE.
var ouiDB = map[string]string{
	"b8:27:eb": "Raspberry Pi",
	"dc:a6:32": "Raspberry Pi",
	"00:12:41": "Hikvision",
	"c0:56:e3": "Hikvision",
	"44:19:b6": "Hikvision",
	"00:17:29": "ZKTeco",
	"00:0e:0c": "Suprema",
	"00:13:5e": "Suprema",
	"00:06:8e": "HID Global",
	"00:1c:27": "Dahua",
	"14:a7:8b": "Dahua",
	"00:40:8c": "Axis Communications",
	"ac:cc:8e": "Axis Communications",
	"3c:5a:b4": "Google",
	"b8:8a:60": "Cisco",
	"00:04:96": "Cisco",
	"00:24:e8": "Dell",
	"a4:c3:f0": "Intel",
	"18:cc:23": "Ubiquiti",
	"fc:ec:da": "Ubiquiti",
	"78:8a:20": "Ubiquiti",
	"00:50:56": "VMware",
	"08:00:27": "VirtualBox",
	"52:54:00": "QEMU/KVM",
}

func vendorFromMAC(mac string) string {
	if len(mac) < 8 {
		return ""
	}
	prefix := mac[:8]
	if v, ok := ouiDB[prefix]; ok {
		return v
	}
	return ""
}

// ═══════════════════════════════════════════════════════════════════
// Probe : ONVIF WS-Discovery
// ═══════════════════════════════════════════════════════════════════
// Envoie un multicast SOAP sur 239.255.255.250:3702 et collecte les
// réponses de tous les devices ONVIF pendant 3 secondes.
func onvifProbe(ctx context.Context) ([]Device, error) {
	const (
		multicastAddr = "239.255.255.250:3702"
		listenTimeout = 3 * time.Second
	)

	// Message WS-Discovery Probe minimal
	probeMsg := `<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:dn="http://www.onvif.org/ver10/network/wsdl" xmlns="http://www.w3.org/2003/05/soap-envelope">
  <Header>
    <wsa:MessageID xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">uuid:1</wsa:MessageID>
    <wsa:To xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
  </Header>
  <Body>
    <Probe xmlns="http://schemas.xmlsoap.org/ws/2005/04/discovery">
      <Types xmlns:dp0="http://www.onvif.org/ver10/network/wsdl">dp0:NetworkVideoTransmitter</Types>
    </Probe>
  </Body>
</Envelope>`

	addr, err := net.ResolveUDPAddr("udp4", multicastAddr)
	if err != nil {
		return nil, err
	}
	// Bind sur port aléatoire local
	conn, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4zero, Port: 0})
	if err != nil {
		return nil, fmt.Errorf("bind UDP: %w", err)
	}
	defer conn.Close()

	// Envoi de la sonde
	if _, err := conn.WriteToUDP([]byte(probeMsg), addr); err != nil {
		return nil, fmt.Errorf("send probe: %w", err)
	}

	// Collect responses
	deadline := time.Now().Add(listenTimeout)
	conn.SetReadDeadline(deadline)

	var found []Device
	buf := make([]byte, 8192)
	for {
		select {
		case <-ctx.Done():
			return found, nil
		default:
		}
		n, remote, err := conn.ReadFromUDP(buf)
		if err != nil {
			// Timeout ou ctx annulé — sortir proprement
			break
		}
		if n == 0 {
			continue
		}
		dev := parseOnvifResponse(remote.IP.String(), buf[:n])
		if dev != nil {
			found = append(found, *dev)
		}
	}
	return found, nil
}

// parseOnvifResponse extrait IP + hint vendor depuis une réponse SOAP Match.
func parseOnvifResponse(ip string, raw []byte) *Device {
	// On ne parse pas tout le SOAP — juste les balises XAddrs et Types.
	type XAddrsMatch struct {
		XMLName xml.Name `xml:"Envelope"`
		Body    struct {
			ProbeMatches struct {
				ProbeMatch []struct {
					Types  string `xml:"Types"`
					Scopes string `xml:"Scopes"`
					XAddrs string `xml:"XAddrs"`
				} `xml:"ProbeMatch"`
			} `xml:"ProbeMatches"`
		} `xml:"Body"`
	}
	var m XAddrsMatch
	if err := xml.Unmarshal(raw, &m); err != nil {
		return &Device{IP: ip, Protocol: "onvif"}
	}
	dev := &Device{IP: ip, Protocol: "onvif"}
	if len(m.Body.ProbeMatches.ProbeMatch) > 0 {
		pm := m.Body.ProbeMatches.ProbeMatch[0]
		if strings.Contains(pm.Types, "NetworkVideoTransmitter") {
			dev.Model = "IP Camera"
		}
		// Scopes contient souvent "onvif://www.onvif.org/name/<vendor>"
		if strings.Contains(pm.Scopes, "onvif://") {
			for _, scope := range strings.Fields(pm.Scopes) {
				if strings.Contains(scope, "/name/") {
					parts := strings.SplitN(scope, "/name/", 2)
					if len(parts) == 2 {
						dev.Vendor = parts[1]
					}
				}
				if strings.Contains(scope, "/hardware/") {
					parts := strings.SplitN(scope, "/hardware/", 2)
					if len(parts) == 2 {
						dev.Model = parts[1]
					}
				}
			}
		}
		if dev.Metadata == nil {
			dev.Metadata = make(map[string]string)
		}
		dev.Metadata["onvif_xaddrs"] = pm.XAddrs
	}
	return dev
}

// ═══════════════════════════════════════════════════════════════════
// Probe : mDNS / Bonjour (léger — parse la liste des services connus)
// ═══════════════════════════════════════════════════════════════════
// Envoie une query mDNS "_services._dns-sd._udp.local" et collecte
// les réponses pour 2 secondes.
func mdnsProbe(ctx context.Context) ([]Device, error) {
	const (
		mdnsAddr = "224.0.0.251:5353"
		listen   = 2 * time.Second
	)
	// Query mDNS basique en binaire (DNS-SD standard)
	// Question : _services._dns-sd._udp.local PTR IN
	query := buildMDNSQuery()

	addr, err := net.ResolveUDPAddr("udp4", mdnsAddr)
	if err != nil {
		return nil, err
	}
	conn, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4zero, Port: 0})
	if err != nil {
		return nil, err
	}
	defer conn.Close()

	if _, err := conn.WriteToUDP(query, addr); err != nil {
		return nil, err
	}

	conn.SetReadDeadline(time.Now().Add(listen))
	buf := make([]byte, 4096)
	var out []Device
	seen := make(map[string]bool)

	for {
		select {
		case <-ctx.Done():
			return out, nil
		default:
		}
		n, remote, err := conn.ReadFromUDP(buf)
		if err != nil {
			break
		}
		if n < 12 {
			continue
		}
		ip := remote.IP.String()
		if seen[ip] {
			continue
		}
		seen[ip] = true
		out = append(out, Device{
			IP:       ip,
			Protocol: "mdns",
		})
	}
	return out, nil
}

// buildMDNSQuery construit un packet DNS mDNS pour "_services._dns-sd._udp.local".
func buildMDNSQuery() []byte {
	// Header DNS
	buf := []byte{
		0x00, 0x00, // Transaction ID
		0x00, 0x00, // Flags (standard query)
		0x00, 0x01, // Questions: 1
		0x00, 0x00, // Answer RRs: 0
		0x00, 0x00, // Authority RRs: 0
		0x00, 0x00, // Additional RRs: 0
	}
	// Question: _services._dns-sd._udp.local
	labels := []string{"_services", "_dns-sd", "_udp", "local"}
	for _, label := range labels {
		buf = append(buf, byte(len(label)))
		buf = append(buf, []byte(label)...)
	}
	buf = append(buf, 0x00)       // terminator
	buf = append(buf, 0x00, 0x0c) // QTYPE PTR
	buf = append(buf, 0x00, 0x01) // QCLASS IN
	return buf
}
