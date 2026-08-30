"""Shared enums for analytics modules."""

from __future__ import annotations

from enum import StrEnum


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


__all__ = ["Confidence"]
