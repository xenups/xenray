# PLAN — Reusable sweep animation + fix stats/sysinfo init timing

## Branch: fix/auto-reconnect-v (working tree, no commit)

## User requests (verbatim intent):
1. «check core update هم دقیقا همون انیمیشن رو باید داشته باشه و اسپینرش حذف بشه» — the update-check button must use EXACTLY the same animation as ConfigCard (server inspection), spinner removed.
2. «این انیمیشن باید ری یوزبل باشه» — the sweep animation must be REUSABLE (shared component), not copy-pasted.
3. «خرددفعه اینقدر فونت باید کوچیک شه» — the button font must NOT shrink.
4. «و للبالایی هم همینتطور» — the top label (title) must not shrink either.
5. «آمار موقع اسپلش اسکرین باید اینشیالایز بشه نه وقتی که رو صفحه اش کلیک میکنیم» — Statistics must initialize DURING the splash screen, not when the user clicks onto the page.
6. «اطلاعات سیستم تو صفحه لاگ هم همینطور نباید چیزی برای نمایش دیلی دداشته باشه» — system info on the Logs page must also initialize during splash — no delayed display.

## Root causes (verified by orchestrator):
- **R1 (reuse):** `update_card.py` has a hand-copied SweepGradient disc + `_animate_sweep` + `_schedule_animation` — a fork of ConfigCard's code. Any fix must be duplicated in both. → Extract a shared `NeonSweepBorder` component.
- **R2 (font shrink):** check current font sizes — `_btn_text` size=12, title size=14, version size=12. If a previous edit shrunk them (or ButtonStyle overrides text style), restore explicit sizes and ensure ButtonStyle doesn't override.
- **R3 (stats init timing):** `StatsForwardingService.forward_system_stats` (src/ui/services/stats_forwarding_service.py:111-132) has `if self._mw._active_tab != "logs": continue` (line 118) — it ONLY polls when the Logs tab is active. So when the user clicks the Logs tab, they must wait up to 3s for the first poll. Fix: poll ALWAYS (remove the tab check for system stats — psutil read is cheap, 3s interval), so values are fresh before the user even opens the tab. Also `start()` is called in `bind_handlers` (main_window.py:145) which runs during splash → the loop already starts early; just remove the tab gate.
- **R4 (statistics page init):** StatisticsPage starts with '—' placeholders and `_has_data=False`; telemetry only arrives while connected. The user wants the page initialized during splash — i.e. the network-stats forwarding loop (`forward_network_stats`) should also run regardless of active tab (check line ~66: `if not is_running or self._mw._nav_locked` — it already runs when connected; verify it isn't tab-gated too). And on app start (disconnected), the page should show its empty-state immediately (already done by previous work) — the KEY fix is that system stats (R3) and network stats must be pre-warmed so nothing is "delayed" when navigating.

## Task 1 — Extract reusable NeonSweepBorder component
- Create `src/ui/components/common/neon_sweep_border.py`:
  - `class NeonSweepBorder(ft.Container)`: takes `child` (the control to wrap), `width` (explicit, default None→auto), `height` (default 32), `border_radius` (default 8), `opaque_bgcolor` (default "#161922").
  - Internally: the EXACT ConfigCard pattern — outer Container padding=1.5, border_radius, clip_behavior=HARD_EDGE, width/height; content = Stack([sweep_disc (400px, negative left/top offsets), opaque inner Container(child, bgcolor=opaque_bgcolor, border_radius, HARD_EDGE)]).
  - Public API: `start()` / `stop()` — arm/cancel the sweep; `_sweep_disc.gradient` toggles; `_animate_sweep` loop; `_schedule_animation` (same as ConfigCard); `is_animating` property.
  - SWEEP_COLORS/SWEEP_STOPS stay module-level in the component.
- Refactor `config_card.py` to USE the component (replace its inline disc code with NeonSweepBorder wrapping `_inner_card`). Keep its public API (`start_inspection_animation`, `stop_inspection_animation`, `update_ping`, etc.) identical — tests must not change behavior.
- Refactor `update_card.py` to USE the component (replace inline disc with NeonSweepBorder wrapping the OutlinedButton). `set_checking` calls `border.start()/stop()`. KEEP font sizes: title 14, version 12, btn text 12 (verify no shrink).
- Tests: `tests/test_neon_sweep_border.py` (new): construct NeonSweepBorder(child=ft.Text("x")), assert (a) disc has negative offsets, (b) opaque inner layer present, (c) start() arms gradient + is_animating True, (d) stop() cancels + gradient None. Update `tests/test_update_card.py` + `tests/test_config_card.py` if constructor changed (keep public APIs stable so most tests pass unchanged).

## Task 2 — Fix stats/sysinfo init timing (splash pre-warm)
- `src/ui/services/stats_forwarding_service.py`:
  - `forward_system_stats` (line 111): REMOVE the `if self._mw._active_tab != "logs": continue` gate (line 118) — poll system stats ALWAYS (3s interval). This pre-warms memory/threads/health during splash so the Logs page has fresh data the moment it's opened. Keep the `_nav_locked` guard (don't fight during nav) OR remove it too if it delays first paint — decide: keep `_nav_locked` skip but do an IMMEDIATE first poll on start (before the sleep) so first values land instantly.
  - `forward_network_stats` (line ~36): verify it isn't tab-gated; if it is, same fix. Ensure it also does an immediate first poll.
  - `start()`: after `run_task(...)` calls, the loops begin — add immediate first-iteration data push (call the update once synchronously or make the loop update before sleeping).
