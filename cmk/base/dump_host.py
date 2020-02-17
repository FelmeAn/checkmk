#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

import time
from typing import Optional  # pylint: disable=unused-import

import six

import cmk.utils.tty as tty
import cmk.utils.render
from cmk.utils.encoding import make_utf8

import cmk.base.config as config
import cmk.base.core_config as core_config
import cmk.base.console as console
import cmk.base.data_sources as data_sources
import cmk.base.ip_lookup as ip_lookup
import cmk.base.check_table as check_table
import cmk.base.checking as checking
from cmk.utils.type_defs import HostName  # pylint: disable=unused-import
from cmk.base.check_utils import CheckParameters  # pylint: disable=unused-import


def dump_host(hostname):
    # type: (HostName) -> None
    config_cache = config.get_config_cache()
    host_config = config_cache.get_host_config(hostname)

    console.output("\n")
    if host_config.is_cluster:
        nodes = host_config.nodes
        if nodes is None:
            raise RuntimeError()
        color = tty.bgmagenta
        add_txt = " (cluster of " + (", ".join(nodes)) + ")"
    else:
        color = tty.bgblue
        add_txt = ""
    console.output("%s%s%s%-78s %s\n" %
                   (color, tty.bold, tty.white, hostname + add_txt, tty.normal))

    ipaddress = _ip_address_for_dump_host(host_config)

    addresses = ""  # type: Optional[str]
    if not host_config.is_ipv4v6_host:
        addresses = ipaddress
    else:
        try:
            if host_config.is_ipv6_primary:
                secondary = _ip_address_for_dump_host(host_config, 4)
            else:
                secondary = _ip_address_for_dump_host(host_config, 6)
        except Exception:
            secondary = "X.X.X.X"

        addresses = "%s, %s" % (ipaddress, secondary)
        if host_config.is_ipv6_primary:
            addresses += " (Primary: IPv6)"
        else:
            addresses += " (Primary: IPv4)"

    console.output(tty.yellow + "Addresses:              " + tty.normal +
                   (addresses if addresses is not None else "No IP") + "\n")

    tag_template = tty.bold + "[" + tty.normal + "%s" + tty.bold + "]" + tty.normal
    tags = [(tag_template % ":".join(t)) for t in sorted(host_config.tag_groups.items())]
    console.output(tty.yellow + "Tags:                   " + tty.normal + ", ".join(tags) + "\n")

    labels = [
        (tag_template % ":".join(l)).encode("utf-8") for l in sorted(host_config.labels.items())
    ]
    console.output(tty.yellow + "Labels:                 " + tty.normal + ", ".join(labels) + "\n")

    # TODO: Clean this up once cluster parent handling has been moved to HostConfig
    if host_config.is_cluster:
        parents_list = host_config.nodes
        if parents_list is None:
            raise RuntimeError()
    else:
        parents_list = host_config.parents
    if len(parents_list) > 0:
        console.output(tty.yellow + "Parents:                " + tty.normal +
                       ", ".join(parents_list) + "\n")
    console.output(tty.yellow + "Host groups:            " + tty.normal +
                   make_utf8(", ".join(host_config.hostgroups)) + "\n")
    console.output(tty.yellow + "Contact groups:         " + tty.normal +
                   make_utf8(", ".join(host_config.contactgroups)) + "\n")

    agenttypes = []
    sources = data_sources.DataSources(hostname, ipaddress)
    for source in sources.get_data_sources():
        agenttypes.append(source.describe())

    if host_config.is_ping_host:
        agenttypes.append('PING only')

    console.output(tty.yellow + "Agent mode:             " + tty.normal)
    console.output(sources.describe_data_sources() + "\n")

    console.output(tty.yellow + "Type of agent:          " + tty.normal)
    if len(agenttypes) == 1:
        console.output(agenttypes[0] + "\n")
    else:
        console.output("\n  ")
        console.output("\n  ".join(agenttypes) + "\n")

    console.output(tty.yellow + "Services:" + tty.normal + "\n")

    headers = ["checktype", "item", "params", "description", "groups"]
    colors = [tty.normal, tty.blue, tty.normal, tty.green, tty.normal]

    table_data = []
    for service in sorted(check_table.get_check_table(hostname).values(),
                          key=lambda s: s.description):
        table_data.append([
            service.check_plugin_name,
            six.ensure_str("None" if service.item is None else service.item),
            _evaluate_params(service.parameters),
            six.ensure_str(service.description),
            ",".join(config_cache.servicegroups_of_service(hostname, service.description))
        ])

    tty.print_table(headers, colors, table_data, "  ")


def _evaluate_params(params):
    # type: (CheckParameters) -> str
    if not isinstance(params, cmk.base.config.TimespecificParamList):
        return "%r" % (params,)

    current_params = checking.determine_check_params(params)
    return "Timespecific parameters at %s: %r" % (cmk.utils.render.date_and_time(
        time.time()), current_params)


def _ip_address_for_dump_host(host_config, family=None):
    # type: (config.HostConfig, Optional[int]) -> Optional[str]
    if host_config.is_cluster:
        try:
            return ip_lookup.lookup_ip_address(host_config.hostname, family)
        except Exception:
            return ""

    try:
        return ip_lookup.lookup_ip_address(host_config.hostname, family)
    except Exception:
        return core_config.fallback_ip_for(host_config, family)
