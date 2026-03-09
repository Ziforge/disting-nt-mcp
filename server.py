"""Disting NT MCP Server — control an Expert Sleepers Disting NT DSP module."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from mcp.server.fastmcp import Context, FastMCP

from config import DistingNTConfig
from disting_nt_engine import DistingNTEngine
from protocol import DISPLAY_MODE_NAMES, DISPLAY_MODE_VALUES

# ---------------------------------------------------------------------------
# Lifespan: initialize engine + optional auto-connect
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
    config = DistingNTConfig.from_env()
    engine = DistingNTEngine(sysex_id=config.sysex_id)

    if config.auto_connect and config.output_port:
        try:
            result = engine.connect(
                output_port=config.output_port,
                input_port=config.input_port or config.output_port,
            )
            print(f"[disting-nt-mcp] Auto-connected: {result}")
        except Exception as e:
            print(f"[disting-nt-mcp] Auto-connect failed: {e}")

    yield {"engine": engine, "config": config}

    # Cleanup
    engine.disconnect()


mcp = FastMCP(
    "disting-nt-midi",
    instructions=(
        "Control an Expert Sleepers Disting NT multi-algorithm DSP Eurorack module. "
        "Provides algorithm management, preset control, per-algorithm parameter editing, "
        "CV/MIDI mapping, display control, Lua scripting, tuning, "
        "and standard MIDI messaging over USB SysEx."
    ),
    lifespan=lifespan,
)


def _engine(ctx: Context) -> DistingNTEngine:
    return ctx.request_context.lifespan_context["engine"]


def _config(ctx: Context) -> DistingNTConfig:
    return ctx.request_context.lifespan_context["config"]


def _require_connection(ctx: Context) -> DistingNTEngine:
    engine = _engine(ctx)
    if not engine.connected:
        raise ValueError(
            "Not connected to Disting NT. Use connect_disting_nt first."
        )
    return engine


# ===================================================================
# 1. CONNECTION TOOLS (3)
# ===================================================================


@mcp.tool()
async def list_midi_ports(ctx: Context) -> str:
    """List all available MIDI input and output ports."""
    engine = _engine(ctx)
    loop = asyncio.get_event_loop()
    out_ports = await loop.run_in_executor(None, engine.list_output_ports)
    in_ports = await loop.run_in_executor(None, engine.list_input_ports)

    lines = ["=== Output Ports ==="]
    for i, p in enumerate(out_ports):
        lines.append(f"  [{i}] {p}")
    if not out_ports:
        lines.append("  (none)")

    lines.append("\n=== Input Ports ===")
    for i, p in enumerate(in_ports):
        lines.append(f"  [{i}] {p}")
    if not in_ports:
        lines.append("  (none)")

    return "\n".join(lines)


@mcp.tool()
async def connect_disting_nt(
    ctx: Context,
    output_port: str = "",
    input_port: str = "",
) -> str:
    """Connect to Disting NT MIDI ports. Auto-detects "Disting NT" if no port specified.

    Args:
        output_port: Port name substring or index (e.g. "Disting NT" or "0").
            If empty, uses DISTING_NT_OUTPUT_PORT from .env or auto-detects.
        input_port: Port name substring or index. If empty, matches output.
    """
    engine = _engine(ctx)
    config = _config(ctx)

    out = output_port or config.output_port
    inp = input_port or config.input_port or out

    # Try numeric index
    try:
        out = int(out)
    except (ValueError, TypeError):
        pass
    try:
        inp = int(inp)
    except (ValueError, TypeError):
        pass

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: engine.connect(output_port=out, input_port=inp)
    )
    return result


@mcp.tool()
async def disconnect_disting_nt(ctx: Context) -> str:
    """Disconnect from Disting NT MIDI ports."""
    engine = _engine(ctx)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, engine.disconnect)


# ===================================================================
# 2. DISPLAY TOOLS (3)
# ===================================================================


@mcp.tool()
async def take_screenshot(ctx: Context) -> str:
    """Capture the Disting NT 256x64 display as ASCII art (CMD 0x01 → 0x33).

    Returns a text representation of the screen pixels.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, engine.take_screenshot)


