from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from spawnbound.domain.coordinates import GridPos


JUMP_LIFT = (0, 0, 4, 8, 9, 6, 1, 0)


class MotionKind(str, Enum):
    IDLE = "idle"
    WALK = "walk"
    STEP_UP = "step_up"
    STEP_DOWN = "step_down"
    JUMP = "jump"
    STRIKE = "strike"
    SWIM = "swim"
    HURT = "hurt"


@dataclass(frozen=True, slots=True)
class PlayerPose:
    motion: MotionKind
    facing: GridPos
    elapsed: float = 0.0
    progress: float = 0.0


@dataclass(frozen=True, slots=True)
class FrameSequence:
    frame_count: int
    fps: float = 8.0
    loop: bool = True

    def __post_init__(self) -> None:
        if self.frame_count < 1 or self.fps <= 0:
            raise ValueError("animation requires frames and a positive frame rate")

    def frame_index(self, pose: PlayerPose) -> int:
        if pose.motion in (MotionKind.STEP_UP, MotionKind.STEP_DOWN, MotionKind.JUMP, MotionKind.STRIKE,
                           MotionKind.HURT):
            return min(self.frame_count - 1, int(max(0.0, min(1.0, pose.progress)) * self.frame_count))
        index = int(max(0.0, pose.elapsed) * self.fps)
        return index % self.frame_count if self.loop else min(index, self.frame_count - 1)
