#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""A CLI for the ramses_rf library.

ramses_rf is used to parse/process Honeywell's RAMSES-II packets.
"""

# import cProfile
# import pstats

import asyncio
import json
import logging
import sys

import click
from colorama import Fore, Style
from colorama import init as colorama_init

from ramses_rf import Gateway, GracefulExit, is_valid_dev_id
from ramses_rf.const import DONT_CREATE_MESSAGES, SZ_ZONE_IDX
from ramses_rf.discovery import GET_FAULTS, GET_SCHED, SET_SCHED, spawn_scripts
from ramses_rf.helpers import merge
from ramses_rf.protocol.exceptions import EvohomeError
from ramses_rf.protocol.logger import CONSOLE_COLS, DEFAULT_DATEFMT, DEFAULT_FMT
from ramses_rf.protocol.schemas import (
    SZ_DISABLE_SENDING,
    SZ_ENFORCE_KNOWN_LIST,
    SZ_EVOFW_FLAG,
    SZ_KNOWN_LIST,
    SZ_SERIAL_PORT,
)
from ramses_rf.schemas import (
    SCH_GLOBAL_GATEWAY,
    SZ_CONFIG,
    SZ_DISABLE_DISCOVERY,
    SZ_ENABLE_EAVESDROP,
    SZ_REDUCE_PROCESSING,
)
from tests_rf.mock import MockGateway

# skipcq: PY-W2000
from ramses_rf.const import (  # noqa: F401, isort: skip, pylint: disable=unused-import
    I_,
    RP,
    RQ,
    W_,
    DEV_TYPE_MAP,
    Code,
)

DEV_MODE = False

SZ_DEBUG_MODE = "debug_mode"
DEBUG_ADDR = "0.0.0.0"
DEBUG_PORT = 5678

SZ_INPUT_FILE = "input_file"


# DEFAULT_SUMMARY can be: True, False, or None
SHOW_SCHEMA = False
SHOW_PARAMS = False
SHOW_STATUS = False
SHOW_KNOWNS = False
SHOW_TRAITS = False
SHOW_CRAZYS = False

PRINT_STATE = False  # print engine state
# GET_STATE = False  # get engine state
# SET_STATE = False  # set engine state

# this is called after import colorlog to ensure its handlers wrap the correct streams
logging.basicConfig(level=logging.WARNING, format=DEFAULT_FMT, datefmt=DEFAULT_DATEFMT)


EXECUTE = "execute"
LISTEN = "listen"
MONITOR = "monitor"
PARSE = "parse"


COLORS = {
    I_: Fore.GREEN,
    RP: Fore.CYAN,
    RQ: Fore.CYAN,
    W_: Style.BRIGHT + Fore.MAGENTA,
}

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])

LIB_KEYS = tuple(SCH_GLOBAL_GATEWAY({}).keys()) + (SZ_SERIAL_PORT,)
LIB_CFG_KEYS = tuple(SCH_GLOBAL_GATEWAY({})[SZ_CONFIG].keys()) + (SZ_EVOFW_FLAG,)


def normalise_config(lib_config: dict) -> tuple[str, dict]:
    """Convert a HA config dict into the client library's own format."""

    serial_port = lib_config.pop(SZ_SERIAL_PORT, None)

    return serial_port, lib_config


def split_kwargs(obj: tuple[dict, dict], kwargs: dict) -> tuple[dict, dict]:
    """Split kwargs into cli/library kwargs."""
    cli_kwargs, lib_kwargs = obj

    cli_kwargs.update(
        {k: v for k, v in kwargs.items() if k not in LIB_KEYS + LIB_CFG_KEYS}
    )
    lib_kwargs.update({k: v for k, v in kwargs.items() if k in LIB_KEYS})
    lib_kwargs[SZ_CONFIG].update({k: v for k, v in kwargs.items() if k in LIB_CFG_KEYS})

    return cli_kwargs, lib_kwargs


class DeviceIdParamType(click.ParamType):
    name = "device_id"

    def convert(self, value: str, param, ctx):
        if is_valid_dev_id(value):
            return value.upper()
        self.fail(f"{value!r} is not a valid device_id", param, ctx)