@mcp.tool()
async def set_display_mode(ctx: Context, mode: str) -> str:
    """Switch the Disting NT display mode (CMD 0x20).

    Args:
        mode: One of: parameters, algorithmUI, overview, overviewVUs.
    """
    engine = _require_connection(ctx)
    mode_lower = mode.lower().strip()
    mode_val = DISPLAY_MODE_VALUES.get(mode_lower)
    if mode_val is None:
        modes = ", ".join(DISPLAY_MODE_VALUES.keys())
        raise ValueError(f"Unknown mode '{mode}'. Available: {modes}")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: engine.set_display_mode(mode_val))
    return f"Display mode: {mode_lower}"


@mcp.tool()
async def set_focus(ctx: Context, algo_index: int) -> str:
    """Focus the Disting NT display on a specific algorithm slot (CMD 0x4A).

    Args:
        algo_index: Algorithm slot index (0-based).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: engine.set_focus(algo_index))
    return f"Focus set to algorithm slot {algo_index}"


# ===================================================================
# 3. ALGORITHM MANAGEMENT TOOLS (7)
# ===================================================================


@mcp.tool()
async def get_num_algorithms_in_library(ctx: Context) -> str:
    """Get the total number of algorithms available in the Disting NT library (CMD 0x30)."""
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    count = await loop.run_in_executor(None, engine.get_num_algorithms_in_library)
    if count < 0:
        return "No response from Disting NT"
    return f"Algorithm library: {count} algorithms available"


@mcp.tool()
async def get_algorithm_info(ctx: Context, index: int) -> str:
    """Query a library algorithm by index: GUID, name, specs (CMD 0x31).

    Args:
        index: Algorithm index in the library (0-based).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(
        None, lambda: engine.get_algorithm_info(index)
    )

    if "error" in info:
        return f"Error: {info['error']}"

    lines = [f"=== Algorithm {info.get('index', index)} ==="]
    lines.append(f"  GUID: {info.get('guid', '?')}")
    lines.append(f"  Name: {info.get('name', '?')}")

    specs = info.get("specifications", [])
    if specs:
        lines.append(f"  Specifications ({len(specs)}):")
        for s in specs:
            name = s.get("name", "?")
            lines.append(
                f"    {name}: min={s.get('min')}, max={s.get('max')}, "
                f"default={s.get('default')}, type={s.get('type')}"
            )

    if info.get("is_plugin"):
        lines.append(f"  Plugin: {info.get('filename', '?')} "
                      f"(loaded={info.get('is_loaded', False)})")

    return "\n".join(lines)


@mcp.tool()
async def get_loaded_algorithm_count(ctx: Context) -> str:
    """Get how many algorithm slots are occupied in the current preset (CMD 0x60)."""
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    count = await loop.run_in_executor(None, engine.get_loaded_algorithm_count)
    if count < 0:
        return "No response from Disting NT"
    return f"Loaded algorithms: {count} slots occupied"


@mcp.tool()
async def get_loaded_algorithm(ctx: Context, slot_index: int) -> str:
    """Query what algorithm is in a specific slot: GUID, name (CMD 0x40).

    Args:
        slot_index: Slot index (0-based).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(
        None, lambda: engine.get_loaded_algorithm(slot_index)
    )

    if "error" in info:
        return f"Error: {info['error']}"

    return (
        f"Slot {info.get('index', slot_index)}: "
        f"GUID={info.get('guid', '?')}, Name={info.get('name', '?')}"
    )


@mcp.tool()
async def add_algorithm(
    ctx: Context,
    guid: str,
    spec_values: list[int] | None = None,
) -> str:
    """Load an algorithm by its 4-character GUID with optional spec values (CMD 0x32).

    Args:
        guid: 4-character algorithm GUID (e.g. "VCO1", "DLYM").
        spec_values: Optional list of specification values (signed 16-bit each).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: engine.add_algorithm(guid, spec_values)
    )
    return f"Add algorithm '{guid}': {result}"


