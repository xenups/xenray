# PLAN — Fix LAN button, Update button, and monitoring false-pulses

## Branch: fix/auto-reconnect-v (working tree, do NOT commit without user OK)

## A. LAN Sidebar button — restore EXACT original, add fade only
File: `src/ui/components/common/nav_sidebar.py`
- Original (commit 7308951, verified): `_lan_btn = ft.Container(content=self._lan_icon, padding=all(10), border_radius=12, bgcolor/border/shadow from style, alignment=CENTER, on_click, ink=True)`
- ADD ONLY: `animate=ft.Animation(500, curve=ft.AnimationCurve.EASE_OUT)` to the Container (fade on bgcolor/border/color change).
- NO Stack, NO indicator dot, NO width/height overrides. Size/shape untouched.
- `_apply_lan_styles`: set icon.color/bgcolor/border/shadow + `self._lan_btn.update()` ONLY (no indicator refs).
- Remove `update_lan_badge` if it only delegated; keep the public API that lan_sharing_page actually uses (verify: `update_lan_button(allow_lan)`).
- Tests: `tests/test_nav_sidebar_lan_fade.py` — assert button content is `_lan_icon`, animate duration 500, no `_lan_indicator` attr, update_lan_button(True) applies style without error.

## B. Update button in Settings — make it render clean + animation work
File: `src/ui/components/settings/update_card.py`
- Current simplified version has no animation; user says it's still broken ("انیمیشنش کار نمیکنه").
- Goal: clean glass card + compact OutlinedButton + a REAL working check animation.
- Use `ft.ProgressRing` swap + button disabled while checking (this works in Flet 0.86.1).
- Verify `set_checking()` is actually called by the caller (grep settings_page / update flow). If the caller never calls it, wire it.
- NO sweep disc (too heavy/broken on this Flet version). Keep it simple: icon→ring swap + label change.
- Check Flet 0.86.1 API: OutlinedButton accepts `content` (verified in code); ProgressRing width/height/stroke_width ok.
- Test: construct UpdateCard with mock callback; call set_checking(True) → btn.disabled True, progress_ring.visible True, icon hidden; set_checking(False) → reversed.

## C. Monitoring false-pulses — stop the wrong PASSIVE_FAILURE spam
Files: `src/services/monitoring/passive_log_monitor.py`, `src/services/monitoring/auto_reconnect_service.py`, `src/core/connection_manager.py`
Root cause (from user log):
1. `dial tcp` + `i/o timeout` in ERROR_KEYWORDS are TOO BROAD — they match any dial failure, including LAN-internal dials (e.g. `dial tcp 172.16.0.2:1688: i/o timeout` = local service unreachable, NOT a VPN outage). Every such line spams `[PassiveLogMonitor] Keyword 'dial tcp' matched` (12× in one second in the log) → false PASSIVE_FAILURE → needless reconnect attempts.
2. The reconnect flow itself has a state-machine inconsistency: after `reconnect_failed` (FSM→ERROR, Gen 3), the next `connect()` success emits `"connected"` → FSM→CONNECTED (Gen 5) — UI shows error then jumps to connected, and a LATER PASSIVE_FAILURE fires again. The session/generation guards do not prevent the ERROR→CONNECTED jump because `connect()` bumps the session BEFORE the UI has settled.
Fixes:
- C1. Narrow ERROR_KEYWORDS: remove bare `dial tcp` and `i/o timeout`; replace with tighter patterns that only match outbound-to-INTERNET failures: e.g. `dial tcp` only when followed by a public IP/domain and NOT a private/LAN address (10./172.16-31./192.168./127./169.254.), or better: keep `connection refused`/`connection reset`/`handshake failed` (which are unambiguous) and drop the two noisiest. Decide with tests: a line `dial tcp 172.16.0.2:1688: i/o timeout` must NOT alert; a line `dial tcp 1.1.1.1:443: i/o timeout` (public) MUST alert.
- C2. Passive monitor: add a private/LAN-address guard — if the matched line contains a private IPv4 (10.x, 172.16-31.x, 192.168.x, 127.x, 169.254.x), skip the alert (it's an internal dial, not a VPN path failure).
- C3. AutoReconnectService: after `reconnect_failed`, do NOT let a subsequent `connect()` success silently flip FSM ERROR→CONNECTED without a real user-visible recovery. Verify the session_id is the SAME for the whole reconnect attempt; if `reconnect_failed` was emitted (session still valid), the reconnect loop must STOP (backoff) — the next "connected" must come from a USER action or a NEW deliberate attempt, not from the failed loop's connect(). Check `_emit_safe("reconnect_failed")` then `_attempt_reconnect` — there may be a path where handle_failure continues after emitting reconnect_failed. Ensure early return after reconnect_failed (no-internet case already returns False — verify the connect_failed case does too).
- C4. ConnectionManager `_handle_signal`: when PASSIVE_FAILURE arrives and auto-reconnect decides "no internet" (emits reconnect_failed → FSM ERROR), the UI must show ERROR state consistently until a real reconnect succeeds. Verify `reconnect_event_handler` handles `reconnect_failed` by setting UI to error/stopped (not leaving it "connected").
- Tests: unit tests for C1/C2 (keyword matching with private vs public IPs), C3 (reconnect_failed stops the loop), C4 (signal→event mapping). Existing monitoring tests must stay green (currently 721).

## D. State machine sanity (already fixed earlier — do NOT regress)
- PINGING/ERROR→STARTING→PREPARING mapper fix stays.
- Single-publisher EngineEvent stays.
- Full suite must remain green.

## Verification
1. `.venv/Scripts/python.exe -m pytest -q --no-cov` — full suite green (721 baseline).
2. black + isort on changed files (line 120).
3. Manual: user runs app — LAN button same size as before + fades; update button clean + ring animation on check; no more `dial tcp` spam in logs for LAN-internal addresses.
