#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

# pylint: disable=protected-access

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Literal

import pytest
from pytest import MonkeyPatch

from livestatus import SiteId

from cmk.utils.hostaddress import HostName

from cmk.gui import metrics
from cmk.gui.config import active_config
from cmk.gui.graphing import _graph_templates as gt
from cmk.gui.graphing import perfometer_info
from cmk.gui.graphing._expression import (
    Constant,
    CriticalOf,
    MaximumOf,
    Metric,
    MetricExpression,
    MinimumOf,
    parse_expression,
    Product,
    WarningOf,
)
from cmk.gui.graphing._graph_specification import (
    HorizontalRule,
    MetricOpOperator,
    MetricOpRRDSource,
)
from cmk.gui.graphing._graph_templates import matching_graph_templates
from cmk.gui.graphing._perfometer import (
    _DualPerfometerSpec,
    _LinearPerfometerSpec,
    _StackedPerfometerSpec,
    LogarithmicPerfometerSpec,
)
from cmk.gui.graphing._utils import (
    _graph_templates_internal,
    graph_info,
    GraphTemplate,
    ScalarDefinition,
    translate_metrics,
)
from cmk.gui.type_defs import Perfdata, PerfDataTuple

_GRAPH_TEMPLATES = [
    GraphTemplate(
        id="1",
        title="Graph 1",
        scalars=[],
        conflicting_metrics=[],
        optional_metrics=[],
        consolidation_function=None,
        range=None,
        omit_zero_metrics=False,
        metrics=[],
    ),
    GraphTemplate(
        id="2",
        title="Graph 2",
        scalars=[],
        conflicting_metrics=[],
        optional_metrics=[],
        consolidation_function=None,
        range=None,
        omit_zero_metrics=False,
        metrics=[],
    ),
]


@pytest.mark.parametrize(
    ("graph_id", "graph_index", "expected_result"),
    [
        pytest.param(
            None,
            None,
            list(enumerate(_GRAPH_TEMPLATES)),
            id="no index and no id",
        ),
        pytest.param(
            None,
            0,
            [(0, _GRAPH_TEMPLATES[0])],
            id="matching index and no id",
        ),
        pytest.param(
            None,
            10,
            [],
            id="non-matching index and no id",
        ),
        pytest.param(
            "2",
            None,
            [(1, _GRAPH_TEMPLATES[1])],
            id="no index and matching id",
        ),
        pytest.param(
            "wrong",
            None,
            [],
            id="no index and non-matching id",
        ),
        pytest.param(
            "1",
            0,
            [(0, _GRAPH_TEMPLATES[0])],
            id="matching index and matching id",
        ),
        pytest.param(
            "2",
            0,
            [],
            id="inconsistent matching index and matching id",
        ),
    ],
)
def test_matching_graph_templates(
    monkeypatch: MonkeyPatch,
    graph_id: str | None,
    graph_index: int | None,
    expected_result: Sequence[tuple[int, GraphTemplate]],
) -> None:
    monkeypatch.setattr(
        gt,
        "get_graph_templates",
        lambda _metrics: _GRAPH_TEMPLATES,
    )
    assert (
        list(
            matching_graph_templates(
                graph_id=graph_id,
                graph_index=graph_index,
                translated_metrics={},
            )
        )
        == expected_result
    )


def test__replace_expressions() -> None:
    perfdata: Perfdata = [PerfDataTuple(n, n, len(n), "", 120, 240, 0, 25) for n in ["load1"]]
    translated_metrics = translate_metrics(perfdata, "check_mk-cpu.loads")
    assert (
        gt._replace_expressions("CPU Load - %(load1:max@count) CPU Cores", translated_metrics)
        == "CPU Load - 25 CPU Cores"
    )


def test__replace_expressions_missing_scalars() -> None:
    perfdata: Perfdata = [
        PerfDataTuple(n, n, len(n), "", None, None, None, None) for n in ["load1"]
    ]
    translated_metrics = translate_metrics(perfdata, "check_mk-cpu.loads")
    assert (
        gt._replace_expressions("CPU Load - %(load1:max@count) CPU Cores", translated_metrics)
        == "CPU Load"
    )