@mcp.tool()
async def remove_algorithm(ctx: Context, slot_index: int) -> str:
    """Remove an algorithm from a slot (CMD 0x33).

    Args:
        slot_index: Slot index to remove (0-based).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: engine.remove_algorithm(slot_index)
    )
    return f"Removed algorithm from slot {slot_index}"


@mcp.tool()
async def move_algorithm(
    ctx: Context, from_index: int, to_index: int
) -> str:
    """Reorder algorithms by moving one slot to another position (CMD 0x37).

    Args:
        from_index: Source slot index.
        to_index: Destination slot index.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: engine.move_algorithm(from_index, to_index)
    )
    return f"Moved algorithm from slot {from_index} to slot {to_index}"


# ===================================================================
# 4. PRESET MANAGEMENT TOOLS (6)
# ===================================================================


@mcp.tool()
async def new_preset(ctx: Context) -> str:
    """Clear all algorithm slots (new preset) (CMD 0x35)."""
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, engine.new_preset)
    return "New preset created (all slots cleared)"


@mcp.tool()
async def load_preset(
    ctx: Context, name: str, append: bool = False
) -> str:
    """Load a preset by name, optionally appending to current preset (CMD 0x34).

    Args:
        name: Preset name to load.
        append: If true, append to current preset instead of replacing.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: engine.load_preset(name, append)
    )
    mode = "appended" if append else "loaded"
    return f"Preset '{name}' {mode}"


@mcp.tool()
async def save_preset(ctx: Context, option: int = 0) -> str:
    """Save the current preset state (CMD 0x36).

    Args:
        option: Save option (default 0).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: engine.save_preset(option))
    return "Preset saved"


@mcp.tool()
async def get_preset_name(ctx: Context) -> str:
    """Request the current preset name (CMD 0x41)."""
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    name = await loop.run_in_executor(None, engine.get_preset_name)
    return f"Preset name: {name}"


@mcp.tool()
async def set_preset_name(ctx: Context, name: str) -> str:
    """Set the current preset name (CMD 0x47).

    Args:
        name: New preset name (ASCII).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: engine.set_preset_name(name))
    return f"Preset name set to: {name}"


@mcp.tool()
async def set_slot_name(
    ctx: Context, algo_index: int, name: str
) -> str:
    """Set a custom label for an algorithm slot (CMD 0x51).

    Args:
        algo_index: Algorithm slot index (0-based).
        name: Custom slot label (ASCII).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: engine.set_slot_name(algo_index, name)
    )
    return f"Slot {algo_index} label: {name}"


# ===================================================================
# 5. PARAMETER CONTROL TOOLS (8)
# ===================================================================


@mcp.tool()
async def get_num_parameters(ctx: Context, algo_index: int) -> str:
    """Count parameters for an algorithm slot (CMD 0x42).

    Args:
        algo_index: Algorithm slot index (0-based).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: engine.get_num_parameters(algo_index)
    )
    count = result.get("count", -1)
    if count < 0:
        return "No response from Disting NT"
    return f"Algorithm slot {algo_index}: {count} parameters"


@mcp.tool()
async def get_parameter_info(
    ctx: Context, algo_index: int, param_num: int
) -> str:
    """Get parameter info: name, min, max, default, unit, flags (CMD 0x43).

    Args:
        algo_index: Algorithm slot index (0-based).
        param_num: Parameter number (0-based).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(
        None, lambda: engine.get_parameter_info(algo_index, param_num)
    )

    if "error" in info:
        return f"Error: {info['error']}"

    lines = [f"=== Parameter {info.get('param_num', param_num)} ==="]
    lines.append(f"  Name: {info.get('name', '?')}")
    lines.append(f"  Range: {info.get('min')} to {info.get('max')}")
    lines.append(f"  Default: {info.get('default')}")
    lines.append(f"  Unit: {info.get('unit', 0)}")
    if "power_of_ten" in info:
        lines.append(f"  Power of ten: {info['power_of_ten']}")
    if info.get("is_input"):
        lines.append("  Type: Input")
    if info.get("is_output"):
        lines.append("  Type: Output")
    if info.get("is_audio"):
        lines.append("  Signal: Audio")

    return "\n".join(lines)


