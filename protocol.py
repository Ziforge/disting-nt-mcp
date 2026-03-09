"""Disting NT SysEx protocol: constants, encoding, message builders, response parsers."""

from __future__ import annotations

from math import pow
from typing import Any

# ---------------------------------------------------------------------------
# SysEx Header
# ---------------------------------------------------------------------------

MANUFACTURER_ID = [0x00, 0x21, 0x27]  # Expert Sleepers
DISTING_NT_PREFIX = 0x6D


def sysex_msg(sysex_id: int, cmd: int, data: list[int] | None = None) -> list[int]:
    """Build a complete Disting NT SysEx message.

    Format: F0 00 21 27 6D [sysex_id] [cmd] [data...] F7
    """
    msg = [0xF0] + MANUFACTURER_ID + [DISTING_NT_PREFIX, sysex_id & 0x7F, cmd]
    if data:
        msg.extend(data)
    msg.append(0xF7)
    return msg


# ---------------------------------------------------------------------------
# 16-bit Encoding (3 bytes, signed)
# ---------------------------------------------------------------------------


def encode16(value: int) -> list[int]:
    """Encode a signed 16-bit value as 3 SysEx-safe bytes."""
    v = value & 0xFFFF
    return [(v >> 14) & 0x03, (v >> 7) & 0x7F, v & 0x7F]


def decode16(data: list[int], offset: int = 0) -> int:
    """Decode 3 SysEx-safe bytes to a signed 16-bit value."""
    v = (data[offset] << 14) | (data[offset + 1] << 7) | data[offset + 2]
    if v & 0x8000:
        v -= 0x10000
    return v


def decode16_unsigned(data: list[int], offset: int = 0) -> int:
    """Decode 3 SysEx-safe bytes to an unsigned 16-bit value."""
    return (data[offset] << 14) | (data[offset + 1] << 7) | data[offset + 2]


# ---------------------------------------------------------------------------
# 32-bit Encoding (5 bytes, for timestamps)
# ---------------------------------------------------------------------------


def encode32(value: int) -> list[int]:
    """Encode a 32-bit value as 5 SysEx-safe bytes (MSB first)."""
    v = value & 0xFFFFFFFF
    return [
        (v >> 28) & 0x0F,
        (v >> 21) & 0x7F,
        (v >> 14) & 0x7F,
        (v >> 7) & 0x7F,
        v & 0x7F,
    ]


def decode32(data: list[int], offset: int = 0) -> int:
    """Decode 5 SysEx-safe bytes to a 32-bit value (LSB first in decode)."""
    return (
        (data[offset] & 0x7F)
        | ((data[offset + 1] & 0x7F) << 7)
        | ((data[offset + 2] & 0x7F) << 14)
        | ((data[offset + 3] & 0x7F) << 21)
        | ((data[offset + 4] & 0x0F) << 28)
    )


def decode35(data: list[int], offset: int = 0) -> int:
    """Decode 5 SysEx-safe bytes to a 35-bit value (for routing)."""
    return (
        (data[offset] & 0x7F)
        | ((data[offset + 1] & 0x7F) << 7)
        | ((data[offset + 2] & 0x7F) << 14)
        | ((data[offset + 3] & 0x7F) << 21)
        | ((data[offset + 4] & 0x7F) << 28)
    )


# ---------------------------------------------------------------------------
# ASCII Encoding
# ---------------------------------------------------------------------------


def encode_null_terminated_ascii(text: str) -> list[int]:
    """Encode a string as null-terminated ASCII bytes."""
    return [b & 0x7F for b in text.encode("ascii", errors="replace")] + [0x00]


def decode_null_terminated_ascii(data: list[int], offset: int = 0) -> tuple[str, int]:
    """Decode null-terminated ASCII, returning (string, next_offset)."""
    end = offset
    while end < len(data) and data[end] != 0x00:
        end += 1
    text = "".join(chr(b) if 32 <= b < 127 else "?" for b in data[offset:end])
    next_offset = end + 1 if end < len(data) else end
    return text, next_offset


# ---------------------------------------------------------------------------
# Display Mode Constants
# ---------------------------------------------------------------------------

DISPLAY_PARAMETERS = 0
DISPLAY_ALGORITHM_UI = 1
DISPLAY_OVERVIEW = 2
DISPLAY_OVERVIEW_VUS = 3

DISPLAY_MODE_NAMES = {
    DISPLAY_PARAMETERS: "parameters",
    DISPLAY_ALGORITHM_UI: "algorithmUI",
    DISPLAY_OVERVIEW: "overview",
    DISPLAY_OVERVIEW_VUS: "overviewVUs",
}