# Args/Params for both RF and file
@click.group(context_settings=CONTEXT_SETTINGS)  # , invoke_without_command=True)
@click.option("-z", "--debug-mode", count=True, help="enable debugger")
@click.option("-c", "--config-file", type=click.File("r"))
@click.option("-rk", "--restore-schema", type=click.File("r"), help="from a HA store")
@click.option("-rs", "--restore-state", type=click.File("r"), help=" from a HA store")
@click.option("-r", "--reduce-processing", count=True, help="-rrr will give packets")
@click.option("-lf", "--long-format", is_flag=True, help="dont truncate STDOUT")
@click.option("-e/-ne", "--eavesdrop/--no-eavesdrop", default=None)
@click.option("-g", "--print-state", count=True, help="print state (g=schema, gg=all)")
# @click.option("--get-state/--no-get-state", default=GET_STATE, help="get the engine state")
# @click.option("--set-state/--no-set-state", default=SET_STATE, help="set the engine state")
@click.option(  # show_schema
    "-k/-nk",
    "--show-schema/--no-show-schema",
    default=SHOW_SCHEMA,
    help="display system schema",
)
@click.option(  # show_params
    "-p/-np",
    "--show-params/--no-show-params",
    default=SHOW_PARAMS,
    help="display system params",
)
@click.option(  # show_status
    "-s/-ns",
    "--show-status/--no-show-status",
    default=SHOW_STATUS,
    help="display system state",
)
@click.option(  # show_knowns
    "-n/-nn",
    "--show-knowns/--no-show-knowns",
    default=SHOW_KNOWNS,
    help="display known_list (of devices)",
)
@click.option(  # show_traits
    "-t/-nt",
    "--show-traits/--no-show-traits",
    default=SHOW_TRAITS,
    help="display device traits",
)
@click.option(  # show_crazys
    "-x/-nx",
    "--show-crazys/--no-show-crazys",
    default=SHOW_CRAZYS,
    help="display crazy things",
)
@click.pass_context
def cli(ctx, config_file=None, eavesdrop: bool = None, **kwargs):
    """A CLI for the ramses_rf library."""

    if kwargs[SZ_DEBUG_MODE] > 0:  # Do first
        import debugpy

        debugpy.listen(address=(DEBUG_ADDR, DEBUG_PORT))
        print(f" - Debugging is enabled, listening on: {DEBUG_ADDR}:{DEBUG_PORT}")

        if kwargs[SZ_DEBUG_MODE] == 1:
            print("   - execution paused, waiting for debugger to attach...")
            debugpy.wait_for_client()
            print("   - debugger is now attached, continuing execution.")

    kwargs, lib_kwargs = split_kwargs(({}, {SZ_CONFIG: {}}), kwargs)

    if eavesdrop is not None:
        lib_kwargs[SZ_CONFIG][SZ_ENABLE_EAVESDROP] = eavesdrop

    if config_file:  # TODO: validate with voluptuous, use YAML
        lib_kwargs = merge(lib_kwargs, json.load(config_file))  # CLI takes precidence

    ctx.obj = kwargs, lib_kwargs


# Args/Params for packet log only
class FileCommand(click.Command):  # client.py parse <file>
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.params.insert(  # input_file
            0, click.Argument(("input-file",), type=click.File("r"), default=sys.stdin)
        )
        """ # self.params.insert(  # --packet-log  # NOTE: useful for only for test/dev
        #     1,
        #     click.Option(
        #         ("-o", "--packet-log"),
        #         type=click.Path(),
        #         help="Log all packets to this file",
        #     ),
        # )
        """


# Args/Params for RF packets only
class PortCommand(
    click.Command
):  # client.py <command> <port> --packet-log xxx --evofw3-flag xxx
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.params.insert(0, click.Argument(("serial-port",)))
        """ # self.params.insert(  # --no-discover
        #     1,
        #     click.Option(
        #         ("-d/-nd", "--discover/--no-discover"),
        #         is_flag=True,
        #         default=False,
        #         help="Log all packets to this file",
        #     ),
        # )
        # """
        self.params.insert(  # --packet-log
            2,
            click.Option(
                ("-o", "--packet-log"),
                type=click.Path(),
                help="Log all packets to this file",
            ),
        )
        self.params.insert(  # --evofw-flag
            3,
            click.Option(
                ("-T", "--evofw-flag"),
                type=click.STRING,
                help="Pass this traceflag to evofw",
            ),
        )


