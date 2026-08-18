# PLAN — 3 isolated workstreams (UI / State / Notifications)

## Branch: fix/auto-reconnect-v (working tree, no commit)

## Dependency map (no overlaps — disjoint files):
- **WS1 (UI)**: src/ui/components/settings/update_card.py, xray_core_card.py, src/ui/components/logs/terminal_window.py, src/ui/pages/logs_page.py, src/ui/builders/ui_builder.py, tests/test_update_card.py, tests/test_terminal_window_fonts.py, tests/test_logs_drawer_visibility.py
- **WS2 (State)**: src/ui/components/servers/server_list_sort.py, src/core/app_context.py (settings), src/core/settings*.py, tests/test_server_sort_persistence.py (new)
- **WS3 (Notifications)**: src/ui/controllers/settings_controller.py, src/ui/pages/settings_page.py, tests/test_settings_toasts.py (new)
- NO file appears in two workstreams → zero conflicts. WS2 touches src/core (settings), WS1/WS3 touch src/ui only.

---

## WS1 — UI Fixes (subagent 1)

### 1a. Update buttons: fixed size during loading
- update_card.py + xray_core_card.py: NeonSweepBorder width=180, height=32 already explicit. VERIFY the inner OutlinedButton does NOT shrink: set_checking toggles label text "Check for Updates"→"Updating..." (short, fits). Ensure the ButtonStyle has NO min-width removal and the wrapper width is FIXED. If the button still shrinks, set explicit width on the OutlinedButton itself (width=170 inside the 180 wrapper) so content changes never resize it.
- Add test: record wrapper width before/after set_checking(True/False) → unchanged.

### 1b. Start button uniform with sibling buttons
- terminal_window.py: _toggle_tail_btn (FilledButton, height=32) sits in a Row with copy/download/clear (OutlinedButton height ~32). Make Start/Stop the SAME height and visual weight as siblings: height=32, same border_radius=8, consistent padding. Do NOT make it expand (user wants uniform, not oversized).
- logs_drawer.py: the drawer's _toggle_tail_btn (FilledButton height=36, expand=True) — align to 32 and remove expand if it makes it inconsistent; keep it clearly visible (green/red) but same size class as other buttons.

### 1c. Logs view cleanup
- Remove the Download button from TerminalWindow (terminal_window.py): delete download_btn + on_download_click param (or keep param optional for backward-compat but drop the button from the Row). Update logs_page.py to stop passing on_download_logs_click (or make optional). Remove from the Row: [copy_btn, clear_btn, toggle_tail_btn].
- "Remove duplicate/redundant logs from UI display": check log_viewer._append_batch — dedupe consecutive identical lines (if line == last appended line, skip) to kill repeated spam lines in the viewer. Add a small dedupe (max consecutive duplicates shown once, or collapse N identical into "×N"). Keep it simple: skip consecutive identical lines.
- Tests: test_terminal_window_fonts.py updated (no download btn), new assert in test_logs_drawer_visibility or a new test for dedupe in log_viewer.

## WS2 — Sort Order Persistence (subagent 2)
- server_list_sort.py: `_on_sort_changed` calls `self._app_context.settings.set_sort_mode(mode)` (line 35) — verify set_sort_mode/get_sort_mode actually PERSIST to disk (check src/core/app_context.py settings + settings repository). If they only keep in-memory, fix the persistence layer: save to the config file (same mechanism as other settings, e.g. auto_reconnect_enabled.txt or settings.json — follow the existing pattern).
- On app start, `_apply_sort` (line 90-92) reads `get_sort_mode()` — verify it's loaded from disk at startup (app_context init). If the startup path resets it, load persisted value.
- Tests: tests/test_server_sort_persistence.py — set sort mode, re-create app_context/settings (simulate restart), assert get_sort_mode() returns persisted value; assert server_list_sort._on_sort_changed persists.

## WS3 — Settings Change Notifications (subagent 3)
- Root cause: SettingsController._show_toast exists (settings_controller.py:21) and update flow calls it (check_for_updates → _show_toast at :68/:75 etc.), but the toast may not RENDER because `_toast_callback` is never wired in the SettingsView path (settings_page.py uses ToastManager directly at :148/:170 for OTHER toasts, but the controller's _show_toast needs a callback or page).
- Fix: in SettingsPage (or wherever SettingsController is constructed), wire `toast_callback` to `ToastManager.show` (or page._toast_manager.show) so ALL controller toasts (update success/error, core update, config changes) render. Alternatively, if SettingsController holds no page ref, pass a callback that routes to the page's toast manager.
- ALSO: any settings change (mode switch, tun engine, port, country, auto-reconnect toggle, LAN toggle) must show a toast — check which rows already fire toast_callback (auto_reconnect_toggle_row, lan_share_toggle_row do at :59/:66) and which DON'T (mode_switch_row? port_row? country_row? update rows?). Add toasts where missing, using the same toast_callback pattern.
- Tests: tests/test_settings_toasts.py — construct SettingsController with a mock toast_callback; call check_for_updates success path → assert callback called with success message; check update failure path → error toast; verify mode/country/port change handlers call toast_callback.

## Verification (each subagent runs its own, then full suite)
1. Targeted tests pass.
2. `.venv/Scripts/python.exe -m pytest -q --no-cov` — FULL green (780 baseline).
3. black + isort (line 120). tests/conftest.py untouched. No commit.