@mcp.tool()
async def get_parameter_value(
    ctx: Context, algo_index: int, param_num: int
) -> str:
    """Get a single parameter value (CMD 0x45).

    Args:
        algo_index: Algorithm slot index (0-based).
        param_num: Parameter number (0-based).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: engine.get_parameter_value(algo_index, param_num)
    )

    if "error" in result:
        return f"Error: {result['error']}"

    return (
        f"Algo {result.get('algo_index', algo_index)} "
        f"param {result.get('param_num', param_num)}: "
        f"value={result.get('value', '?')}"
    )


@mcp.tool()
async def get_parameter_value_string(
    ctx: Context, algo_index: int, param_num: int
) -> str:
    """Get the formatted value text for a parameter (CMD 0x50).

    Args:
        algo_index: Algorithm slot index (0-based).
        param_num: Parameter number (0-based).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: engine.get_parameter_value_string(algo_index, param_num)
    )

    if "error" in result:
        return f"Error: {result['error']}"

    return (
        f"Algo {result.get('algo_index', algo_index)} "
        f"param {result.get('param_num', param_num)}: "
        f"{result.get('value_string', '?')}"
    )


@mcp.tool()
async def set_parameter_value(
    ctx: Context, algo_index: int, param_num: int, value: int
) -> str:
    """Set a parameter value (CMD 0x46).

    Args:
        algo_index: Algorithm slot index (0-based).
        param_num: Parameter number (0-based).
        value: Parameter value (signed 16-bit).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: engine.set_parameter_value(algo_index, param_num, value)
    )
    return f"Set algo {algo_index} param {param_num} = {value}"


@mcp.tool()
async def get_all_parameter_values(ctx: Context, algo_index: int) -> str:
    """Bulk read all parameter values for an algorithm slot (CMD 0x44).

    Args:
        algo_index: Algorithm slot index (0-based).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: engine.get_all_parameter_values(algo_index)
    )

    if "error" in result:
        return f"Error: {result['error']}"

    values = result.get("values", [])
    disabled = result.get("disabled", [])

    lines = [f"=== All Parameters for Slot {result.get('algo_index', algo_index)} ({len(values)} params) ==="]
    for i, v in enumerate(values):
        suffix = " [disabled]" if i < len(disabled) and disabled[i] else ""
        lines.append(f"  [{i:3d}] {v}{suffix}")

    return "\n".join(lines)


@mcp.tool()
async def get_enum_strings(
    ctx: Context, algo_index: int, param_num: int
) -> str:
    """Get enum option names for a parameter (CMD 0x49).

    Args:
        algo_index: Algorithm slot index (0-based).
        param_num: Parameter number (0-based).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: engine.get_enum_strings(algo_index, param_num)
    )

    if "error" in result:
        return f"Error: {result['error']}"

    strings = result.get("strings", [])
    if not strings:
        return f"No enum strings for algo {algo_index} param {param_num}"

    lines = [f"=== Enum Options (algo {algo_index}, param {param_num}) ==="]
    for i, s in enumerate(strings):
        lines.append(f"  [{i}] {s}")

    return "\n".join(lines)


@mcp.tool()
async def get_unit_strings(ctx: Context) -> str:
    """Get the unit name table (CMD 0x48).

    Returns the list of unit strings used by parameter info responses.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    strings = await loop.run_in_executor(None, engine.get_unit_strings)

    if not strings:
        return "No unit strings received"

    lines = [f"=== Unit Strings ({len(strings)}) ==="]
    for i, s in enumerate(strings):
        lines.append(f"  [{i}] {s}")

    return "\n".join(lines)


# ===================================================================
# 6. MAPPING TOOLS (3)
# ===================================================================


