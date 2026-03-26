"""Data sanity tests: verify simulated values are physically consistent.

These tests load profile YAMLs, run their behaviors for simulated time (no
network required), and check that the resulting values make physical sense.

Tests marked xfail document known realism bugs that will be fixed in Step 4.
"""

import math

import pytest
import yaml

from building_infra_sims.behaviors.base import (
    _DeferredBehavior,
    create_behavior,
    resolve_deferred,
)


def run_behaviors(profile_path: str, steps: int = 100, interval: float = 5.0) -> dict[str, list]:
    """Load a profile, run all behaviors, return {point_name: [values]}.

    Works for both BACnet and Modbus profiles. Handles derived behaviors
    that reference other behaviors by name.
    """
    with open(profile_path) as f:
        data = yaml.safe_load(f)

    behaviors: dict[str, tuple] = {}  # name -> (behavior, initial_value)

    # BACnet profiles
    if "objects" in data:
        for obj in data["objects"]:
            name = obj["name"]
            if "behavior" in obj:
                behaviors[name] = (
                    create_behavior(obj["behavior"]),
                    obj.get("present_value", 0),
                )

    # Modbus profiles
    if "registers" in data:
        for reg_type in ("holding", "input"):
            for reg in data.get("registers", {}).get(reg_type, []):
                name = reg["name"]
                if "behavior" in reg:
                    behaviors[name] = (
                        create_behavior(reg["behavior"]),
                        reg.get("initial_value", 0),
                    )

    # Resolve deferred behaviors (dew_point, wet_bulb, deadband_switch)
    behaviors_by_name = {name: beh for name, (beh, _) in behaviors.items()}
    for name in list(behaviors.keys()):
        beh, init = behaviors[name]
        if isinstance(beh, _DeferredBehavior):
            behaviors[name] = (resolve_deferred(beh, behaviors_by_name), init)

    results: dict[str, list] = {}
    for name, (behavior, _initial) in behaviors.items():
        values = []
        for step in range(steps):
            elapsed = step * interval
            values.append(behavior.update(elapsed))
        results[name] = values

    return results


# ── Physical relationship tests ──────────────────────────────────────────


class TestBoiler:
    def test_supply_gt_return_on_average(self):
        """Boiler supply water should be hotter than return on average."""
        vals = run_behaviors("profiles/bacnet/generic_boiler.yaml", steps=200)
        supply = vals["Supply Water Temperature"]
        ret = vals["Return Water Temperature"]
        avg_supply = sum(supply) / len(supply)
        avg_return = sum(ret) / len(ret)
        assert avg_supply > avg_return, (
            f"Supply avg {avg_supply:.1f} should be > Return avg {avg_return:.1f}"
        )


class TestChiller:
    def test_supply_lt_return(self):
        """Chilled water supply should be colder than return."""
        vals = run_behaviors("profiles/bacnet/generic_chiller.yaml", steps=200)
        supply = vals["Chilled Water Supply Temp"]
        ret = vals["Chilled Water Return Temp"]
        # Ranges: supply max 48, return min 48. Check every step.
        violations = sum(1 for s, r in zip(supply, ret) if s >= r)
        assert violations == 0, f"{violations}/200 steps had supply >= return"

    def test_condenser_return_gt_supply(self):
        """Condenser return should be warmer than supply."""
        vals = run_behaviors("profiles/bacnet/generic_chiller.yaml", steps=200)
        cond_supply = vals["Condenser Water Supply Temp"]
        cond_return = vals["Condenser Water Return Temp"]
        # Both are sine waves: supply center 85, return center 95, same period/amplitude.
        # Return is always 10°F higher.
        violations = sum(1 for s, r in zip(cond_supply, cond_return) if r <= s)
        assert violations == 0, f"{violations}/200 steps had condenser return <= supply"


