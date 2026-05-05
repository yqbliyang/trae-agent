"""Adapter registry — name → instance."""

from __future__ import annotations

from typing import Iterable

from orch_backend.adapters.base import CodingAgentAdapter


class AdapterRegistry:
    """Phase 1: just a dict lookup + list for UI `/adapters`."""

    def __init__(self) -> None:
        self._adapters: dict[str, CodingAgentAdapter] = {}

    def register(self, name: str, adapter: CodingAgentAdapter) -> None:
        if name in self._adapters:
            raise ValueError(f"adapter already registered: {name}")
        self._adapters[name] = adapter

    def get(self, name: str) -> CodingAgentAdapter:
        if name not in self._adapters:
            raise KeyError(f"unknown adapter: {name}")
        return self._adapters[name]

    def names(self) -> list[str]:
        return sorted(self._adapters.keys())

    def all(self) -> Iterable[tuple[str, CodingAgentAdapter]]:
        return list(self._adapters.items())