@mcp.tool()
async def get_mappings(
    ctx: Context, algo_index: int, param_num: int
) -> str:
    """Get CV/MIDI/i2c mappings for a parameter (CMD 0x4B).

    Args:
        algo_index: Algorithm slot index (0-based).
        param_num: Parameter number (0-based).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: engine.get_mappings(algo_index, param_num)
    )

    if "error" in result:
        return f"Error: {result['error']}"

    lines = [
        f"=== Mappings (algo {result.get('algo_index')}, "
        f"param {result.get('param_num')}, v{result.get('version')}) ==="
    ]

    cv = result.get("cv", {})
    if cv:
        lines.append(f"  CV: input={cv.get('cv_input')}, "
                      f"unipolar={cv.get('is_unipolar')}, "
                      f"gate={cv.get('is_gate')}, "
                      f"volts={cv.get('volts')}, delta={cv.get('delta')}")
        if "source" in cv:
            lines.append(f"    Source: {cv['source']}")

    midi = result.get("midi", {})
    if midi:
        lines.append(f"  MIDI: cc={midi.get('cc')}, "
                      f"enabled={midi.get('enabled')}, "
                      f"ch={midi.get('channel')}, "
                      f"range=[{midi.get('min')}, {midi.get('max')}]")
        if "mapping_type" in midi:
            types = ["CC", "NoteMomentary", "NoteToggle", "CC14BitLow", "CC14BitHigh"]
            mt = midi["mapping_type"]
            type_name = types[mt] if mt < len(types) else str(mt)
            lines.append(f"    Type: {type_name}")

    i2c = result.get("i2c", {})
    if i2c:
        lines.append(f"  I2C: cc={i2c.get('cc')}, "
                      f"enabled={i2c.get('enabled')}, "
                      f"range=[{i2c.get('min')}, {i2c.get('max')}]")

    return "\n".join(lines)


@mcp.tool()
async def set_cv_mapping(
    ctx: Context,
    algo_index: int,
    param_num: int,
    cv_input: int,
    flags: int = 0,
    volts: int = 0,
    delta: int = 0,
    version: int = 5,
    source: int = 0,
) -> str:
    """Assign a CV input to a parameter (CMD 0x4D).

    Args:
        algo_index: Algorithm slot index (0-based).
        param_num: Parameter number (0-based).
        cv_input: CV input number (0-127).
        flags: Bit 0 = unipolar, bit 1 = gate.
        volts: Voltage range (0-127).
        delta: Delta value (signed 16-bit).
        version: Mapping format version (default 5).
        source: Source byte (version 4+ only).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: engine.set_cv_mapping(
            algo_index, param_num, version, cv_input, flags, volts, delta, source
        ),
    )
    return (
        f"CV mapping set: algo {algo_index} param {param_num} "
        f"← CV input {cv_input}"
    )


@mcp.tool()
async def set_midi_mapping(
    ctx: Context,
    algo_index: int,
    param_num: int,
    midi_cc: int,
    midi_channel: int = 0,
    enabled: bool = True,
    symmetric: bool = False,
    aftertouch: bool = False,
    relative: bool = False,
    mapping_type: int = 0,
    midi_min: int = 0,
    midi_max: int = 127,
    version: int = 5,
) -> str:
    """Assign a MIDI CC to a parameter (CMD 0x4E).

    Args:
        algo_index: Algorithm slot index (0-based).
        param_num: Parameter number (0-based).
        midi_cc: MIDI CC number (0-127).
        midi_channel: MIDI channel (0-15, 0=omni).
        enabled: Enable this mapping.
        symmetric: Symmetric mode.
        aftertouch: Use aftertouch instead of CC.
        relative: Relative CC mode.
        mapping_type: 0=CC, 1=NoteMomentary, 2=NoteToggle, 3=CC14BitLow, 4=CC14BitHigh.
        midi_min: Minimum value (signed 16-bit).
        midi_max: Maximum value (signed 16-bit).
        version: Mapping format version (default 5).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: engine.set_midi_mapping(
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
        ),
    )
    return (
        f"MIDI mapping set: algo {algo_index} param {param_num} "
        f"← CC {midi_cc} (ch {midi_channel})"
    )


# ===================================================================
# 7. SYSTEM TOOLS (6)
# ===================================================================


@mcp.tool()
async def get_firmware_version(ctx: Context) -> str:
    """Request the Disting NT firmware version string (CMD 0x22)."""
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    version = await loop.run_in_executor(None, engine.get_firmware_version)
    return f"Firmware: {version}"


@mcp.tool()
async def get_cpu_usage(ctx: Context) -> str:
    """Request CPU usage per core and per algorithm slot (CMD 0x62)."""
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, engine.get_cpu_usage)

    if "error" in result:
        return f"Error: {result['error']}"

    lines = ["=== CPU Usage ==="]
    lines.append(f"  Core 1: {result.get('cpu1', '?')}%")
    lines.append(f"  Core 2: {result.get('cpu2', '?')}%")

    slots = result.get("slot_usage", [])
    if slots:
        lines.append("  Per-slot:")
        for i, usage in enumerate(slots):
            lines.append(f"    Slot {i}: {usage}%")

    return "\n".join(lines)


@mcp.tool()
async def get_routing(ctx: Context, algo_index: int) -> str:
    """Request signal routing info for an algorithm (CMD 0x61).

    Args:
        algo_index: Algorithm slot index (0-based).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: engine.get_routing(algo_index)
    )

    if "error" in result:
        return f"Error: {result['error']}"

    lines = [f"=== Routing for Slot {result.get('algo_index', algo_index)} ==="]
    routing = result.get("routing", [])
    for i, r in enumerate(routing):
        lines.append(f"  Route {i}: {r}")
    lines.append(f"  Format: {'long' if result.get('long_format') else 'short'}")

    return "\n".join(lines)


