"""Tests for the shared WorldState (Boston climate + occupancy) and the
behaviors that read from it (WorldValue, Tracks, ConditionalOnOAT,
OccupancyBinary, MixedAir).

All tests pin an explicit epoch to the underlying helpers that accept `t`,
and patch `time.time` for behaviors that don't. No network or BACnet/Modbus
stacks are exercised.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from building_infra_sims.behaviors.base import (
    ConditionalOnOAT,
    MixedAir,
    OccupancyBinary,
    StaticValue,
    Tracks,
    WorldValue,
    create_behavior,
    resolve_deferred,
)
from building_infra_sims.world import WorldState, get_world, reset_world


# ── Epoch helpers ───────────────────────────────────────────────────────


def _epoch(year: int, month: int, day: int, hour: int = 12) -> float:
    """Naive local-time epoch: `datetime.fromtimestamp(t)` will return these fields."""
    return datetime(year, month, day, hour).timestamp()


_WINTER_NOON = _epoch(2026, 1, 15, 12)  # mid-January
_SUMMER_NOON = _epoch(2026, 7, 15, 14)  # mid-July, hottest hour
_WINTER_NIGHT = _epoch(2026, 1, 15, 3)
_SHOULDER_NOON = _epoch(2026, 4, 15, 12)  # mild

# DOE schedule checkpoints
_MON_PREDAWN = _epoch(2026, 4, 13, 4)   # Monday 4am → occ 0
_MON_NOON = _epoch(2026, 4, 13, 12)     # Monday 12pm → occ 1
_SAT_NOON = _epoch(2026, 4, 18, 12)     # Saturday 12pm → occ 0.3
_SUN_NOON = _epoch(2026, 4, 19, 12)     # Sunday → 0


# ── WorldState climate sanity ───────────────────────────────────────────


class TestWorldStateClimate:
    def test_winter_colder_than_summer(self):
        w = WorldState()
        assert w.oat_f(_WINTER_NOON) < w.oat_f(_SUMMER_NOON)

    def test_winter_oat_near_boston_jan_mean(self):
        """Jan mid-month should be close to the KBOS Jan normal of ~29°F."""
        w = WorldState()
        oat = w.oat_f(_WINTER_NOON)
        assert 15 <= oat <= 45, f"Winter noon OAT {oat:.1f}°F outside plausible Jan range"

    def test_summer_oat_near_boston_jul_mean(self):
        """Mid-July ~2pm should be near peak summer ~80°F."""
        w = WorldState()
        oat = w.oat_f(_SUMMER_NOON)
        assert 68 <= oat <= 92, f"Summer afternoon OAT {oat:.1f}°F outside plausible Jul range"

    def test_diurnal_swing(self):
        """Winter afternoon should be warmer than winter pre-dawn."""
        w = WorldState()
        assert w.oat_f(_WINTER_NOON) > w.oat_f(_WINTER_NIGHT)

    def test_rh_bounds(self):
        w = WorldState()
        for t in (_WINTER_NOON, _SUMMER_NOON, _WINTER_NIGHT, _SHOULDER_NOON):
            rh = w.outdoor_rh(t)
            assert 20.0 <= rh <= 95.0

    def test_solar_zero_at_night(self):
        w = WorldState()
        assert w.solar_ghi(_epoch(2026, 7, 15, 2)) == 0.0
        assert w.solar_ghi(_epoch(2026, 1, 15, 23)) == 0.0

    def test_solar_peaks_summer_over_winter(self):
        w = WorldState()
        summer_peak = w.solar_ghi(_epoch(2026, 7, 15, 12))
        winter_peak = w.solar_ghi(_epoch(2026, 1, 15, 12))
        assert summer_peak > winter_peak > 0

    def test_occupancy_weekday_workhours(self):
        w = WorldState()
        assert w.occupancy(_MON_PREDAWN) == 0.0
        assert w.occupancy(_MON_NOON) == pytest.approx(1.0)

    def test_occupancy_saturday_partial(self):
        w = WorldState()
        assert 0.0 < w.occupancy(_SAT_NOON) < 0.5

    def test_occupancy_sunday_zero(self):
        w = WorldState()
        assert w.occupancy(_SUN_NOON) == 0.0

    def test_cooling_heating_are_exclusive(self):
        """At any single instant you don't need both substantial cooling and heating."""
        w = WorldState()
        for t in (_WINTER_NOON, _SUMMER_NOON, _SHOULDER_NOON):
            c = w.cooling_demand(t)
            h = w.heating_demand(t)
            assert c * h < 0.05, f"Both demands active at once: cool={c:.2f} heat={h:.2f}"

    def test_economizer_favorable_in_shoulder(self):
        """Sometime during April should hit the 50–65°F economizer window."""
        w = WorldState()
        # Sample an April afternoon at several hours
        any_favorable = any(
            w.is_economizer_favorable(_epoch(2026, 4, 15, h))
            for h in range(6, 20)
        )
        assert any_favorable


