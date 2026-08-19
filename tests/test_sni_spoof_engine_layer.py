"""Tests for the typed SNI-spoof engine layer (models, ABC, factory, wrapper).

Pure structural tests — they do NOT touch packet injection or sockets, and do
not modify any existing test logic. The WinDivert engine here is exercised only
as a thin supervision wrapper (its real loop delegates to FakeTcpInjector, which
is covered by tests/test_sni_spoof_core.py).
"""

import pytest

from src.services.sni_spoof.engines import BaseSpoofEngine, WinDivertWrongSeqEngine
from src.services.sni_spoof.factory import SpoofEngineFactory
from src.services.sni_spoof.models import EngineHealthStatus, SpoofEngineConfig, SpoofMethod


def _cfg(**over) -> SpoofEngineConfig:
    base = dict(
        fake_sni="chatgpt.com",
        connect_ip="185.193.30.94",
        connect_port=443,
        listen_host="127.0.0.1",
        listen_port=40443,
    )
    base.update(over)
    return SpoofEngineConfig(**base)


class TestTypedModels:
    def test_config_defaults(self):
        cfg = _cfg()
        assert cfg.method is SpoofMethod.WRONG_SEQ
        assert cfg.connect_port == 443
        assert cfg.listen_port == 40443

    def test_config_frozen(self):
        cfg = _cfg()
        with pytest.raises(Exception):
            cfg.connect_ip = "8.8.8.8"  # frozen dataclass

    def test_health_status_defaults(self):
        h = EngineHealthStatus()
        assert h.running is False
        assert h.injected_connections == 0
        assert h.last_error is None

    def test_method_enum_values(self):
        assert SpoofMethod.WRONG_SEQ == "wrong_seq"


class TestEngineInterface:
    def test_abc_not_instantiable(self):
        with pytest.raises(TypeError):
            BaseSpoofEngine(_cfg())  # abstract

    def test_concrete_implements_abc(self):
        eng = WinDivertWrongSeqEngine(_cfg())
        assert isinstance(eng, BaseSpoofEngine)
        assert eng.config.method is SpoofMethod.WRONG_SEQ

    def test_engine_rejects_wrong_method(self):
        # only wrong_seq exists; an unknown method value must be rejected by the
        # factory/engine (SpoofMethod(...) raises for unknown values)
        with pytest.raises(ValueError):
            SpoofMethod("fake-method")


class TestFactory:
    def test_factory_creates_wrong_seq_engine(self):
        eng = SpoofEngineFactory.create(_cfg())
        assert isinstance(eng, WinDivertWrongSeqEngine)

    def test_factory_rejects_unknown_method(self):
        with pytest.raises(ValueError):
            SpoofEngineFactory.create(_cfg(method="fake-method"))  # type: ignore[arg-type]

    def test_engine_health_snapshot(self):
        eng = SpoofEngineFactory.create(_cfg())
        assert eng.health().method is SpoofMethod.WRONG_SEQ
        assert eng.health().running is False