@mcp.tool()
async def set_clock(ctx: Context, unix_time: int) -> str:
    """Set the Disting NT real-time clock (CMD 0x04).

    Args:
        unix_time: Unix timestamp in seconds.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: engine.set_clock(unix_time))
    return f"Clock set to {unix_time}"


@mcp.tool()
async def wake(ctx: Context) -> str:
    """Wake the Disting NT from sleep (CMD 0x07)."""
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, engine.wake)
    return "Wake signal sent"


@mcp.tool()
async def reboot(ctx: Context) -> str:
    """Reboot the Disting NT module (CMD 0x7F)."""
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, engine.reboot)
    return "Reboot command sent"


# ===================================================================
# 8. TUNING TOOLS (2)
# ===================================================================


@mcp.tool()
async def install_scala(ctx: Context, filepath: str) -> str:
    """Upload a Scala tuning file to the Disting NT (CMD 0x11).

    Args:
        filepath: Path to the .scl Scala tuning file.
    """
    engine = _require_connection(ctx)
    path = Path(filepath)
    if not path.exists():
        return f"File not found: {filepath}"

    loop = asyncio.get_event_loop()
    size = await loop.run_in_executor(
        None, lambda: engine.install_scala(filepath)
    )
    return f"Installed Scala tuning from {path.name} ({size} bytes)"


@mcp.tool()
async def install_kbm(ctx: Context, filepath: str) -> str:
    """Upload a keyboard mapping file to the Disting NT (CMD 0x12).

    Args:
        filepath: Path to the .kbm keyboard mapping file.
    """
    engine = _require_connection(ctx)
    path = Path(filepath)
    if not path.exists():
        return f"File not found: {filepath}"

    loop = asyncio.get_event_loop()
    size = await loop.run_in_executor(
        None, lambda: engine.install_kbm(filepath)
    )
    return f"Installed keyboard mapping from {path.name} ({size} bytes)"


# ===================================================================
# 9. LUA SCRIPTING TOOLS (2)
# ===================================================================


@mcp.tool()
async def execute_lua(ctx: Context, source: str) -> str:
    """Execute Lua code immediately on the Disting NT (CMD 0x08).

    Args:
        source: Lua source code to execute.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None, lambda: engine.execute_lua(source)
    )
    return f"Lua output: {output}"


@mcp.tool()
async def install_lua(ctx: Context, slot: int, source: str) -> str:
    """Install a Lua script to a specific algorithm slot (CMD 0x09).

    Args:
        slot: Algorithm slot index (0-based).
        source: Lua source code to install.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None, lambda: engine.install_lua(slot, source)
    )
    return f"Lua install (slot {slot}): {output}"


# ===================================================================
# 10. STANDARD MIDI TOOLS (5)
# ===================================================================


@mcp.tool()
async def send_note(
    ctx: Context,
    channel: int,
    note: int,
    velocity: int = 100,
    duration_ms: int = 500,
) -> str:
    """Send a note (Note On, wait, Note Off) on a MIDI channel.

    Args:
        channel: MIDI channel 1-16.
        note: MIDI note number 0-127 (60 = middle C).
        velocity: Note velocity 0-127.
        duration_ms: Note duration in milliseconds.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()

    await loop.run_in_executor(
        None, lambda: engine.send_note_on(channel, note, velocity)
    )
    await asyncio.sleep(duration_ms / 1000.0)
    await loop.run_in_executor(
        None, lambda: engine.send_note_off(channel, note)
    )
    return f"Note {note} vel={velocity} dur={duration_ms}ms on ch {channel}"


