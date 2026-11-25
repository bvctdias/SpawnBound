from __future__ import annotations

import math
from collections import deque


class FramePacer:
    WINDOW = 120
    KEEP_MARGIN = 1.15
    FASTER_MARGIN = 1.4
    FASTER_AFTER = 3
    UPLOAD = .0015
    CATCH_UP = .1
    INITIAL_COST = .008

    def __init__(self, max_fps: int = 144, refresh_hz: float = 60.0) -> None:
        self.max_fps = max_fps
        self.refresh_hz = refresh_hz if refresh_hz > 0 else 60.0
        self.vsync = False
        self.upload = self.UPLOAD
        self._costs: deque[float] = deque(maxlen=self.WINDOW)
        self._intervals: deque[float] = deque(maxlen=self.WINDOW)
        self._faster_votes = 0
        self._lag = 0.0
        self.refreshes = self._least_refreshes(self.INITIAL_COST, self.FASTER_MARGIN)
        self.spare = self.period / 4

    @property
    def period(self) -> float:
        return self.refreshes / self.refresh_hz

    def set_refresh(self, hz: float) -> None:
        if hz > 0 and hz != self.refresh_hz:
            self.refresh_hz = hz
            if len(self._costs) >= 30:
                self._set_refreshes(self._least_refreshes(self._p90(), self.KEEP_MARGIN))
            else:
                self._set_refreshes(self._least_refreshes(self.INITIAL_COST, self.FASTER_MARGIN))
            self._faster_votes = 0

    def record(self, cost: float, interval: float) -> None:
        self._costs.append(max(0., cost) + self.upload)
        self._intervals.append(max(0., interval))

    def frame_time(self, interval: float) -> float:
        period = self.period
        self._lag += interval - period
        if abs(self._lag) > 2 * period:
            elapsed, self._lag = period + self._lag, 0.0
        else:
            paid = self._lag * self.CATCH_UP
            elapsed = period + paid
            self._lag -= paid
        return max(0.0, elapsed)

    def update(self) -> None:
        if self.vsync and len(self._intervals) >= 30:
            # Intervalos muito menores que o período indicam que o driver ignorou a sincronização vertical.
            if sorted(self._intervals)[len(self._intervals) // 2] < .7 * self.period:
                self.vsync = False
        if len(self._costs) < 30:
            return
        cost = self._p90()
        if self._least_refreshes(cost, self.KEEP_MARGIN) > self.refreshes:
            self._set_refreshes(self._least_refreshes(cost, self.KEEP_MARGIN))
            self._faster_votes = 0
        elif self._least_refreshes(cost, self.FASTER_MARGIN) < self.refreshes:
            self._faster_votes += 1
            # Exigir folga por vários ciclos evita oscilar entre duas taxas de quadros.
            if self._faster_votes >= self.FASTER_AFTER:
                self._set_refreshes(self._least_refreshes(cost, self.FASTER_MARGIN))
                self._faster_votes = 0
        else:
            self._faster_votes = 0
        self.spare = max(0., self.period - cost)

    def _set_refreshes(self, refreshes: int) -> None:
        if refreshes != self.refreshes:
            self.refreshes = refreshes
            self._intervals.clear()

    def _p90(self) -> float:
        costs = sorted(self._costs)
        return costs[int(.9 * (len(costs) - 1))]

    def _least_refreshes(self, cost: float, margin: float) -> int:
        cap = math.ceil(self.refresh_hz / self.max_fps - 1e-9)
        need = math.ceil(cost * margin * self.refresh_hz - 1e-9)
        return max(1, cap, need)
