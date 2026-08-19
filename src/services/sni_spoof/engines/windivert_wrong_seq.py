"""WinDivert + wrong_seq SNI-spoof engine.

This is a thin, typed wrapper around the proven ``FakeTcpInjector``
(``tcp_injector.py``). It does NOT reimplement any packet/TCP logic — the
sequence-tracking, fake-ClientHello injection and relay behaviour are exactly
those of ``FakeTcpInjector``. Zero functional regression by construction.
"""

from __future__ import annotations

from typing import Optional

from src.services.sni_spoof.engines.base import BaseSpoofEngine
from src.services.sni_spoof.models import EngineHealthStatus, SpoofEngineConfig, SpoofMethod
from src.services.sni_spoof.tcp_injector import FakeTcpInjector


class WinDivertWrongSeqEngine(BaseSpoofEngine):
    """Engine that supervises a ``FakeTcpInjector`` (wrong_seq method)."""

    def __init__(self, config: SpoofEngineConfig):
        if config.method is not SpoofMethod.WRONG_SEQ:
            raise ValueError(f"Unsupported method for this engine: {config.method}")
        super().__init__(config)
        self._injector: Optional[FakeTcpInjector] = None
        self._started = False
        self._conns: dict = {}
        self._last_error: Optional[str] = None

    def start(self, fake_injective_connections: dict, on_fail=None) -> bool:
        # NOTE: the actual WinDivert filter string + open must be constructed by
        # the listener (it owns the physical-NIC detection + filter). start()
        # here only records the shared registry and marks intent; the listener
        # finalises via bind_injector() once the filter is known.
        self._conns = fake_injective_connections
        self._started = True
        return True

    def bind_injector(self, injector: FakeTcpInjector, on_fail=None) -> None:
        """Attach the concrete injector built by the listener (owns the filter)."""
        self._injector = injector
        if on_fail is not None:
            # wrap so the error path also updates our health
            orig = on_fail

            def _on_fail():
                self._last_error = "corrective"
                orig()

            self._on_fail_wrapped = _on_fail
        else:
            self._on_fail_wrapped = None

    def run_loop(self, on_fail=None) -> None:
        """Blocking capture loop — delegates straight to the injector's run()."""
        if self._injector is None:
            return
        self._injector.run(on_fail=on_fail)

    def stop(self) -> None:
        if self._injector is not None:
            self._injector.stop()
        self._started = False

    def health(self) -> EngineHealthStatus:
        return EngineHealthStatus(
            running=self._started,
            method=SpoofMethod.WRONG_SEQ,
            injected_connections=len(self._conns),
            last_error=self._last_error,
        )

    def on_packet(self, packet) -> None:
        if self._injector is not None:
            self._injector.inject(packet)
