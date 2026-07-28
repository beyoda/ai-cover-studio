"""Cover-layer job context (not the Pipeline ``core.context.JobContext``).

Holds a resolved request plus the service-assigned ``job_id``.
The adapter maps this (or ``CoverRequest``) onto the existing Pipeline job.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from aivoice_studio.cover.domain.request import CoverRequest


@dataclass(slots=True)
class JobContext:
    request: CoverRequest
    job_id: str

    @classmethod
    def from_request(cls, request: CoverRequest, job_id: str | None = None) -> JobContext:
        return cls(request=request, job_id=job_id or uuid4().hex[:12])