@pytest.mark.parametrize(
    "perf_string, result",
    [
        pytest.param(
            "one=5;;;; power=5;;;; output=5;;;;",
            [],
            id="Unknown thresholds from check",
        ),
        pytest.param(
            "one=5;7;6;; power=5;9;10;; output=5;2;3;;",
            [
                HorizontalRule(7.0, "7.00", "#ffd000", "Warning"),
                HorizontalRule(10.0, "10 W", "#ff3232", "Critical power"),
                HorizontalRule(-2.0, "-2 ", "#ffd000", "Warning output"),
            ],
            id="Thresholds present",
        ),
    ],
)
def test_horizontal_rules_from_thresholds(
    perf_string: str, result: Sequence[HorizontalRule]
) -> None:
    assert (
        gt._horizontal_rules_from_thresholds(
            [
                ScalarDefinition(
                    expression=WarningOf(Metric("one")),
                    title="Warning",
                ),
                ScalarDefinition(
                    expression=CriticalOf(Metric("power")),
                    title="Critical power",
                ),
                ScalarDefinition(
                    expression=Product([WarningOf(Metric("output")), Constant(-1)]),
                    title="Warning output",
                ),
            ],
            metrics.translate_perf_data(perf_string, config=active_config),
        )
        == result
    )


def test_duplicate_graph_templates() -> None:
    idents_by_metrics: dict[tuple[str, ...], list[str]] = {}
    for ident, template in _graph_templates_internal().items():
        expressions = [m.expression for m in template.metrics] + [
            s.expression for s in template.scalars
        ]
        if template.range:
            expressions.extend((template.range.min, template.range.max))

        idents_by_metrics.setdefault(
            tuple(sorted(m.name for e in expressions for m in e.metrics())), []
        ).append(ident)

    assert {tuple(idents) for idents in idents_by_metrics.values() if len(idents) >= 2} == {
        ("livestatus_requests_per_connection", "livestatus_connects_and_requests"),
    }


def test_graph_template_with_layered_areas() -> None:
    # area, area, ... -> two layers
    # area, stack, ... -> one layer
    # stack, stack, ... -> one layer
    @dataclass
    class _GraphTemplateArea:
        pos: list[Literal["area", "stack"]] = field(default_factory=list)
        neg: list[Literal["-area", "-stack"]] = field(default_factory=list)

    areas_by_ident: dict[str, _GraphTemplateArea] = {}
    for ident, template in _graph_templates_internal().items():
        for metric in template.metrics:
            if metric.line_type == "area":
                areas_by_ident.setdefault(ident, _GraphTemplateArea()).pos.append(metric.line_type)
            elif metric.line_type == "stack":
                areas_by_ident.setdefault(ident, _GraphTemplateArea()).pos.append(metric.line_type)
            elif metric.line_type == "-area":
                areas_by_ident.setdefault(ident, _GraphTemplateArea()).neg.append(metric.line_type)
            elif metric.line_type == "-stack":
                areas_by_ident.setdefault(ident, _GraphTemplateArea()).neg.append(metric.line_type)

    templates_with_more_than_one_layer = [
        ident
        for ident, areas in areas_by_ident.items()
        if areas.pos.count("area") > 1 or areas.neg.count("-area") > 1
    ]
    assert not templates_with_more_than_one_layer


def _conditional_perfometer(
    perfometer: (
        _LinearPerfometerSpec
        | LogarithmicPerfometerSpec
        | _DualPerfometerSpec
        | _StackedPerfometerSpec
    ),
) -> Iterator[_LinearPerfometerSpec]:
    if perfometer["type"] == "linear":
        if "condition" in perfometer:
            yield perfometer
    elif perfometer["type"] == "logarithmic":
        pass
    elif perfometer["type"] in ("dual", "stacked"):
        for p in perfometer["perfometers"]:
            yield from _conditional_perfometer(p)


def test_conditional_perfometer() -> None:
    conditional_perfometers: list[_LinearPerfometerSpec] = []
    for perfometer in perfometer_info:
        if not isinstance(perfometer, dict):
            continue
        conditional_perfometers.extend(_conditional_perfometer(perfometer))

    assert not conditional_perfometers


