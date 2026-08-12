# طراحی بازسازی ماژول مانیتورینگ و اتوریکانکت (XenRay)

برنچ: `fix/auto-reconnect-v` (از `origin/main`، تمیز)

## ۱. مشکلات فعلی (ریشهها)

1. **پسیو مانیتور فقط Xray را تیل میکند** — اما در حالت VPN با TUN سینگباکس، Xray فقط پراکسی است و خطاهای حیاتی (کرش TUN، خطای strict_route، از دست رفتن رابط) در لاگ `singbox.log` میآید. پس پسیو «شرایط را درست نمیفهمد».
2. **کلمههای کلیدی پسیو با `loglevel: warning` ناسازگار است** — `ERROR_KEYWORDS` پر از رشتههایی است که Xray فقط در `debug/info` مینویسد (مثل `failed to get`, `wsarecv:`). در `warning` این خطها اصلاً ظاهر نمیشوند → پسیو عملاً کور است.
3. **اکتیو مانیتور «متریک» واقعی ندارد** — `XrayProcessProvider` فقط `process_alive` را برمیگرداند؛ `uplink/downlink` همیشه `0` است، بنابراین `_evaluate_stall_condition` همیشه `delta=0` → همیشه «stalled» → هیجان کاذب یا نادیدهگرفتن واقعی. `_verify_connectivity` هم همیشه از پورت SOCKS ثابت استفاده میکند.
4. **اتوریکانکت سشنآگاه نیست** — `connect_fn(file_path, mode)` فقط؛ `current_connection` (با `file`/`mode`/پورتها) به تلاش reconnect نمیرسد؛ سشن قدیمی پس از `connect()` باطل میشود و رویدادها گم میشوند؛ `reconnecting` قبل از bump سشن ارسال میشود.
5. **کراش هسته (CoreHealthMonitor) فقط FSM را به ERROR میبرد** — تلاش reconnect نمیکند و با مانیتورینگ هماهنگ نیست؛ پس کراش sing-box در VPN هیچ recovery ندارد.
6. **تستهای خودکار reconnect وجود ندارند** — قرارداد سشن/رویداد مستند نیست.

## ۲. هدف (فلسفه)

- **مانیتورها فقط سیگنال (واقعیت) منتشر میکنند**؛ `ConnectionManager` تنها مرجع رویداد و سیاست است.
- **پسیو = تشخیص قطع/خطای پروتکل** از لاگ هر دو هسته (Xray و sing-box) با کلمههای کلیدی همراستای `loglevel: warning`.
- **اکتیو = تشخیص توقف/قطع واقعی** با پروب TCP/HTTP واقعی (نه دلتای صفر).
- **FSM و EventBus = منبع حقیقت** برای وضعیت اتصال؛ همه اجزا به آن گوش میدهند.
- **ریکانکت = سشن تازه**؛ `session_id` جدید، رویداد `connected` جدید، بدون رویدادهای stale.

## ۳. معماری جدید

### ۳.۱ `signals.py`
```python
class MonitorSignal(Enum):
    PASSIVE_FAILURE      # خطای لاگ هسته (Xray یا sing-box)
    ACTIVE_LOST          # قطع واقعی (پروب شکست خورد)
    ACTIVE_RESTORED      # بازیابی
    ACTIVE_DEGRADED      # هشدار نرم
    ENGINE_CRASHED       # کراش هسته (پابلیش روی EVENT_CORE_CRASHED)
```

### ۳.۲ `passive_log_monitor.py` — بازسازی
- `__init__(on_failure_callback, log_files: list[str])` — **چند فایل** (Xray + sing-box).
- **یک تیلتر تکی** برای همهی فایلها (یک حلقه، stat هر دو فایل) — نه یک ترد per-file.
- فقط وقتی سایز تغییر کرده بخواند (`stat` ارزان؛ خواندن فقط بایتهای جدید از آخر فایل؛ هیچگاه کل فایل خوانده نمیشود).
- `_is_file_rotated` برای هر دو پلتفرم.
- `ERROR_KEYWORDS` بازنویسی با الگوهای واقعی `warning` Xray و sing-box:
  - Xray: `connection refused`, `connection reset`, `i/o timeout`, `read timeout`, `handshake failed`, `all retry attempts failed`, `failed to handler`, `transport closed`, `no such host`, `no route to host`, `network is unreachable`, `wsarecv:` (فقط debug است → حذف یا به info منتقل).
  - sing-box: `fatal`, `panic`, `failed to start`, `error creating`, `permission denied`, `address already in use`, `no such device`, `interface not found`, `route`, `tun`.