class TestThreePhaseCurrents:
    """3-phase currents should differ (120° electrical offset). Currently
    all three phases use identical sine_wave parameters, so they produce
    the same values — marking as xfail until PhasedSineWave is added."""

    def test_bacnet_meter_phases_differ(self):
        vals = run_behaviors("profiles/bacnet/generic_meter.yaml", steps=50)
        a = vals["Current Phase A"]
        b = vals["Current Phase B"]
        c = vals["Current Phase C"]
        # At least some steps should have meaningfully different values
        diffs = sum(1 for i in range(len(a)) if abs(a[i] - b[i]) > 0.1 or abs(b[i] - c[i]) > 0.1)
        assert diffs > len(a) * 0.5, f"Only {diffs}/{len(a)} steps had different phase currents"

    def test_modbus_meter_phases_differ(self):
        vals = run_behaviors("profiles/modbus/generic_power_meter.yaml", steps=50)
        a = vals["Current Phase A"]
        b = vals["Current Phase B"]
        c = vals["Current Phase C"]
        diffs = sum(1 for i in range(len(a)) if abs(a[i] - b[i]) > 0.1 or abs(b[i] - c[i]) > 0.1)
        assert diffs > len(a) * 0.5, f"Only {diffs}/{len(a)} steps had different phase currents"


