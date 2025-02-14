#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""RAMSES RF - a RAMSES-II protocol decoder & analyser.

Test the payload parsers.
"""

from pathlib import Path, PurePath

from ramses_rf.protocol.message import Message
from ramses_rf.protocol.packet import Packet
from tests.common import gwy  # noqa: F401
from tests.common import TEST_DIR

WORK_DIR = f"{TEST_DIR}/parsers"


def id_fnc(param):
    return PurePath(param).name


def pytest_generate_tests(metafunc):
    metafunc.parametrize("f_name", sorted(Path(WORK_DIR).glob("*.log")), ids=id_fnc)


def _proc_log_line(gwy, pkt_line):  # noqa: F811
    pkt_line, pkt_dict, *_ = list(
        map(str.strip, pkt_line.split("#", maxsplit=1) + [""])
    )

    if pkt_line:
        msg = Message(gwy, Packet.from_file(gwy, pkt_line[:26], pkt_line[27:]))
        assert not pkt_dict or msg.payload == eval(pkt_dict)


def test_parsers_from_log_files(gwy, f_name):  # noqa: F811
    with open(f_name) as f:
        while line := (f.readline()):
            _proc_log_line(gwy, line)