DISPLAY_MODE_VALUES = {v: k for k, v in DISPLAY_MODE_NAMES.items()}


# ---------------------------------------------------------------------------
# Command Constants — Host → Device
# ---------------------------------------------------------------------------

CMD_TAKE_SCREENSHOT = 0x01
CMD_SET_REAL_TIME_CLOCK = 0x04
CMD_WAKE = 0x07
CMD_EXECUTE_LUA = 0x08
CMD_INSTALL_LUA = 0x09
CMD_SCL_FILE = 0x11
CMD_KBM_FILE = 0x12
CMD_SET_DISPLAY_MODE = 0x20
CMD_REQUEST_VERSION_STRING = 0x22
CMD_REQUEST_NUM_ALGORITHMS = 0x30
CMD_REQUEST_ALGORITHM_INFO = 0x31
CMD_ADD_ALGORITHM = 0x32
CMD_REMOVE_ALGORITHM = 0x33
CMD_LOAD_PRESET = 0x34
CMD_NEW_PRESET = 0x35
CMD_SAVE_PRESET = 0x36
CMD_MOVE_ALGORITHM = 0x37
CMD_LOAD_PLUGIN = 0x38
CMD_REQUEST_ALGORITHM = 0x40
CMD_REQUEST_PRESET_NAME = 0x41
CMD_REQUEST_NUM_PARAMETERS = 0x42
CMD_REQUEST_PARAMETER_INFO = 0x43
CMD_REQUEST_ALL_PARAMETER_VALUES = 0x44
CMD_REQUEST_PARAMETER_VALUE = 0x45
CMD_SET_PARAMETER_VALUE = 0x46
CMD_SET_PRESET_NAME = 0x47
CMD_REQUEST_UNIT_STRINGS = 0x48
CMD_REQUEST_ENUM_STRINGS = 0x49
CMD_SET_FOCUS = 0x4A
CMD_REQUEST_MAPPINGS = 0x4B
CMD_SET_CV_MAPPING = 0x4D
CMD_SET_MIDI_MAPPING = 0x4E
CMD_SET_I2C_MAPPING = 0x4F
CMD_REQUEST_PARAMETER_VALUE_STRING = 0x50
CMD_SET_SLOT_NAME = 0x51
CMD_SET_PARAMETER_STRING = 0x53
CMD_REQUEST_NUM_ALGORITHMS_IN_PRESET = 0x60
CMD_REQUEST_ROUTING = 0x61
CMD_REQUEST_CPU_USAGE = 0x62
CMD_REBOOT = 0x7F

# ---------------------------------------------------------------------------
# Response Constants — Device → Host
# ---------------------------------------------------------------------------

RESP_LUA_OUTPUT = 0x09
RESP_NUM_ALGORITHMS = 0x30
RESP_ALGORITHM_INFO = 0x31
RESP_MESSAGE = 0x32
RESP_SCREENSHOT = 0x33
RESP_ALGORITHM = 0x40
RESP_PRESET_NAME = 0x41
RESP_NUM_PARAMETERS = 0x42
RESP_PARAMETER_INFO = 0x43
RESP_ALL_PARAMETER_VALUES = 0x44
RESP_PARAMETER_VALUE = 0x45
RESP_UNIT_STRINGS = 0x48
RESP_ENUM_STRINGS = 0x49
RESP_MAPPING = 0x4B
RESP_PARAMETER_VALUE_STRING = 0x50
RESP_NUM_ALGORITHMS_IN_PRESET = 0x60
RESP_ROUTING = 0x61
RESP_CPU_USAGE = 0x62


# ---------------------------------------------------------------------------
# Message Builders
# ---------------------------------------------------------------------------


def msg_take_screenshot(sysex_id: int) -> list[int]:
    """Request display screenshot (256x64)."""
    return sysex_msg(sysex_id, CMD_TAKE_SCREENSHOT)


def msg_set_real_time_clock(sysex_id: int, unix_time: int) -> list[int]:
    """Set the real-time clock."""
    return sysex_msg(sysex_id, CMD_SET_REAL_TIME_CLOCK, encode32(unix_time))


def msg_wake(sysex_id: int) -> list[int]:
    """Wake from sleep."""
    return sysex_msg(sysex_id, CMD_WAKE)


def msg_execute_lua(sysex_id: int, source: str) -> list[int]:
    """Execute Lua code immediately. No null terminator — F7 ends the data."""
    data = list(source.encode("utf-8"))
    return sysex_msg(sysex_id, CMD_EXECUTE_LUA, data)