- `src/ui/main_window.py`: verify `bind_handlers()` (which calls `_stats_forwarding.start()`) runs during splash (line 145). If it runs AFTER splash dismissal, move it earlier so stats pre-warm during splash.
- Verify `LoggerController`/`LogsPage.update_memory` etc. handle being called before the page is visible (they check `self._memory_card.page` — safe).
- Tests: `tests/test_stats_forwarding_init.py` (new): (a) simulate `forward_system_stats` loop without the tab gate — construct the service with a mock `_mw` where `_active_tab="dashboard"` and assert update_memory is still called; (b) immediate-first-poll: assert first call happens without waiting 3s (mock asyncio.sleep or check the loop structure); (c) `_nav_locked` still guards.

## Task 3 — Font/label size regression check + spinner sweep (DONE)
- ✅ Font sizes verified against HEAD (no shrink in any working-tree change):
  - UpdateCard: title "XenRay Client" size 14, version 12, button label 12.
  - XrayCoreCard: title "Xray-Core" 14, version 12, button label 12.
  - TerminalWindow: Copy/Download/Clear labels 11, title 11.
  - LogsDrawer Start/Stop button label 14 bold.
  - QRCard: "Scan to Connect" 11, "Generating..." 10 (acceptable). stats/logs pages: sizes preserved (only placeholder values changed to '—').
- ✅ No ButtonStyle `text_style` override in update_card / logs_drawer / terminal_window buttons (grep: only server_search_bar + log_viewer use text_style — unrelated).
- ✅ Spinner removed from BOTH update flows:
  - update_card.py: ProgressRing already removed (neon sweep-glow border instead).
  - **xray_core_card.py: ProgressRing REMOVED here** — converted to the same neon sweep-glow pattern as UpdateCard (set_checking drives start/stop_glow_animation, icon stays visible, no resize).
  - Remaining ProgressRings are legit: splash_screen loading ring, rules-update dialog (settings_handler.py:320), installer progress dialog, xray_core_card was the last update-button ring.
- ✅ Tests: test_update_card.py `test_font_sizes_not_shrunk` (title 14 / version 12 / btn 12 + no text_style override), test_xray_core_card.py `test_xray_core_card_no_spinner_ring` + `test_xray_core_card_font_sizes` + sweep-state assertions, test_logs_drawer_visibility.py `test_toggle_btn_label_is_14_bold`, NEW tests/test_terminal_window_fonts.py (labels+title 11). Full suite: 766 passed (baseline 760 + 6 new).

## Constraints
- Flet 0.86.1 (verify new kwargs via inspect.signature). black/isort 120. tests/conftest.py untouched. No commit. Full suite green (760 baseline).
- SRP: the component is pure UI; ConfigCard keeps its inspection semantics (start/stop names), UpdateCard keeps set_checking semantics.