#
# 1/4: PARSE (a file, +/- eavesdrop)
@click.command(cls=FileCommand)  # parse a packet log, then stop
@click.pass_obj
def parse(obj, **kwargs):
    """Parse a log file for messages/packets."""
    config, lib_config = split_kwargs(obj, kwargs)

    lib_config[SZ_INPUT_FILE] = config.pop(SZ_INPUT_FILE)

    asyncio.run(main(PARSE, lib_config, **config))


#
# 2/4: MONITOR (listen to RF, +/- discovery, +/- eavesdrop)
@click.command(cls=PortCommand)  # (optionally) execute a command/script, then monitor
@click.option("-d/-nd", "--discover/--no-discover", default=None)  # --no-discover
@click.option(  # --exec-cmd 'RQ 01:123456 1F09 00'
    "-x", "--exec-cmd", type=click.STRING, help="e.g. 'RQ 01:123456 1F09 00'"
)
@click.option(  # --execute-scr script device_id
    "-X",
    "--exec-scr",
    type=(str, DeviceIdParamType()),
    help="scan_disc|scan_full|scan_hard|bind device_id",
)
@click.option(  # --poll-devices device_id, device_id,...
    "--poll-devices", type=click.STRING, help="e.g. 'device_id, device_id, ...'"
)
@click.pass_obj
def monitor(obj, discover: bool = None, **kwargs):
    """Monitor (eavesdrop and/or probe) a serial port for messages/packets."""
    config, lib_config = split_kwargs(obj, kwargs)

    if discover is None:
        if kwargs["exec_scr"] is None and kwargs["poll_devices"] is None:
            print(" - Discovery is enabled...")
            lib_config[SZ_CONFIG][SZ_DISABLE_DISCOVERY] = False
        else:
            print(" - Discovery is disabled...")
            lib_config[SZ_CONFIG][SZ_DISABLE_DISCOVERY] = True

    asyncio.run(main(MONITOR, lib_config, **config))


#
# 3/4: EXECUTE (send cmds to RF, +/- discovery, +/- eavesdrop)
@click.command(cls=PortCommand)  # execute a (complex) script, then stop
@click.option("-d/-nd", "--discover/--no-discover", default=None)  # --no-discover
@click.option(  # --exec-cmd 'RQ 01:123456 1F09 00'
    "-x", "--exec-cmd", type=click.STRING, help="e.g. 'RQ 01:123456 1F09 00'"
)
@click.option(  # --get-faults ctl_id
    "--get-faults", type=DeviceIdParamType(), help="controller_id"
)
@click.option(  # --get-schedule ctl_id zone_idx|HW
    "--get-schedule",
    default=[None, None],
    type=(DeviceIdParamType(), str),
    help="controller_id, zone_idx (e.g. '0A', 'HW')",
)
@click.option(  # --set-schedule ctl_id zone_idx|HW
    "--set-schedule",
    default=[None, None],
    type=(DeviceIdParamType(), click.File("r")),
    help="controller_id, filename.json",
)
@click.pass_obj
def execute(obj, **kwargs):
    """Execute any specified scripts, return the results, then quit.

    Disables discovery, and enforces a strict allow_list.
    """
    config, lib_config = split_kwargs(obj, kwargs)

    print(" - Discovery is force-disabled...")
    lib_config[SZ_CONFIG][SZ_DISABLE_DISCOVERY] = False

    if kwargs[GET_FAULTS]:
        known_list = {kwargs[GET_FAULTS][0]: {}}
    elif kwargs[GET_SCHED][0]:
        known_list = {kwargs[GET_SCHED][0]: {}}
    elif kwargs[SET_SCHED][0]:
        known_list = {kwargs[SET_SCHED][0]: {}}
    else:
        known_list = {}

    if known_list:
        print(" - Known list is force-configured/enforced...")
        lib_config[SZ_KNOWN_LIST] = known_list
        lib_config[SZ_CONFIG][SZ_ENFORCE_KNOWN_LIST] = True

    asyncio.run(main(EXECUTE, lib_config, **config))