def msg_install_lua(sysex_id: int, slot: int, source: str) -> list[int]:
    """Install Lua script to a specific algorithm slot."""
    data = [slot & 0x7F] + list(source.encode("utf-8"))
    return sysex_msg(sysex_id, CMD_INSTALL_LUA, data)


def msg_install_scala(sysex_id: int, file_data: list[int]) -> list[int]:
    """Upload Scala tuning data."""
    return sysex_msg(sysex_id, CMD_SCL_FILE, file_data)


def msg_install_kbm(sysex_id: int, file_data: list[int]) -> list[int]:
    """Upload keyboard mapping data."""
    return sysex_msg(sysex_id, CMD_KBM_FILE, file_data)


def msg_set_display_mode(sysex_id: int, mode: int) -> list[int]:
    """Set display mode (0=params, 1=algorithmUI, 2=overview, 3=overviewVUs)."""
    return sysex_msg(sysex_id, CMD_SET_DISPLAY_MODE, [mode & 0x7F])


def msg_request_version_string(sysex_id: int) -> list[int]:
    """Request firmware version string."""
    return sysex_msg(sysex_id, CMD_REQUEST_VERSION_STRING)


def msg_request_num_algorithms(sysex_id: int) -> list[int]:
    """Request total number of algorithms in library."""
    return sysex_msg(sysex_id, CMD_REQUEST_NUM_ALGORITHMS)


def msg_request_algorithm_info(sysex_id: int, index: int) -> list[int]:
    """Request info about a library algorithm by index."""
    return sysex_msg(sysex_id, CMD_REQUEST_ALGORITHM_INFO, encode16(index))


def msg_add_algorithm(
    sysex_id: int, guid: str, spec_values: list[int] | None = None
) -> list[int]:
    """Add algorithm by GUID with optional spec values."""
    data = [ord(c) & 0x7F for c in guid[:4]]
    if spec_values:
        for v in spec_values:
            data.extend(encode16(v))
    return sysex_msg(sysex_id, CMD_ADD_ALGORITHM, data)


def msg_remove_algorithm(sysex_id: int, slot_index: int) -> list[int]:
    """Remove algorithm from a slot."""
    return sysex_msg(sysex_id, CMD_REMOVE_ALGORITHM, [slot_index & 0x7F])


def msg_load_preset(sysex_id: int, name: str, append: bool = False) -> list[int]:
    """Load preset by name."""
    data = [1 if append else 0] + encode_null_terminated_ascii(name)
    return sysex_msg(sysex_id, CMD_LOAD_PRESET, data)


def msg_new_preset(sysex_id: int) -> list[int]:
    """Clear all slots (new preset)."""
    return sysex_msg(sysex_id, CMD_NEW_PRESET)


def msg_save_preset(sysex_id: int, option: int = 0) -> list[int]:
    """Save current state."""
    return sysex_msg(sysex_id, CMD_SAVE_PRESET, [option & 0x7F])


def msg_move_algorithm(
    sysex_id: int, from_index: int, to_index: int
) -> list[int]:
    """Move algorithm from one slot to another."""
    return sysex_msg(
        sysex_id, CMD_MOVE_ALGORITHM, [from_index & 0x7F, to_index & 0x7F]
    )


def msg_load_plugin(sysex_id: int, guid: str) -> list[int]:
    """Load a plugin by GUID."""
    data = [ord(c) & 0x7F for c in guid[:4]]
    return sysex_msg(sysex_id, CMD_LOAD_PLUGIN, data)


def msg_request_algorithm(sysex_id: int, slot_index: int) -> list[int]:
    """Request what algorithm is loaded in a slot."""
    return sysex_msg(sysex_id, CMD_REQUEST_ALGORITHM, [slot_index & 0x7F])


def msg_request_preset_name(sysex_id: int) -> list[int]:
    """Request current preset name."""
    return sysex_msg(sysex_id, CMD_REQUEST_PRESET_NAME)


def msg_request_num_parameters(sysex_id: int, algo_index: int) -> list[int]:
    """Request parameter count for an algorithm slot."""
    return sysex_msg(sysex_id, CMD_REQUEST_NUM_PARAMETERS, [algo_index & 0x7F])


def msg_request_parameter_info(
    sysex_id: int, algo_index: int, param_num: int
) -> list[int]:
    """Request info about a specific parameter."""
    return sysex_msg(
        sysex_id,
        CMD_REQUEST_PARAMETER_INFO,
        [algo_index & 0x7F] + encode16(param_num),
    )