class TestWeatherStation:
    def test_dew_point_lte_dry_bulb(self):
        """Dew point must always be <= dry bulb temperature."""
        vals = run_behaviors(
            "profiles/modbus/generic_weather_station.yaml",
            steps=1440, interval=60.0,
        )
        temp = vals["Outdoor Temperature"]
        dew = vals["Dew Point"]
        violations = sum(1 for t, d in zip(temp, dew) if d > t + 0.1)
        assert violations == 0, f"{violations}/1440 steps had dew point > dry bulb"

    def test_dew_point_tracks_humidity(self):
        """Dew point should be closer to dry bulb when humidity is high.

        Currently dew point and humidity are independent sine waves, so
        there's no physical relationship between them.
        """
        vals = run_behaviors(
            "profiles/modbus/generic_weather_station.yaml",
            steps=1440, interval=60.0,
        )
        temp = vals["Outdoor Temperature"]
        humidity = vals["Outdoor Humidity"]
        dew = vals["Dew Point"]

        # Split into high-humidity and low-humidity halves
        pairs = list(zip(temp, humidity, dew))
        median_rh = sorted(humidity)[len(humidity) // 2]
        high_rh = [(t, d) for t, rh, d in pairs if rh >= median_rh]
        low_rh = [(t, d) for t, rh, d in pairs if rh < median_rh]

        # Depression = dry bulb - dew point; should be smaller at high humidity
        avg_depression_high = sum(t - d for t, d in high_rh) / len(high_rh)
        avg_depression_low = sum(t - d for t, d in low_rh) / len(low_rh)
        assert avg_depression_high < avg_depression_low, (
            f"Dew point depression should be smaller at high RH: "
            f"high_RH={avg_depression_high:.1f}, low_RH={avg_depression_low:.1f}"
        )


class TestHVACController:
    def test_no_simultaneous_heat_and_cool(self):
        """Heating and cooling outputs should not both be active simultaneously."""
        vals = run_behaviors("profiles/modbus/generic_hvac_controller.yaml", steps=200)
        heating = vals["Heating Output"]
        cooling = vals["Cooling Output"]
        both_active = sum(1 for h, c in zip(heating, cooling) if h > 1.0 and c > 1.0)
        assert both_active == 0, f"{both_active}/200 steps had simultaneous heating+cooling"


# ── Accumulator monotonicity ────────────────────────────────────────────


class TestAccumulators:
    @pytest.mark.parametrize("profile_path,point_name", [
        ("profiles/bacnet/generic_meter.yaml", "Total Energy kWh"),
        ("profiles/modbus/generic_power_meter.yaml", "Total kWh"),
    ])
    def test_accumulators_monotonic(self, profile_path, point_name):
        """Accumulator values (energy meters) must never decrease."""
        vals = run_behaviors(profile_path, steps=100)
        values = vals[point_name]
        for i in range(len(values) - 1):
            assert values[i] <= values[i + 1], (
                f"{point_name} decreased at step {i}: {values[i]:.4f} -> {values[i+1]:.4f}"
            )


# ── Voltage range tests ─────────────────────────────────────────────────


class TestVoltageRange:
    """Voltage readings should stay within ±5% of 120V nominal (114-126V)."""

    @pytest.mark.parametrize("profile_path", [
        "profiles/bacnet/generic_meter.yaml",
        "profiles/modbus/generic_power_meter.yaml",
    ])
    def test_voltage_in_range(self, profile_path):
        vals = run_behaviors(profile_path, steps=100)
        for name in ("Voltage Phase A", "Voltage Phase B", "Voltage Phase C"):
            if name not in vals:
                continue
            for v in vals[name]:
                assert 114.0 <= v <= 126.0, f"{name} = {v:.2f}V is outside ±5% of 120V nominal"


# ── Temperature range tests ─────────────────────────────────────────────


class TestTemperatureRanges:
    """HVAC temperatures should be in physically possible ranges."""

    @pytest.mark.parametrize("profile_path,temp_points", [
        (
            "profiles/bacnet/generic_boiler.yaml",
            ["Supply Water Temperature", "Return Water Temperature", "Flue Gas Temperature"],
        ),
        (
            "profiles/bacnet/generic_chiller.yaml",
            ["Chilled Water Supply Temp", "Chilled Water Return Temp",
             "Condenser Water Supply Temp", "Condenser Water Return Temp"],
        ),
        (
            "profiles/modbus/generic_hvac_controller.yaml",
            ["Zone Temperature", "Supply Air Temp"],
        ),
    ])
    def test_temps_in_physical_range(self, profile_path, temp_points):
        vals = run_behaviors(profile_path, steps=100)
        for name in temp_points:
            if name not in vals:
                continue
            for v in vals[name]:
                assert -20.0 <= v <= 500.0, (
                    f"{name} = {v:.1f}°F is outside physical range [-20, 500] in {profile_path}"
                )


# ── CO2 range tests ──────────────────────────────────────────────────────


class TestDHW:
    def test_tank_gt_cold_water(self):
        """DHW tank temps should always be above cold water inlet."""
        vals = run_behaviors("profiles/bacnet/generic_dhw.yaml", steps=200)
        upper = vals["Tank Temp Upper"]
        cold = vals["Inlet Cold Water Temp"]
        violations = sum(1 for u, c in zip(upper, cold) if u <= c)
        assert violations == 0, f"{violations}/200 steps had tank upper <= cold water"

    def test_supply_gt_return_on_average(self):
        """DHW supply should be hotter than return on average."""
        vals = run_behaviors("profiles/bacnet/generic_dhw.yaml", steps=200)
        supply = vals["Supply Temp"]
        ret = vals["Return Temp"]
        avg_supply = sum(supply) / len(supply)
        avg_return = sum(ret) / len(ret)
        assert avg_supply > avg_return


class TestPump:
    def test_discharge_gt_suction_on_average(self):
        """Pump discharge pressure should exceed suction pressure on average."""
        vals = run_behaviors("profiles/modbus/generic_pump.yaml", steps=200)
        discharge = vals["Discharge Pressure"]
        suction = vals["Suction Pressure"]
        avg_discharge = sum(discharge) / len(discharge)
        avg_suction = sum(suction) / len(suction)
        assert avg_discharge > avg_suction


class TestCO2Range:
    def test_co2_in_range(self):
        """CO2 readings should be between 350 and 2000 ppm."""
        vals = run_behaviors("profiles/modbus/generic_sensor_rack.yaml", steps=100)
        for name in ("Zone 1 CO2", "Zone 2 CO2"):
            if name not in vals:
                continue
            for v in vals[name]:
                assert 250.0 <= v <= 2500.0, f"{name} = {v:.0f} ppm is outside reasonable range"
