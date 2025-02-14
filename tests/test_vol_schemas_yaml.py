#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""RAMSES RF - a RAMSES-II protocol decoder & analyser.

Test the configuration parsers.
"""


import pytest
import voluptuous as vol
import yaml

from ramses_rf.protocol.schemas import (
    SCH_ENGINE,
    SCH_GLOBAL_TRAITS,
    SCH_GLOBAL_TRAITS_DICT,
    SCH_PACKET_LOG,
    SCH_PACKET_LOG_DICT,
    SCH_SERIAL_PORT,
    SCH_SERIAL_PORT_DICT,
)
from ramses_rf.schemas import (
    SCH_GATEWAY,
    SCH_GLOBAL_SCHEMAS,
    SCH_GLOBAL_SCHEMAS_DICT,
    SCH_RESTORE_CACHE,
    SCH_RESTORE_CACHE_DICT,
)

# TODO: These schema pass testing, but shouldn't

_FAIL_BUT_VALID = (
    """
    01:333333: {is_vcs: true}
    """,
    """
    02:333333: {is_vcs: true}
    """,
)
_PASS_BUT_INVALID = (
    """
    main_tcs: 01:111111  # no TCS schema
    """,
    """
    known_list:
      01:111111: {}
    block_list:
      01:111111: {}  # also in known_list
    """,
)


def no_duplicates_constructor(loader, node, deep=False):
    """Check for duplicate keys."""
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                f"Duplicate key: {key} ('{mapping[key]}' overwrites '{value_node}')"
            )
        value = loader.construct_object(value_node, deep=deep)
        mapping[key] = value
    return loader.construct_mapping(node, deep)


class CheckForDuplicatesLoader(yaml.Loader):
    """Local class to prevent pollution of global yaml.Loader."""

    pass


CheckForDuplicatesLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_duplicates_constructor
)


def _test_schema(validator: vol.Schema, schema: str) -> dict:
    # cant use yaml.safe_load(schema): PyYAML silently swallows duplicate dict keys!
    return validator(yaml.load(schema, CheckForDuplicatesLoader))


def _test_schema_bad(validator: vol.Schema, schema: str) -> None:
    global test_schemas_bad_failed
    try:
        _test_schema(validator, schema)
    except (vol.MultipleInvalid, yaml.YAMLError):
        pass
    else:
        test_schemas_bad_failed = True
        raise TypeError(f"should *not* be valid YAML, but is: {schema}")


def _test_schema_good(validator: vol.Schema, schema: str) -> dict:
    global test_schemas_good_failed
    try:
        _test_schema(validator, schema)
    except (vol.MultipleInvalid, yaml.YAMLError) as exc:
        test_schemas_good_failed = True
        raise TypeError(f"should be valid YAML, but isn't ({exc}): {schema}")


ENGINE_BAD = (
    """
    #  expected a dictionary
    """,
    """
    other_key: null  # extra keys not allowed @ data['other_key']
    """,
    """
    disable_sending: null
    """,
    """
    evofw_flag: !V
    """,
    """
    disable_sending: null
    enforce_known_list: null
    evofw_flag: null
    use_regex: null
    """,
)
ENGINE_GOOD = (
    """
    {}
    """,
    """
    disable_sending: false
    """,
    """
    disable_sending: false
    enforce_known_list: false
    evofw_flag: null
    use_regex: {}
    """,
    """
    disable_sending: true
    enforce_known_list: true
    evofw_flag: "!V"
    use_regex:
      inbound: {}
      outbound: {}
    """,
)


@pytest.mark.parametrize("index", range(len(ENGINE_BAD)))
def test_engine_bad(index, schemas=ENGINE_BAD):
    _test_schema_bad(SCH_ENGINE, schemas[index])


@pytest.mark.parametrize("index", range(len(ENGINE_GOOD)))
def test_engine_good(index, schemas=ENGINE_GOOD):
    _test_schema_good(SCH_ENGINE, schemas[index])


GATEWAY_BAD = (
    """
    #  expected a dictionary
    """,
    """
    other_key: null  # extra keys not allowed @ data['other_key']
    """,
    """
    disable_discovery: null
    """,
    """
    max_zones: 19
    """,
    """
    disable_discovery: null
    enable_eavesdrop: null
    max_zones: null
    reduce_processing: null
    use_aliases: null
    use_native_ot: null
    """,
)
GATEWAY_GOOD = (
    """
    {}
    """,
    """
    disable_discovery: false
    """,
    """
    max_zones: 16
    """,
    """
    disable_discovery: false
    enable_eavesdrop: false
    max_zones: 12
    reduce_processing: 0
    use_aliases: false
    use_native_ot: false
    """,
    """
    disable_discovery: true
    enable_eavesdrop: true
    max_zones: 3
    reduce_processing: 2
    use_aliases: true
    use_native_ot: true
    """,
)


@pytest.mark.parametrize("index", range(len(GATEWAY_BAD)))
def test_gateway_bad(index, schemas=GATEWAY_BAD):
    _test_schema_bad(SCH_GATEWAY, schemas[index])


@pytest.mark.parametrize("index", range(len(GATEWAY_GOOD)))
def test_gateway_good(index, schemas=GATEWAY_GOOD):
    _test_schema_good(SCH_GATEWAY, schemas[index])


KNOWN_LIST_BAD = (
    """
    #  expected a dictionary
    """,
    """
    other_key: null  # extra keys not allowed @ data['other_key']
    """,
    """
    known_list: []  # expected a dictionary for dictionary value @ data['known_list']
    """,
    """
    known_list:
      01:111111: {class: xxx}
    """,
    """
    known_list:
      01:111111: {class: CTL, notes: this is invalid note}
      02:111111: {class: UFC}
    """,
    """
    known_list:
      01:111111: {class: CTL}
      01:111111: {class: UFC}
    """,
    """
    known_list:
      05:111111: {class: REM, scheme: xxxxxx}
    """,
)
KNOWN_LIST_GOOD = (
    """
    {}
    """,
    """
    known_list: {}
    """,
    """
    known_list: {}
    block_list: {}
    """,
    """
    known_list:
      01:111111: {}
    block_list:
      01:222222: {}
    """,
    """
    known_list:
      01:111111: {class: CTL}
      02:111111: {class: UFC}
      03:111111: {class: THM, faked: true}
      04:111111: {class: TRV}
      07:111111: {class: DHW, faked: true}
      10:111111: {class: OTB}
      12:111111: {class: THM}
      13:111111: {class: BDR}
      17:111111: {class: OUT, faked: true}
      18:111111: {class: HGI}
      22:111111: {class: THM}
      23:111111: {class: THM}
      30:111111: {class: RFG}
      34:111111: {class: THM, _note: this is a note}
    """,
    """
    known_list:
      01:111111: {class: FAN}
      02:111111: {class: RFS}
      03:111111: {class: CO2, faked: true}
      04:111111: {class: HUM, faked: true}
      05:111111: {class: REM, faked: true, scheme: nuaire}
      06:111111:
        class: DIS
        scheme: orcon
        _note: this is a note
    """,
)


@pytest.mark.parametrize("index", range(len(KNOWN_LIST_BAD)))
def test_known_list_bad(index, schemas=KNOWN_LIST_BAD):
    _test_schema_bad(SCH_GLOBAL_TRAITS, schemas[index])


@pytest.mark.parametrize("index", range(len(KNOWN_LIST_GOOD)))
def test_known_list_good(index, schemas=KNOWN_LIST_GOOD):
    _test_schema_good(SCH_GLOBAL_TRAITS, schemas[index])


PACKET_LOG_BAD = (
    """
    #  expected a dictionary
    """,
    """
    other_key: null  # extra keys not allowed @ data['other_key']
    """,
    """
    packet_log:
      file_name: null  # expected str for dictionary value @ data['packet_log']['file_name']
    """,
    """
    packet_log:  # required key not provided @ data['packet_log']['file_name']
      rotate_backups: 7
      rotate_bytes: 204800
    """,
)
PACKET_LOG_GOOD = (
    """
    {}
    """,
    """
    packet_log: packet.log
    """,
    """
    packet_log: null  # expected str for dictionary value @ data['packet_log']
    """,
    """
    packet_log:
      file_name: packet.log
    """,
    """
    packet_log:
      file_name: packet.log
      rotate_backups: 7
    """,
    """
    packet_log:
      file_name: packet.log
      rotate_bytes: 204800
    """,
    """
    packet_log:
      file_name: packet.log
      rotate_backups: 7
      rotate_bytes: 204800
    """,
)


@pytest.mark.parametrize("index", range(len(PACKET_LOG_BAD)))
def test_packet_log_bad(index, schemas=PACKET_LOG_BAD):
    _test_schema_bad(SCH_PACKET_LOG, schemas[index])


@pytest.mark.parametrize("index", range(len(PACKET_LOG_GOOD)))
def test_packet_log_good(index, schemas=PACKET_LOG_GOOD):
    _test_schema_good(SCH_PACKET_LOG, schemas[index])


RESTORE_CACHE_BAD = (
    """
    #  expected a dictionary
    """,
    """
    other_key: null  # extra keys not allowed @ data['other_key']
    """,
    """
    restore_cache: none  # should be boolean
    """,
    """
    restore_cache: true
      restore_schema: true  # yaml.scanner.ScannerError
    """,
    """
    restore_schema: true  # should be: restore_cache: restore_schema: true
    """,
    """
    restore_state: false  # should be: restore_cache: restore_state: true
    """,
)
RESTORE_CACHE_GOOD = (
    """
    {}
    """,
    """
    restore_cache: false
    """,
    """
    restore_cache: true
    """,
    """
    restore_cache:
      restore_schema: true
    """,
    """
    restore_cache:
      restore_state:  true
    """,
    """
    restore_cache:
      restore_schema: true
      restore_state:  false
    """,
    """
    restore_cache:
      restore_schema: false
      restore_state:  true
    """,
)


@pytest.mark.parametrize("index", range(len(RESTORE_CACHE_BAD)))
def test_restore_cache_bad(index, schemas=RESTORE_CACHE_BAD):
    _test_schema_bad(SCH_RESTORE_CACHE, schemas[index])


@pytest.mark.parametrize("index", range(len(RESTORE_CACHE_GOOD)))
def test_restore_cache_good(index, schemas=RESTORE_CACHE_GOOD):
    _test_schema_good(SCH_RESTORE_CACHE, schemas[index])


SERIAL_PORT_BAD = (
    """
    #  expected a dictionary
    """,
    """
    {}  # required key not provided @ data['serial_port']
    """,
    """
    other_key: null  # extra keys not allowed @ data['other_key']
    """,
    """
    serial_name: /dev/ttyMOCK  # should be: serial_port:
    """,
    """
    serial_port: /dev/ttyMOCK  # yaml.parser.ParserError
      baudrate: 115200  # default
    """,
    """
    serial_port:
      port_name: /dev/ttyMOCK
      baud_rate: 57600  # should be: baudrate:
    """,
    """
    serial_port:
      port_name: /dev/ttyMOCK
        baudrate: 57600  # yaml.parser.ScannerError
    """,
)
SERIAL_PORT_GOOD = (
    """
    serial_port: /dev/ttyMOCK
    """,
    """
    serial_port:
      port_name: /dev/ttyMOCK
    """,
    """
    serial_port:
      port_name: /dev/ttyMOCK
      baudrate: 115200  # default
    """,
    """
    serial_port:
      port_name: /dev/ttyMOCK
      baudrate: 57600
    """,
    """
    serial_port:
      port_name: /dev/ttyMOCK
      baudrate: 57600
    """,
    """
    serial_port:
      port_name: /dev/ttyMOCK
      baudrate: 57600
      dsrdtr: false
      rtscts: false
      timeout: 0
      xonxoff: true
    """,
)


@pytest.mark.parametrize("index", range(len(SERIAL_PORT_BAD)))
def test_serial_port_bad(index, schemas=SERIAL_PORT_BAD):
    _test_schema_bad(SCH_SERIAL_PORT, schemas[index])


@pytest.mark.parametrize("index", range(len(SERIAL_PORT_GOOD)))
def test_serial_port_good(index, schemas=SERIAL_PORT_GOOD):
    _test_schema_good(SCH_SERIAL_PORT, schemas[index])


SCHEMAS_TCS_BAD = (
    """
    #  expected a dictionary
    """,
    """
    other_key: null  # extra keys not allowed @ data['other_key']
    """,
    """
    01:111111:  # expected a dictionary for dictionary value @ data['01:111111']
    """,
    """
    01:111111:
      system:  # expected a dictionary for dictionary value @ data['01:111111']['system']
    """,
    """
    13:111111:  # should be: 01:111111
      system: {}  # The ventilation control system schema must include at least one of [remotes, sensors] @ data['13:111111']
    """,
    """
    01:111111:
      system:
        appliance_control: 10:111111
      zones:  # should be "00"
        00: {}  # extra keys not allowed @ data['01:111111']['zones'][0]
    """,
    """
    01:111111:
      system:
        appliance_control: 10:111111
      zones:
        "00":  # extra keys not allowed @ data['01:111111']['zones']['00']
    """,
    """
    01:111111:
      system:
        appliance_control: 10:111111
      zones:
        "1C": {}  # extra keys not allowed @ data['01:111111']['zones']['1C']
    """,
    """
    01:111111:
      system:
        appliance_control: 10:111111
    01:111111: {remotes: [29:111111, 29:222222]}
    """,
)
SCHEMAS_TCS_GOOD = (
    """
    {}
    """,
    """
    01:111111: {}
    """,
    """
    01:111111: {is_tcs: true}
    """,
    """
    01:111111:
      system: {}
    """,
    """
    01:111111:
      system:
        appliance_control:
    """,
    """
    01:111111:
      system:
        appliance_control: null
    """,
    """
    01:111111:
      system:
        appliance_control: 10:111111
    """,
    """
    01:111111:
      system:
        appliance_control: 10:111111
    01:222222:
      system:
        appliance_control: 13:222222
    """,
    """
    main_tcs: null
    01:111111:
      system:
        appliance_control: 10:111111
      zones:
        "0B":
          sensor: 01:111111
    """,
    """
    main_tcs: 01:222222
    01:111111:
      system:
        appliance_control: 10:111111
      zones:
        "00": {}
        "01": {sensor: 03:111111}
        "02": {actuators: [04:111111, 04:222222]}
        "03": {actuators: [13:111111, 13:222222]}
    """,
    """
    main_tcs: 01:222222
    01:111111:
      system:
        appliance_control: 10:111111
    01:222222:
      system:
        appliance_control: 10:222222
    """,
)


@pytest.mark.parametrize("index", range(len(SCHEMAS_TCS_BAD)))
def test_schemas_tcs_bad(index, schemas=SCHEMAS_TCS_BAD):
    _test_schema_bad(SCH_GLOBAL_SCHEMAS, schemas[index])


@pytest.mark.parametrize("index", range(len(SCHEMAS_TCS_GOOD)))
def test_schemas_tcs_good(index, schemas=SCHEMAS_TCS_GOOD):
    _test_schema_good(SCH_GLOBAL_SCHEMAS, schemas[index])


SCHEMAS_VCS_BAD = (
    """
    #  expected a dictionary
    """,
    """
    other_key: null  # extra keys not allowed @ data['other_key']
    """,
    """
    32:111111:  # expected a dictionary for dictionary value @ data['01:111111']
    """,
    """
    32:111111: {is_vcs: true}
    """,
    """
    01:111111:
      remotes: []
      is_tcs: true
    """,
    """
    32:111111:  # should not duplicate device_id
      remotes: [29:111111, 29:111111]  # not a valid value for dictionary value @ data['32:111111']['remotes']
    """,
    """
    32:111111: {remotes: [29:111111, 29:222222]}
    32:111111: {remotes: [29:111111, 29:222222]}  # has duplicate key
    32:333333: {remotes: [29:111111, 29:222222]}
    """,
)
SCHEMAS_VCS_GOOD = (
    """
    {}
    """,
    """
    01:333333:
      remotes: []
    """,
    """
    32:111111:
      remotes: []
    """,
    """
    32:111111:
      remotes: []
      is_vcs: true
    """,
    """
    32:111111:
      remotes: [29:111111]
    """,
    """
    32:111111:
      remotes: [29:111111, 29:222222]
      sensors: [29:111111, 29:333333]
      is_vcs: true
    """,
    """
    32:111111: {remotes: [29:111111, 29:222222]}
    32:222222: {remotes: [29:111111, 29:222222]}
    32:333333: {remotes: [29:111111, 29:222222]}
    """,
)


@pytest.mark.parametrize("index", range(len(SCHEMAS_VCS_BAD)))
def test_schemas_vcs_bad(index, schemas=SCHEMAS_VCS_BAD):
    _test_schema_bad(SCH_GLOBAL_SCHEMAS, schemas[index])


@pytest.mark.parametrize("index", range(len(SCHEMAS_VCS_GOOD)))
def test_schemas_vcs_good(index, schemas=SCHEMAS_VCS_GOOD):
    _test_schema_good(SCH_GLOBAL_SCHEMAS, schemas[index])


SCHEMAS_MIXED_BAD = tuple(x + y for x in SCHEMAS_TCS_GOOD for y in SCHEMAS_VCS_BAD[1:])
SCHEMAS_MIXED_BAD += tuple(
    x + y for x in SCHEMAS_TCS_BAD[1:] for y in SCHEMAS_VCS_GOOD[1:]
)
SCHEMAS_MIXED_GOOD = tuple(
    x + y for x in SCHEMAS_TCS_GOOD[1:] for y in SCHEMAS_VCS_GOOD[1:]
)


test_schemas_bad_failed = False
test_schemas_good_failed = False


@pytest.mark.parametrize("index", range(len(SCHEMAS_MIXED_BAD)))
def test_schemas_mixed_bad(index, schemas=SCHEMAS_MIXED_BAD):
    global test_schemas_bad_failed
    if not test_schemas_bad_failed:
        _test_schema_bad(SCH_GLOBAL_SCHEMAS, schemas[index])


@pytest.mark.parametrize("index", range(len(SCHEMAS_MIXED_GOOD)))
def test_schemas_mixed_good(index, schemas=SCHEMAS_MIXED_GOOD):
    global test_schemas_good_failed
    if not test_schemas_good_failed:
        _test_schema_good(SCH_GLOBAL_SCHEMAS, schemas[index])


SCHEMAS_HASS_BAD = (
    """
    #  expected a dictionary
    """,
    """
    {}
    """,
    """
    other_key: null  # extra keys not allowed @ data['other_key']
    """,
    """
