from enum import Enum


class JobState(str, Enum):
    PENDING = "pending"
    UVR = "uvr"
    SVC = "svc"
    MIXING = "mixing"
    EXPORTING = "exporting"
    DONE = "done"
    FAILED = "failed"
