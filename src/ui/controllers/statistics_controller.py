"""Statistics Controller - Catmull-Rom spline wave math, peak speed calculations, and traffic parsing."""

from __future__ import annotations

import math
from typing import List, NamedTuple, Optional


class TrafficStatsPayload(NamedTuple):
    """Calculated traffic statistics payload."""

    rate_str: str
    dl_speed_str: str
    ul_speed_str: str
    download_str: str
    upload_str: str
    total_transfer_str: str
    peak_speed_str: str
    dl_heights: List[float]
    ul_heights: List[float]
    activity: float

    @property
    def dl_text(self) -> str:
        return self.dl_speed_str

    @property
    def ul_text(self) -> str:
        return self.ul_speed_str


class StatisticsController:
    """Controller handling network history queues, wave visualizer splines, and rate formatting."""

    def __init__(self, history_size: int = 16, num_bars: int = 32) -> None:
        self._history_size = history_size
        self._num_bars = num_bars
        self._dl_history = [0.0] * history_size
        self._ul_history = [0.0] * history_size
        self._peak_bps = 0.0

    def reset(self) -> None:
        """Reset history arrays and peak counters."""
        self._dl_history = [0.0] * self._history_size
        self._ul_history = [0.0] * self._history_size
        self._peak_bps = 0.0

    @staticmethod
    def parse_size_to_bytes(size_str: str) -> float:
        """Parse size string (e.g. '12.4 MB', '500 KB', '1.2 GB', '1024 B') into bytes float."""
        if not size_str:
            return 0.0
        try:
            parts = size_str.strip().split()
            if not parts:
                return 0.0
            val = float(parts[0])
            unit = parts[1].upper() if len(parts) > 1 else "B"
            if "GB" in unit:
                return val * 1024.0 * 1024.0 * 1024.0
            elif "MB" in unit:
                return val * 1024.0 * 1024.0
            elif "KB" in unit:
                return val * 1024.0
            else:
                return val
        except Exception:
            return 0.0

    @staticmethod
    def format_bytes(bytes_val: float) -> str:
        """Format bytes into human-readable data transfer string."""
        if bytes_val < 1024:
            return f"{bytes_val:.0f} B"
        elif bytes_val < 1024 * 1024:
            return f"{(bytes_val / 1024.0):.1f} KB"
        elif bytes_val < 1024 * 1024 * 1024:
            return f"{(bytes_val / (1024.0 * 1024.0)):.1f} MB"
        else:
            return f"{(bytes_val / (1024.0 * 1024.0 * 1024.0)):.2f} GB"

    @staticmethod
    def compute_smooth_wave_heights(
        history: List[float],
        num_output: int = 32,
        min_h: float = 6.0,
        max_h: float = 160.0,
    ) -> List[float]:
        """Compute smooth Catmull-Rom spline wave heights across num_output wave bars."""
        n = len(history)
        if n == 0:
            return [min_h] * num_output

        max_val = max(max(history), 1024.0 * 1024.0)
        norm = [min(1.0, max(0.0, float(v) / max_val)) for v in history]

        heights = []
        for i in range(num_output):
            pos = (i / max(1, num_output - 1)) * (n - 1)
            idx = int(pos)
            t_val = pos - idx

            p0 = norm[max(0, idx - 1)]
            p1 = norm[idx]
            p2 = norm[min(n - 1, idx + 1)]
            p3 = norm[min(n - 1, idx + 2)]

            val = 0.5 * (
                (2 * p1)
                + (-p0 + p2) * t_val
                + (2 * p0 - 5 * p1 + 4 * p2 - p3) * (t_val**2)
                + (-p0 + 3 * p1 - 3 * p2 + p3) * (t_val**3)
            )
            val = max(0.0, min(1.0, val))

            idle_wave = 0.035 * (math.sin(i * 0.45) + 1.0)
            final_pct = max(val, idle_wave) if max(history) < 100.0 else val

            h = max(min_h, final_pct * max_h)
            heights.append(round(h, 2))

        return heights

    def process_stats(
        self,
        is_connected: bool,
        download_bps: float = 0.0,
        upload_bps: float = 0.0,
        download_str: str = "0.0 MB",
        upload_str: str = "0.0 MB",
        total_bps: float = 0.0,
        rate_str: str = "0.0 MB/s",
        speed_text: Optional[str] = None,
        download_total: Optional[str] = None,
        upload_total: Optional[str] = None,
    ) -> TrafficStatsPayload:
        """Process incoming throughput rates and return calculated UI payloads."""
        dl_text = speed_text if speed_text is not None else f"{(download_bps / (1024.0 * 1024.0)):.1f} MB/s"
        ul_speed_kb = upload_bps / 1024.0
        if ul_speed_kb < 1024.0:
            ul_text = f"{ul_speed_kb:.1f} KB/s"
        else:
            ul_text = f"{(ul_speed_kb / 1024.0):.1f} MB/s"

        u_str = upload_total if upload_total is not None else upload_str
        d_str = download_total if download_total is not None else download_str

        cur_max = max(float(download_bps), float(upload_bps))
        if cur_max > self._peak_bps:
            self._peak_bps = cur_max

        peak_kb = self._peak_bps / 1024.0
        peak_speed_str = f"{peak_kb:.1f} KB/s" if peak_kb < 1024.0 else f"{(peak_kb / 1024.0):.1f} MB/s"

        dl_bytes = self.parse_size_to_bytes(d_str)
        ul_bytes = self.parse_size_to_bytes(u_str)
        total_transfer_str = self.format_bytes(dl_bytes + ul_bytes)

        self._dl_history.pop(0)
        self._dl_history.append(download_bps if is_connected else 0.0)
        self._ul_history.pop(0)
        self._ul_history.append(upload_bps if is_connected else 0.0)

        dl_heights = self.compute_smooth_wave_heights(self._dl_history, num_output=self._num_bars)
        ul_heights = self.compute_smooth_wave_heights(self._ul_history, num_output=self._num_bars)

        # Compute activity normalized between 0.0 and 1.0
        eff_total = total_bps if total_bps > 0 else (download_bps + upload_bps)
        activity = min(1.0, eff_total / (10.0 * 1024.0 * 1024.0))

        return TrafficStatsPayload(
            rate_str=rate_str,
            dl_speed_str=dl_text,
            ul_speed_str=ul_text,
            download_str=d_str,
            upload_str=u_str,
            total_transfer_str=total_transfer_str,
            peak_speed_str=peak_speed_str,
            dl_heights=dl_heights,
            ul_heights=ul_heights,
            activity=activity,
        )
