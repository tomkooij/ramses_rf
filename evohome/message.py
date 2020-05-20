"""Message processor."""

import logging
from typing import Any

from . import parsers
from .const import (
    __dev_mode__,
    COMMAND_MAP,
    DEVICE_TYPES,
    DOMAIN_MAP,
    MSG_FORMAT_10,
    MSG_FORMAT_18,
    NON_DEV_ID,
    NUL_DEV_ID,
)
from .entity import DEVICE_CLASS_MAP, Device, Domain, Zone

_LOGGER = logging.getLogger(__name__)


class Message:
    """The message class."""

    def __init__(self, pkt, gateway) -> None:
        """Create a message, assumes a valid packet."""
        self._gwy = gateway
        self._evo = gateway.evo
        self._pkt = packet = pkt.packet

        self.date = pkt.date
        self.time = pkt.time

        self.rssi = packet[0:3]
        self.verb = packet[4:6]
        self.seq_no = packet[7:10]  # sequence number (as used by 31D9)?
        self.code = packet[41:45]

        self.device_id = {}
        self.dev_from = self.dev_dest = NON_DEV_ID
        for dev, i in enumerate(range(11, 32, 10)):
            device_id = self.device_id[dev] = packet[i : i + 9]  # noqa: E203
            if device_id not in [NON_DEV_ID, NUL_DEV_ID]:
                if self.dev_from == NON_DEV_ID:
                    self.dev_from = device_id
                else:
                    self.dev_dest = device_id

        self.len = int(packet[46:49])  # TODO:  is useful? / is user used?
        self.raw_payload = packet[50:]

        self._payload = self._is_array = self._is_valid = self._repr = None
        self._is_valid = self.is_valid

    def __repr__(self) -> str:
        """Represent the entity as a string."""

        def display_name(device_id) -> str:
            """Return a formatted device name, uses a friendly name if there is one."""
            if device_id == NON_DEV_ID:
                return f"{'':<10}"

            if device_id == NUL_DEV_ID:
                return "NUL:------"

            if device_id in self._gwy.known_devices:  # can be up to 18 characters
                if self._gwy.known_devices[device_id].get("friendly_name"):
                    return self._gwy.known_devices[device_id]["friendly_name"]

            device_type = DEVICE_TYPES.get(device_id[:2], f"{device_id[:2]:>3}")
            return f"{device_type}:{device_id[3:]}"

        if self._repr:
            return self._repr

        if self._gwy.config.get("known_devices"):
            msg_format = MSG_FORMAT_18
        else:
            msg_format = MSG_FORMAT_10

        self._repr = msg_format.format(
            display_name(self.dev_from),
            display_name(self.dev_dest),
            self.verb,
            COMMAND_MAP.get(self.code, f"unknown_{self.code}"),
            self.raw_payload if self.len < 4 else f"{self.raw_payload[:5]}..."[:9],
            self._payload,
        )

        return self._repr

    @property
    def payload(self) -> Any:  # Any[dict, List[dict]]:
        """Return the payload."""
        return self._payload

    @property
    def is_array(self) -> bool:
        """Return True if the message payload is an array."""

        if self._is_array is not None:
            return self._is_array

        if self.code in ["000A", "2309", "30C9"] and self.verb == " I":  # of zones
            # actually, I/01:, or 01:/01: would do for these codes
            self._is_array = all(
                [self.dev_from[:2] == "01", self.dev_from == self.dev_dest]
            )

        elif self.code in ["000C", "1FC9", "22C9"]:  # also: 0005?
            # 056  I --- 02:001107 --:------ 02:001107 22C9 006 0408340A2801
            self._is_array = self.verb not in ["RQ", " W"]

        elif self.code in ["0009"]:  # of domains
            # 045  I --- 01:158182 --:------ 01:158182 0009 003 0B00FF
            # 045  I --- 01:158182 --:------ 01:158182 0009 003 FC00FF
            # 045  I --- 01:145038 --:------ 01:145038 0009 006 FC00FFF900FF
            self._is_array = self.verb == " I" and self.raw_payload[:1] == "F"

        else:
            self._is_array = False

        return self._is_array

    @property
    def is_valid(self) -> bool:  # Main code here
        """Return True if the message payload is valid.

        All exceptions are to be trapped, and logged appropriately.
        """

        if self._is_valid is not None:
            return self._is_valid

        # STATE: get controller ID by eavesdropping (here, as create_entity is optional)
        if self._evo.ctl_id is None and self.dev_from[:2] != "18":
            if self.dev_from[:2] == "01":
                self._evo.ctl_id = self.dev_from
            elif self.dev_dest[:2] == "01":
                self._evo.ctl_id = self.dev_dest

        # STATE: get number of zones by eavesdropping
        if self._evo._num_zones is None:  # and self._evo._prev_code == "1F09":
            if self.code in ["2309", "30C9"] and self.is_array:  # 000A may be >1 pkt
                assert len(self.raw_payload) % 6 == 0  # simple validity check
                self._evo._num_zones = len(self.raw_payload) / 6

        try:  # determine which parser to use
            payload_parser = getattr(parsers, f"parser_{self.code}".lower())
        except AttributeError:  # there's no parser for this command code!
            payload_parser = getattr(parsers, "parser_unknown")

        try:  # run the parser
            self._payload = payload_parser(self.raw_payload, self)  # TODO: messy
            assert isinstance(self.payload, dict) or isinstance(self.payload, list)
        except AssertionError:  # for development only?
            # beware: HGI80 can send parseable but 'odd' packets +/- get invalid reply
            if self.dev_from[:2] == "18":  # TODO: should be a warning
                _LOGGER.exception("%s", self._pkt, extra=self.__dict__)
            else:
                _LOGGER.exception("%s", self._pkt, extra=self.__dict__)
            return False

        # STATE: update parser state (last packet code) - not needed?
        if self.dev_from == self._evo.ctl_id:
            self._evo._prev_code = self.code if self.verb == " I" else None
        # TODO: add state for 000C?

        # for dev_id in self.device_id:  # TODO: leave in, or out?
        #     assert dev_id[:2] in DEVICE_TYPES  # incl. "--", "63"

        # any remaining messages are valid, so: log them
        if False and __dev_mode__:
            if " I" in str(self):
                _LOGGER.info("%s", self, extra=self.__dict__)
            elif "RP" in str(self):
                _LOGGER.warning("%s", self, extra=self.__dict__)
            else:
                _LOGGER.error("%s", self, extra=self.__dict__)
        else:
            _LOGGER.info("%s", self, extra=self.__dict__)

        return True  # self._is_valid = True

    def _create_entities(self) -> None:
        """Discover and create new devices, domains and zones."""
        # contains true, programmer's checking asserts, which are OK to -O

        def _ent(ent_cls, ent_id, ent_by_id, ents) -> None:
            try:  # does the system already know about this entity?
                _ = ent_by_id[ent_id]
            except KeyError:  # this is a new entity, so create it
                ent_by_id.update({ent_id: ent_cls(ent_id, self._gwy)})
                ents.append(ent_by_id[ent_id])

        def get_device(dev_id, parent_zone=None) -> None:
            """Get a Device, create it if required."""
            assert dev_id[:2] in DEVICE_TYPES
            dev_cls = DEVICE_CLASS_MAP.get(dev_id[:2], Device)
            _ent(dev_cls, dev_id, self._evo.device_by_id, self._evo.devices)
            if parent_zone is not None:  # TODO: this is a dup of _update_device
                self._evo.device_by_id[dev_id].parent_000c = parent_zone

        def get_domain(domain_id) -> None:
            """Get a Domain, create it if required."""
            assert domain_id in DOMAIN_MAP
            _ent(Domain, domain_id, self._evo.domain_by_id, self._evo.domains)

        def get_zone(zone_idx) -> None:
            """Get a Zone, create it if required."""  # TODO: other zone types?
            assert int(zone_idx, 16) < 12  # TODO: > 11 not for Hometronic
            zone_cls = Zone  # TODO: DhwZone if zone_idx == "HW" else Zone?
            _ent(zone_cls, zone_idx, self._evo.zone_by_id, self._evo.zones)

        # STEP 0: harvest zone_actuators payload to discover devices
        if self.code == "000C" and self.verb == "RP":  # or: from CTL/000C
            for d in self.payload["actuators"]:
                get_device(d, self.payload["zone_idx"])

        # STEP 1: devices by eavesdropping
        [get_device(d) for d in self.device_id if d[:2] not in ["18", "63", "--"]]

        # STEP 2: discover domains and zones by eavesdropping
        if isinstance(self._payload, dict):  # discover zones and domains
            if self._payload.get("domain_id"):  # is not None:
                get_domain(self._payload["domain_id"])

            if self._payload.get("zone_idx"):  # is not None:  # TODO: parent_zone too?
                get_zone(self._payload["zone_idx"])

        elif isinstance(self._payload, list):  # discover zones
            if self.dev_from[:2] == "01" and self.verb == " I":
                if self.code == "0009":  # the few remaining sync cycles
                    for domain in self.payload:
                        get_domain(domain["domain_id"])

                elif self.code == "000A":  # the few remaining sync_cycles
                    for i in range(0, len(self.raw_payload), 12):
                        get_zone(self.raw_payload[i : i + 2])

                elif self.code in ["2309", "30C9"]:  # almost all sync_cycles
                    for i in range(0, len(self.raw_payload), 6):
                        get_zone(self.raw_payload[i : i + 2])

    def _update_entities(self) -> None:  # TODO: needs work
        """Update the system state with the message data."""

        def _update_entity(data: dict) -> None:
            if "domain_id" in data:
                self._evo.domain_by_id[data["domain_id"]].update(self)
            elif "zone_idx" in data:
                self._evo.zone_by_id[data["zone_idx"]].update(self)
            else:
                self._evo.device_by_id[self.dev_from].update(self)

        # STEP 0: harvest zone_actuators payload to discover device parentage
        if self.code == "000C" and self.verb == "RP":  # or: from CTL/000C
            for dev_id in self.payload["actuators"]:
                self._evo.device_by_id[dev_id].parent_000c = self.payload["zone_idx"]

        # CHECK: check parent_zone_idx hueristics using the data in known_devices.json
        if __dev_mode__ and isinstance(self.payload, dict):
            # assert self.dev_from in self._gwy.known_devices
            if self.dev_from in self._gwy.known_devices:
                zone_idx = self._gwy.known_devices[self.dev_from].get("zone_idx")
                if self._evo.device_by_id[dev_id].parent_000c:
                    assert zone_idx == self._evo.device_by_id[dev_id].parent_000c
                if "parent_zone_idx" in self.payload:
                    assert zone_idx == self.payload["parent_zone_idx"]

        if not self.payload:  # should be {} (possibly empty) or [] (never empty)
            return  # TODO: will stop useful RQs getting to update()? (e.g. RQ/3EF1)

        # STEP 1: who was the message from?
        self._evo.device_by_id[self.dev_from].update(self)

        # STEP 2: what was the message about: system, domain, or zone?
        if isinstance(self.payload, list):
            # do zones keep their own pkts, or simly extract that data fromteh CTL?
            if self.code in ["000A", "2309", "30C9"]:  # array of zones
                # [_update_entity(zone) for zone in self.payload]  # TODO:  bad idea?
                return
            # do domains keep their own pkts, or simly extract that data fromteh CTL?
            if self.code in ["0009"]:  # array of domains
                # [_update_entity(domain) for domain in self.payload]  # TODO: bad idea?
                return
            if self.code in ["22C9", "3150"]:  # array of UFH zones TODO ? 3150/array
                return  # TODO: something
            if self.code in ["1FC9"]:  # TODO: array of codes
                return
            assert False  # the above are the only known lists...

        if "zone_idx" in self.payload:
            if self.code == "0418":
                return
            elif self.code == "0008":
                return
            # assert self.code in ["12B0", "2309", "3150"]
            _update_entity(self.payload)

        elif "domain_id" in self.payload:
            _update_entity(self.payload)

        elif self.code in ["1FD4", "22D9", "3220"]:  # is for opentherm...
            _update_entity(self.payload)  # TODO: needs checking

        elif "parent_zone_idx" in self.payload:  # is from/to a device...
            _update_entity(self.payload)  # TODO; do I need this and step 1?

        else:  # is for a device...
            _update_entity(self.payload)
