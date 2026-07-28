"""Pipeline stage labels — aligned with ``aivoice_studio.core.state.JobState`` values."""

from __future__ import annotations

from enum import Enum


class Stage(str, Enum):
    PENDING = "pending"
    UVR = "uvr"
    SVC = "svc"
    MIXING = "mixing"
    EXPORTING = "exporting"
    DONE = "done"
    FAILED = "failed"

    @classmethod
    def from_value(cls, value: object) -> Stage:
        if isinstance(value, cls):
            return value
        text = getattr(value, "value", value)
        try:
            return cls(str(text))
        except ValueError:
            return cls.PENDING