def msg_request_all_parameter_values(sysex_id: int, algo_index: int) -> list[int]:
    """Request all parameter values for an algorithm slot."""
    return sysex_msg(
        sysex_id, CMD_REQUEST_ALL_PARAMETER_VALUES, [algo_index & 0x7F]
    )


def msg_request_parameter_value(
    sysex_id: int, algo_index: int, param_num: int
) -> list[int]:
    """Request a single parameter value."""
    return sysex_msg(
        sysex_id,
        CMD_REQUEST_PARAMETER_VALUE,
        [algo_index & 0x7F] + encode16(param_num),
    )


def msg_set_parameter_value(
    sysex_id: int, algo_index: int, param_num: int, value: int
) -> list[int]:
    """Set a parameter value."""
    return sysex_msg(
        sysex_id,
        CMD_SET_PARAMETER_VALUE,
        [algo_index & 0x7F] + encode16(param_num) + encode16(value),
    )


def msg_set_preset_name(sysex_id: int, name: str) -> list[int]:
    """Set current preset name."""
    return sysex_msg(
        sysex_id, CMD_SET_PRESET_NAME, encode_null_terminated_ascii(name)
    )


def msg_request_unit_strings(sysex_id: int) -> list[int]:
    """Request the unit strings table."""
    return sysex_msg(sysex_id, CMD_REQUEST_UNIT_STRINGS)


def msg_request_enum_strings(
    sysex_id: int, algo_index: int, param_num: int
) -> list[int]:
    """Request enum option names for a parameter."""
    return sysex_msg(
        sysex_id,
        CMD_REQUEST_ENUM_STRINGS,
        [algo_index & 0x7F] + encode16(param_num),
    )


def msg_set_focus(sysex_id: int, algo_index: int) -> list[int]:
    """Focus display on a specific algorithm slot."""
    return sysex_msg(sysex_id, CMD_SET_FOCUS, [algo_index & 0x7F])


def msg_request_mappings(
    sysex_id: int, algo_index: int, param_num: int
) -> list[int]:
    """Request CV/MIDI/i2c mappings for a parameter."""
    return sysex_msg(
        sysex_id,
        CMD_REQUEST_MAPPINGS,
        [algo_index & 0x7F] + encode16(param_num),
    )


def msg_set_cv_mapping(
    sysex_id: int,
    algo_index: int,
    param_num: int,
    version: int,
    cv_input: int,
    flags: int,
    volts: int,
    delta: int,
    source: int = 0,
) -> list[int]:
    """Set CV mapping for a parameter.

    Args:
        algo_index: Algorithm slot index.
        param_num: Parameter number.
        version: Mapping format version (1-5).
        cv_input: CV input number (0-127).
        flags: Bit 0 = unipolar, bit 1 = gate.
        volts: Voltage range (0-127).
        delta: Delta value (signed 16-bit).
        source: Source byte (version 4+ only).
    """
    data = [algo_index & 0x7F] + encode16(param_num) + [version & 0x7F]
    if version >= 4:
        data.append(source & 0x7F)
    data.extend([cv_input & 0x7F, flags & 0x7F, volts & 0x7F])
    data.extend(encode16(delta))
    return sysex_msg(sysex_id, CMD_SET_CV_MAPPING, data)


def msg_set_midi_mapping(
    sysex_id: int,
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
) -> list[int]:
    """Set MIDI mapping for a parameter.

    Args:
        algo_index: Algorithm slot index.
        param_num: Parameter number.
        version: Mapping format version (1-5).
        midi_cc: MIDI CC number (0-127).
        midi_channel: MIDI channel (0-15, 0=omni).
        enabled: Enable this mapping.
        symmetric: Symmetric mode.
        aftertouch: Use aftertouch instead of CC.
        relative: Relative CC mode (version 2+).
        mapping_type: 0=CC, 1=NoteMomentary, 2=NoteToggle, 3=CC14BitLow, 4=CC14BitHigh.
        midi_min: Minimum value (signed 16-bit).
        midi_max: Maximum value (signed 16-bit).
    """
    flags = (1 if enabled else 0) | (2 if symmetric else 0) | (4 if aftertouch else 0)
    flags |= (midi_channel & 0x0F) << 3

    data = [algo_index & 0x7F] + encode16(param_num) + [version & 0x7F]
    data.append(midi_cc & 0x7F)
    data.append(flags & 0x7F)
    if version >= 2:
        midi_flags2 = (1 if relative else 0) | ((mapping_type & 0x1F) << 2)
        data.append(midi_flags2 & 0x7F)
    data.extend(encode16(midi_min))
    data.extend(encode16(midi_max))
    return sysex_msg(sysex_id, CMD_SET_MIDI_MAPPING, data)


