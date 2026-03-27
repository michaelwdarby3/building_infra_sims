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


class PhasedSineWave(SineWave):
    """Sine wave with a phase offset. For 3-phase electrical simulation."""

    def __init__(self, center: float, amplitude: float, period: float = 3600.0, phase_offset: float = 0.0):
        super().__init__(center, amplitude, period)
        self.phase_offset = phase_offset  # radians

    def update(self, elapsed: float) -> float:
        return self.center + self.amplitude * math.sin(
            2 * math.pi * elapsed / self.period + self.phase_offset
        )


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


class DerivedDewPoint(ValueBehavior):
    """Dew point derived from temperature and relative humidity using the Magnus formula."""

    def __init__(self, temp_behavior: ValueBehavior, rh_behavior: ValueBehavior):
        self.temp_behavior = temp_behavior
        self.rh_behavior = rh_behavior

    def update(self, elapsed: float) -> float:
        temp_f = self.temp_behavior.update(elapsed)
        rh = self.rh_behavior.update(elapsed)
        rh = max(1.0, min(100.0, rh))
        # Convert to Celsius for Magnus formula
        temp_c = (temp_f - 32.0) * 5.0 / 9.0
        a, b = 17.27, 237.7
        gamma = (a * temp_c) / (b + temp_c) + math.log(rh / 100.0)
        dew_c = (b * gamma) / (a - gamma)
        return dew_c * 9.0 / 5.0 + 32.0


class DerivedWetBulb(ValueBehavior):
    """Wet bulb temperature derived from temp and RH using the Stull approximation."""

    def __init__(self, temp_behavior: ValueBehavior, rh_behavior: ValueBehavior):
        self.temp_behavior = temp_behavior
        self.rh_behavior = rh_behavior

    def update(self, elapsed: float) -> float:
        temp_f = self.temp_behavior.update(elapsed)
        rh = self.rh_behavior.update(elapsed)
        rh = max(1.0, min(100.0, rh))
        # Convert to Celsius for Stull formula
        temp_c = (temp_f - 32.0) * 5.0 / 9.0
        # Stull (2011) approximation
        wb_c = temp_c * math.atan(0.151977 * math.sqrt(rh + 8.313659)) + \
            math.atan(temp_c + rh) - math.atan(rh - 1.676331) + \
            0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh) - 4.686035
        return wb_c * 9.0 / 5.0 + 32.0


class WeightedChoice(ValueBehavior):
    """Randomly selects from weighted discrete values, holding each for a duration.

    Parameters:
        choices: list of dicts, each with "value" (any) and optional "weight" (float, default 1.0)
        hold_min: minimum seconds to hold a value before re-rolling (default 300)
        hold_max: maximum seconds to hold a value before re-rolling (default 1800)
    """

    def __init__(self, choices: list[dict], hold_min: float = 300.0, hold_max: float = 1800.0):
        self.values = [c["value"] for c in choices]
        self.weights = [c.get("weight", 1.0) for c in choices]
        self.hold_min = hold_min
        self.hold_max = hold_max
        self._current = random.choices(self.values, weights=self.weights, k=1)[0]
        self._next_change = random.uniform(hold_min, hold_max)

    def update(self, elapsed: float) -> Any:
        if elapsed >= self._next_change:
            self._current = random.choices(self.values, weights=self.weights, k=1)[0]
            self._next_change = elapsed + random.uniform(self.hold_min, self.hold_max)
        return self._current


class DeadbandSwitch(ValueBehavior):
    """Outputs a value when source crosses a threshold, zero otherwise.

    Useful for mutually exclusive heating/cooling: heating only when
    source < threshold, cooling only when source > threshold.
    """

    def __init__(
        self,
        source_behavior: ValueBehavior,
        threshold: float,
        above: bool = True,
        output_behavior: ValueBehavior | None = None,
        output_value: float = 100.0,
    ):
        self.source_behavior = source_behavior
        self.threshold = threshold
        self.above = above
        self.output_behavior = output_behavior
        self.output_value = output_value

    def update(self, elapsed: float) -> float:
        source_val = self.source_behavior.update(elapsed)
        active = (source_val > self.threshold) if self.above else (source_val < self.threshold)
        if not active:
            return 0.0
        if self.output_behavior:
            return max(0.0, self.output_behavior.update(elapsed))
        return self.output_value


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

    elif behavior_type == "phased_sine_wave":
        return PhasedSineWave(
            center=config["center"],
            amplitude=config["amplitude"],
            period=config.get("period", 3600.0),
            phase_offset=config.get("phase_offset", 0.0),
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

    elif behavior_type == "weighted_choice":
        return WeightedChoice(
            choices=config["choices"],
            hold_min=config.get("hold_min", 300.0),
            hold_max=config.get("hold_max", 1800.0),
        )

    elif behavior_type in ("dew_point", "wet_bulb", "deadband_switch"):
        # These require source behaviors — resolved in a second pass by the
        # profile loader. Return a placeholder that stores the config.
        return _DeferredBehavior(config)

    else:
        raise ValueError(f"Unknown behavior type: {behavior_type}")


class _DeferredBehavior(ValueBehavior):
    """Placeholder for behaviors that need source resolution."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def update(self, elapsed: float) -> Any:
        raise RuntimeError(
            f"Deferred behavior '{self.config['type']}' was not resolved — "
            f"missing second-pass source resolution"
        )


def resolve_deferred(
    behavior: ValueBehavior,
    behaviors_by_name: dict[str, ValueBehavior],
) -> ValueBehavior:
    """Resolve a _DeferredBehavior into its real behavior using source references."""
    if not isinstance(behavior, _DeferredBehavior):
        return behavior

    config = behavior.config
    btype = config["type"]
    sources = config.get("sources", [])

    if btype == "dew_point":
        return DerivedDewPoint(
            temp_behavior=behaviors_by_name[sources[0]],
            rh_behavior=behaviors_by_name[sources[1]],
        )
    elif btype == "wet_bulb":
        return DerivedWetBulb(
            temp_behavior=behaviors_by_name[sources[0]],
            rh_behavior=behaviors_by_name[sources[1]],
        )
    elif btype == "deadband_switch":
        source = behaviors_by_name[sources[0]]
        output = behaviors_by_name.get(sources[1]) if len(sources) > 1 else None
        return DeadbandSwitch(
            source_behavior=source,
            threshold=config.get("threshold", 72.0),
            above=config.get("above", True),
            output_behavior=output,
            output_value=config.get("output_value", 100.0),
        )
    else:
        raise ValueError(f"Cannot resolve deferred behavior type: {btype}")
