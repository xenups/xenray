# PLAN — Fix 3 UI issues (orchestrator dispatch)

## Branch: fix/auto-reconnect-v (working tree, no commit)

## Issue 1 — Update button: sweep disc shows as FULL CIRCLE (mask missing) + button resizes
File: `src/ui/components/settings/update_card.py`
User: «الان چک آپدیت کلاینت ماسک نداره کل دایره داره توی دکمه میچرخه و معلومه و دکمه موقع آپدیت تغییر سایزم میده»

Root cause (verified):
- The sweep disc is a 400px circle inside `_btn_wrapper` (Stack + clip HARD_EDGE). But the disc is a SIBLING of the button in the Stack — the Stack sizes to its largest child (the 400px disc!), so the button wrapper expands to ~400px and the FULL CIRCLE shows (HARD_EDGE on the Stack clips the DISC to the wrapper's bounds, but the wrapper's bounds are huge because the disc is inside).
- ConfigCard solves this with a SEPARATE outer border container (1.5px padding) + inner opaque card: the disc is positioned with left/top NEGATIVE offsets so it never contributes to layout, and an opaque inner card covers the center leaving only the rim.
- Button resizes during check because `set_checking` toggles `_btn_icon.visible` — the Row (icon+text) loses the icon → narrower. Fix: reserve icon space (keep icon but swap to a subtle state, or use a fixed-width container), OR set an explicit min width on the button.

Fix (copy ConfigCard exactly):
1. Wrap the BUTTON in a small border container like ConfigCard: outer container padding 1.5px + border_radius 8, inner opaque button. The disc goes in a Stack with left/top NEGATIVE offsets ((w - diameter)/2 where w=button width ~140) so it never affects layout.
2. Better: make `_btn_wrapper` a Stack with the disc POSITIONED (left/top negative) and `clip_behavior=HARD_EDGE` on the OUTER container only, and the button as the sizing child (not the disc). The Stack must NOT size to the disc — use `ft.Stack` with the button first + disc positioned absolutely.
3. Remove the visible icon toggle that shrinks the button: keep `_btn_icon` always visible (or swap to a fixed-size invisible placeholder). Set `self._update_btn` explicit `width`/`min_width` (e.g. 150) so it never resizes.
4. Keep the neon SweepGradient rim (that part is right — user just wants the MASK so only the rim shows, not the full circle).
Tests: `tests/test_update_card.py` — assert the wrapper Stack's disc uses negative left/top offsets (does not affect layout), button has explicit width, icon does NOT toggle visible (or placeholder), set_checking(True) does not change button width.

## Issue 2 — Logs drawer: START/STOP button still not visible/clear
File: `src/ui/components/logs/logs_drawer.py`
User: «دکمه های لاگ برای استارت استاپ مشخص نیست هنوز»

Root cause: The `_toggle_tail_btn` is an `ft.ElevatedButton` with default theme styling (likely dark-on-dark, low contrast) inside `_tail_row` — it exists but is NOT visually distinct (blends into the drawer bg).

Fix:
1. Give the button a STRONG visible style: `FilledButton` (or ElevatedButton with explicit bgcolor ACCENT/green + white text + border). Use `ft.FilledButton` if Flet 0.86.1 supports it (verify via inspect.signature), else ElevatedButton with `style=ft.ButtonStyle(bgcolor=..., color=...)`.
2. Make the label explicit: «▶ Start» / «■ Stop» (i18n keys exist: logs.enable/logs.disable). Icon swaps PLAY/STOP. 
3. Ensure `_tail_row` has full width and the button expands (`expand=True` on the row or button) so it's a big obvious control.
4. Verify contrast: bgcolor `#4ADE80`-ish green when OFF (invites click), red `#f43f5e` when ON (stop), white text both.
Tests: `tests/test_logs_drawer_visibility.py` — construct LogsDrawer (needs LogViewer + heartbeat mocks), assert _toggle_tail_btn has explicit bgcolor, label text is Start, icon is PLAY; toggle → label Stop, icon STOP, bgcolor changes.

## Issue 3 — Statistics page: blank/zero until data loads (annoying)
File: `src/ui/pages/statistics_page.py` (+ maybe WaveVisualizer/WaveCard)
User: «تو صفحه آمار باید صبر کنن اطلاعات لود بشه که آزار دهنده اس»

Root cause: The page starts with «0.0 MB/s» everywhere and only fills when telemetry events arrive (only while connected). If not connected / before first event, the user stares at zeros.

Fix options (pick the cleanest):
1. **Placeholder state**: when `_is_connected == False`, show a clear «Not connected — start a connection to see live stats» empty-state (icon + text) instead of zero values. When connected, show the real cards.
2. OR **skeleton shimmer**: show a skeleton (pulsing blocks) in the cards until the FIRST telemetry event arrives, then swap to real values.
3. Keep it simple: implement a `_has_data` flag — until first telemetry, cards show «—» (em dash) instead of «0.0 MB/s», plus a small hint text under the header. Avoid fake zeros.
Decision: option 1 (empty-state) is clearest — connected=False → centered hint; connected=True but no data yet → «—» placeholders. Update `set_connection_state` to toggle the empty-state visibility. WaveVisualizer should show an empty/awaiting state too (check its API — maybe `set_data([])` or a `show_empty` flag).
Tests: `tests/test_statistics_page.py` — construct StatisticsPage (needs controller mocks), assert initial state shows empty-hint (not zeros), set_connection_state(True) hides it, first telemetry event populates values.

## Constraints
- Flet 0.86.1: verify any new control kwargs via inspect.signature (.venv). Dropdown=on_select, Button=content.
- black + isort line 120; flake8 clean.
- tests/conftest.py — DO NOT touch.
- Do NOT commit. Full suite must stay green (currently 743).

## Verification
1. Targeted tests pass.
2. `.venv/Scripts/python.exe -m pytest -q --no-cov` — FULL green.
3. black/isort clean.
