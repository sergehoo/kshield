// Package all — Import blank pour enregistrer tous les drivers au boot.
//
// Utilisation dans main.go ou cmd/run.go :
//
//	import _ "github.com/sergehoo/kshield/agent-go/internal/drivers/all"
//
// L'init() de chaque driver s'enregistre dans le registry via drivers.Register().
// Ce package est la SEULE façon officielle de "activer" les drivers, ce qui
// évite les imports oubliés dans le main.
package all

import (
	// Chaque driver ci-dessous s'auto-enregistre via son init().
	_ "github.com/sergehoo/kshield/agent-go/internal/drivers/axis"
	_ "github.com/sergehoo/kshield/agent-go/internal/drivers/dahua"
	_ "github.com/sergehoo/kshield/agent-go/internal/drivers/hid"
	_ "github.com/sergehoo/kshield/agent-go/internal/drivers/hikvision"
	_ "github.com/sergehoo/kshield/agent-go/internal/drivers/suprema"
	_ "github.com/sergehoo/kshield/agent-go/internal/drivers/zkteco"
)