def msg_set_i2c_mapping(
    sysex_id: int,
    algo_index: int,
    param_num: int,
    version: int,
    i2c_cc: int,
    enabled: bool = True,
    symmetric: bool = False,
    i2c_min: int = 0,
    i2c_max: int = 16383,
) -> list[int]:
    """Set I2C mapping for a parameter (CMD 0x4F).

    Args:
        algo_index: Algorithm slot index.
        param_num: Parameter number.
        version: Mapping format version (1-5).
        i2c_cc: I2C CC number (0-255, low 7 bits in first byte, bit 7 in cc_high).
        enabled: Enable this mapping.
        symmetric: Symmetric mode.
        i2c_min: Minimum value (signed 16-bit).
        i2c_max: Maximum value (signed 16-bit).
    """
    data = [algo_index & 0x7F] + encode16(param_num) + [version & 0x7F]
    data.append(i2c_cc & 0x7F)
    if version >= 3:
        data.append((i2c_cc >> 7) & 0x01)
    flags = (1 if enabled else 0) | (2 if symmetric else 0)
    data.append(flags & 0x7F)
    data.extend(encode16(i2c_min))
    data.extend(encode16(i2c_max))
    return sysex_msg(sysex_id, CMD_SET_I2C_MAPPING, data)


def msg_request_parameter_value_string(
    sysex_id: int, algo_index: int, param_num: int
) -> list[int]:
    """Request formatted value text for a parameter."""
    return sysex_msg(
        sysex_id,
        CMD_REQUEST_PARAMETER_VALUE_STRING,
        [algo_index & 0x7F] + encode16(param_num),
    )


def msg_set_slot_name(sysex_id: int, algo_index: int, name: str) -> list[int]:
    """Set a custom label for an algorithm slot."""
    return sysex_msg(
        sysex_id,
        CMD_SET_SLOT_NAME,
        [algo_index & 0x7F] + encode_null_terminated_ascii(name),
    )


def msg_set_parameter_string(
    sysex_id: int, algo_index: int, param_num: int, text: str
) -> list[int]:
    """Set parameter string value."""
    data = [algo_index & 0x7F] + encode16(param_num)
    data.extend(list(text.encode("utf-8")))
    data.append(0x00)
    return sysex_msg(sysex_id, CMD_SET_PARAMETER_STRING, data)


def msg_request_num_algorithms_in_preset(sysex_id: int) -> list[int]:
    """Request how many algorithm slots are occupied."""
    return sysex_msg(sysex_id, CMD_REQUEST_NUM_ALGORITHMS_IN_PRESET)


def msg_request_routing(sysex_id: int, algo_index: int) -> list[int]:
    """Request signal routing for an algorithm."""
    return sysex_msg(sysex_id, CMD_REQUEST_ROUTING, [algo_index & 0x7F])


def msg_request_cpu_usage(sysex_id: int) -> list[int]:
    """Request CPU usage."""
    return sysex_msg(sysex_id, CMD_REQUEST_CPU_USAGE)


def msg_reboot(sysex_id: int) -> list[int]:
    """Reboot the module."""
    return sysex_msg(sysex_id, CMD_REBOOT)


# ---------------------------------------------------------------------------
# Response Parsers
# ---------------------------------------------------------------------------

# Payload starts after: F0 00 21 27 6D [sysex_id] [cmd] ... F7
# So header is 7 bytes, payload = data[7:-1]

HEADER_LEN = 7  # F0 + 3 mfr + 6D + sysex_id + cmd


def _payload(data: list[int]) -> list[int]:
    """Extract payload from a Disting NT SysEx message (after header, before F7)."""
    if len(data) > HEADER_LEN + 1:
        return data[HEADER_LEN:-1]
    return []


def _get_response_cmd(data: list[int]) -> int | None:
    """Get the command byte from a Disting NT SysEx response."""
    if len(data) >= HEADER_LEN and data[4] == DISTING_NT_PREFIX:
        return data[6]
    return None


def parse_version_string(data: list[int]) -> str:
    """Parse version string response (RESP 0x32 / respMessage)."""
    payload = _payload(data)
    if not payload:
        return "(empty)"
    return "".join(chr(b) if 32 <= b < 127 else "" for b in payload).rstrip("\x00").strip()


