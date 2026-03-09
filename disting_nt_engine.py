"""Disting NT engine: thread-safe MIDI wrapper + SysEx commands + cached state."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rtmidi

from protocol import (
    DISTING_NT_PREFIX,
    MANUFACTURER_ID,
    RESP_ALGORITHM,
    RESP_ALGORITHM_INFO,
    RESP_ALL_PARAMETER_VALUES,
    RESP_CPU_USAGE,
    RESP_ENUM_STRINGS,
    RESP_LUA_OUTPUT,
    RESP_MAPPING,
    RESP_MESSAGE,
    RESP_NUM_ALGORITHMS,
    RESP_NUM_ALGORITHMS_IN_PRESET,
    RESP_NUM_PARAMETERS,
    RESP_PARAMETER_INFO,
    RESP_PARAMETER_VALUE,
    RESP_PARAMETER_VALUE_STRING,
    RESP_PRESET_NAME,
    RESP_ROUTING,
    RESP_SCREENSHOT,
    RESP_UNIT_STRINGS,
    msg_add_algorithm,
    msg_execute_lua,
    msg_install_kbm,
    msg_install_lua,
    msg_install_scala,
    msg_load_preset,
    msg_move_algorithm,
    msg_new_preset,
    msg_reboot,
    msg_remove_algorithm,
    msg_request_algorithm,
    msg_request_algorithm_info,
    msg_request_all_parameter_values,
    msg_request_cpu_usage,
    msg_request_enum_strings,
    msg_request_mappings,
    msg_request_num_algorithms,
    msg_request_num_algorithms_in_preset,
    msg_request_num_parameters,
    msg_request_parameter_info,
    msg_request_parameter_value,
    msg_request_parameter_value_string,
    msg_request_preset_name,
    msg_request_routing,
    msg_request_unit_strings,
    msg_request_version_string,
    msg_save_preset,
    msg_set_cv_mapping,
    msg_set_display_mode,
    msg_set_focus,
    msg_set_i2c_mapping,
    msg_set_midi_mapping,
    msg_set_parameter_value,
    msg_set_preset_name,
    msg_set_real_time_clock,
    msg_set_slot_name,
    msg_take_screenshot,
    msg_wake,
    parse_algorithm,
    parse_algorithm_info,
    parse_all_parameter_values,
    parse_cpu_usage,
    parse_enum_strings,
    parse_lua_output,
    parse_mapping,
    parse_num_algorithms,
    parse_num_algorithms_in_preset,
    parse_num_parameters,
    parse_parameter_info,
    parse_parameter_value,
    parse_parameter_value_string,
    parse_preset_name,
    parse_routing,
    parse_screenshot,
    parse_unit_strings,
    parse_version_string,
)


@dataclass
class MidiMessage:
    """Parsed MIDI message with timestamp."""

    raw: list[int]
    timestamp: float
    type: str = ""
    channel: int | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.type:
            self.type, self.channel, self.description = _parse_message(self.raw)


def _parse_message(data: list[int]) -> tuple[str, int | None, str]:
    """Parse raw MIDI bytes into type, channel, description."""
    if not data:
        return "unknown", None, "empty"

    status = data[0]

    # System messages
    if status == 0xFA:
        return "start", None, "Start"
    if status == 0xFB:
        return "continue", None, "Continue"
    if status == 0xFC:
        return "stop", None, "Stop"
    if status == 0xF8:
        return "clock", None, "Clock"
    if status == 0xFE:
        return "active_sense", None, "Active Sensing"
    if status == 0xF0:
        return "sysex", None, f"SysEx ({len(data)} bytes)"

    # Channel messages
    msg_type = status & 0xF0
    ch = (status & 0x0F) + 1

    if msg_type == 0x90 and len(data) >= 3:
        vel = data[2]
        if vel == 0:
            return "note_off", ch, f"Note Off ch{ch} note={data[1]}"
        return "note_on", ch, f"Note On ch{ch} note={data[1]} vel={vel}"
    if msg_type == 0x80 and len(data) >= 3:
        return "note_off", ch, f"Note Off ch{ch} note={data[1]} vel={data[2]}"
    if msg_type == 0xB0 and len(data) >= 3:
        return "cc", ch, f"CC ch{ch} cc={data[1]} val={data[2]}"
    if msg_type == 0xC0 and len(data) >= 2:
        return "program_change", ch, f"PC ch{ch} prog={data[1]}"
    if msg_type == 0xE0 and len(data) >= 3:
        val = data[1] | (data[2] << 7)
        return "pitch_bend", ch, f"PitchBend ch{ch} val={val}"
    if msg_type == 0xD0 and len(data) >= 2:
        return "aftertouch", ch, f"Aftertouch ch{ch} val={data[1]}"
    if msg_type == 0xA0 and len(data) >= 3:
        return "poly_aftertouch", ch, f"PolyAT ch{ch} note={data[1]} val={data[2]}"

    return "unknown", None, f"Unknown 0x{status:02X}"


class DistingNTEngine:
    """Thread-safe Disting NT MIDI engine with SysEx command support."""

    def __init__(self, sysex_id: int = 0) -> None:
        self._sysex_id = sysex_id & 0x7F
        self._lock = threading.Lock()
        self._midi_out: rtmidi.MidiOut | None = None
        self._midi_in: rtmidi.MidiIn | None = None
        self._out_port_name: str = ""
        self._in_port_name: str = ""
        self._connected = False

        # Monitoring
        self._monitoring = False
        self._message_log: deque[MidiMessage] = deque(maxlen=1000)

        # SysEx accumulation
        self._sysex_buffer: list[list[int]] = []
        self._sysex_event = threading.Event()
        self._collecting_sysex = False

        # Cached state
        self._firmware_version: str | None = None
        self._preset_name: str | None = None
        self._unit_strings: list[str] | None = None

    # -- Port Discovery --

    @staticmethod
    def list_output_ports() -> list[str]:
        tmp = rtmidi.MidiOut()
        try:
            return tmp.get_ports()
        finally:
            del tmp

    @staticmethod
    def list_input_ports() -> list[str]:
        tmp = rtmidi.MidiIn()
        try:
            return tmp.get_ports()
        finally:
            del tmp

    @staticmethod
    def _find_port(ports: list[str], query: str) -> int | None:
        """Find port index by case-insensitive substring match."""
        q = query.lower()
        for i, name in enumerate(ports):
            if q in name.lower():
                return i
        return None

    # -- Connection --

    def connect(
        self,
        output_port: str | int = "",
        input_port: str | int = "",
    ) -> str:
        """Connect to Disting NT MIDI ports. Accepts port name (substring) or index."""
        with self._lock:
            if self._connected:
                self._disconnect_locked()

            # Output
            self._midi_out = rtmidi.MidiOut()
            out_ports = self._midi_out.get_ports()

            if isinstance(output_port, int):
                out_idx = output_port
            elif output_port:
                out_idx = self._find_port(out_ports, output_port)
                if out_idx is None:
                    raise ValueError(
                        f"Output port '{output_port}' not found. "
                        f"Available: {out_ports}"
                    )
            else:
                # Auto-detect Disting NT
                out_idx = self._find_port(out_ports, "Disting NT")
                if out_idx is None:
                    raise ValueError(
                        f"Disting NT not found in output ports. Available: {out_ports}"
                    )

            self._midi_out.open_port(out_idx)
            self._out_port_name = out_ports[out_idx]

            # Input
            self._midi_in = rtmidi.MidiIn()
            self._midi_in.ignore_types(
                sysex=False, timing=False, active_sense=True
            )
            in_ports = self._midi_in.get_ports()

            if isinstance(input_port, int):
                in_idx = input_port
            elif input_port:
                in_idx = self._find_port(in_ports, input_port)
                if in_idx is None:
                    raise ValueError(
                        f"Input port '{input_port}' not found. "
                        f"Available: {in_ports}"
                    )
            else:
                query = (
                    output_port
                    if isinstance(output_port, str) and output_port
                    else "Disting NT"
                )
                in_idx = self._find_port(in_ports, query)

            if in_idx is not None:
                self._midi_in.open_port(in_idx)
                self._in_port_name = in_ports[in_idx]
                self._midi_in.set_callback(self._input_callback)
            else:
                self._in_port_name = "(none)"

            self._connected = True
            return (
                f"Connected: out='{self._out_port_name}', "
                f"in='{self._in_port_name}'"
            )

    def _disconnect_locked(self) -> None:
        """Disconnect MIDI (must hold lock)."""
        self._monitoring = False
        if self._midi_out:
            self._midi_out.close_port()
            del self._midi_out
            self._midi_out = None
        if self._midi_in:
            self._midi_in.close_port()
            del self._midi_in
            self._midi_in = None
        self._connected = False
        self._out_port_name = ""
        self._in_port_name = ""

    def disconnect(self) -> str:
        """Disconnect from MIDI ports."""
        with self._lock:
            self._disconnect_locked()
        return "Disconnected"

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def port_info(self) -> str:
        if not self._connected:
            return "Not connected"
        return f"out='{self._out_port_name}', in='{self._in_port_name}'"

    # -- Input Callback --

    def _input_callback(
        self, event: tuple[list[int], float], data: Any = None
    ) -> None:
        message, delta = event

        if self._monitoring:
            msg = MidiMessage(raw=message, timestamp=time.time())
            self._message_log.append(msg)

        # SysEx collection
        if self._collecting_sysex and message and message[0] == 0xF0:
            self._sysex_buffer.append(message)
            self._sysex_event.set()

    # -- Send Helpers --

    def _send(self, message: list[int]) -> None:
        """Send raw MIDI message (thread-safe)."""
        with self._lock:
            if not self._connected or not self._midi_out:
                raise RuntimeError("Not connected to Disting NT MIDI")
            self._midi_out.send_message(message)

    def send_and_wait(
        self, message: list[int], timeout: float = 2.0
    ) -> list[int] | None:
        """Send a SysEx message and wait for a single response."""
        self._sysex_buffer.clear()
        self._sysex_event.clear()
        self._collecting_sysex = True
        self._send(message)
        got = self._sysex_event.wait(timeout=timeout)
        self._collecting_sysex = False
        if got and self._sysex_buffer:
            return self._sysex_buffer[0]
        return None

    def send_and_collect(
        self, message: list[int], timeout: float = 5.0, idle_timeout: float = 1.0
    ) -> list[list[int]]:
        """Send a SysEx and collect multiple responses."""
        self._sysex_buffer.clear()
        self._sysex_event.clear()
        self._collecting_sysex = True
        self._send(message)

        start = time.time()
        last_count = 0
        last_activity = time.time()

        while True:
            time.sleep(0.1)
            count = len(self._sysex_buffer)
            if count > last_count:
                last_count = count
                last_activity = time.time()

            if time.time() - start > timeout:
                break
            if count > 0 and time.time() - last_activity > idle_timeout:
                break

        self._collecting_sysex = False
        return list(self._sysex_buffer)

    # -- Channel Messages --

    @staticmethod
    def _validate_channel(channel: int) -> int:
        if not 1 <= channel <= 16:
            raise ValueError(f"Channel must be 1-16, got {channel}")
        return channel

    def send_note_on(self, channel: int, note: int, velocity: int = 100) -> None:
        self._validate_channel(channel)
        self._send([0x90 | (channel - 1), note & 0x7F, velocity & 0x7F])

    def send_note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        self._validate_channel(channel)
        self._send([0x80 | (channel - 1), note & 0x7F, velocity & 0x7F])

    def send_cc(self, channel: int, cc: int, value: int) -> None:
        self._validate_channel(channel)
        self._send([0xB0 | (channel - 1), cc & 0x7F, value & 0x7F])

    def send_program_change(self, channel: int, program: int) -> None:
        self._validate_channel(channel)
        self._send([0xC0 | (channel - 1), program & 0x7F])

    def send_pitch_bend(self, channel: int, value: int = 8192) -> None:
        self._validate_channel(channel)
        value = max(0, min(16383, value))
        lsb = value & 0x7F
        msb = (value >> 7) & 0x7F
        self._send([0xE0 | (channel - 1), lsb, msb])

    def send_bank_select(
        self, channel: int, bank_msb: int, bank_lsb: int | None = None
    ) -> None:
        self.send_cc(channel, 0, bank_msb)
        if bank_lsb is not None:
            self.send_cc(channel, 32, bank_lsb)

    # -- Safety --

    def all_notes_off(self, channel: int) -> None:
        self.send_cc(channel, 123, 0)

    def panic(self) -> None:
        """All Notes Off + Reset All Controllers + center pitch bend on all 16 channels + Stop."""
        for ch in range(1, 17):
            self.send_cc(ch, 123, 0)
            self.send_cc(ch, 121, 0)
            self.send_pitch_bend(ch, 8192)
        self._send([0xFC])

    # -- SysEx --

    def send_sysex(self, data: list[int]) -> None:
        """Send SysEx. Auto-frames with F0/F7 if not present."""
        if data[0] != 0xF0:
            data = [0xF0] + data
        if data[-1] != 0xF7:
            data = data + [0xF7]
        self._send(data)

    def send_raw(self, data: list[int]) -> None:
        self._send(data)

    def wait_for_sysex(self, timeout: float = 5.0) -> list[int] | None:
        """Wait for a single incoming SysEx message."""
        self._sysex_buffer.clear()
        self._sysex_event.clear()
        self._collecting_sysex = True
        got = self._sysex_event.wait(timeout=timeout)
        self._collecting_sysex = False
        if got and self._sysex_buffer:
            return self._sysex_buffer[0]
        return None

    # -- Monitor --

    def start_monitor(self) -> None:
        self._message_log.clear()
        self._monitoring = True

    def stop_monitor(self) -> None:
        self._monitoring = False

    @property
    def is_monitoring(self) -> bool:
        return self._monitoring

    @property
    def log_count(self) -> int:
        return len(self._message_log)

    def get_log(
        self, count: int = 50, type_filter: str | None = None
    ) -> list[MidiMessage]:
        msgs = list(self._message_log)
        if type_filter:
            f = type_filter.lower()
            msgs = [m for m in msgs if f in m.type]
        return msgs[-count:]

    # -- Disting NT SysEx Commands --

    def get_firmware_version(self) -> str:
        """Request firmware version string."""
        resp = self.send_and_wait(msg_request_version_string(self._sysex_id))
        if resp is None:
            return "No response (is Disting NT connected?)"
        version = parse_version_string(resp)
        self._firmware_version = version
        return version

    def take_screenshot(self) -> str:
        """Take a screenshot and return ASCII art."""
        resp = self.send_and_wait(
            msg_take_screenshot(self._sysex_id), timeout=5.0
        )
        if resp is None:
            return "No response (is Disting NT connected?)"
        return parse_screenshot(resp)

    def set_display_mode(self, mode: int) -> None:
        """Set display mode."""
        self._send(msg_set_display_mode(self._sysex_id, mode))

    def set_focus(self, algo_index: int) -> None:
        """Focus display on a specific algorithm slot."""
        self._send(msg_set_focus(self._sysex_id, algo_index))

    # -- Algorithm Management --

    def get_num_algorithms_in_library(self) -> int:
        """Get total number of algorithms in library."""
        resp = self.send_and_wait(msg_request_num_algorithms(self._sysex_id))
        if resp is None:
            return -1
        return parse_num_algorithms(resp)

    def get_algorithm_info(self, index: int) -> dict[str, Any]:
        """Get info about a library algorithm by index."""
        resp = self.send_and_wait(
            msg_request_algorithm_info(self._sysex_id, index), timeout=3.0
        )
        if resp is None:
            return {"error": "No response"}
        return parse_algorithm_info(resp)

    def get_loaded_algorithm_count(self) -> int:
        """Get number of algorithm slots occupied in current preset."""
        resp = self.send_and_wait(
            msg_request_num_algorithms_in_preset(self._sysex_id)
        )
        if resp is None:
            return -1
        return parse_num_algorithms_in_preset(resp)

    def get_loaded_algorithm(self, slot_index: int) -> dict[str, Any]:
        """Get what algorithm is in a specific slot."""
        resp = self.send_and_wait(
            msg_request_algorithm(self._sysex_id, slot_index)
        )
        if resp is None:
            return {"error": "No response"}
        return parse_algorithm(resp)

    def add_algorithm(
        self, guid: str, spec_values: list[int] | None = None
    ) -> str:
        """Load algorithm by GUID with optional spec values. Returns response message."""
        resp = self.send_and_wait(
            msg_add_algorithm(self._sysex_id, guid, spec_values), timeout=5.0
        )
        if resp is None:
            return "No response"
        return parse_version_string(resp)  # respMessage uses same format

    def remove_algorithm(self, slot_index: int) -> None:
        """Remove algorithm from a slot."""
        self._send(msg_remove_algorithm(self._sysex_id, slot_index))

    def move_algorithm(self, from_index: int, to_index: int) -> None:
        """Reorder algorithms."""
        self._send(msg_move_algorithm(self._sysex_id, from_index, to_index))

    # -- Preset Management --

    def new_preset(self) -> None:
        """Clear all slots."""
        self._send(msg_new_preset(self._sysex_id))
        self._preset_name = None

    def load_preset(self, name: str, append: bool = False) -> None:
        """Load preset by name."""
        self._send(msg_load_preset(self._sysex_id, name, append))
        self._preset_name = name

    def save_preset(self, option: int = 0) -> None:
        """Save current state."""
        self._send(msg_save_preset(self._sysex_id, option))

    def get_preset_name(self) -> str:
        """Request current preset name."""
        resp = self.send_and_wait(msg_request_preset_name(self._sysex_id))
        if resp is None:
            return "(no response)"
        name = parse_preset_name(resp)
        self._preset_name = name
        return name

    def set_preset_name(self, name: str) -> None:
        """Set preset name."""
        self._send(msg_set_preset_name(self._sysex_id, name))
        self._preset_name = name

    def set_slot_name(self, algo_index: int, name: str) -> None:
        """Set custom label for an algorithm slot."""
        self._send(msg_set_slot_name(self._sysex_id, algo_index, name))

    # -- Parameter Control --

    def get_num_parameters(self, algo_index: int) -> dict[str, int]:
        """Get parameter count for an algorithm."""
        resp = self.send_and_wait(
            msg_request_num_parameters(self._sysex_id, algo_index)
        )
        if resp is None:
            return {"algo_index": algo_index, "count": -1}
        return parse_num_parameters(resp)

    def get_parameter_info(
        self, algo_index: int, param_num: int
    ) -> dict[str, Any]:
        """Get info about a specific parameter."""
        resp = self.send_and_wait(
            msg_request_parameter_info(self._sysex_id, algo_index, param_num)
        )
        if resp is None:
            return {"error": "No response"}
        return parse_parameter_info(resp)

    def get_parameter_value(
        self, algo_index: int, param_num: int
    ) -> dict[str, Any]:
        """Get a single parameter value."""
        resp = self.send_and_wait(
            msg_request_parameter_value(self._sysex_id, algo_index, param_num)
        )
        if resp is None:
            return {"error": "No response"}
        return parse_parameter_value(resp)

    def get_parameter_value_string(
        self, algo_index: int, param_num: int
    ) -> dict[str, Any]:
        """Get formatted value text for a parameter."""
        resp = self.send_and_wait(
            msg_request_parameter_value_string(
                self._sysex_id, algo_index, param_num
            )
        )
        if resp is None:
            return {"error": "No response"}
        return parse_parameter_value_string(resp)

    def set_parameter_value(
        self, algo_index: int, param_num: int, value: int
    ) -> None:
        """Set a parameter value."""
        self._send(
            msg_set_parameter_value(
                self._sysex_id, algo_index, param_num, value
            )
        )

    def get_all_parameter_values(self, algo_index: int) -> dict[str, Any]:
        """Bulk read all parameter values for an algorithm."""
        resp = self.send_and_wait(
            msg_request_all_parameter_values(self._sysex_id, algo_index),
            timeout=3.0,
        )
        if resp is None:
            return {"error": "No response"}
        return parse_all_parameter_values(resp)

    def get_enum_strings(
        self, algo_index: int, param_num: int
    ) -> dict[str, Any]:
        """Get enum option names for a parameter."""
        resp = self.send_and_wait(
            msg_request_enum_strings(self._sysex_id, algo_index, param_num)
        )
        if resp is None:
            return {"error": "No response"}
        return parse_enum_strings(resp)

    def get_unit_strings(self) -> list[str]:
        """Get the unit name table."""
        resp = self.send_and_wait(msg_request_unit_strings(self._sysex_id))
        if resp is None:
            return []
        strings = parse_unit_strings(resp)
        self._unit_strings = strings
        return strings

    # -- Mappings --

    def get_mappings(
        self, algo_index: int, param_num: int
    ) -> dict[str, Any]:
        """Get CV/MIDI/i2c mappings for a parameter."""
        resp = self.send_and_wait(
            msg_request_mappings(self._sysex_id, algo_index, param_num)
        )
        if resp is None:
            return {"error": "No response"}
        return parse_mapping(resp)

    def set_cv_mapping(
        self,
        algo_index: int,
        param_num: int,
        version: int,
        cv_input: int,
        flags: int = 0,
        volts: int = 0,
        delta: int = 0,
        source: int = 0,
    ) -> None:
        """Set CV mapping for a parameter."""
        self._send(
            msg_set_cv_mapping(
                self._sysex_id,
                algo_index,
                param_num,
                version,
                cv_input,
                flags,
                volts,
                delta,
                source,
            )
        )

    def set_midi_mapping(
        self,
        algo_index: int,
        param_num: int,
        version: int,
        midi_cc: int,
        midi_channel: int = 0,
        enabled: bool = True,
        symmetric: bool = False,
        aftertouch: bool = False,
        relative: bool = False,
        mapping_type: int = 0,
        midi_min: int = 0,
        midi_max: int = 127,
    ) -> None:
        """Set MIDI mapping for a parameter."""
        self._send(
            msg_set_midi_mapping(
                self._sysex_id,
                algo_index,
                param_num,
                version,
                midi_cc,
                midi_channel,
                enabled,
                symmetric,
                aftertouch,
                relative,
                mapping_type,
                midi_min,
                midi_max,
            )
        )

    def set_i2c_mapping(
        self,
        algo_index: int,
        param_num: int,
        version: int,
        i2c_cc: int,
        enabled: bool = True,
        symmetric: bool = False,
        i2c_min: int = 0,
        i2c_max: int = 16383,
    ) -> None:
        """Set I2C mapping for a parameter."""
        self._send(
            msg_set_i2c_mapping(
                self._sysex_id,
                algo_index,
                param_num,
                version,
                i2c_cc,
                enabled,
                symmetric,
                i2c_min,
                i2c_max,
            )
        )

    # -- System --

    def get_routing(self, algo_index: int) -> dict[str, Any]:
        """Get signal routing for an algorithm."""
        resp = self.send_and_wait(
            msg_request_routing(self._sysex_id, algo_index)
        )
        if resp is None:
            return {"error": "No response"}
        return parse_routing(resp)

    def get_cpu_usage(self) -> dict[str, Any]:
        """Get CPU usage per core and per slot."""
        resp = self.send_and_wait(msg_request_cpu_usage(self._sysex_id))
        if resp is None:
            return {"error": "No response"}
        return parse_cpu_usage(resp)

    def set_clock(self, unix_time: int) -> None:
        """Set the real-time clock."""
        self._send(msg_set_real_time_clock(self._sysex_id, unix_time))

    def wake(self) -> None:
        """Wake from sleep."""
        self._send(msg_wake(self._sysex_id))

    def reboot(self) -> None:
        """Reboot the module."""
        self._send(msg_reboot(self._sysex_id))

    # -- Tuning --

    def install_scala(self, filepath: str) -> int:
        """Upload a Scala tuning file. Returns bytes sent."""
        path = Path(filepath)
        raw = path.read_bytes()
        data = [b & 0x7F for b in raw]
        self._send(msg_install_scala(self._sysex_id, data))
        return len(data)

    def install_kbm(self, filepath: str) -> int:
        """Upload a keyboard mapping file. Returns bytes sent."""
        path = Path(filepath)
        raw = path.read_bytes()
        data = [b & 0x7F for b in raw]
        self._send(msg_install_kbm(self._sysex_id, data))
        return len(data)

    # -- Lua --

    def execute_lua(self, source: str) -> str:
        """Execute Lua code and return output."""
        resp = self.send_and_wait(
            msg_execute_lua(self._sysex_id, source), timeout=5.0
        )
        if resp is None:
            return "(no output)"
        return parse_lua_output(resp)

    def install_lua(self, slot: int, source: str) -> str:
        """Install Lua script to an algorithm slot. Returns output/status."""
        resp = self.send_and_wait(
            msg_install_lua(self._sysex_id, slot, source), timeout=5.0
        )
        if resp is None:
            return "(no response)"
        return parse_lua_output(resp)