def _is_non_trivial(expressions: Sequence[MetricExpression]) -> bool:
    return any(
        not isinstance(
            e,
            (Constant, Metric, WarningOf, CriticalOf, MinimumOf, MaximumOf),
        )
        for e in expressions
    )


def _perfometer_with_non_trivial_declarations(
    perfometer: (
        _LinearPerfometerSpec
        | LogarithmicPerfometerSpec
        | _DualPerfometerSpec
        | _StackedPerfometerSpec
    ),
) -> Iterator[_LinearPerfometerSpec | LogarithmicPerfometerSpec]:
    if perfometer["type"] == "linear":
        expressions = [parse_expression(s, {}) for s in perfometer["segments"]]
        if (total := perfometer.get("total")) is not None:
            expressions.append(parse_expression(total, {}))
        if (label := perfometer.get("label")) is not None:
            expressions.append(parse_expression(label[0], {}))
        if _is_non_trivial(expressions):
            yield perfometer

    elif perfometer["type"] == "logarithmic":
        if _is_non_trivial([parse_expression(perfometer["metric"], {})]):
            yield perfometer

    elif perfometer["type"] in ("dual", "stacked"):
        for p in perfometer["perfometers"]:
            yield from _perfometer_with_non_trivial_declarations(p)


def test_non_trivial_perfometer_declarations() -> None:
    non_trivial_perfometers: list[_LinearPerfometerSpec | LogarithmicPerfometerSpec] = []
    for perfometer in perfometer_info:
        if not isinstance(perfometer, dict):
            continue
        non_trivial_perfometers.extend(_perfometer_with_non_trivial_declarations(perfometer))
    assert not non_trivial_perfometers


def test_non_trivial_graph_declarations() -> None:
    non_trivial_graphs = []
    for ident, raw_template in graph_info.items():
        template = GraphTemplate.from_template(ident, raw_template)
        expressions = [m.expression for m in template.metrics] + [
            s.expression for s in template.scalars
        ]
        if template.range:
            expressions.extend((template.range.min, template.range.max))
        if _is_non_trivial(expressions):
            non_trivial_graphs.append(ident)

    assert not non_trivial_graphs


def test_graph_templates_with_consolidation_function() -> None:
    assert [
        ident
        for ident, template in _graph_templates_internal().items()
        if template.consolidation_function
    ] == []


@pytest.mark.parametrize(
    "orig_names, scales, expected_operation",
    [
        pytest.param(
            ["metric-name"],
            [1.0],
            MetricOpRRDSource(
                site_id=SiteId("Site-ID"),
                host_name=HostName("HostName"),
                service_name="Service Description",
                metric_name="metric-name",
                consolidation_func_name=None,
                scale=1.0,
            ),
            id="no translation",
        ),
        pytest.param(
            ["metric-name", "old-metric-name"],
            [1.0, 2.0],
            MetricOpOperator(
                operator_name="MERGE",
                operands=[
                    MetricOpRRDSource(
                        site_id=SiteId("Site-ID"),
                        host_name=HostName("HostName"),
                        service_name="Service Description",
                        metric_name="metric-name",
                        consolidation_func_name=None,
                        scale=1.0,
                    ),
                    MetricOpRRDSource(
                        site_id=SiteId("Site-ID"),
                        host_name=HostName("HostName"),
                        service_name="Service Description",
                        metric_name="old-metric-name",
                        consolidation_func_name=None,
                        scale=2.0,
                    ),
                ],
            ),
            id="translation",
        ),
    ],
)
def test__to_metric_operation(
    orig_names: Sequence[str],
    scales: Sequence[int | float],
    expected_operation: MetricOpOperator | MetricOpRRDSource,
) -> None:
    assert (
        gt._to_metric_operation(
            Metric("metric-name"),
            {
                "metric-name": {
                    "orig_name": list(orig_names),
                    "value": 23.5,
                    "scalar": {},
                    "scale": list(scales),
                    "auto_graph": False,
                    "title": "Title",
                    "unit": {
                        "title": "Unit Title",
                        "symbol": "",
                        "render": lambda v: f"{v}",
                        "js_render": "js-render",
                    },
                    "color": "#111111",
                },
            },
            {
                "site": "Site-ID",
                "host_name": "HostName",
                "service_description": "Service Description",
            },
            None,
        )
        == expected_operation
    )
