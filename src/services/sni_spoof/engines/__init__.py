"""SNI-spoof engine plugins."""

from src.services.sni_spoof.engines.base import BaseSpoofEngine
from src.services.sni_spoof.engines.windivert_wrong_seq import WinDivertWrongSeqEngine

__all__ = ["BaseSpoofEngine", "WinDivertWrongSeqEngine"]
