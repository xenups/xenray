"""Abstract engine interface for the SNI-spoof layer.

Plugins implement ``BaseSpoofEngine``; the factory picks one by ``SpoofMethod``.
The concrete engine delegates to the proven WinDivert/wrong_seq algorithm in
``tcp_injector.py`` — this ABC only defines the contract, it does not reimplement
any packet/TCP logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.services.sni_spoof.models import EngineHealthStatus, SpoofEngineConfig


class BaseSpoofEngine(ABC):
    """Contract every SNI-spoof engine plugin must satisfy."""

    def __init__(self, config: SpoofEngineConfig):
        self._config = config

    @property
    def config(self) -> SpoofEngineConfig:
        return self._config

    @abstractmethod
    def start(self, fake_injective_connections: dict, on_fail=None) -> bool:
        """Start the packet-capture/injector loop.

        ``fake_injective_connections`` is the shared connection registry the
        listener fills; the engine filters/injects against it.
        Returns True on successful start.
        """

    @abstractmethod
    def stop(self) -> None:
        """Ask the capture loop to exit and release any handle."""

    @abstractmethod
    def health(self) -> EngineHealthStatus:
        """Return a snapshot of current engine state."""

    # A method attribute name kept for parity with the listener's ``inject``
    # call-site when delegating a captured packet. Engines that only supervise
    # the underlying injector may leave it as a thin forward.
    @abstractmethod
    def on_packet(self, packet) -> None:
        """Handle a captured packet (thin forward to the underlying injector)."""
