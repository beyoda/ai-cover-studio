"""Non-intrusive pipeline profiling (timing / metrics / command capture).

Does not change pipeline business results; only observes and records.
"""

from aivoice_studio.profiling.session import get_profiler, Profiler

__all__ = ["get_profiler", "Profiler"]