class TestWorldSingleton:
    def test_singleton_identity(self):
        reset_world()
        a = get_world()
        b = get_world()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = get_world()
        reset_world()
        b = get_world()
        assert a is not b


# ── WorldValue ──────────────────────────────────────────────────────────


class TestWorldValue:
    def test_unknown_signal_rejected(self):
        with pytest.raises(ValueError, match="Unknown world signal"):
            WorldValue(signal="not_a_signal")

    def test_scale_and_offset(self):
        wv = WorldValue(signal="occupancy", scale=100.0, offset=10.0)
        with patch("building_infra_sims.behaviors.base.time.time", return_value=_MON_NOON):
            v = wv.update(0)
        assert v == pytest.approx(110.0)  # occupancy=1 * 100 + 10

    def test_clamping(self):
        wv = WorldValue(signal="occupancy", scale=1000.0, max_val=50.0)
        with patch("building_infra_sims.behaviors.base.time.time", return_value=_MON_NOON):
            assert wv.update(0) == 50.0

    def test_noise_varies_output(self):
        random.seed(42)
        wv = WorldValue(signal="occupancy", scale=100.0, noise=5.0)
        with patch("building_infra_sims.behaviors.base.time.time", return_value=_MON_NOON):
            samples = {wv.update(0) for _ in range(20)}
        assert len(samples) > 1

    def test_oat_follows_world(self):
        wv = WorldValue(signal="oat")
        w = get_world()
        with patch("building_infra_sims.behaviors.base.time.time", return_value=_WINTER_NOON):
            v = wv.update(0)
        assert v == pytest.approx(w.oat_f(_WINTER_NOON))


# ── Tracks ──────────────────────────────────────────────────────────────


class TestTracks:
    def test_converges_to_target_with_no_lag(self):
        t = Tracks(source_behavior=StaticValue(72.0), lag_factor=0.0)
        for _ in range(3):
            v = t.update(0)
        assert v == pytest.approx(72.0)

    def test_bias_applied(self):
        t = Tracks(source_behavior=StaticValue(72.0), bias=1.5, lag_factor=0.0)
        v = t.update(0)
        assert v == pytest.approx(73.5)

    def test_lag_slows_convergence(self):
        slow = Tracks(source_behavior=StaticValue(100.0), lag_factor=0.9, initial=0.0)
        fast = Tracks(source_behavior=StaticValue(100.0), lag_factor=0.0, initial=0.0)
        slow_v = slow.update(0)
        fast_v = fast.update(0)
        assert abs(100.0 - slow_v) > abs(100.0 - fast_v)

    def test_lag_clamped(self):
        t = Tracks(source_behavior=StaticValue(1.0), lag_factor=5.0)
        assert t.lag_factor <= 0.95

    def test_initial_value_used(self):
        t = Tracks(source_behavior=StaticValue(100.0), lag_factor=0.9, initial=50.0)
        v = t.update(0)
        # First step: 50 + 0.1 * (100 - 50) = 55
        assert v == pytest.approx(55.0)


# ── ConditionalOnOAT ────────────────────────────────────────────────────


class TestConditionalOnOAT:
    def test_requires_bands(self):
        with pytest.raises(ValueError):
            ConditionalOnOAT(bands=[])

    def test_band_selection(self):
        c = ConditionalOnOAT(
            bands=[
                {"oat_below": 30, "value": 100.0},
                {"oat_below": 60, "value": 50.0},
                {"oat_below": 200, "value": 10.0},
            ]
        )
        with patch.object(c._world, "oat_f", return_value=20.0):
            assert c.update(0) == pytest.approx(100.0)
        with patch.object(c._world, "oat_f", return_value=45.0):
            assert c.update(0) == pytest.approx(50.0)
        with patch.object(c._world, "oat_f", return_value=80.0):
            assert c.update(0) == pytest.approx(10.0)

    def test_fallback_when_no_band_matches(self):
        """OAT above every threshold falls through to the last band."""
        c = ConditionalOnOAT(
            bands=[
                {"oat_below": 30, "value": 1.0},
                {"oat_below": 60, "value": 2.0},
            ]
        )
        with patch.object(c._world, "oat_f", return_value=99.0):
            assert c.update(0) == pytest.approx(2.0)


# ── OccupancyBinary ─────────────────────────────────────────────────────


