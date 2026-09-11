package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	xlog "github.com/xtls/xray-core/common/log"
	"github.com/xtls/libxray/share"
	"github.com/xtls/libxray/xray"
)

type discardLogHandler struct{}

func (d *discardLogHandler) Handle(msg xlog.Message) {}

type SingleEnvelope struct {
	Success  bool            `json:"success"`
	Name     string          `json:"name,omitempty"`
	Outbound json.RawMessage `json:"outbound,omitempty"`
	Error    string          `json:"error,omitempty"`
}

type BatchItem struct {
	Name     string          `json:"name"`
	Outbound json.RawMessage `json:"outbound"`
}

type BatchEnvelope struct {
	Success bool        `json:"success"`
	Count   int         `json:"count"`
	Items   []BatchItem `json:"items"`
	Error   string      `json:"error,omitempty"`
}

type XrayOutboundsDocument struct {
	Outbounds []json.RawMessage `json:"outbounds"`
}

type OutboundTagProbe struct {
	Tag string `json:"tag"`
}

func main() {
	// Silence Xray-core internal logging completely to preserve clean JSON output on stdout
	xlog.RegisterHandler(&discardLogHandler{})

	var linkArg string
	var useStdin bool
	var batchMode bool
	var showVersion bool
	var testConfig bool
	flag.StringVar(&linkArg, "link", "", "Proxy share link to parse")
	flag.BoolVar(&useStdin, "stdin", false, "Read link from stdin")
	flag.BoolVar(&batchMode, "batch", false, "Parse multiple links in batch mode (newline or base64 separated)")
	flag.BoolVar(&showVersion, "version", false, "Print embedded Xray core version")
	flag.BoolVar(&testConfig, "test", false, "Validate full Xray JSON configuration from stdin")
	flag.Parse()

	if showVersion {
		res := map[string]any{
			"success": true,
			"version": xray.XrayVersion(),
		}
		out, _ := json.MarshalIndent(res, "", "  ")
		fmt.Println(string(out))
		return
	}

	if testConfig {
		data, err := io.ReadAll(os.Stdin)
		if err != nil {
			outputError("FAILED_READ_STDIN", err.Error(), 1, false)
			return
		}
		configStr := strings.TrimSpace(string(data))
		if configStr == "" {
			outputError("EMPTY_CONFIG", "Configuration JSON cannot be empty", 1, false)
			return
		}
		if err := xray.TestXray(configStr); err != nil {
			res := map[string]any{
				"success": false,
				"error":   err.Error(),
			}
			out, _ := json.MarshalIndent(res, "", "  ")
			fmt.Println(string(out))
			return
		}
		res := map[string]any{
			"success": true,
			"message": "Configuration is valid",
		}
		out, _ := json.MarshalIndent(res, "", "  ")
		fmt.Println(string(out))
		return
	}

	var link string
	if useStdin || (batchMode && linkArg == "") {
		data, err := io.ReadAll(os.Stdin)
		if err != nil {
			outputError("FAILED_READ_STDIN", err.Error(), 1, batchMode)
			return
		}
		link = strings.TrimSpace(string(data))
	} else {
		link = strings.TrimSpace(linkArg)
	}

	if link == "" {
		outputError("EMPTY_INPUT", "Link cannot be empty", 1, batchMode)
		return
	}

	raw, err := share.ConvertShareLinksToXrayJson(link, "")
	if err != nil {
		outputError("PARSE_FAILED", err.Error(), 2, batchMode)
		return
	}

	var doc XrayOutboundsDocument
	if err := json.Unmarshal(raw, &doc); err != nil || len(doc.Outbounds) == 0 {
		outputError("NO_OUTBOUNDS", "No valid outbounds produced from link", 2, batchMode)
		return
	}

	if batchMode {
		items := make([]BatchItem, 0, len(doc.Outbounds))
		for i, ob := range doc.Outbounds {
			name := fmt.Sprintf("Node %d", i+1)
			var probe OutboundTagProbe
			if err := json.Unmarshal(ob, &probe); err == nil && probe.Tag != "" {
				name = probe.Tag
			}
			items = append(items, BatchItem{
				Name:     name,
				Outbound: ob,
			})
		}
		env := BatchEnvelope{
			Success: true,
			Count:   len(items),
			Items:   items,
		}
		out, _ := json.MarshalIndent(env, "", "  ")
		fmt.Println(string(out))
		return
	}

	firstOutbound := doc.Outbounds[0]
	name := "Proxy Server"
	var tagProbe OutboundTagProbe
	if err := json.Unmarshal(firstOutbound, &tagProbe); err == nil && tagProbe.Tag != "" {
		name = tagProbe.Tag
	}

	env := SingleEnvelope{
		Success:  true,
		Name:     name,
		Outbound: firstOutbound,
	}

	out, _ := json.MarshalIndent(env, "", "  ")
	fmt.Println(string(out))
}

func outputError(code, message string, exitCode int, batchMode bool) {
	errStr := fmt.Sprintf("[%s] %s", code, message)
	if batchMode {
		env := BatchEnvelope{
			Success: false,
			Error:   errStr,
		}
		out, _ := json.MarshalIndent(env, "", "  ")
		fmt.Println(string(out))
	} else {
		env := SingleEnvelope{
			Success: false,
			Error:   errStr,
		}
		out, _ := json.MarshalIndent(env, "", "  ")
		fmt.Println(string(out))
	}
	os.Exit(exitCode)
}
