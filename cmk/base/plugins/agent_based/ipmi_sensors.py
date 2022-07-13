#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from typing import Any, Mapping, NamedTuple, Optional

from .agent_based_api.v1 import register, Service, State
from .agent_based_api.v1.type_defs import CheckResult, DiscoveryResult, StringTable
from .utils import ipmi as ipmi_utils

_NA_VALUES = {"NA", "N/A"}


def _na_str(str_value: str) -> str:
    return "" if str_value in _NA_VALUES else str_value


def _na_float(str_value: str) -> Optional[float]:
    return None if str_value in _NA_VALUES else float(str_value)


class Status(NamedTuple):
    txt: str
    is_ok: bool


def _parse_status_txt(status_txt: str) -> Status:
    if status_txt.startswith("[") or status_txt.startswith("'"):
        status_txt = status_txt[1:]
    if status_txt.endswith("]") or status_txt.endswith("'"):
        status_txt = status_txt[:-1]
    if status_txt in ["NA", "N/A", "Unknown"] or "_=_" in status_txt:
        return Status(txt=status_txt.replace("_", " "), is_ok=False)
    if status_txt in ["S0G0", "S0/G0"]:
        return Status(txt="System full operational, working", is_ok=True)
    return Status(txt=status_txt.replace("_", " "), is_ok=True)


def parse_ipmi_sensors(string_table: StringTable) -> ipmi_utils.Section:
    section: ipmi_utils.Section = {}
    for line in string_table:
        stripped_line = [x.strip(" \n\t\x00") for x in line]
        status = _parse_status_txt(stripped_line[-1])

        sensorname = stripped_line[1].replace(" ", "_")

        if not status.is_ok and sensorname not in section:
            continue

        sensor = section.setdefault(
            sensorname,
            ipmi_utils.Sensor(status_txt=status.txt, unit=""),
        )

        match stripped_line[2:-1]:
            case [reading_levels]:
                if "(" in reading_levels:
                    # 339 Voltage_3.3VCC 3.33_V_(NA/NA) [OK]
                    current, levels = reading_levels.split("(")
                    lower, upper = levels[:-1].split("/")
                else:
                    # 59 M2_Temp0(PCIe1)_(Temperature) NA/79.00_41.00_C [OK]
                    levels, current = reading_levels.split("_", 1)
                    lower, upper = levels.split("/")
                cparts = current.split("_")

                sensor.unit = _na_str(cparts[1])
                sensor.value = _na_float(cparts[0])
                sensor.crit_low = _na_float(lower)
                sensor.crit_high = _na_float(upper)

            case [_, value, unit] | [_, _, value, unit]:
                sensor.value = _na_float(value)
                sensor.unit = _na_str(unit)
            case [_, _, value, unit, _, lower_c, lower_nc, upper_nc, upper_c, _]:
                sensor.value = _na_float(value)
                sensor.unit = _na_str(unit)
                sensor.crit_low = _na_float(lower_c)
                sensor.warn_low = _na_float(lower_nc)
                sensor.warn_high = _na_float(upper_nc)
                sensor.crit_high = _na_float(upper_c)

    return section


register.agent_section(
    name="ipmi_sensors",
    parse_function=parse_ipmi_sensors,
)


def discover_ipmi_sensors(
    params: ipmi_utils.DiscoveryParams,
    section: ipmi_utils.Section,
) -> DiscoveryResult:
    mode, ignore_params = params["discovery_mode"]

    if mode == "summarize":
        yield Service(item="Summary FreeIPMI")
        return

    yield from (
        Service(item=sensor_name)
        for sensor_name, sensor in section.items()
        if not ipmi_utils.ignore_sensor(sensor_name, sensor.status_txt, ignore_params)
    )


def _status_txt_mapping(status_txt: str) -> State:
    state = {
        "ok": State.OK,
        "warning": State.WARN,
        "critical": State.CRIT,
        "failed": State.CRIT,
        "unknown": State.UNKNOWN,
    }.get(status_txt.lower())
    if state is not None:
        return state

    if "non-critical" in status_txt.lower():
        return State.WARN
    if status_txt.lower().startswith("nc"):
        return State.WARN

    if (
        status_txt.lower()
        in [
            "entity present",
            "battery presence detected",
            "drive presence",
            "transition to running",
            "device enabled",
            "system full operational, working",
            "system restart",
            "present",
            "transition to ok",
        ]
        or status_txt.startswith("Fully Redundant")
        or status_txt.endswith("is connected")
        or status_txt.endswith("Presence detected")
        or status_txt.endswith("Device Present")
    ):
        return State.OK
    return State.CRIT


def check_ipmi_sensors(
    item: str,
    params: Mapping[str, Any],
    section: ipmi_utils.Section,
) -> CheckResult:
    yield from ipmi_utils.check_ipmi(
        item,
        params,
        section,
        True,
        _status_txt_mapping,
    )


register.check_plugin(
    name="ipmi_sensors",
    service_name="IPMI Sensor %s",
    discovery_function=discover_ipmi_sensors,
    discovery_ruleset_name="inventory_ipmi_rules",
    discovery_default_parameters={"discovery_mode": ("single", {})},
    check_function=check_ipmi_sensors,
    check_ruleset_name="ipmi",
    check_default_parameters={},
)