#
# 4/4: LISTEN (to RF, +/- eavesdrop - NO sending/discovery)
@click.command(cls=PortCommand)  # (optionally) execute a command, then listen
@click.pass_obj
def listen(obj, **kwargs):
    """Listen to (eavesdrop only) a serial port for messages/packets."""
    config, lib_config = split_kwargs(obj, kwargs)

    print(" - Sending is force-disabled...")
    lib_config[SZ_CONFIG][SZ_DISABLE_SENDING] = True

    asyncio.run(main(LISTEN, lib_config, **config))


def print_results(gwy, **kwargs):

    if kwargs[GET_FAULTS]:
        fault_log = gwy.system_by_id[kwargs[GET_FAULTS]]._fault_log.fault_log

        if fault_log is None:
            print("No fault log, or failed to get the fault log.")
        else:
            [print(f"{k:02X}", v) for k, v in fault_log.items()]

    if kwargs[GET_SCHED][0]:
        system_id, zone_idx = kwargs[GET_SCHED]
        if zone_idx == "HW":
            zone = gwy.system_by_id[system_id].dhw
        else:
            zone = gwy.system_by_id[system_id].zone_by_idx[zone_idx]
        schedule = zone.schedule

        if schedule is None:
            print("Failed to get the schedule.")
        else:
            result = {SZ_ZONE_IDX: zone_idx, "schedule": schedule}
            print(">>> Schedule JSON begins <<<")
            print(json.dumps(result, indent=4))
            print(">>> Schedule JSON ended <<<")

    if kwargs[SET_SCHED][0]:
        system_id, _ = kwargs[GET_SCHED]


def _save_state(gwy):
    schema, msgs = gwy._get_state()

    with open("state_msgs.log", "w") as f:
        [f.write(f"{dtm} {pkt}\r\n") for dtm, pkt in msgs.items()]  # if not m._expired

    with open("state_schema.json", "w") as f:
        f.write(json.dumps(schema, indent=4))


def _print_engine_state(gwy, **kwargs):
    (schema, packets) = gwy._get_state(include_expired=True)

    if kwargs["print_state"] > 0:
        print(f"schema: {json.dumps(schema, indent=4)}\r\n")
    if kwargs["print_state"] > 1:
        print(f"packets: {json.dumps(packets, indent=4)}\r\n")


def print_summary(gwy, **kwargs):
    entity = gwy.tcs or gwy

    if kwargs.get("show_schema"):
        print(f"Schema[{entity}] = {json.dumps(entity.schema, indent=4)}\r\n")

        # schema = {d.id: d.schema for d in sorted(gwy.devices)}
        # print(f"Schema[devices] = {json.dumps({'schema': schema}, indent=4)}\r\n")

    if kwargs.get("show_params"):
        print(f"Params[{entity}] = {json.dumps(entity.params, indent=4)}\r\n")

        params = {d.id: d.params for d in sorted(gwy.devices)}
        print(f"Params[devices] = {json.dumps({'params': params}, indent=4)}\r\n")

    if kwargs.get("show_status"):
        print(f"Status[{entity}] = {json.dumps(entity.status, indent=4)}\r\n")

        status = {d.id: d.status for d in sorted(gwy.devices)}
        print(f"Status[devices] = {json.dumps({'status': status}, indent=4)}\r\n")

    if kwargs.get("show_knowns"):  # show device hints (show-knowns)
        print(f"allow_list (hints) = {json.dumps(gwy._include, indent=4)}\r\n")

    if kwargs.get("show_traits"):  # show device traits
        result = {
            d.id: d.traits  # {k: v for k, v in d.traits.items() if k[:1] == "_"}
            for d in sorted(gwy.devices)
        }
        print(json.dumps(result, indent=4), "\r\n")

    if kwargs.get("show_crazys"):
        for device in [d for d in gwy.devices if d.type == DEV_TYPE_MAP.CTL]:
            for code, verbs in device._msgz.items():
                if code in (Code._0005, Code._000C):
                    for verb in verbs.values():
                        for pkt in verb.values():
                            print(f"{pkt}")
            print()
        for device in [d for d in gwy.devices if d.type == DEV_TYPE_MAP.UFC]:
            for code in device._msgz.values():
                for verb in code.values():
                    for pkt in verb.values():
                        print(f"{pkt}")
            print()