def parse_screenshot(data: list[int]) -> str:
    """Parse screenshot response (RESP 0x33): 256x64 pixel intensities → ASCII art.

    Raw pixel values are 0-15 intensity. Apply gamma correction to map to visible chars.
    """
    payload = _payload(data)
    if not payload:
        return "(empty screenshot)"

    width = 256
    height = 64

    # Map intensity to ASCII characters
    chars = " .:-=+*#%@"

    lines = []
    for y in range(height):
        row = []
        for x in range(width):
            idx = y * width + x
            if idx < len(payload):
                raw = payload[idx]
                # Gamma correction: raw is 0-15
                v = raw / 15.0
                v = pow(v, 0.45)  # gamma
                v = pow(v, 0.45)  # second gamma pass
                char_idx = int(v * (len(chars) - 1))
                char_idx = max(0, min(len(chars) - 1, char_idx))
                row.append(chars[char_idx])
            else:
                row.append(" ")
        lines.append("".join(row).rstrip())

    # Trim trailing blank lines
    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines)


def parse_num_algorithms(data: list[int]) -> int:
    """Parse number of algorithms in library (RESP 0x30)."""
    payload = _payload(data)
    if len(payload) >= 3:
        return decode16(payload, 0)
    return 0


def parse_algorithm_info(data: list[int]) -> dict[str, Any]:
    """Parse algorithm info response (RESP 0x31).

    Returns dict with: index, guid, name, specifications, plugin_info.
    """
    payload = _payload(data)
    if len(payload) < 6:
        return {"error": "Payload too short"}

    result: dict[str, Any] = {}
    offset = 0

    # Algorithm index (2 bytes in this response format)
    algo_index = (payload[offset] << 7) | payload[offset + 1]
    result["index"] = algo_index
    offset += 2

    # Skip 1 byte
    offset += 1

    # GUID (4 ASCII chars)
    if offset + 4 <= len(payload):
        result["guid"] = "".join(chr(b) for b in payload[offset : offset + 4])
        offset += 4
    else:
        return result

    # Number of specs
    if offset < len(payload):
        num_specs = payload[offset]
        offset += 1
    else:
        return result

    # Spec values: min, max, default, type for each
    specs = []
    for _ in range(num_specs):
        if offset + 10 > len(payload):
            break
        spec_min = decode16(payload, offset)
        offset += 3
        spec_max = decode16(payload, offset)
        offset += 3
        spec_default = decode16(payload, offset)
        offset += 3
        spec_type = payload[offset]
        offset += 1
        specs.append({
            "min": spec_min,
            "max": spec_max,
            "default": spec_default,
            "type": spec_type,
        })

    # Algorithm name (null-terminated)
    if offset < len(payload):
        name, offset = decode_null_terminated_ascii(payload, offset)
        result["name"] = name
    else:
        result["name"] = "(unknown)"

    # Spec names
    for i, spec in enumerate(specs):
        if offset < len(payload):
            spec_name, offset = decode_null_terminated_ascii(payload, offset)
            spec["name"] = spec_name

    result["specifications"] = specs

    # Optional plugin info
    if offset + 2 <= len(payload):
        result["is_plugin"] = bool(payload[offset])
        result["is_loaded"] = bool(payload[offset + 1])
        offset += 2
        if offset < len(payload):
            filename, offset = decode_null_terminated_ascii(payload, offset)
            result["filename"] = filename

    return result


def parse_algorithm(data: list[int]) -> dict[str, Any]:
    """Parse algorithm response (RESP 0x40): what's in a slot."""
    payload = _payload(data)
    if len(payload) < 5:
        return {"error": "Payload too short"}

    result: dict[str, Any] = {}
    result["index"] = payload[0]

    # GUID (4 ASCII chars)
    result["guid"] = "".join(chr(b) for b in payload[1:5])

    # Name (null-terminated)
    if len(payload) > 5:
        name, _ = decode_null_terminated_ascii(payload, 5)
        result["name"] = name
    else:
        result["name"] = "(unknown)"

    return result


def parse_preset_name(data: list[int]) -> str:
    """Parse preset name response (RESP 0x41)."""
    payload = _payload(data)
    if not payload:
        return "(empty)"
    name, _ = decode_null_terminated_ascii(payload, 0)
    return name


def parse_num_parameters(data: list[int]) -> dict[str, int]:
    """Parse number of parameters response (RESP 0x42)."""
    payload = _payload(data)
    if len(payload) < 4:
        return {"algo_index": 0, "count": 0}
    return {
        "algo_index": payload[0],
        "count": decode16(payload, 1),
    }


