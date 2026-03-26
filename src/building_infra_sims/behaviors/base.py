"""Value simulation behaviors for generating realistic sensor data."""

import math
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class ValueBehavior(ABC):
    """Base class for simulated value update patterns."""

    @abstractmethod
    def update(self, elapsed: float) -> Any:
        """Return a new value. `elapsed` is seconds since simulation start."""
        ...


class StaticValue(ValueBehavior):
    """Constant value that never changes."""

    def __init__(self, value: Any):
        self.value = value

    def update(self, elapsed: float) -> Any:
        return self.value


class SineWave(ValueBehavior):
    """Oscillates around a center value. Good for temperatures, pressures."""

    def __init__(self, center: float, amplitude: float, period: float = 3600.0):
        self.center = center
        self.amplitude = amplitude
        self.period = period

    def update(self, elapsed: float) -> float:
        return self.center + self.amplitude * math.sin(2 * math.pi * elapsed / self.period)


class RandomWalk(ValueBehavior):
    """Brownian motion within bounds."""

    def __init__(
        self, center: float, step_size: float = 0.5, min_val: float = 0.0, max_val: float = 100.0
    ):
        self.current = center
        self.center = center
        self.step_size = step_size
        self.min_val = min_val
        self.max_val = max_val

    def update(self, elapsed: float) -> float:
        # Drift slightly toward center to prevent extended excursions
        drift = (self.center - self.current) * 0.01
        step = random.gauss(drift, self.step_size)
        self.current = max(self.min_val, min(self.max_val, self.current + step))
        return self.current


class Accumulator(ValueBehavior):
    """Monotonically increasing value (e.g., energy meters)."""

    def __init__(self, initial: float = 0.0, rate_per_second: float = 0.001):
        self.initial = initial
        self.rate = rate_per_second

    def update(self, elapsed: float) -> float:
        return self.initial + self.rate * elapsed


class ScheduleBased(ValueBehavior):
    """Changes value based on time-of-day schedule.

    Schedule is a dict of "HH:MM" -> value, sorted by time.
    The value active is the most recent schedule entry before current time.
    """

    def __init__(self, schedule: dict[str, Any], default: Any = None):
        # Sort schedule entries by time
        self.entries = sorted(schedule.items(), key=lambda x: x[0])
        self.default = default if default is not None else self.entries[0][1]

    def update(self, elapsed: float) -> Any:
        now = datetime.now().strftime("%H:%M")
        active_value = self.default
        for time_str, value in self.entries:
            if now >= time_str:
                active_value = value
            else:
                break
        return active_value


class BinaryToggle(ValueBehavior):
    """Toggles between two values on a cycle."""

    def __init__(
        self,
        on_value: Any = "active",
        off_value: Any = "inactive",
        on_duration: float = 300.0,
        off_duration: float = 300.0,
    ):
        self.on_value = on_value
        self.off_value = off_value
        self.on_duration = on_duration
        self.off_duration = off_duration

    def update(self, elapsed: float) -> Any:
        cycle = self.on_duration + self.off_duration
        position = elapsed % cycle
        return self.on_value if position < self.on_duration else self.off_value


def create_behavior(config: dict[str, Any]) -> ValueBehavior:
    """Factory: create a ValueBehavior from a profile config dict."""
    behavior_type = config["type"]

    if behavior_type == "static":
        return StaticValue(config.get("value", 0))

    elif behavior_type == "sine_wave":
        return SineWave(
            center=config["center"],
            amplitude=config["amplitude"],
            period=config.get("period", 3600.0),
        )

    elif behavior_type == "random_walk":
        return RandomWalk(
            center=config["center"],
            step_size=config.get("step_size", 0.5),
            min_val=config.get("min", 0.0),
            max_val=config.get("max", 100.0),
        )

    elif behavior_type == "accumulator":
        return Accumulator(
            initial=config.get("initial", 0.0),
            rate_per_second=config.get("rate_per_second", 0.001),
        )

    elif behavior_type == "schedule":
        return ScheduleBased(
            schedule=config["schedule"],
            default=config.get("default"),
        )

    elif behavior_type == "binary_toggle":
        return BinaryToggle(
            on_value=config.get("on_value", "active"),
            off_value=config.get("off_value", "inactive"),
            on_duration=config.get("on_duration", 300.0),
            off_duration=config.get("off_duration", 300.0),
        )

    else:
        raise ValueError(f"Unknown behavior type: {behavior_type}")
