import time
import subprocess
import json
import statistics

# 1. Prepare sample links
sample_links = [
    "vless://00000000-0000-0000-0000-000000000001@example.com:443?security=tls&sni=example.com&type=ws&path=%2Fws#Node-TLS-WS",
    "vless://00000000-0000-0000-0000-000000000001@example.com:443?security=reality&sni=example.com&pbk=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&sid=0123456789abcdef&flow=xtls-rprx-vision&fp=chrome#Node-Reality",
    "vless://00000000-0000-0000-0000-000000000001@example.com:443?type=xhttp&path=%2Fxhttp&mode=auto&security=tls&sni=example.com#Node-XHTTP",
    "vmess://eyJ2IjoiMiIsInBzIjoiVk1lc3MtMSIsImFkZCI6InZtZXNzMS5leGFtcGxlLmNvbSIsInBvcnQiOiI0NDMiLCJpZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMiIsImFpZCI6IjAiLCJzY3kiOiJhdXRvIiwibmV0Ijoid3MiLCJ0eXBlIjoibm9uZSIsImhvc3QiOiJ2bWVzcy5leGFtcGxlLmNvbSIsInBhdGgiOiIvdm1lc3MiLCJ0bHMiOiJ0bHMiLCJzbmkiOiJ2bWVzcy5leGFtcGxlLmNvbSJ9",
    "vless://00000000-0000-0000-0000-000000000001@example.com:443?security=tls&sni=example.com&type=tcp&headerType=none&fm=%7B%22tcp%22%3A%5B%7B%22type%22%3A%22fragment%22%2C%22settings%22%3A%7B%22packets%22%3A%22tlshello%22%2C%22length%22%3A%22100-200%22%2C%22interval%22%3A%2210-20%22%7D%7D%5D%7D#Node-FinalMask",
]

# Generate 50 links for benchmarking
test_links = (sample_links * 10)[:50]
total_count = len(test_links)
print(f"=== BENCHMARK: Parsing {total_count} Links (Sequential Subprocess vs Single Batch) ===")

# Benchmark 1: Sequential Subprocess Invocation (One process per link)
seq_times = []
seq_results = []
t0_total_seq = time.perf_counter()

for i, link in enumerate(test_links):
    t0 = time.perf_counter()
    p = subprocess.run(
        ["bin/xray-parser.exe", "-link", link],
        capture_output=True,
        text=True,
        creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    )
    dt = (time.perf_counter() - t0) * 1000.0  # ms
    seq_times.append(dt)
    data = json.loads(p.stdout)
    seq_results.append(data.get("success", False))

total_seq_duration = (time.perf_counter() - t0_total_seq) * 1000.0

# Benchmark 2: Batch Subprocess Invocation (All 50 links in 1 process call)
batch_input = "\n".join(test_links)
t0_batch = time.perf_counter()

p_batch = subprocess.run(
    ["bin/xray-parser.exe", "-batch"],
    input=batch_input,
    capture_output=True,
    text=True,
    creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
)
total_batch_duration = (time.perf_counter() - t0_batch) * 1000.0
batch_data = json.loads(p_batch.stdout)
batch_results = batch_data.get("items", [])

# Raw output verification
print("\n--- RAW DATA SAMPLE ---")
print("Sequential first 5 run times (ms):", [round(t, 2) for t in seq_times[:5]])
print("Batch output count:", len(batch_results))
print("Batch success count:", sum(1 for r in batch_results if r.get("config")))
print("Sequential success count:", sum(1 for s in seq_results if s))

print("\n--- PERFORMANCE SUMMARY ---")
print(f"Sequential (50 process spawns):")
print(f"  Total wall-clock: {total_seq_duration:.2f} ms ({total_seq_duration / 1000.0:.3f} s)")
print(f"  Min latency:      {min(seq_times):.2f} ms")
print(f"  Max latency:      {max(seq_times):.2f} ms")
print(f"  Mean latency:     {statistics.mean(seq_times):.2f} ms per link")
print(f"  Median latency:   {statistics.median(seq_times):.2f} ms")
print(f"  StdDev:           {statistics.stdev(seq_times):.2f} ms")

print(f"\nBatch (1 process spawn for 50 links):")
print(f"  Total wall-clock: {total_batch_duration:.2f} ms ({total_batch_duration / 1000.0:.3f} s)")
print(f"  Avg per link:     {total_batch_duration / total_count:.2f} ms per link")

speedup = total_seq_duration / total_batch_duration
print(f"\nSpeedup factor:     {speedup:.2f}x faster with Batch mode!")
