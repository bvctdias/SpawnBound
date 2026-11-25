from dataclasses import dataclass
from enum import IntEnum


class DayPhase(IntEnum):
    DAY = 0
    AFTERNOON = 1
    NIGHT = 2

    @property
    def following(self) -> "DayPhase":
        return DayPhase((self.value + 1) % len(DayPhase))


@dataclass(frozen=True, slots=True)
class Daylight:
    phase: DayPhase
    progress: float

    @property
    def blend(self) -> float:
        t = max(0.0, (self.progress - 0.8) / 0.2)
        return t * t * (3 - 2 * t)

    @classmethod
    def at(cls, seconds: float, durations: tuple[float, float, float]) -> "Daylight":
        elapsed = seconds % sum(durations)
        for phase in DayPhase:
            duration = durations[phase]
            if elapsed < duration:
                return cls(phase, elapsed / duration)
            elapsed -= duration
        return cls(DayPhase.DAY, 0.0)
