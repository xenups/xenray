import subprocess

go_code = """package main

import (
	"fmt"
	"github.com/xtls/libxray/share"
)

func main() {
	link := "vless://00000000-0000-0000-0000-000000000001@example.com:443?security=tls&sni=example.com&type=tcp&headerType=none&fm=%7B%22tcp%22%3A%5B%7B%22type%22%3A%22http%22%7D%5D%7D#SampleFM"
	res, err := share.ConvertShareLinksToXrayJson(link, "")
	fmt.Printf("RES: %s\\nERR: %v\\n", string(res), err)
}
"""

with open("tools/xray-parser/test_fm.go", "w", encoding="utf-8") as f:
    f.write(go_code)

p = subprocess.run(["go", "run", "test_fm.go"], cwd="tools/xray-parser", capture_output=True, text=True)
print("STDOUT:")
print(p.stdout)
print("STDERR:")
print(p.stderr)