@mcp.tool()
async def send_cc(
    ctx: Context, channel: int, cc: int, value: int
) -> str:
    """Send a MIDI CC message.

    Args:
        channel: MIDI channel 1-16.
        cc: CC number 0-127.
        value: CC value 0-127.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: engine.send_cc(channel, cc, value)
    )
    return f"CC {cc}={value} on ch {channel}"


@mcp.tool()
async def send_program_change(
    ctx: Context,
    channel: int,
    program: int,
    bank_msb: int = -1,
    bank_lsb: int = -1,
) -> str:
    """Send Program Change with optional bank select.

    Args:
        channel: MIDI channel 1-16.
        program: Program number 0-127.
        bank_msb: Bank select MSB (CC#0). -1 to skip.
        bank_lsb: Bank select LSB (CC#32). -1 to skip.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()

    if bank_msb >= 0:
        lsb = bank_lsb if bank_lsb >= 0 else None
        await loop.run_in_executor(
            None, lambda: engine.send_bank_select(channel, bank_msb, lsb)
        )

    await loop.run_in_executor(
        None, lambda: engine.send_program_change(channel, program)
    )

    parts = [f"PC {program} on ch {channel}"]
    if bank_msb >= 0:
        parts.append(f"bank MSB={bank_msb}")
    if bank_lsb >= 0:
        parts.append(f"LSB={bank_lsb}")
    return "Sent " + ", ".join(parts)


@mcp.tool()
async def send_pitch_bend(
    ctx: Context, channel: int, value: int = 8192
) -> str:
    """Send 14-bit pitch bend.

    Args:
        channel: MIDI channel 1-16.
        value: Pitch bend value 0-16383 (8192 = center/no bend).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: engine.send_pitch_bend(channel, value)
    )
    return f"Pitch bend {value} on ch {channel}"


@mcp.tool()
async def send_chord(
    ctx: Context,
    channel: int,
    notes: list[int],
    velocity: int = 100,
    duration_ms: int = 500,
) -> str:
    """Send multiple notes simultaneously as a chord.

    Args:
        channel: MIDI channel 1-16.
        notes: List of MIDI note numbers (e.g. [60, 64, 67] for C major).
        velocity: Velocity 0-127.
        duration_ms: Chord duration in milliseconds.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()

    for n in notes:
        await loop.run_in_executor(
            None, lambda note=n: engine.send_note_on(channel, note, velocity)
        )

    await asyncio.sleep(duration_ms / 1000.0)

    for n in notes:
        await loop.run_in_executor(
            None, lambda note=n: engine.send_note_off(channel, note)
        )

    note_str = ", ".join(str(n) for n in notes)
    return f"Chord [{note_str}] vel={velocity} dur={duration_ms}ms on ch {channel}"


# ===================================================================
# 11. MONITOR TOOLS (3)
# ===================================================================


@mcp.tool()
async def start_midi_monitor(ctx: Context) -> str:
    """Start logging incoming MIDI messages to a ring buffer (1000 max)."""
    engine = _require_connection(ctx)
    engine.start_monitor()
    return f"MIDI monitor started on {engine.port_info}"


@mcp.tool()
async def stop_midi_monitor(ctx: Context) -> str:
    """Stop logging incoming MIDI messages."""
    engine = _require_connection(ctx)
    engine.stop_monitor()
    return "MIDI monitor stopped"


@mcp.tool()
async def get_midi_log(
    ctx: Context, count: int = 50, type_filter: str = ""
) -> str:
    """Get recent MIDI messages from the monitor log.

    Args:
        count: Number of messages to return (default 50, max 200).
        type_filter: Filter by message type substring (e.g. "note", "cc", "sysex").
    """
    engine = _require_connection(ctx)
    count = min(count, 200)
    filt = type_filter if type_filter else None
    msgs = engine.get_log(count=count, type_filter=filt)

    if not msgs:
        status = "monitoring" if engine.is_monitoring else "not monitoring"
        return f"No messages in log ({status})"

    lines = [f"=== MIDI Log ({len(msgs)} messages) ==="]
    for m in msgs:
        t = time.strftime("%H:%M:%S", time.localtime(m.timestamp))
        ms = int((m.timestamp % 1) * 1000)
        lines.append(f"  [{t}.{ms:03d}] {m.description}")

    return "\n".join(lines)


# ===================================================================
# 12. SYSEX TOOLS (3)
# ===================================================================


@mcp.tool()
async def send_sysex(ctx: Context, data: list[int]) -> str:
    """Send a raw SysEx message. Auto-frames with F0/F7 if needed.

    Args:
        data: List of byte values, e.g. [0xF0, 0x00, 0x21, 0x27, 0x6D, 0x00, 0x22, 0xF7].
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: engine.send_sysex(data))
    return f"Sent SysEx ({len(data)} bytes)"


@mcp.tool()
async def receive_sysex(ctx: Context, timeout: float = 5.0) -> str:
    """Listen for a single incoming SysEx message with timeout.

    Args:
        timeout: Seconds to wait (default 5).
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: engine.wait_for_sysex(timeout)
    )
    if result is None:
        return f"No SysEx received within {timeout}s"
    hex_str = " ".join(f"{b:02X}" for b in result)
    return f"Received SysEx ({len(result)} bytes): {hex_str}"


@mcp.tool()
async def send_raw(ctx: Context, data: list[int]) -> str:
    """Send raw MIDI bytes directly - no framing, no validation.

    Args:
        data: Raw MIDI bytes, e.g. [0x90, 60, 100] for Note On C4.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: engine.send_raw(data))
    hex_str = " ".join(f"{b:02X}" for b in data)
    return f"Sent raw MIDI ({len(data)} bytes): {hex_str}"


# ===================================================================
# 13. SAFETY TOOLS (2)
# ===================================================================


@mcp.tool()
async def all_notes_off(ctx: Context, channel: int = 0) -> str:
    """Send All Notes Off (CC#123) to silence stuck notes.

    Args:
        channel: MIDI channel 1-16, or 0 for all channels.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()

    if channel == 0:
        for ch in range(1, 17):
            await loop.run_in_executor(
                None, lambda c=ch: engine.all_notes_off(c)
            )
        return "All Notes Off sent on channels 1-16"
    else:
        await loop.run_in_executor(
            None, lambda: engine.all_notes_off(channel)
        )
        return f"All Notes Off sent on ch {channel}"


@mcp.tool()
async def midi_panic(ctx: Context) -> str:
    """Emergency MIDI panic - silence everything immediately.

    Sends All Notes Off (CC#123), Reset All Controllers (CC#121),
    and centers pitch bend on all 16 channels, then sends MIDI Stop.
    """
    engine = _require_connection(ctx)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, engine.panic)
    return "MIDI PANIC: All Notes Off + Reset Controllers + Stop on all 16 channels"


# ===================================================================
# 14. STATUS TOOL (1)
# ===================================================================


@mcp.tool()
async def query_status(ctx: Context) -> str:
    """Show full Disting NT MCP server status: connection, monitor, firmware, preset, CPU, algorithms."""
    engine = _engine(ctx)
    config = _config(ctx)

    lines = ["=== Disting NT MCP Status ==="]
    lines.append(f"  Connected: {engine.connected}")
    if engine.connected:
        lines.append(f"  Output: {engine._out_port_name}")
        lines.append(f"  Input:  {engine._in_port_name}")
    lines.append(f"  SysEx ID: {engine._sysex_id}")
    lines.append(f"  MIDI channel: {config.midi_channel}")
    lines.append(f"  Monitor: {'running' if engine.is_monitoring else 'stopped'}")
    lines.append(f"  Log messages: {engine.log_count}")
    lines.append(f"  Firmware: {engine._firmware_version or '(not queried)'}")
    lines.append(f"  Preset name: {engine._preset_name or '(not queried)'}")
    lines.append(f"  Unit strings: {'cached' if engine._unit_strings else '(not queried)'}")
    return "\n".join(lines)


# ===================================================================
# Entry point
# ===================================================================


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
