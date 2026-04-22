"""Shared simulation world state — Boston, MA (ASHRAE climate zone 5A).

Models outdoor conditions, occupancy, and derived HVAC load demand as
deterministic functions of wall-clock time. All behaviors that want to
react to "the weather" or "the schedule" read from this single source
so every simulated device agrees on whether it's a cold winter morning
or a hot summer afternoon.

Calibrated to NOAA KBOS 1991–2020 normals and the DOE medium-office
prototype occupancy schedule (see docs/realistic_values_research.md).

Pure functions of time — same `t` in, same value out. Tests can pass
an explicit epoch; production behaviors use the default `time.time()`.
"""

from __future__ import annotations

import math
import time
from datetime import datetime


# NOAA KBOS 1991–2020 normals
_ANNUAL_MEAN_F = 51.0
_ANNUAL_AMP_F = 23.0          # half-span of 29°F Jan mean → 75°F July mean
_SUMMER_PEAK_DOY = 208        # late July (day-of-year 208)

# ASHRAE 90.1 default office schedule (DOE medium office prototype)
_WEEKDAY_PEAK_OCC = 1.00
_SATURDAY_PEAK_OCC = 0.30
_OCC_RAMP_START = 6.0
_OCC_RAMP_END = 9.0
_OCC_DECAY_START = 17.0
_OCC_DECAY_END = 20.0