- `DNS_FALLBACK_KEYWORDS` حفظ (اینها خطا نیستند).
- `pause(duration)`/`resume()` با `_paused_until` برای backoff حفظ.
- سیگنال یکسان: `PASSIVE_FAILURE` (با متادیتا: `source` = xray|singbox).

### ۳.۳ `active_connectivity_monitor.py` — بازسازی
- **حذف** `XrayProcessProvider`/دلتای بایت (چون متریک واقعی نیست).
- تشخیص جدید:
  1. **سوکت SOCKS واقعی**: `socket.create_connection(("127.0.0.1", socks_port), timeout=2)` → اثبات زندهبودن پراکسی (ارزان؛ یک اتصال).
  2. **پروب HTTP واقعی** از طریق پراکسی: `curl -x socks5h://127.0.0.1:port https://cp.cloudflare.com/generate_204` (یا `requests`).
  3. در VPN: پروب مستقیم به گوگل/کلادفلر (بدون پراکسی) برای «اینترنت قطع است یا فقط تانل؟».
- **بهرهوری منابع (مهم):**
  - **هرگز در هر tick همهی پروبها اجرا نمیشود** — فقط یک پروب در هر `SAMPLE_INTERVAL`؛ و فقط وقتی واقعاً لازم است (مثلاً بعد از N نمونهی مشکوک) پروب کامل HTTP اجرا میشود.
  - **اسکالاژ هوشمند**: سوکت سبک اول (هر ۳-۶ ثانیه)؛ فقط اگر سوکت شکست خورد یا تعداد نمونههای مشکوک به حد آستانه رسید، پروب HTTP سنگین اجرا شود. (یعنی اکثر اوقات فقط یک `connect()` ارزان داریم.)
  - **بدون polling اضافی**: اگر ترافیک جریان دارد (از رویداد/FSM بدانیم CONNECTED است)، پروب نمیگیریم.
  - **هیچ سوکت/پروبی در ترد UI** — همه در ترد مانیتور (daemon) با timeout کوتاه (≤5s).
- `SAMPLE_INTERVAL`, `REQUIRED_SAMPLES`, `WARNING_SAMPLES`, `MAX_STALL_SAMPLES` حفظ.
- `_verify_connectivity(port)` پارامتری.
- سیگنالها: `ACTIVE_LOST/RESTORED/DEGRADED`.

### ۳.۴ `auto_reconnect_service.py` — بازسازی
- `connect_fn(file_path, mode, connection_info: dict)` — کانتکست کامل.
- **ریکانکت با سشن تازه**: `ConnectionManager._reconnect_internal` یک `connect()` جدید صدا میزند که `_session_id` را افزایش میدهد و موتور قبلی را teardown میکند.
- `_attempt_reconnect` بعد از موفقیت، **رویداد `reconnecting` را قبل از فراخوانی `connect()`** منتشر میکند (نه بعد)، تا UI درست واکنش نشان دهد؛ بعد از موفقیت، `connected` از سشن جدید میآید (نه `reconnected` استایل).
- شکست reconnect: `reconnect_failed` با `reason` روی همان سشن (هنوز معتبر).
- backoff: `STABILIZATION_BUFFER` (2s) + `max_attempts`/فاصله تصاعدی (اختیاری).
- **بهرهوری منابع:**
  - **بدون حلقهی polling اضافی**: reconnect فقط وقتی سیگنال شکست از مانیتور میرسد اجرا میشود (رویداد-محور، نه تایمر).
  - **حداکثر ۱ تلاش در هر دوره**: `STABILIZATION_BUFFER` قبل از تلاش؛ بعد از هر شکست، backoff تا `MAX_COOLDOWN_SECONDS` (۵ دقیقه) — جلوگیری از طوفان reconnect.
  - **بررسی اینترنت سبک**: `socket.create_connection((8.8.8.8, 53), timeout=2)` بهجای curl/سنگین (فقط قبل از تلاش reconnect).
  - **هیچ چیز روی ترد UI** — همه در ترد مانیتور (daemon).

