"""Adapter protocol + MockAdapter + registry."""

from __future__ import annotations

import pytest

from orch_backend.adapters import (
    AdapterError,
    AdapterRegistry,
    CodingAgentAdapter,
    MockAdapter,
)


async def test_mock_adapter_scripted_reply():
    a = MockAdapter(scripted_outputs=["hello", "world"])
    h = await a.start_session("req_decomposer", "sys", "/tmp")
    r1 = await a.send(h, "msg1")
    r2 = await a.send(h, "msg2")
    assert r1.text == "hello" and r2.text == "world"


async def test_mock_adapter_callback():
    a = MockAdapter(callback=lambda s, m: f"ECHO:{m}")
    h = await a.start_session("req_decomposer", "sys", "/tmp")
    r = await a.send(h, "ping")
    assert r.text == "ECHO:ping"


async def test_mock_adapter_stream_callback_fires_end():
    events = []

    async def cb(evt):
        events.append((evt.kind, evt.text))

    a = MockAdapter(scripted_outputs=["abcdefghij"])
    h = await a.start_session("arch_designer", "sys", "/tmp")
    await a.send(h, "x", stream_cb=cb)
    assert events[-1][0] == "end"
    assert "".join(e[1] for e in events if e[0] == "token") == "abcdefghij"


async def test_mock_adapter_raises_when_no_reply():
    a = MockAdapter()
    h = await a.start_session("req_decomposer", "sys", "/tmp")
    with pytest.raises(AdapterError):
        await a.send(h, "x")


async def test_mock_adapter_records_env_dict_per_send():
    a = MockAdapter(scripted_outputs=["r"])
    h = await a.start_session("arch_designer", "sys", "/tmp", env={"PPE_LANE": "g-1"})
    await a.send(h, "hi")
    assert a.sent[0][2] == {"PPE_LANE": "g-1"}


def test_registry_register_and_get():
    r = AdapterRegistry()
    m = MockAdapter()
    r.register("mock", m)
    assert r.get("mock") is m
    assert "mock" in r.names()


def test_registry_reject_double_register():
    r = AdapterRegistry()
    r.register("mock", MockAdapter())
    with pytest.raises(ValueError):
        r.register("mock", MockAdapter())


def test_mock_adapter_satisfies_protocol():
    a = MockAdapter()
    assert isinstance(a, CodingAgentAdapter)
