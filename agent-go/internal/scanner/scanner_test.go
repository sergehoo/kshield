package scanner

import (
	"strings"
	"testing"
)

func TestParseArpOutput_LinuxIpNeigh(t *testing.T) {
	// Format `ip neigh` Linux moderne
	raw := `192.168.1.1 dev eth0 lladdr 00:12:41:aa:bb:cc REACHABLE
192.168.1.42 dev eth0 lladdr b8:27:eb:11:22:33 STALE
192.168.1.99 dev eth0  FAILED
`
	devs := parseArpOutput(raw)

	if len(devs) != 2 {
		t.Fatalf("expected 2 devices, got %d: %v", len(devs), devs)
	}

	// Le premier doit être identifié comme Hikvision (OUI 00:12:41)
	if devs[0].Vendor != "Hikvision" {
		t.Errorf("expected Hikvision, got %q", devs[0].Vendor)
	}

	// Le second doit être identifié comme Raspberry Pi (OUI b8:27:eb)
	if devs[1].Vendor != "Raspberry Pi" {
		t.Errorf("expected Raspberry Pi, got %q", devs[1].Vendor)
	}
}

func TestParseArpOutput_MacOsFormat(t *testing.T) {
	raw := `? (192.168.1.1) at 00:12:41:aa:bb:cc on en0 [ethernet]
? (192.168.1.42) at c0:56:e3:44:55:66 on en0 [ethernet]
`
	devs := parseArpOutput(raw)
	if len(devs) != 2 {
		t.Fatalf("expected 2, got %d", len(devs))
	}
	// c0:56:e3 = Hikvision aussi
	if devs[1].Vendor != "Hikvision" {
		t.Errorf("expected Hikvision for c0:56:e3, got %q", devs[1].Vendor)
	}
}

func TestParseArpOutput_IgnoresIncomplete(t *testing.T) {
	raw := `192.168.1.99 dev eth0  INCOMPLETE
192.168.1.1 dev eth0 lladdr 00:12:41:aa:bb:cc REACHABLE
`
	devs := parseArpOutput(raw)
	if len(devs) != 1 {
		t.Errorf("expected 1 (skip INCOMPLETE), got %d", len(devs))
	}
}

func TestParseArpOutput_IgnoresBroadcast(t *testing.T) {
	raw := `192.168.1.255 dev eth0 lladdr ff:ff:ff:ff:ff:ff REACHABLE
192.168.1.1 dev eth0 lladdr 00:12:41:aa:bb:cc REACHABLE
`
	devs := parseArpOutput(raw)
	if len(devs) != 1 {
		t.Errorf("expected 1 (skip broadcast MAC), got %d", len(devs))
	}
}

func TestVendorFromMAC_KnownOUIs(t *testing.T) {
	tests := map[string]string{
		"b8:27:eb:11:22:33": "Raspberry Pi",
		"dc:a6:32:44:55:66": "Raspberry Pi",
		"00:12:41:77:88:99": "Hikvision",
		"00:17:29:aa:bb:cc": "ZKTeco",
		"00:40:8c:11:22:33": "Axis Communications",
		"unknown-mac-xxx":   "",
	}
	for mac, expected := range tests {
		got := vendorFromMAC(mac)
		if got != expected {
			t.Errorf("vendorFromMAC(%q) = %q, want %q", mac, got, expected)
		}
	}
}

func TestBuildMDNSQuery(t *testing.T) {
	pkt := buildMDNSQuery()
	if len(pkt) < 12 {
		t.Fatalf("packet trop court: %d bytes", len(pkt))
	}
	// Header : transaction ID (2) + flags (2) + counts (8) = 12 bytes
	// Ensuite : QNAME + QTYPE + QCLASS
	// Vérifie que la question _services._dns-sd._udp.local est là
	if !bytesContain(pkt, []byte("_services")) {
		t.Error("QNAME manque '_services'")
	}
	if !bytesContain(pkt, []byte("_dns-sd")) {
		t.Error("QNAME manque '_dns-sd'")
	}
	// Le dernier byte utile doit être QCLASS = 0x0001 (IN)
	if pkt[len(pkt)-1] != 0x01 {
		t.Errorf("QCLASS pas IN: last byte=0x%02x", pkt[len(pkt)-1])
	}
}

func bytesContain(haystack, needle []byte) bool {
	return strings.Contains(string(haystack), string(needle))
}
