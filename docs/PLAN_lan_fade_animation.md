# پلن: انیمیشن fade سبز برای دکمه LAN در سایدبار

## هدف
وقتی LAN sharing فعال میشود، دکمهی LAN در سایدبار باید مثل روشن شدن چراغ/ایستگاه رادیویی با **fade نرم** سبز شود — نه تغییر رنگ فوری.

## وضعیت فعلی
- `NavSidebar._apply_lan_styles(is_active)` رنگها را **فوری** ست میکند: `_lan_icon.color`, `_lan_btn.bgcolor`, `_lan_btn.border`, `_lan_btn.shadow` و `update()`.
- فراخوانیها: `update_lan_button(allow_lan)` از `LanSharingPage` (خط ۲۳۲) + `set_active_tab`.
- `NavigationController.get_lan_button_style()` توکنهای سبز (#4ADE80 / #10B981) را برمیگرداند وقتی `allow_lan=True`.

## راهحل (fade سبز)
۱. **ایندیکاتور چراغ**: یک `ft.Container` دایرهای کوچک کنار/روی دکمه LAN اضافه میشود که در حالت OFF خاکستری/شفاف است و با `animate_opacity` (GPU، ~600-800ms) به سبز روشن fade میشود.
   - ساختار: `self._lan_indicator = ft.Container(width=6, height=6, border_radius=3, bgcolor="#4ADE80", opacity=0.0, animate_opacity=ft.Animation(700, CURVE_EASE_OUT))`
   - `update_lan_button(True)` → `opacity=1.0` (روشن) + سایهی سبز نرم روی دکمه (glow)
   - `update_lan_button(False)` → `opacity=0.15` (خاموش)

۲. **glow روی خود دکمه**: `_lan_btn.shadow` با `animate_shadow` یا ست کردن `BoxShadow` سبز با `blur` — fade نرم دور دکمه.

۳. **ترتیب**: `_apply_lan_styles` → `self._lan_indicator.update()` + `self._lan_btn.update()` — فقط این دو کنترل (بدون re-render کل سایدبار).

## فایلهای درگیر
- `src/ui/components/common/nav_sidebar.py` — ایندیکاتور + `_apply_lan_styles` (فقط رنگ/opacity را عوض کند، با animate)
- `src/ui/controllers/navigation_controller.py` — (اختیاری) `LanButtonStyle` با `indicator_opacity`/`glow_shadow` برای OFF/ON

## تست
- تست واحد: ساخت `NavSidebar` با `allow_lan=True/False` → `_lan_indicator.opacity` درست است
- تست کل: ۶۷۱ تست موجود باید پاس بمانند

## معیار Done
- دکمهی LAN با fade نرم (نه snap) سبز میشود
- خاموش شدن هم fade دارد
- بدون re-render کل سایدبار (فقط indicator + button)
- تستها سبز
