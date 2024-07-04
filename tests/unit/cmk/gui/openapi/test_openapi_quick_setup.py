#!/usr/bin/env python3
# Copyright (C) 2024 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

import json
from typing import Any

import pytest

from tests.testlib.rest_api_client import ClientRegistry

from cmk.utils import paths

from cmk.ccc import version

cloud_only = pytest.mark.skipif(
    version.edition(paths.omd_root) is not version.Edition.CME,
    reason="Test data differs per edition",
)


# TODO Once all the formspecs are implemented, this can be removed and the correct data can be added
def remove_keys(obj: Any, keys_to_remove: set[str]) -> Any:
    if isinstance(obj, dict):
        return {
            key: remove_keys(value, keys_to_remove)
            for key, value in obj.items()
            if key not in keys_to_remove
        }

    if isinstance(obj, list):
        return [remove_keys(item, keys_to_remove) for item in obj]

    return obj


def quick_setup_test_data() -> dict:
    with open("tests/unit/cmk/gui/openapi/quick_setup_test_data.json") as f:
        return json.load(f)


@pytest.mark.usefixtures("patch_theme")
def test_get_overview(clients: ClientRegistry) -> None:
    resp = clients.QuickSetup.get_overview("aws_quick_setup")
    resp_modified = remove_keys(obj=resp.json, keys_to_remove={"html", "varprefix"})
    assert resp_modified == {
        "quick_setup_id": "aws_quick_setup",
        "overviews": [
            {
                "stage_id": 1,
                "title": "Prepare AWS for Checkmk",
                "sub_title": None,
            },
            {
                "stage_id": 2,
                "title": "Configure host and regions",
                "sub_title": "Name your host, define the path and select the regions you would like to monitor",
            },
            {
                "stage_id": 3,
                "title": "Configure services to monitor",
                "sub_title": "Select and configure AWS services you would like to monitor",
            },
            {
                "stage_id": 4,
                "title": "Review and run service discovery",
                "sub_title": "Review your configuration, run and preview service discovery",
            },
        ],
        "stage": {
            "stage_id": 1,
            "validation_errors": [],
            "stage_summary": [],
            "components": quick_setup_test_data()["stage_1"],
        },
    }


def test_get_overview_non_existing_quicksetup_id(clients: ClientRegistry) -> None:
    clients.QuickSetup.get_overview("frodo", expect_ok=False).assert_status_code(404)


@pytest.mark.usefixtures("patch_theme")
def test_send_aws_stage_one(clients: ClientRegistry) -> None:
    resp = clients.QuickSetup.send_stage_retrieve_next(
        quick_setup_id="aws_quick_setup",
        stages=[
            {
                "stage_id": 1,
                "form_data": {
                    "aws_account_name": {
                        "account_name": "nombre_de_cuenta_de_aws",
                    },
                    "credentials": {
                        "access_key_id": "identificación_de_clave_de_acceso",
                        "secret_access_key": {
                            "input_context": {
                                "explicit": "clave de acceso secreta",
                            },
                        },
                    },
                },
            }
        ],
    )
    resp_modified = remove_keys(obj=resp.json, keys_to_remove={"html", "varprefix"})
    assert resp_modified == {
        "stage_id": 2,
        "validation_errors": [],
        "stage_summary": [],
        "components": quick_setup_test_data()["stage_2"],
    }


@cloud_only
def test_send_aws_stage_two(clients: ClientRegistry) -> None:
    resp = clients.QuickSetup.send_stage_retrieve_next(
        quick_setup_id="aws_quick_setup",
        stages=[
            {
                "stage_id": 1,
                "form_data": {
                    "aws_account_name": {
                        "account_name": "nombre_de_cuenta_de_aws",
                    },
                    "credentials": {
                        "access_key_id": "identificación_de_clave_de_acceso",
                        "secret_access_key": {
                            "input_context": {},
                        },
                    },
                },
            },
            {
                "stage_id": 2,
                "form_data": {
                    "configure_host_and_region": {
                        "regions_to_monitor": {
                            "input_context": {},
                        },
                    },
                },
            },
        ],
    )
    resp_modified = remove_keys(obj=resp.json, keys_to_remove={"html", "varprefix"})
    assert resp_modified == {
        "stage_id": 3,
        "validation_errors": [],
        "stage_summary": [],
        "components": quick_setup_test_data()["stage_3"],
    }


@cloud_only
def test_send_aws_stage_three(clients: ClientRegistry) -> None:
    _resp = clients.QuickSetup.send_stage_retrieve_next(
        quick_setup_id="aws_quick_setup",
        stages=[
            {
                "stage_id": 1,
                "form_data": {
                    "aws_account_name": {
                        "account_name": "nombre_de_cuenta_de_aws",
                    },
                    "credentials": {
                        "access_key_id": "identificación_de_clave_de_acceso",
                        "secret_access_key": {
                            "input_context": {},
                        },
                    },
                },
            },
            {
                "stage_id": 2,
                "form_data": {
                    "configure_host_and_region": {
                        "regions_to_monitor": {
                            "input_context": {},
                        },
                    },
                },
            },
            {
                "stage_id": 3,
                "form_data": {  # TODO No idea what this data looks like.
                    "configure_services_to_monitor": {}
                },
            },
        ],
        expect_ok=False,
    )
    # assert resp.json == {
    #     "stage_id": 4,
    #     "validation_errors": [],
    #     "stage_summary": [],
    #     "components": [],
    # }


@cloud_only
def test_send_aws_stage_four(clients: ClientRegistry) -> None:
    resp = clients.QuickSetup.send_stage_retrieve_next(
        quick_setup_id="aws_quick_setup",
        stages=[
            {"stage_id": 1, "form_data": {}},
            {"stage_id": 2, "form_data": {}},
            {"stage_id": 3, "form_data": {}},
            {"stage_id": 4, "form_data": {}},
        ],
    )
    assert resp.json == {
        "stage_id": -1,
        "validation_errors": [],
        "stage_summary": [],
        "components": [],
    }
