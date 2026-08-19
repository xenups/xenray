"""Factory for SNI-spoof engines.

Selects and constructs a ``BaseSpoofEngine`` from a typed ``SpoofEngineConfig``.
Currently only the WinDivert + wrong_seq engine exists; future engines (e.g. a
TLS-native variant) register here without touching the listener's packet logic.
"""

from __future__ import annotations

from src.services.sni_spoof.engines.base import BaseSpoofEngine
from src.services.sni_spoof.engines.windivert_wrong_seq import WinDivertWrongSeqEngine
from src.services.sni_spoof.models import SpoofEngineConfig, SpoofMethod


class SpoofEngineFactory:
    """Constructs the engine matching the configured ``SpoofMethod``."""

    @staticmethod
    def create(config: SpoofEngineConfig) -> BaseSpoofEngine:
        if config.method is SpoofMethod.WRONG_SEQ:
            return WinDivertWrongSeqEngine(config)
        raise ValueError(f"Unsupported spoof method: {config.method}")
