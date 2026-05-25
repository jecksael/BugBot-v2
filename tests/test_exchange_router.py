from __future__ import annotations

from types import SimpleNamespace

import pytest

from bugbot.adapters import exchange as exchange_mod


class DummyExchange:
    def __init__(self, params: dict[str, object]):
        self.params = params
        self.id = "dummy"


def _make_settings(**overrides):
    defaults = {
        "exchanges": ["dummy"],
        "API_KEY": None,
        "API_SECRET": None,
        "api_key": None,
        "api_secret": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_from_env_uses_exchange_from_settings(monkeypatch):
    captured = {}

    class Bitstamp(DummyExchange):
        def __init__(self, params: dict[str, object]):
            captured["params"] = params
            super().__init__(params)
            self.id = "bitstamp"

    settings = _make_settings(exchanges=["Bitstamp"], API_KEY="KEY", API_SECRET="SECRET")

    monkeypatch.setattr(exchange_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(exchange_mod.ccxt, "bitstamp", Bitstamp)

    router = exchange_mod.ExchangeRouter.from_env()

    assert isinstance(router.raw, Bitstamp)
    assert captured["params"] == {
        "enableRateLimit": True,
        "apiKey": "KEY",
        "secret": "SECRET",
    }


def test_from_env_falls_back_when_no_exchanges(monkeypatch):
    captured = {}

    class Kraken(DummyExchange):
        def __init__(self, params: dict[str, object]):
            captured["params"] = params
            super().__init__(params)
            self.id = "kraken"

    settings = _make_settings(exchanges=[])

    monkeypatch.setattr(exchange_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(exchange_mod.ccxt, "kraken", Kraken)

    router = exchange_mod.ExchangeRouter.from_env()

    assert isinstance(router.raw, Kraken)
    assert captured["params"] == {"enableRateLimit": True}


def test_from_env_raises_on_unknown_exchange(monkeypatch):
    settings = _make_settings(exchanges=["does-not-exist"])

    monkeypatch.setattr(exchange_mod, "get_settings", lambda: settings)

    with pytest.raises(ValueError):
        exchange_mod.ExchangeRouter.from_env()
