from collections.abc import Callable

from aivoice_studio.core.state import JobState

ProgressCallback = Callable[[JobState, int, str], None]


class JobManager:
    def __init__(self, callback: ProgressCallback | None = None) -> None:
        self.callback = callback

    def update(self, state: JobState, progress: int, message: str) -> None:
        if self.callback:
            self.callback(state, progress, message)