async def main(command: str, lib_kwargs: dict, **kwargs):
    """Do certain things."""

    def process_msg(msg, prev_msg=None) -> None:
        """Process the message as it arrives (a callback).

        In this case, the message is merely printed.
        """

        if DEV_MODE and kwargs["long_format"]:  # HACK for test/dev
            print(
                f'{msg.dtm.isoformat(timespec="microseconds")} ... {msg!r}  # {msg.payload}'
            )
            # print(f'{msg.dtm.isoformat(timespec="microseconds")} ... {msg!r}  # ("{msg.src!r}", "{msg.dst!r}")')
            return

        if kwargs["long_format"]:
            dtm = msg.dtm.isoformat(timespec="microseconds")
            con_cols = None
        else:
            dtm = f"{msg.dtm:%H:%M:%S.%f}"[:-3]
            con_cols = CONSOLE_COLS

        if msg.src and msg.src.type == DEV_TYPE_MAP.HGI:
            print(f"{Style.BRIGHT}{COLORS.get(msg.verb)}{dtm} {msg}"[:con_cols])
        elif msg.code == Code._1F09 and msg.verb == I_:
            print(f"{Fore.YELLOW}{dtm} {msg}"[:con_cols])
        elif msg.code in (Code._000A, Code._2309, Code._30C9) and msg._has_array:
            print(f"{Fore.YELLOW}{dtm} {msg}"[:con_cols])
        else:
            print(f"{COLORS.get(msg.verb)}{dtm} {msg}"[:con_cols])

    serial_port, lib_kwargs = normalise_config(lib_kwargs)

    if kwargs["restore_schema"]:
        print(" - Restoring client schema from a HA cache...")
        state = json.load(kwargs["restore_schema"])["data"]["client_state"]
        lib_kwargs = lib_kwargs | state["schema"]

    if serial_port == "/dev/ttyMOCK":
        gwy = MockGateway(serial_port, **lib_kwargs)
    else:
        gwy = Gateway(serial_port, **lib_kwargs)

    if lib_kwargs[SZ_CONFIG][SZ_REDUCE_PROCESSING] < DONT_CREATE_MESSAGES:
        # library will not send MSGs to STDOUT, so we'll send PKTs instead
        colorama_init(autoreset=True)  # WIP: remove strip=True
        gwy.create_client(process_msg)

    if kwargs["restore_state"]:
        print(" - Restoring client state from a HA cache...")
        state = json.load(kwargs["restore_state"])["data"]["client_state"]
        await gwy._set_state(packets=state["packets"])

    print("client.py: Starting engine...")

    try:  # main code here
        await gwy.start()

        if command == EXECUTE:
            tasks = spawn_scripts(gwy, **kwargs)
            await asyncio.gather(*tasks)

        elif command in MONITOR:
            tasks = spawn_scripts(gwy, **kwargs)
            await gwy.pkt_source

        elif gwy.pkt_source:  # else:  # elif command in (LISTEN, PARSE):
            await gwy.pkt_source

    except asyncio.CancelledError:
        msg = "ended via: CancelledError (e.g. SIGINT)"
    except GracefulExit:
        msg = "ended via: GracefulExit"
    except KeyboardInterrupt:
        msg = "ended via: KeyboardInterrupt"
    except EvohomeError as err:
        msg = f"ended via: EvohomeError: {err}"
    else:  # if no Exceptions raised, e.g. EOF when parsing, or Ctrl-C?
        msg = "ended without error (e.g. EOF)"
    finally:
        await gwy.stop()

    print(f"client.py: Engine stopped: {msg}.")

    # if kwargs["save_state"]:
    #    _save_state(gwy)

    if kwargs["print_state"]:
        _print_engine_state(gwy, **kwargs)

    elif command == EXECUTE:
        print_results(gwy, **kwargs)

    print_summary(gwy, **kwargs)


cli.add_command(parse)
cli.add_command(monitor)
cli.add_command(execute)
cli.add_command(listen)

if __name__ == "__main__":
    print("\r\nclient.py: Starting ramses_rf...")

    # profile = cProfile.Profile()

    if sys.platform == "win32":
        print("Setting event_loop_policy...")
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        # profile.run("cli()")
        cli()
    except SystemExit:
        pass

    # ps = pstats.Stats(profile)
    # ps.sort_stats(pstats.SortKey.TIME).print_stats(60)

    print("\r\nclient.py: Finished ramses_rf.")