### ۳.۵ `ConnectionManager` — هماهنگی FSM/EventBus
- `_handle_signal`: PASSIVE_FAILURE → `handle_failure`؛ ACTIVE_LOST → `connectivity_lost` + `handle_failure`؛ DEGRADED/RESTORED → رویدادها.
- `_handle_core_crash`: (فعلاً) hard-reset + `disconnected`؛ در فاز ۲ میتوان reconnect برای کراش sing-box اضافه کرد.
- `_reconnect_internal(file_path, mode, connection_info)` → `connect(...)` (سشن تازه).
- `disconnect()` بدون تغییر (ترمینال).

### ۳.۶ `CoreHealthMonitor`
- بدون تغییر در این فاز (کراش → EVENT_CORE_CRASHED → hard-reset). هماهنگی reconnect کراش در فاز ۲ (اختیاری).

## ۴. ترتیب پیادهسازی (TDD)

1. بازسازی `signals.py` (اضافه کردن ENGINE_CRASHED).
2. بازسازی `passive_log_monitor.py` (چند فایل + کلمههای کلیدی درست + تست).
3. بازسازی `active_connectivity_monitor.py` (سوکت/پروب + تست).
4. بازسازی `auto_reconnect_service.py` (سشن + `reconnecting` قبل از connect + تست).
5. بهروزرسانی `ConnectionManager` (پاس دادن کانتکست + سیاست سیگنالها).
6. تستهای واحد جدید + اجرای کل سویییت (روی برنچ).
7. فرمت (black/isort) + کامیت (با تأیید شما).

## ۵. ریسکها / نکات

- **سازگاری با tests موجود**: `test_passive_log_monitor.py`, `test_core_health_monitor.py`, `test_monitoring_service.py` باید آپدیت شوند (امضاها).
- **تستهای اکتیو** نیاز به موک سوکت/پروب دارند (بدون شبکه واقعی).
- **Windows**: تیل فایل با `ctime`؛ `socket.create_connection` با timeout کوتاه؛ `curl` موجود است.
- **رگرسیون**: ۲ تست شکستخورده از قبل (QR و LAN) روی main هم fail هستند — خارج از scope.

## ۵.۱ بهرهوری منابع (خلاصه)

| جزء | هزینهی پایه | فرکانس | کاهش |
|---|---|---|---|
| پسیو (تیل) | `stat` دو فایل | هر ۱-۲ ثانیه | فقط خواندن بایتهای جدید؛ یک ترد تکی |
| اکتیو (سوکت) | ۱ `connect()` به 127.0.0.1 | هر ۳-۶ ثانیه | فقط وقتی CONNECTED |
| اکتیو (پروب HTTP) | ۱ درخواست curl/requests | فقط بعد از N نمونهی مشکوک | اسکالاژ؛ نادر |
| ریکانکت | ۱ بررسی اینترنت سبک | فقط قبل از تلاش reconnect | رویداد-محور + backoff تا ۵ دقیقه |
| کراش هسته | ۱ بررسی PID | هر ۱ ثانیه | فقط CONNECTED/STARTING/PREPARING |

**قانون طلایی**: در حالت عادی (اتصال سالم) سیستم فقط ۲ stat فایل در ثانیه + ۱ اتصال سوکت سبک هر چند ثانیه مصرف میکند — نه چیزی بیشتر.

## ۶. معیار Done

- [ ] پسیو هر دو هسته (Xray + sing-box) را مانیتور میکند.
- [ ] اکتیو با سوکت/پروب واقعی کار میکند (بدون دلتای صفر).
- [ ] ریکانکت سشن تازه + رویداد `reconnecting` قبل از connect.
- [ ] FSM/EventBus محور؛ کراش هسته → hard-reset.
- [ ] تستهای جدید سبز + کل سویییت سبز (بهجز ۲ باگ قبلی).
- [ ] black/isort تمیز؛ کامیت با تأیید شما.