def parse_parameter_info(data: list[int]) -> dict[str, Any]:
    """Parse parameter info response (RESP 0x43).

    Returns: algo_index, param_num, min, max, default, unit, name, flags.
    """
    payload = _payload(data)
    if len(payload) < 14:
        return {"error": "Payload too short"}

    result: dict[str, Any] = {}
    offset = 0

    result["algo_index"] = payload[offset]
    offset += 1

    result["param_num"] = decode16(payload, offset)
    offset += 3

    result["min"] = decode16(payload, offset)
    offset += 3

    result["max"] = decode16(payload, offset)
    offset += 3

    result["default"] = decode16(payload, offset)
    offset += 3

    result["unit"] = payload[offset] if offset < len(payload) else 0
    offset += 1

    # Name (null-terminated)
    if offset < len(payload):
        name, offset = decode_null_terminated_ascii(payload, offset)
        result["name"] = name
    else:
        result["name"] = "(unknown)"

    # Flags byte after name
    if offset < len(payload):
        flags_byte = payload[offset]
        result["power_of_ten"] = -(flags_byte & 0x03)
        io_flags = (flags_byte >> 2) & 0x0F
        result["is_input"] = bool(io_flags & 0x01)
        result["is_output"] = bool(io_flags & 0x02)
        result["is_audio"] = bool(io_flags & 0x04)
        result["controls_output_mode"] = bool(io_flags & 0x08)
        result["flags_raw"] = flags_byte

    return result


def parse_all_parameter_values(data: list[int]) -> dict[str, Any]:
    """Parse all parameter values response (RESP 0x44).

    Each param is 3 bytes: [flags|ms2, mid7, ls7].
    """
    payload = _payload(data)
    if len(payload) < 1:
        return {"algo_index": 0, "values": []}

    algo_index = payload[0]
    values = []
    disabled = []

    offset = 1
    param_num = 0
    while offset + 3 <= len(payload):
        byte0 = payload[offset]
        # Extract flag bits (bits 2-6 of byte0)
        flag = (byte0 >> 2) & 0x1F
        is_disabled = flag == 1

        # Extract value (mask out flags from byte0)
        masked_byte0 = byte0 & 0x03
        v = (masked_byte0 << 14) | (payload[offset + 1] << 7) | payload[offset + 2]
        if v & 0x8000:
            v -= 0x10000

        values.append(v)
        disabled.append(is_disabled)
        offset += 3
        param_num += 1

    return {
        "algo_index": algo_index,
        "values": values,
        "disabled": disabled,
    }


def parse_parameter_value(data: list[int]) -> dict[str, Any]:
    """Parse single parameter value response (RESP 0x45)."""
    payload = _payload(data)
    if len(payload) < 4:
        return {"error": "Payload too short"}

    return {
        "algo_index": payload[0],
        "param_num": decode16(payload, 1),
        "value": decode16(payload, 4) if len(payload) >= 7 else 0,
    }


def parse_unit_strings(data: list[int]) -> list[str]:
    """Parse unit strings response (RESP 0x48)."""
    payload = _payload(data)
    if len(payload) < 1:
        return []

    num_strings = payload[0]
    strings = []
    offset = 1
    for _ in range(num_strings):
        if offset >= len(payload):
            break
        s, offset = decode_null_terminated_ascii(payload, offset)
        strings.append(s)

    return strings


def parse_enum_strings(data: list[int]) -> dict[str, Any]:
    """Parse enum strings response (RESP 0x49)."""
    payload = _payload(data)
    if len(payload) < 5:
        return {"algo_index": 0, "param_num": 0, "strings": []}

    algo_index = payload[0]
    param_num = decode16(payload, 1)
    count = payload[4]

    strings = []
    offset = 5
    for _ in range(count):
        if offset >= len(payload):
            break
        s, offset = decode_null_terminated_ascii(payload, offset)
        strings.append(s)

    return {
        "algo_index": algo_index,
        "param_num": param_num,
        "strings": strings,
    }