ramses_rf:
  serial_port: /dev/ttyUSB0

  ramses_rf:
    enforce_known_list: true
    """,
    """
ramses_cc:
  serial_port: /dev/ttyUSB0

  ramses_cc:
    enforce_known_list: true
    """,
    """
ramses_cc:
  serial_port: /dev/ttyUSB0

  schema:  # this not used
    01:111111:  # Temperature control system (e.g. evohome)
      system:
        appliance_control: 10:123446
      zones:
        "07": {sensor: 01:111111}

    orphans_hvac: [30:111111, 32:333333, 32:555555, 32:666666]
    """,
)
SCHEMAS_HASS_GOOD = (
    """
ramses_cc:
  serial_port: /dev/ttyACM0
    """,
    """
ramses_cc:
  serial_port: /dev/ttyUSB0
  restore_cache: false
  known_list:
    """,
    """
ramses_cc:
  serial_port: rfc2217://localhost:5001
  restore_cache:
    restore_schema: true
  known_list: {}
  block_list:
    """,
    """
ramses_cc:
  serial_port: /dev/serial/by-id/usb-SHK_NANO_CUL_868-if00-port0
  restore_cache:
    restore_state: true
  known_list:
    30:111111:              # becomes empty {}
    32:333333: {}           #
    32:555555: {class: CO2} #
  block_list: {}
    """,
    """
