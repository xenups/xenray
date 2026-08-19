"""Typed models for the SNI-spoof engine layer.

Replaces raw-dict plumbing with explicit dataclasses and an Enum, without
changing any runtime behaviour (the underlying WinDivert/wrong_seq algorithm in
``tcp_injector.py`` is untouched — this module only describes its config/state).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SpoofMethod(str, Enum):
    """The DPI-bypass injection method (only ``wrong_seq`` is implemented)."""

    WRONG_SEQ = "wrong_seq"


@dataclass(frozen=True)
class SpoofEngineConfig:
    """Fully-typed engine configuration (mirrors the persisted SNI settings)."""

    fake_sni: str
    connect_ip: str
    connect_port: int
    listen_host: str
    listen_port: int
    method: SpoofMethod = SpoofMethod.WRONG_SEQ
    data_mode: str = "tls"


@dataclass
class EngineHealthStatus:
    """Snapshot of an engine's runtime health/state."""

    running: bool = False
    method: SpoofMethod = SpoofMethod.WRONG_SEQ
    injected_connections: int = 0
    last_error: Optional[str] = None