class WorldState:
    """Deterministic Boston-climate simulation clock.

    All methods accept `t` (epoch seconds); when omitted, uses `time.time()`.
    Thread-safe because there is no mutable state.
    """

    def __init__(self, latitude: float = 42.36, longitude: float = -71.01):
        # Boston Logan (KBOS)
        self.latitude = latitude
        self.longitude = longitude

    def _now(self, t: float | None) -> float:
        return time.time() if t is None else t

    def oat_f(self, t: float | None = None) -> float:
        """Outdoor air temperature in °F.

        Annual cosine calibrated to KBOS normals (29°F late Jan → 75°F late Jul),
        diurnal cosine with seasonal amplitude (8°F winter, 15°F summer),
        plus two incommensurate sub-diurnal harmonics for texture.
        """
        t = self._now(t)
        dt = datetime.fromtimestamp(t)
        doy = dt.timetuple().tm_yday
        hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0

        annual_phase = 2 * math.pi * (doy - _SUMMER_PEAK_DOY) / 365.25
        annual = _ANNUAL_MEAN_F + _ANNUAL_AMP_F * math.cos(annual_phase)

        # Seasonal diurnal amplitude: ~8°F winter, ~15°F summer
        season_fraction = 0.5 + 0.5 * math.cos(annual_phase)  # 0=winter, 1=summer
        diurnal_amp = 8.0 + 7.0 * season_fraction
        diurnal = diurnal_amp * math.cos(2 * math.pi * (hour - 15) / 24.0)

        # Two incommensurate sub-diurnal harmonics for realistic texture
        # (passing cloud, wind shift). Period 2h and ~3.7h.
        texture = 1.2 * math.sin(2 * math.pi * t / 7200.0) \
                + 0.6 * math.sin(2 * math.pi * t / 13400.0)

        return annual + diurnal + texture

    def outdoor_rh(self, t: float | None = None) -> float:
        """Outdoor relative humidity %, 25–85 range.

        Inverse of diurnal temperature (RH peaks at dawn, minimum mid-afternoon)
        plus seasonal bias (humid summer 55%, dry winter 40%).
        """
        t = self._now(t)
        dt = datetime.fromtimestamp(t)
        doy = dt.timetuple().tm_yday
        hour = dt.hour + dt.minute / 60.0

        annual_phase = 2 * math.pi * (doy - _SUMMER_PEAK_DOY) / 365.25
        season_fraction = 0.5 + 0.5 * math.cos(annual_phase)
        seasonal_mean = 40.0 + 15.0 * season_fraction  # 40% winter, 55% summer

        # Diurnal inverse: high at dawn (06:00), low mid-afternoon (15:00)
        diurnal = -12.0 * math.cos(2 * math.pi * (hour - 15) / 24.0)
        texture = 3.0 * math.sin(2 * math.pi * t / 7200.0)

        return max(20.0, min(95.0, seasonal_mean + diurnal + texture))

    def solar_ghi(self, t: float | None = None) -> float:
        """Global horizontal irradiance in W/m².

        Bounded sinusoid over daylight hours, peaks ~1000 W/m² summer noon,
        ~400 W/m² winter noon. Zero at night. No cloud cover modeled —
        a separate random-walk overlay could be added later.
        """
        t = self._now(t)
        dt = datetime.fromtimestamp(t)
        doy = dt.timetuple().tm_yday
        hour = dt.hour + dt.minute / 60.0

        # Daylight hours vary with season
        sunrise = 7.5 - 2.0 * math.cos(2 * math.pi * (doy - _SUMMER_PEAK_DOY) / 365.25)
        sunset = 16.5 + 2.0 * math.cos(2 * math.pi * (doy - _SUMMER_PEAK_DOY) / 365.25)
        if hour < sunrise or hour > sunset:
            return 0.0

        # Half-sine from sunrise to sunset
        day_fraction = (hour - sunrise) / (sunset - sunrise)
        peak = 400.0 + 600.0 * (0.5 + 0.5 * math.cos(
            2 * math.pi * (doy - _SUMMER_PEAK_DOY) / 365.25
        ))
        return peak * math.sin(math.pi * day_fraction)

    def occupancy(self, t: float | None = None) -> float:
        """Office occupancy fraction, 0..1.

        DOE medium-office schedule: weekday 6–20h with ramp/decay, Saturday
        partial, Sunday empty. No holiday calendar.
        """
        t = self._now(t)
        dt = datetime.fromtimestamp(t)
        dow = dt.weekday()  # 0=Mon, 6=Sun
        hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0

        if dow == 6:  # Sunday
            return 0.0
        peak = _WEEKDAY_PEAK_OCC if dow < 5 else _SATURDAY_PEAK_OCC

        if hour < _OCC_RAMP_START or hour >= _OCC_DECAY_END:
            return 0.0
        if hour < _OCC_RAMP_END:
            return peak * (hour - _OCC_RAMP_START) / (_OCC_RAMP_END - _OCC_RAMP_START)
        if hour < _OCC_DECAY_START:
            return peak
        return peak * (_OCC_DECAY_END - hour) / (_OCC_DECAY_END - _OCC_DECAY_START)

    def cooling_demand(self, t: float | None = None) -> float:
        """Fraction of cooling-coil capacity required, 0..1.

        Rises linearly from 0 at 55°F OAT to 1 at 88°F. Modulated by occupancy:
        a hot empty building still needs ~30% cooling (overnight setback).
        """
        t = self._now(t)
        oat = self.oat_f(t)
        occ = self.occupancy(t)
        raw = max(0.0, min(1.0, (oat - 55.0) / 33.0))
        return raw * (0.3 + 0.7 * occ)

    def heating_demand(self, t: float | None = None) -> float:
        """Fraction of heating capacity required, 0..1.

        Rises from 0 at 55°F OAT to 1 at 0°F (design heating temperature for
        Boston per ASHRAE 169). Modulated by occupancy for setback.
        """
        t = self._now(t)
        oat = self.oat_f(t)
        occ = self.occupancy(t)
        raw = max(0.0, min(1.0, (55.0 - oat) / 55.0))
        return raw * (0.3 + 0.7 * occ)

    def is_economizer_favorable(self, t: float | None = None) -> bool:
        """True when OAT is in the economizer sweet spot (50–65°F).

        Below 50°F, outside air is too cold for free cooling without freezing
        coils. Above 65°F, mechanical cooling is more efficient than pulling
        in warm humid air.
        """
        oat = self.oat_f(t)
        return 50.0 <= oat <= 65.0


# Module-level singleton
_world: WorldState | None = None


def get_world() -> WorldState:
    """Return the process-wide WorldState singleton."""
    global _world
    if _world is None:
        _world = WorldState()
    return _world


def reset_world() -> None:
    """Force re-initialization of the WorldState singleton (tests only)."""
    global _world
    _world = None