ramses_cc:
  serial_port: /dev/serial/by-id/usb-SHK_NANO_CUL_868-if00-port0

  scan_interval: 300

  restore_cache:
    restore_schema: true
    restore_state: true

  packet_log:
    file_name: packet.log
    rotate_backups: 28

  ramses_rf:
    enforce_known_list: true

  main_tcs: 01:111111

  01:111111:  # Temperature control system (e.g. evohome)
    system:
      appliance_control: 10:123446
    zones:
      "07": {sensor: 01:111111}

  orphans_heat: [02:123456]
  orphans_hvac: [30:111111, 32:333333, 32:555555, 32:666666]

  known_list:
    30:111111: {class: FAN}               # Orcon HRU
    32:333333: {class: REM, faked: true}  # an impersonatable remote
    32:555555: {class: CO2, faked: true}  # a fully faked sensor
    32:666666: {class: HUM}

  block_list:
    23:111111: {}

  advanced_features:
    send_packet: true
    """,
)


SCH_DOMAIN_CONFIG = (  # as per ramses_cc.schemas, TODO: add advanced_features
    vol.Schema(
        {
            vol.Optional("ramses_rf", default={}): SCH_GATEWAY,
            vol.Optional("scan_interval"): int,
            vol.Optional("advanced_features", default={}): dict,
        },
        extra=vol.PREVENT_EXTRA,
    )
    .extend(SCH_SERIAL_PORT_DICT)
    .extend(SCH_PACKET_LOG_DICT)
    .extend(SCH_RESTORE_CACHE_DICT)
    .extend(SCH_GLOBAL_SCHEMAS_DICT)
    .extend(SCH_GLOBAL_TRAITS_DICT)
)
SCH_GLOBAL_HASS = vol.Schema(
    {vol.Required("ramses_cc"): SCH_DOMAIN_CONFIG}, extra=vol.PREVENT_EXTRA
)


@pytest.mark.parametrize("index", range(len(SCHEMAS_HASS_BAD)))
def test_schemas_hass_bad(index, schemas=SCHEMAS_HASS_BAD):
    _test_schema_bad(SCH_GLOBAL_HASS, schemas[index])


@pytest.mark.parametrize("index", range(len(SCHEMAS_HASS_GOOD)))
def test_schemas_hass_good(index, schemas=SCHEMAS_HASS_GOOD):
    _test_schema_good(SCH_GLOBAL_HASS, schemas[index])
