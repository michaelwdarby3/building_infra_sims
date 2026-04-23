"""BACnet object factory - maps profile type strings to BACpypes3 object classes."""

from typing import Any

from bacpypes3.local.analog import (
    AnalogInputObject,
    AnalogOutputObject,
    AnalogValueObject,
)
from bacpypes3.local.binary import (
    BinaryInputObject,
    BinaryOutputObject,
    BinaryValueObject,
)
from bacpypes3.local.multistate import (
    MultiStateInputObject,
    MultiStateOutputObject,
    MultiStateValueObject,
)
from bacpypes3.object import ScheduleObject

# Map BACnet type names to BACpypes3 classes
BACNET_OBJECT_MAP = {
    "analog-input": AnalogInputObject,
    "analog-output": AnalogOutputObject,
    "analog-value": AnalogValueObject,
    "binary-input": BinaryInputObject,
    "binary-output": BinaryOutputObject,
    "binary-value": BinaryValueObject,
    "multi-state-input": MultiStateInputObject,
    "multi-state-output": MultiStateOutputObject,
    "multi-state-value": MultiStateValueObject,
    "schedule": ScheduleObject,
}

# Common engineering unit mappings
UNIT_MAP = {
    "degrees-fahrenheit": "degreesFahrenheit",
    "degrees-celsius": "degreesCelsius",
    "percent": "percent",
    "watts": "watts",
    "kilowatts": "kilowatts",
    "kilowatt-hours": "kilowattHours",
    "volts": "volts",
    "amperes": "amperes",
    "cubic-feet-per-minute": "cubicFeetPerMinute",
    "inches-of-water": "inchesOfWater",
    "psi": "poundsForcePerSquareInch",
    "pounds-per-square-inch": "poundsForcePerSquareInch",
    "gallons-per-minute": "usGallonsPerMinute",
    "rpm": "revolutionsPerMinute",
    "hertz": "hertz",
    "kilovolt-amperes-reactive": "kilovoltAmperesReactive",
    "no-units": "noUnits",
}


def resolve_units(unit_str: str | None) -> str:
    """Resolve a human-friendly unit string to a BACpypes3 EngineeringUnits value."""
    if unit_str is None:
        return "noUnits"
    return UNIT_MAP.get(unit_str, unit_str)