class TestOccupancyBinary:
    def test_on_during_workday(self):
        ob = OccupancyBinary(threshold=0.05)
        with patch("building_infra_sims.behaviors.base.time.time", return_value=_MON_NOON):
            assert ob.update(0) == "active"

    def test_off_predawn(self):
        ob = OccupancyBinary(threshold=0.05)
        with patch("building_infra_sims.behaviors.base.time.time", return_value=_MON_PREDAWN):
            assert ob.update(0) == "inactive"

    def test_custom_on_off_values(self):
        ob = OccupancyBinary(threshold=0.05, on_value="RUNNING", off_value="STOPPED")
        with patch("building_infra_sims.behaviors.base.time.time", return_value=_MON_NOON):
            assert ob.update(0) == "RUNNING"
        with patch("building_infra_sims.behaviors.base.time.time", return_value=_MON_PREDAWN):
            assert ob.update(0) == "STOPPED"


# ── MixedAir ────────────────────────────────────────────────────────────


class TestMixedAir:
    def test_damper_closed_returns_rat(self):
        ma = MixedAir(damper_behavior=StaticValue(0.0), return_air_behavior=StaticValue(72.0))
        with patch.object(ma._world, "oat_f", return_value=20.0):
            assert ma.update(0) == pytest.approx(72.0)

    def test_damper_full_open_returns_oat(self):
        ma = MixedAir(damper_behavior=StaticValue(100.0), return_air_behavior=StaticValue(72.0))
        with patch.object(ma._world, "oat_f", return_value=20.0):
            assert ma.update(0) == pytest.approx(20.0)

    def test_damper_half_mixes(self):
        ma = MixedAir(damper_behavior=StaticValue(50.0), return_air_behavior=StaticValue(72.0))
        with patch.object(ma._world, "oat_f", return_value=20.0):
            assert ma.update(0) == pytest.approx(46.0)

    def test_damper_values_clamped(self):
        """Damper outputs outside 0..100 shouldn't produce non-physical blends."""
        ma_over = MixedAir(damper_behavior=StaticValue(150.0), return_air_behavior=StaticValue(72.0))
        ma_under = MixedAir(damper_behavior=StaticValue(-10.0), return_air_behavior=StaticValue(72.0))
        with patch.object(ma_over._world, "oat_f", return_value=20.0):
            assert ma_over.update(0) == pytest.approx(20.0)
        with patch.object(ma_under._world, "oat_f", return_value=20.0):
            assert ma_under.update(0) == pytest.approx(72.0)


# ── Factory + deferred resolution ──────────────────────────────────────


class TestFactoryWiring:
    def test_world_value_factory(self):
        b = create_behavior({"type": "world_value", "signal": "oat", "scale": 1.0})
        assert isinstance(b, WorldValue)

    def test_occupancy_binary_factory(self):
        b = create_behavior({"type": "occupancy_binary", "threshold": 0.1})
        assert isinstance(b, OccupancyBinary)

    def test_conditional_on_oat_resolution(self):
        cfg = {
            "type": "conditional_on_oat",
            "bands": [{"oat_below": 50, "value": 1.0}, {"oat_below": 200, "value": 2.0}],
        }
        deferred = create_behavior(cfg)
        resolved = resolve_deferred(deferred, {})
        assert isinstance(resolved, ConditionalOnOAT)

    def test_tracks_resolution(self):
        source = create_behavior({"type": "static", "value": 70.0})
        deferred = create_behavior({"type": "tracks", "source": "Src", "bias": 1.0})
        resolved = resolve_deferred(deferred, {"Src": source})
        assert isinstance(resolved, Tracks)
        assert resolved.bias == 1.0

    def test_mixed_air_resolution(self):
        damper = create_behavior({"type": "static", "value": 50.0})
        rat = create_behavior({"type": "static", "value": 72.0})
        deferred = create_behavior({
            "type": "mixed_air",
            "damper_source": "Damper",
            "return_air_source": "RAT",
        })
        resolved = resolve_deferred(deferred, {"Damper": damper, "RAT": rat})
        assert isinstance(resolved, MixedAir)

    def test_nested_deferred_resolution(self):
        """A mixed_air whose damper_source is itself a deferred conditional_on_oat
        should resolve transparently — fixes the chain MixedAir → ConditionalOnOAT."""
        damper_cfg = {
            "type": "conditional_on_oat",
            "bands": [{"oat_below": 200, "value": 50.0}],
        }
        rat = create_behavior({"type": "static", "value": 72.0})
        damper_deferred = create_behavior(damper_cfg)
        mixed_deferred = create_behavior({
            "type": "mixed_air",
            "damper_source": "Damper",
            "return_air_source": "RAT",
        })
        by_name = {"Damper": damper_deferred, "RAT": rat}
        resolved = resolve_deferred(mixed_deferred, by_name)
        assert isinstance(resolved, MixedAir)
        assert isinstance(resolved.damper_behavior, ConditionalOnOAT)
        assert not isinstance(by_name["Damper"], type(damper_deferred))
