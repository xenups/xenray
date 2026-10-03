package main

import (
	"bufio"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/url"
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
		rawLinks := extractBatchLinks(link)
		candidateLinks := make([]parsedSourceLink, 0, len(rawLinks))
		for _, l := range rawLinks {
			candidateLinks = append(candidateLinks, extractLinkMeta(l))
		}
		usedLinks := make([]bool, len(candidateLinks))

		items := make([]BatchItem, 0, len(doc.Outbounds))
		for i, ob := range doc.Outbounds {
			name := fmt.Sprintf("Node %d", i+1)
			meta := extractOutboundMeta(ob)
			if meta.tag != "" {
				name = meta.tag
			}
			matchedLink := findMatchingLink(meta, candidateLinks, usedLinks, i)
			processedOb := postProcessOutbound(ob, matchedLink)
			items = append(items, BatchItem{
				Name:     name,
				Outbound: processedOb,
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

	singleLink := link
	if strings.Contains(link, "\n") || !strings.Contains(link, "://") {
		if sLinks := extractBatchLinks(link); len(sLinks) > 0 {
			singleLink = sLinks[0]
		}
	}
	firstOutbound := postProcessOutbound(doc.Outbounds[0], singleLink)
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

func postProcessOutbound(rawOb json.RawMessage, linkStr string) json.RawMessage {
	if strings.TrimSpace(linkStr) == "" {
		return rawOb
	}
	u, err := url.Parse(linkStr)
	if err != nil {
		return rawOb
	}
	q := u.Query()

	var ob map[string]any
	if err := json.Unmarshal(rawOb, &ob); err != nil {
		return rawOb
	}

	streamSettings, _ := ob["streamSettings"].(map[string]any)
	if streamSettings == nil {
		streamSettings = make(map[string]any)
		ob["streamSettings"] = streamSettings
	}

	cs := q.Get("cs")
	if cs == "" {
		cs = q.Get("cipherSuites")
	}
	fp := q.Get("fp")

	security, _ := streamSettings["security"].(string)

	if security == "tls" {
		tlsSettings, _ := streamSettings["tlsSettings"].(map[string]any)
		if tlsSettings == nil {
			tlsSettings = make(map[string]any)
			streamSettings["tlsSettings"] = tlsSettings
		}
		if cs != "" {
			tlsSettings["cipherSuites"] = cs
		}
		if fp != "" {
			tlsSettings["fingerprint"] = fp
		}
	} else if security == "reality" {
		realitySettings, _ := streamSettings["realitySettings"].(map[string]any)
		if realitySettings == nil {
			realitySettings = make(map[string]any)
			streamSettings["realitySettings"] = realitySettings
		}
		if cs != "" {
			realitySettings["cipherSuites"] = cs
		}
		if fp != "" {
			realitySettings["fingerprint"] = fp
		}
		if pqv := q.Get("pqv"); pqv != "" {
			realitySettings["mldsa65Verify"] = pqv
		}
		if sids, ok := realitySettings["shortIds"].([]any); ok && len(sids) > 0 {
			delete(realitySettings, "shortIds")
			if _, hasSid := realitySettings["shortId"]; !hasSid {
				realitySettings["shortId"] = fmt.Sprint(sids[0])
			}
		}
	}

	net, _ := streamSettings["network"].(string)
	if net == "xhttp" || net == "splithttp" {
		xhttpSettings, _ := streamSettings["xhttpSettings"].(map[string]any)
		if xhttpSettings == nil {
			xhttpSettings = make(map[string]any)
			streamSettings["xhttpSettings"] = xhttpSettings
		}
		if mode := q.Get("mode"); mode != "" {
			xhttpSettings["mode"] = mode
		}
		if host := q.Get("host"); host != "" {
			xhttpSettings["host"] = host
		}
		if extraRaw := q.Get("extra"); extraRaw != "" {
			var extraMap map[string]any
			if err := json.Unmarshal([]byte(extraRaw), &extraMap); err == nil && len(extraMap) > 0 {
				xhttpSettings["extra"] = extraMap
			}
		}
	}

	if fmRaw := q.Get("fm"); fmRaw != "" {
		var fmMap map[string]any
		if err := json.Unmarshal([]byte(fmRaw), &fmMap); err == nil && len(fmMap) > 0 {
			streamSettings["finalmask"] = fmMap
		}
	}

	res, err := json.Marshal(ob)
	if err != nil {
		return rawOb
	}
	return json.RawMessage(res)
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

type parsedSourceLink struct {
	raw     string
	tag     string
	address string
	port    int
}

type outboundMeta struct {
	tag     string
	address string
	port    int
}

func extractBatchLinks(raw string) []string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return nil
	}

	// Handle base64 encoded batch or subscription payload
	if !strings.Contains(trimmed, "://") {
		b64Clean := strings.ReplaceAll(trimmed, "\r", "")
		b64Clean = strings.ReplaceAll(b64Clean, "\n", "")
		b64Clean = strings.ReplaceAll(b64Clean, " ", "")
		for _, enc := range []*base64.Encoding{
			base64.StdEncoding,
			base64.RawStdEncoding,
			base64.URLEncoding,
			base64.RawURLEncoding,
		} {
			if dec, err := enc.DecodeString(b64Clean); err == nil && len(dec) > 0 {
				decStr := string(dec)
				if strings.Contains(decStr, "://") {
					trimmed = decStr
					break
				}
			}
		}
	}

	var lines []string
	scanner := bufio.NewScanner(strings.NewReader(trimmed))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line != "" && strings.Contains(line, "://") {
			lines = append(lines, line)
		}
	}
	return lines
}

func extractLinkMeta(linkStr string) parsedSourceLink {
	lm := parsedSourceLink{raw: linkStr}
	if strings.HasPrefix(linkStr, "vmess://") {
		b64Payload := strings.TrimPrefix(linkStr, "vmess://")
		b64Payload = strings.TrimSpace(b64Payload)
		for _, enc := range []*base64.Encoding{
			base64.StdEncoding,
			base64.RawStdEncoding,
			base64.URLEncoding,
			base64.RawURLEncoding,
		} {
			if dec, err := enc.DecodeString(b64Payload); err == nil {
				var vmessMap map[string]any
				if err := json.Unmarshal(dec, &vmessMap); err == nil {
					if ps, ok := vmessMap["ps"].(string); ok {
						lm.tag = strings.TrimSpace(ps)
					}
					if add, ok := vmessMap["add"].(string); ok {
						lm.address = strings.TrimSpace(add)
					}
					if pVal, ok := vmessMap["port"]; ok {
						switch v := pVal.(type) {
						case float64:
							lm.port = int(v)
						case string:
							fmt.Sscanf(v, "%d", &lm.port)
						}
					}
					return lm
				}
			}
		}
		return lm
	}

	u, err := url.Parse(linkStr)
	if err != nil {
		return lm
	}

	if u.Fragment != "" {
		frag := u.Fragment
		if unquoted, err := url.QueryUnescape(frag); err == nil && unquoted != "" {
			frag = unquoted
		}
		lm.tag = strings.TrimSpace(frag)
	}

	lm.address = strings.TrimSpace(u.Hostname())
	if pStr := u.Port(); pStr != "" {
		fmt.Sscanf(pStr, "%d", &lm.port)
	}

	return lm
}

func extractOutboundMeta(raw json.RawMessage) outboundMeta {
	var meta outboundMeta
	var obj map[string]any
	if err := json.Unmarshal(raw, &obj); err != nil {
		return meta
	}

	if tag, ok := obj["tag"].(string); ok {
		meta.tag = strings.TrimSpace(tag)
	}

	settings, _ := obj["settings"].(map[string]any)
	if settings == nil {
		return meta
	}

	if vnext, ok := settings["vnext"].([]any); ok && len(vnext) > 0 {
		if first, ok := vnext[0].(map[string]any); ok {
			if addr, ok := first["address"].(string); ok {
				meta.address = strings.TrimSpace(addr)
			}
			if p, ok := first["port"].(float64); ok {
				meta.port = int(p)
			}
		}
	} else if servers, ok := settings["servers"].([]any); ok && len(servers) > 0 {
		if first, ok := servers[0].(map[string]any); ok {
			if addr, ok := first["address"].(string); ok {
				meta.address = strings.TrimSpace(addr)
			}
			if p, ok := first["port"].(float64); ok {
				meta.port = int(p)
			}
		}
	}

	return meta
}

func findMatchingLink(meta outboundMeta, candidateLinks []parsedSourceLink, used []bool, idx int) string {
	if len(candidateLinks) == 0 {
		return ""
	}

	// 1. Exact match on tag + address
	if meta.tag != "" && meta.address != "" {
		for i, cand := range candidateLinks {
			if !used[i] && cand.tag != "" && strings.EqualFold(meta.tag, cand.tag) && strings.EqualFold(meta.address, cand.address) {
				used[i] = true
				return cand.raw
			}
		}
	}

	// 2. Match on tag
	if meta.tag != "" {
		for i, cand := range candidateLinks {
			if !used[i] && cand.tag != "" && strings.EqualFold(meta.tag, cand.tag) {
				used[i] = true
				return cand.raw
			}
		}
	}

	// 3. Match on address and port
	if meta.address != "" && meta.port != 0 {
		for i, cand := range candidateLinks {
			if !used[i] && strings.EqualFold(meta.address, cand.address) && meta.port == cand.port {
				used[i] = true
				return cand.raw
			}
		}
	}

	// 4. Match on address
	if meta.address != "" {
		for i, cand := range candidateLinks {
			if !used[i] && strings.EqualFold(meta.address, cand.address) {
				used[i] = true
				return cand.raw
			}
		}
	}

	// 5. Index-based match if available and not used
	if idx < len(candidateLinks) && !used[idx] {
		used[idx] = true
		return candidateLinks[idx].raw
	}

	// 6. First unused candidate
	for i, cand := range candidateLinks {
		if !used[i] {
			used[i] = true
			return cand.raw
		}
	}

	// 7. Fallback to candidate by index
	if idx < len(candidateLinks) {
		return candidateLinks[idx].raw
	}

	return ""
}