def create_bacnet_object(
    obj_type: str,
    instance: int,
    name: str,
    present_value: Any = None,
    units: str | None = None,
    description: str | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Create a JSON dict for a BACnet object suitable for Application.from_json().

    Returns the JSON object definition that BACpypes3 can instantiate.
    """
    if obj_type not in BACNET_OBJECT_MAP:
        raise ValueError(f"Unknown BACnet object type: {obj_type}. Valid: {list(BACNET_OBJECT_MAP)}")

    obj_def: dict[str, Any] = {
        "object-type": obj_type,
        "object-identifier": f"{obj_type},{instance}",
        "object-name": name,
        "status-flags": [],
        "out-of-service": False,
    }

    if description:
        obj_def["description"] = description

    # Set present-value based on type category
    if obj_type.startswith("analog"):
        val = float(present_value) if present_value is not None else 0.0
        obj_def["present-value"] = val
        obj_def["units"] = resolve_units(units)
    elif obj_type.startswith("binary"):
        if isinstance(present_value, str):
            val = present_value  # "active" or "inactive"
        elif present_value:
            val = "active"
        else:
            val = "inactive"
        obj_def["present-value"] = val
    elif obj_type.startswith("multi-state"):
        val = int(present_value) if present_value is not None else 1
        obj_def["present-value"] = val
        # Multi-state objects need number-of-states
        states = kwargs.get("states", [])
        if states:
            obj_def["number-of-states"] = len(states)
            obj_def["state-text"] = states
    elif obj_type == "schedule":
        # Schedule doesn't go through Application.from_json — it's instantiated
        # programmatically in create_schedule_object using bacpypes3 structured
        # types. We just stash the raw YAML-side fields for later consumption.
        obj_def["weekly_schedule"] = kwargs.get("weekly_schedule", [])
        obj_def["exception_schedule"] = kwargs.get("exception_schedule", [])
        obj_def["effective_period"] = kwargs.get("effective_period")
        obj_def["schedule_default"] = kwargs.get("schedule_default", present_value)
        obj_def["referenced_points"] = kwargs.get("referenced_points", [])

    return obj_def


# Types that use the Commandable mixin and must be created programmatically
# (BACpypes3 json_to_sequence can't handle Commandable default init)
COMMANDABLE_TYPES = {"analog-output", "binary-output", "multi-state-output"}

# Schedule objects also need programmatic construction: their structured
# properties (weeklySchedule, effectivePeriod, ...) don't survive
# Application.from_json's decoding of nested Sequence types.
SCHEDULE_TYPES = {"schedule"}


def create_commandable_object(obj_def: dict[str, Any]) -> Any:
    """Create a Commandable BACnet object instance from a JSON-style dict.

    These can't go through Application.from_json() due to a BACpypes3
    limitation with the Commandable mixin's __init__.
    """
    obj_type = obj_def["object-type"]
    cls = BACNET_OBJECT_MAP[obj_type]

    kwargs: dict[str, Any] = {
        "objectIdentifier": obj_def["object-identifier"],
        "objectName": obj_def["object-name"],
        "statusFlags": [],
        "outOfService": obj_def.get("out-of-service", False),
    }

    if obj_type.startswith("analog"):
        pv = obj_def.get("present-value", 0.0)
        kwargs["presentValue"] = float(pv)
        kwargs["relinquishDefault"] = float(pv)
        units = obj_def.get("units", "noUnits")
        kwargs["units"] = units

    elif obj_type.startswith("binary"):
        pv = obj_def.get("present-value", "inactive")
        kwargs["presentValue"] = pv
        kwargs["relinquishDefault"] = "inactive"

    elif obj_type.startswith("multi-state"):
        pv = obj_def.get("present-value", 1)
        kwargs["presentValue"] = int(pv)
        kwargs["relinquishDefault"] = 1
        if "number-of-states" in obj_def:
            kwargs["numberOfStates"] = obj_def["number-of-states"]
        if "state-text" in obj_def:
            kwargs["stateText"] = obj_def["state-text"]

    if "description" in obj_def:
        kwargs["description"] = obj_def["description"]

    return cls(**kwargs)


def create_schedule_object(obj_def: dict[str, Any]) -> Any:
    """Build a bacpypes3 ScheduleObject from a YAML-derived dict.

    The profile YAML carries plain Python values (floats for presentValue,
    list-of-dicts for weekly_schedule, iso-style strings for dates). We
    translate those into the structured bacpypes3 types (DailySchedule,
    TimeValue, DateRange, Real, ...) required by ScheduleObject.
    """
    from bacpypes3.basetypes import DailySchedule, DateRange, SpecialEvent, TimeValue
    from bacpypes3.object import ScheduleObject
    from bacpypes3.primitivedata import Date, Real, Time

    def _time_from_str(s: str) -> Time:
        # "HH:MM" or "HH:MM:SS" — bacpypes3 Time takes (h, m, s, hundredths)
        parts = [int(p) for p in s.split(":")]
        while len(parts) < 3:
            parts.append(0)
        return Time((parts[0], parts[1], parts[2], 0))

    def _date_from_iso(s: str) -> Date:
        # Python 2.6 + bacpypes3 Date: (year-1900, month, day, day-of-week).
        # Day-of-week = 1 (unspecified) is acceptable; bacpypes3 normalizes.
        from datetime import date

        d = date.fromisoformat(s)
        return Date((d.year - 1900, d.month, d.day, 1))

    # Weekly schedule: list of 7 DailySchedule entries. Each entry is a list of
    # {time, value} dicts. Missing days get empty daySchedule.
    raw_weekly = obj_def.get("weekly_schedule") or []
    weekly: list[DailySchedule] = []
    for day_cfg in raw_weekly:
        day_schedule = []
        for tv in day_cfg or []:
            day_schedule.append(
                TimeValue(
                    time=_time_from_str(tv["time"]),
                    value=Real(float(tv["value"])),
                )
            )
        weekly.append(DailySchedule(daySchedule=day_schedule))
    # Pad to 7 days
    while len(weekly) < 7:
        weekly.append(DailySchedule(daySchedule=[]))

    kwargs: dict[str, Any] = {
        "objectIdentifier": obj_def["object-identifier"],
        "objectName": obj_def["object-name"],
        "presentValue": Real(float(obj_def.get("present-value") or 0.0)),
        "weeklySchedule": weekly,
        "exceptionSchedule": [],
        "scheduleDefault": Real(float(obj_def.get("schedule_default") or 0.0)),
        "listOfObjectPropertyReferences": [],
        "outOfService": False,
        "statusFlags": [],
    }

    ep = obj_def.get("effective_period")
    if ep and isinstance(ep, dict) and "start" in ep and "end" in ep:
        kwargs["effectivePeriod"] = DateRange(
            startDate=_date_from_iso(ep["start"]),
            endDate=_date_from_iso(ep["end"]),
        )

    if "description" in obj_def:
        kwargs["description"] = obj_def["description"]

    return ScheduleObject(**kwargs)
