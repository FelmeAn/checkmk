#!/usr/bin/env python3
# Copyright (C) 2024 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from cmk.graphing.v1 import graphs, metrics, perfometers, Title

UNIT_PERCENTAGE = metrics.Unit(metrics.DecimalNotation("%"))
UNIT_TIME = metrics.Unit(metrics.TimeNotation())

metric_hop_35_pl = metrics.Metric(
    name="hop_35_pl",
    title=Title("Hop 35 packet loss"),
    unit=UNIT_PERCENTAGE,
    color=metrics.Color.BROWN,
)
metric_hop_35_rta = metrics.Metric(
    name="hop_35_rta",
    title=Title("Hop 35 round trip average"),
    unit=UNIT_TIME,
    color=metrics.Color.ORANGE,
)
metric_hop_35_rtmax = metrics.Metric(
    name="hop_35_rtmax",
    title=Title("Hop 35 round trip maximum"),
    unit=UNIT_TIME,
    color=metrics.Color.BLUE,
)
metric_hop_35_rtmin = metrics.Metric(
    name="hop_35_rtmin",
    title=Title("Hop 35 round trip minimum"),
    unit=UNIT_TIME,
    color=metrics.Color.GREEN,
)
metric_hop_35_rtstddev = metrics.Metric(
    name="hop_35_rtstddev",
    title=Title("Hop 35 round trip standard devation"),
    unit=UNIT_TIME,
    color=metrics.Color.PINK,
)

perfometer_hop_35_pl_hop_35_rta = perfometers.Bidirectional(
    name="hop_35_pl_hop_35_rta",
    left=perfometers.Perfometer(
        name="hop_35_pl",
        focus_range=perfometers.FocusRange(
            perfometers.Closed(0),
            perfometers.Closed(100.0),
        ),
        segments=["hop_35_pl"],
    ),
    right=perfometers.Perfometer(
        name="hop_35_rta",
        focus_range=perfometers.FocusRange(
            perfometers.Closed(0),
            perfometers.Open(1),
        ),
        segments=["hop_35_rta"],
    ),
)

graph_hop_35_round_trip_average = graphs.Graph(
    name="hop_35_round_trip_average",
    title=Title("Hop 35 round trip average"),
    simple_lines=[
        "hop_35_rtmax",
        "hop_35_rtmin",
        "hop_35_rta",
        "hop_35_rtstddev",
    ],
)

graph_hop_35_packet_loss = graphs.Graph(
    name="hop_35_packet_loss",
    title=Title("Hop 35 packet loss"),
    compound_lines=["hop_35_pl"],
)