def parse_mapping(data: list[int]) -> dict[str, Any]:
    """Parse mapping response (RESP 0x4B).

    Returns CV, MIDI, and I2C mapping data.
    """
    payload = _payload(data)
    if len(payload) < 5:
        return {"error": "Payload too short"}

    result: dict[str, Any] = {}
    result["algo_index"] = payload[0]
    result["param_num"] = decode16(payload, 1)
    version = payload[4]
    result["version"] = version

    offset = 5

    # CV mapping
    cv: dict[str, Any] = {}
    if version >= 4 and offset < len(payload):
        cv["source"] = payload[offset]
        offset += 1
    if offset + 3 + 3 <= len(payload):
        cv["cv_input"] = payload[offset]
        offset += 1
        cv_flags = payload[offset]
        offset += 1
        cv["is_unipolar"] = bool(cv_flags & 0x01)
        cv["is_gate"] = bool(cv_flags & 0x02)
        cv["volts"] = payload[offset]
        offset += 1
        cv["delta"] = decode16(payload, offset)
        offset += 3
    result["cv"] = cv

    # MIDI mapping
    midi: dict[str, Any] = {}
    if offset < len(payload):
        midi["cc"] = payload[offset]
        offset += 1
    if offset < len(payload):
        midi_flags = payload[offset]
        offset += 1
        midi["enabled"] = bool(midi_flags & 0x01)
        midi["symmetric"] = bool(midi_flags & 0x02)
        midi["aftertouch"] = bool(midi_flags & 0x04)
        midi["channel"] = (midi_flags >> 3) & 0x0F
    if version >= 2 and offset < len(payload):
        midi_flags2 = payload[offset]
        offset += 1
        midi["relative"] = bool(midi_flags2 & 0x01)
        midi["mapping_type"] = (midi_flags2 >> 2) & 0x1F
    if offset + 6 <= len(payload):
        midi["min"] = decode16(payload, offset)
        offset += 3
        midi["max"] = decode16(payload, offset)
        offset += 3
    result["midi"] = midi

    # I2C mapping
    i2c: dict[str, Any] = {}
    if offset < len(payload):
        i2c["cc"] = payload[offset]
        offset += 1
    if version >= 3 and offset < len(payload):
        i2c_cc_high = payload[offset]
        offset += 1
        i2c["cc"] = (i2c.get("cc", 0) & 0x7F) | ((i2c_cc_high & 0x01) << 7)
    if offset < len(payload):
        i2c_flags = payload[offset]
        offset += 1
        i2c["enabled"] = bool(i2c_flags & 0x01)
        i2c["symmetric"] = bool(i2c_flags & 0x02)
    if offset + 6 <= len(payload):
        i2c["min"] = decode16(payload, offset)
        offset += 3
        i2c["max"] = decode16(payload, offset)
        offset += 3
    result["i2c"] = i2c

    return result


def parse_parameter_value_string(data: list[int]) -> dict[str, Any]:
    """Parse parameter value string response (RESP 0x50)."""
    payload = _payload(data)
    if len(payload) < 4:
        return {"algo_index": 0, "param_num": 0, "value_string": ""}

    algo_index = payload[0]
    param_num = decode16(payload, 1)
    value_string, _ = decode_null_terminated_ascii(payload, 4)

    return {
        "algo_index": algo_index,
        "param_num": param_num,
        "value_string": value_string,
    }


def parse_num_algorithms_in_preset(data: list[int]) -> int:
    """Parse number of algorithms in preset response (RESP 0x60)."""
    payload = _payload(data)
    if payload:
        return payload[0]
    return 0


def parse_routing(data: list[int]) -> dict[str, Any]:
    """Parse routing info response (RESP 0x61)."""
    payload = _payload(data)
    if len(payload) < 1:
        return {"error": "Payload too short"}

    algo_index = payload[0]
    routing_data = payload[1:]

    # Determine format based on length
    is_long = len(routing_data) > 30
    routing = []
    offset = 0

    for _ in range(6):
        if offset + 5 > len(routing_data):
            break
        d = decode35(routing_data, offset)
        if is_long:
            offset += 5
            if offset + 5 <= len(routing_data):
                d |= decode35(routing_data, offset) << 35
        else:
            d >>= 1
        offset += 5
        routing.append(d)

    return {
        "algo_index": algo_index,
        "routing": routing,
        "long_format": is_long,
    }


def parse_cpu_usage(data: list[int]) -> dict[str, Any]:
    """Parse CPU usage response (RESP 0x62)."""
    payload = _payload(data)
    if len(payload) < 2:
        return {"error": "Payload too short"}

    result: dict[str, Any] = {
        "cpu1": payload[0],
        "cpu2": payload[1],
    }

    if len(payload) > 2:
        result["slot_usage"] = list(payload[2:])

    return result


def parse_lua_output(data: list[int]) -> str:
    """Parse Lua output response (RESP 0x09)."""
    payload = _payload(data)
    if not payload:
        return ""
    return bytes(payload).decode("utf-8", errors="replace")
