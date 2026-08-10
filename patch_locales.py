"""Temporary script to patch locale files with missing keys."""

import json
from pathlib import Path

LOCALES = Path("assets/locales")


def load(l):
    return json.loads((LOCALES / f"{l}.json").read_text(encoding="utf-8"))


def _sanitize(obj):
    """Replace surrogate characters in strings so json.dumps(ensure_ascii=False) works."""
    if isinstance(obj, str):
        return obj.encode("utf-8", errors="surrogatepass").decode(
            "utf-8", errors="replace"
        )
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(i) for i in obj]
    return obj


def dump(l, d):
    (LOCALES / f"{l}.json").write_text(
        json.dumps(_sanitize(d), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


stats_en = {
    "session": "Session: ",
    "total_data": "Total Data Transfer",
    "peak_speed": "Peak Speed: ",
    "realtime_wave": "Real-Time Traffic Wave Stream",
    "download": "Download",
    "upload": "Upload",
}

fa_extra = {
    "settings": {
        "port_invalid": "\u067e\u0648\u0631\u062a \u0628\u0627\u06cc\u062f \u0628\u06cc\u0646 1024 \u062a\u0627 65535 \u0628\u0627\u0634\u062f",
        "language_desc": "\u0632\u0628\u0627\u0646 \u0646\u0645\u0627\u06cc\u0634 \u0631\u0627\u0628\u0637 \u06a9\u0627\u0631\u0628\u0631\u06cc",
        "startup_saved": "\u062a\u0646\u0638\u06cc\u0645 \u0634\u0631\u0648\u0639 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f",
        "startup_on": "\u0641\u0639\u0627\u0644",
        "startup_off": "\u063a\u06cc\u0631\u0641\u0639\u0627\u0644",
        "connectivity_title": "\u062a\u0646\u0638\u06cc\u0645\u0627\u062a \u0627\u062a\u0635\u0627\u0644",
        "routing_title": "\u0645\u0633\u06cc\u0631\u06cc\u0627\u0628\u06cc \u0648 \u0636\u062f \u0646\u0634\u062a",
        "preferences_title": "\u062a\u0631\u062c\u06cc\u0647\u0627\u062a \u0628\u0631\u0646\u0627\u0645\u0647",
        "vpn_mode": "\u062d\u0627\u0644\u062a TUN / VPN",
        "vpn_mode_desc": "\u062a\u0648\u0646\u0644 \u06a9\u0627\u0645\u0644 VPN",
        "proxy_mode": "\u062d\u0627\u0644\u062a \u067e\u0631\u0648\u06a9\u0633\u06cc \u0633\u06cc\u0633\u062a\u0645",
        "proxy_mode_desc": "\u067e\u0631\u0648\u06a9\u0633\u06cc SOCKS + HTTP",
        "recommended": "\u067e\u06cc\u0634\u0646\u0647\u0627\u062f",
    },
    "status": {
        "checking": "\u062f\u0631 \u062d\u0627\u0644 \u0628\u0631\u0631\u0633\u06cc",
    },
    "dashboard": {
        "network_traffic": "\u062a\u0631\u0627\u0641\u06cc\u06a9 \u0634\u0628\u06a9\u0647",
        "live_statistics": "\u0622\u0645\u0627\u0631 \u0632\u0646\u062f\u0647",
        "current_node": "\u06af\u0631\u0647 \u0641\u0639\u0644\u06cc",
        "change_server": "\u062a\u063a\u06cc\u06cc\u0631 \u0633\u0631\u0648\u0631",
        "uptime": "\u0632\u0645\u0627\u0646 \u06a9\u0627\u0631: {time}",
        "upload": "\u0622\u067e\u0644\u0648\u062f",
        "download": "\u062f\u0627\u0646\u0644\u0648\u062f",
        "protocol": "\u067e\u0631\u0648\u062a\u06a9\u0644",
        "encryption": "\u0631\u0645\u0632\u0646\u06af\u0627\u0631\u06cc",
        "local_ip": "\u0622\u06cc\u200c\u067e\u06cc \u0645\u062d\u0644\u06cc",
        "server_ip": "\u0622\u06cc\u200c\u067e\u06cc \u0633\u0631\u0648\u0631",
        "checking": "\u062f\u0631 \u062d\u0627\u0644 \u0628\u0631\u0631\u0633\u06cc...",
        "secure": "\u0627\u0645\u0646",
        "system_secure": "\u0633\u06cc\u0633\u062a\u0645 \u0627\u0645\u0646",
        "system_ready": "\u0633\u06cc\u0633\u062a\u0645 \u0622\u0645\u0627\u062f\u0647",
        "no_internet": "\u0628\u062f\u0648\u0646 \u0627\u06cc\u0646\u062a\u0631\u0646\u062a",
        "connected": "\u0645\u062a\u0635\u0644",
        "disconnected": "\u0642\u0637\u0639 \u0634\u062f\u0647",
        "quick_disconnect": "\u0642\u0637\u0639 \u0633\u0631\u06cc\u0639",
        "quick_connect": "\u0627\u062a\u0635\u0627\u0644 \u0633\u0631\u06cc\u0639",
        "cpu": "CPU: {percent}%",
        "ram": "RAM: {mb}MB",
        "realtime_wave": "\u0645\u0648\u062c \u0632\u0646\u062f\u0647 \u062a\u0631\u0627\u0641\u06cc\u06a9 \u0648 \u0622\u0645\u0627\u0631 \u062f\u0642\u06cc\u0642",
        "view_statistics": "\u0635\u0641\u062d\u0647 \u0622\u0645\u0627\u0631 \ud83d\udcca",
        "country": "\u06a9\u0634\u0648\u0631",
    },
    "logs": {
        "memory": "\u062d\u0627\u0641\u0638\u0647",
        "active_threads": "\u0631\u0634\u062a\u0647\u200c\u0647\u0627\u06cc \u0641\u0639\u0627\u0644",
        "health_status": "\u0648\u0636\u0639\u06cc\u062a \u0633\u0644\u0627\u0645\u062a",
        "nodes": "\u06af\u0631\u0647\u200c\u0647\u0627",
        "optimal_performance": "\u0639\u0645\u0644\u06a9\u0631\u062f \u0628\u0647\u06cc\u0646\u0647",
        "issues": "\u0645\u0634\u06a9\u0644\u0627\u062a",
        "system_healthy": "\u0633\u06cc\u0633\u062a\u0645 \u0633\u0627\u0644\u0645 \u0627\u0633\u062a",
        "copy": "\u06a9\u067e\u06cc",
        "download": "\u062f\u0627\u0646\u0644\u0648\u062f",
        "clear": "\u067e\u0627\u06a9 \u06a9\u0631\u062f\u0646",
        "terminal_title": "XENRAY_CLI :: \u0644\u0627\u06af \u0627\u0635\u0644\u06cc",
    },
    "nav": {
        "dashboard": "\u062f\u0627\u0634\u0628\u0648\u0631\u062f",
        "statistics": "\u0622\u0645\u0627\u0631",
        "servers": "\u0633\u0631\u0648\u0631\u0647\u0627",
        "logs": "\u0644\u0627\u06af\u200c\u0647\u0627",
        "settings": "\u062a\u0646\u0638\u06cc\u0645\u0627\u062a",
        "connect_now": "\u0627\u062a\u0635\u0627\u0644",
        "disconnect": "\u0642\u0637\u0639 \u0627\u062a\u0635\u0627\u0644",
    },
    "servers": {
        "selected_node": "\u06af\u0631\u0647 \u0627\u0646\u062a\u062e\u0627\u0628 \u0634\u062f\u0647",
        "search_placeholder": "\u062c\u0633\u062a\u062c\u0648\u06cc \u0646\u0627\u0645 \u0633\u0631\u0648\u0631\u060c \u0645\u0646\u0637\u0642\u0647 \u06cc\u0627 \u0622\u06cc\u200c\u067e\u06cc...",
        "add": "\u0627\u0641\u0632\u0648\u062f\u0646 \u0633\u0631\u0648\u0631",
        "latency": "\u062a\u0623\u062e\u06cc\u0631",
    },
    "stats": stats_en,
}

ru_extra = {
    "settings": {
        "port_invalid": "\u041f\u043e\u0440\u0442 \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u043e\u0442 1024 \u0434\u043e 65535",
        "language_desc": "\u042f\u0437\u044b\u043a \u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u0430",
        "startup_saved": "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430 \u0430\u0432\u0442\u043e\u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0430",
        "startup_on": "\u0412\u043a\u043b",
        "startup_off": "\u0412\u044b\u043a\u043b",
        "connectivity_title": "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f",
        "routing_title": "\u041c\u0430\u0440\u0448\u0440\u0443\u0442\u0438\u0437\u0430\u0446\u0438\u044f \u0438 \u0437\u0430\u0449\u0438\u0442\u0430 \u043e\u0442 \u0443\u0442\u0435\u0447\u0435\u043a",
        "preferences_title": "\u041f\u0440\u0435\u0434\u043f\u043e\u0447\u0442\u0435\u043d\u0438\u044f \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f",
        "vpn_mode": "\u0420\u0435\u0436\u0438\u043c TUN / VPN",
        "vpn_mode_desc": "\u041f\u043e\u043b\u043d\u044b\u0439 \u0442\u0443\u043d\u043d\u0435\u043b\u044c VPN",
        "proxy_mode": "\u0420\u0435\u0436\u0438\u043c \u0441\u0438\u0441\u0442\u0435\u043c\u043d\u043e\u0433\u043e \u043f\u0440\u043e\u043a\u0441\u0438",
        "proxy_mode_desc": "SOCKS + HTTP \u043f\u0440\u043e\u043a\u0441\u0438",
        "recommended": "\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0443\u0435\u0442\u0441\u044f",
    },
    "status": {
        "checking": "\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430",
    },
    "dashboard": {
        "network_traffic": "\u0421\u0415\u0422\u0415\u0412\u041e\u0419 \u0422\u0420\u0410\u0424\u0418\u041a",
        "live_statistics": "\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430 \u0432 \u0440\u0435\u0430\u043b\u044c\u043d\u043e\u043c \u0432\u0440\u0435\u043c\u0435\u043d\u0438",
        "current_node": "\u0422\u0415\u041a\u0423\u0429\u0418\u0419 \u0423\u0417\u0415\u041b",
        "change_server": "\u0421\u043c\u0435\u043d\u0438\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440",
        "uptime": "\u0412\u0440\u0435\u043c\u044f \u0440\u0430\u0431\u043e\u0442\u044b: {time}",
        "upload": "\u0412\u044b\u0433\u0440\u0443\u0437\u043a\u0430",
        "download": "\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430",
        "protocol": "\u041f\u0440\u043e\u0442\u043e\u043a\u043e\u043b",
        "encryption": "\u0428\u0438\u0444\u0440\u043e\u0432\u0430\u043d\u0438\u0435",
        "local_ip": "\u041b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0439 IP",
        "server_ip": "IP \u0441\u0435\u0440\u0432\u0435\u0440\u0430",
        "checking": "\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430...",
        "secure": "\u0411\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e",
        "system_secure": "\u0421\u0438\u0441\u0442\u0435\u043c\u0430 \u0437\u0430\u0449\u0438\u0449\u0435\u043d\u0430",
        "system_ready": "\u0421\u0418\u0421\u0422\u0415\u041c\u0410 \u0413\u041e\u0422\u041e\u0412\u0410",
        "no_internet": "\u041d\u0415\u0422 \u0418\u041d\u0422\u0415\u0420\u041d\u0415\u0422\u0410",
        "connected": "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043e",
        "disconnected": "\u041e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u043e",
        "quick_disconnect": "\u0411\u044b\u0441\u0442\u0440\u043e\u0435 \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435",
        "quick_connect": "\u0411\u044b\u0441\u0442\u0440\u043e\u0435 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435",
        "cpu": "\u0426\u041f: {percent}%",
        "ram": "\u041e\u0417\u0423: {mb}MB",
        "realtime_wave": "\u041f\u043e\u0442\u043e\u043a\u043e\u0432\u0430\u044f \u0432\u0438\u0437\u0443\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f \u0442\u0440\u0430\u0444\u0438\u043a\u0430 \u0432 \u0440\u0435\u0430\u043b\u044c\u043d\u043e\u043c \u0432\u0440\u0435\u043c\u0435\u043d\u0438",
        "view_statistics": "\u0421\u0442\u0440\u0430\u043d\u0438\u0446\u0430 \u0441\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0438 \ud83d\udcca",
        "country": "\u0421\u0442\u0440\u0430\u043d\u0430",
    },
    "logs": {
        "memory": "\u041f\u0430\u043c\u044f\u0442\u044c",
        "active_threads": "\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u043f\u043e\u0442\u043e\u043a\u0438",
        "health_status": "\u0421\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0435 \u0441\u0438\u0441\u0442\u0435\u043c\u044b",
        "nodes": "\u0423\u0437\u043b\u044b",
        "optimal_performance": "\u041e\u043f\u0442\u0438\u043c\u0430\u043b\u044c\u043d\u0430\u044f \u043f\u0440\u043e\u0438\u0437\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c",
        "issues": "\u041f\u0440\u043e\u0431\u043b\u0435\u043c\u044b",
        "system_healthy": "\u0421\u0438\u0441\u0442\u0435\u043c\u0430 \u0432 \u043d\u043e\u0440\u043c\u0435",
        "copy": "\u041a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
        "download": "\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430",
        "clear": "\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c",
        "terminal_title": "XENRAY_CLI :: \u0413\u041b\u0410\u0412\u041d\u042b\u0419 \u041b\u041e\u0413",
    },
    "nav": {
        "dashboard": "\u0413\u043b\u0430\u0432\u043d\u0430\u044f",
        "statistics": "\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430",
        "servers": "\u0421\u0435\u0440\u0432\u0435\u0440\u044b",
        "logs": "\u041b\u043e\u0433\u0438",
        "settings": "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438",
        "connect_now": "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u044c",
        "disconnect": "\u041e\u0442\u043a\u043b\u044e\u0447\u0438\u0442\u044c",
    },
    "servers": {
        "selected_node": "\u0412\u042b\u0411\u0420\u0410\u041d\u041d\u042b\u0419 \u0423\u0417\u0415\u041b",
        "search_placeholder": "\u041f\u043e\u0438\u0441\u043a \u0438\u043c\u0435\u043d\u0438, \u0440\u0435\u0433\u0438\u043e\u043d\u0430 \u0438\u043b\u0438 IP \u0441\u0435\u0440\u0432\u0435\u0440\u0430...",
        "add": "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440",
        "latency": "\u0417\u0410\u0414\u0415\u0420\u0416\u041a\u0410",
    },
    "stats": stats_en,
}

zh_extra = {
    "settings": {
        "port_invalid": "\u7aef\u53e3\u5fc5\u987b\u5728 1024 \u5230 65535 \u4e4b\u95f4",
        "language_desc": "\u754c\u9762\u663e\u793a\u8bed\u8a00",
        "startup_saved": "\u542f\u52a8\u8bbe\u7f6e\u5df2\u4fdd\u5b58",
        "startup_on": "\u5f00\u542f",
        "startup_off": "\u5173\u95ed",
        "connectivity_title": "\u8fde\u63a5\u8bbe\u7f6e",
        "routing_title": "\u8def\u7531\u4e0e\u9632\u6cc4\u6f0f",
        "preferences_title": "\u5e94\u7528\u504f\u597d",
        "vpn_mode": "TUN / VPN \u6a21\u5f0f",
        "vpn_mode_desc": "\u5b8c\u6574 VPN \u96a7\u9053",
        "proxy_mode": "\u7cfb\u7edf\u4ee3\u7406\u6a21\u5f0f",
        "proxy_mode_desc": "SOCKS + HTTP \u4ee3\u7406",
        "recommended": "\u63a8\u8350",
    },
    "status": {
        "checking": "\u68c0\u67e5\u4e2d",
    },
    "dashboard": {
        "network_traffic": "\u7f51\u7edc\u6d41\u91cf",
        "live_statistics": "\u5b9e\u65f6\u7edf\u8ba1",
        "current_node": "\u5f53\u524d\u8282\u70b9",
        "change_server": "\u66f4\u6362\u670d\u52a1\u5668",
        "uptime": "\u8fd0\u884c\u65f6\u95f4: {time}",
        "upload": "\u4e0a\u4f20",
        "download": "\u4e0b\u8f7d",
        "protocol": "\u534f\u8bae",
        "encryption": "\u52a0\u5bc6",
        "local_ip": "\u672c\u5730 IP",
        "server_ip": "\u670d\u52a1\u5668 IP",
        "checking": "\u68c0\u67e5\u4e2d...",
        "secure": "\u5b89\u5168",
        "system_secure": "\u7cfb\u7edf\u5b89\u5168",
        "system_ready": "\u7cfb\u7edf\u5c31\u7eea",
        "no_internet": "\u65e0\u4e92\u8054\u7f51",
        "connected": "\u5df2\u8fde\u63a5",
        "disconnected": "\u5df2\u65ad\u5f00",
        "quick_disconnect": "\u5feb\u901f\u65ad\u5f00",
        "quick_connect": "\u5feb\u901f\u8fde\u63a5",
        "cpu": "CPU: {percent}%",
        "ram": "\u5185\u5b58: {mb}MB",
        "realtime_wave": "\u5b9e\u65f6\u6d41\u91cf\u6ce2\u5f62\u56fe\u53ca\u8be6\u7ec6\u7edf\u8ba1",
        "view_statistics": "\u7edf\u8ba1\u9875\u9762 \ud83d\udcca",
        "country": "\u56fd\u5bb6",
    },
    "logs": {
        "memory": "\u5185\u5b58",
        "active_threads": "\u6d3b\u8dc3\u7ebf\u7a0b",
        "health_status": "\u5065\u5eb7\u72b6\u6001",
        "nodes": "\u8282\u70b9",
        "optimal_performance": "\u6700\u4f73\u6027\u80fd",
        "issues": "\u95ee\u9898",
        "system_healthy": "\u7cfb\u7edf\u6b63\u5e38",
        "copy": "\u590d\u5236",
        "download": "\u4e0b\u8f7d",
        "clear": "\u6e05\u9664",
        "terminal_title": "XENRAY_CLI :: \u4e3b\u65e5\u5fd7",
    },
    "nav": {
        "dashboard": "\u4eea\u8868\u76d8",
        "statistics": "\u7edf\u8ba1",
        "servers": "\u670d\u52a1\u5668",
        "logs": "\u65e5\u5fd7",
        "settings": "\u8bbe\u7f6e",
        "connect_now": "\u8fde\u63a5",
        "disconnect": "\u65ad\u5f00",
    },
    "servers": {
        "selected_node": "\u5df2\u9009\u8282\u70b9",
        "search_placeholder": "\u641c\u7d22\u670d\u52a1\u5668\u540d\u79f0\u3001\u5730\u533a\u6216 IP...",
        "add": "\u6dfb\u52a0\u670d\u52a1\u5668",
        "latency": "\u5ef6\u8fdf",
    },
    "stats": stats_en,
    "server_list": {"servers": "\u670d\u52a1\u5668"},
}


def deep_merge(base, override):
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v


# Patch en.json: add stats section + dashboard.country
en = load("en")
en["stats"] = stats_en
en.setdefault("dashboard", {})["country"] = "Country"
dump("en", en)

for lang, extra in [("fa", fa_extra), ("ru", ru_extra), ("zh", zh_extra)]:
    data = load(lang)
    deep_merge(data, extra)
    dump(lang, data)
    with open(LOCALES / f"{lang}.json", encoding="utf-8") as f:
        lines = len(f.readlines())
    print(f"{lang}.json updated ({lines} lines)")

print("All locales patched.")
