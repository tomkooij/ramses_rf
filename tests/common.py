#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""RAMSES RF - a RAMSES-II protocol decoder & analyser."""

import json
import logging
import warnings
from pathlib import Path
from random import shuffle

import pytest

from ramses_rf import Gateway
from ramses_rf.helpers import shrink
from ramses_rf.protocol.schemas import SCH_GLOBAL_TRAITS
from ramses_rf.schemas import SCH_GLOBAL_GATEWAY, SCH_GLOBAL_SCHEMAS

# import tracemalloc
# tracemalloc.start()

warnings.filterwarnings("ignore", category=DeprecationWarning)

DEBUG_MODE = False
DEBUG_ADDR = "0.0.0.0"
DEBUG_PORT = 5678

if DEBUG_MODE:
    import debugpy

    if not debugpy.is_client_connected():
        debugpy.listen(address=(DEBUG_ADDR, DEBUG_PORT))
        print(f"Debugger listening on {DEBUG_ADDR}:{DEBUG_PORT}, waiting for client...")
        debugpy.wait_for_client()

logging.disable(logging.WARNING)  # usu. WARNING


TEST_DIR = Path(__file__).resolve().parent  # TEST_DIR = f"{os.path.dirname(__file__)}"


def shuffle_dict(old_dict) -> dict:
    keys = list(old_dict.keys())
    shuffle(keys)
    new_dict = dict()
    for key in keys:
        new_dict.update({key: old_dict[key]})
    return new_dict


@pytest.fixture
async def gwy() -> Gateway:  # NOTE: async to get running loop
    """Return a vanilla system (with a known, minimal state)."""
    gwy = Gateway("/dev/null", config={})
    gwy.config.disable_sending = True
    return gwy


def assert_expected(actual, expected: dict = None) -> None:
    """Compare an actual system state dict against the corresponding expected state."""

    def assert_expected(actual, expect) -> None:
        assert actual == expect

    if expected:
        assert_expected(shrink(actual), shrink(expected))


def assert_expected_set(gwy, expected) -> None:
    """Compare the actual system state against the expected system state."""

    assert_expected(gwy.schema, expected.get("schema"))
    assert_expected(gwy.params, expected.get("params"))
    assert_expected(gwy.status, expected.get("status"))
    assert_expected(gwy.known_list, expected.get("known_list"))


def assert_raises(exception, fnc, *args):
    try:
        fnc(*args)
    except exception:  # as exc:
        pass  # or: assert True
    else:
        assert False


async def load_test_gwy(dir_name, **kwargs) -> Gateway:
    """Create a system state from a packet log (using an optional configuration)."""

    kwargs = SCH_GLOBAL_GATEWAY({k: v for k, v in kwargs.items() if k[:1] != "_"})

    try:
        with open(f"{dir_name}/config.json") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}

    if config:
        kwargs.update(config)

    with open(f"{dir_name}/packet.log") as f:
        gwy = Gateway(None, input_file=f, **kwargs)
        await gwy.start()

    # if hasattr(
    #     gwy.pkt_transport.serial, "mock_devices"
    # ):  # needs ser instance, so after gwy.start()
    #     gwy.pkt_transport.serial.mock_devices = [MockDeviceCtl(gwy, CTL_ID)]

    return gwy


def load_expected_results(dir_name) -> dict:
    """Return the expected (global) schema/params/status & traits (aka known_list)."""

    try:
        with open(f"{dir_name}/schema.json") as f:
            schema = json.load(f)
    except FileNotFoundError:
        schema = {}
    schema = SCH_GLOBAL_SCHEMAS(schema)

    try:
        with open(f"{dir_name}/known_list.json") as f:
            known_list = json.load(f)["known_list"]
    except FileNotFoundError:
        known_list = {}
    known_list = SCH_GLOBAL_TRAITS({"known_list": shrink(known_list)})["known_list"]

    try:
        with open(f"{dir_name}/params.json") as f:
            params = json.load(f)["params"]
    except FileNotFoundError:
        params = {}

    try:
        with open(f"{dir_name}/status.json") as f:
            status = json.load(f)["status"]
    except FileNotFoundError:
        status = {}

    # TODO: do known_list, status
    return {
        "schema": schema,
        "known_list": known_list,
        "params": params,
        "status": status,
    }
