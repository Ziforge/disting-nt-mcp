# disting-nt-mcp

MCP server for controlling an [Expert Sleepers Disting NT](https://expert-sleepers.co.uk/distingNT.html) multi-algorithm DSP Eurorack module over USB SysEx.

Provides 57 tools for algorithm management, preset control, per-algorithm parameter editing, CV/MIDI/I2C mapping, display control, Lua scripting, tuning, and standard MIDI messaging.

Part of the [Expert Sleepers MCP suite](https://github.com/Ziforge):
[fh2-mcp](https://github.com/Ziforge/fh2-mcp) |
[es9-mcp](https://github.com/Ziforge/es9-mcp) |
[disting-nt-mcp](https://github.com/Ziforge/disting-nt-mcp) |
[es-orchestrator-mcp](https://github.com/Ziforge/es-orchestrator-mcp)

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Expert Sleepers Disting NT connected via USB

## Setup

```bash
git clone https://github.com/Ziforge/disting-nt-mcp.git
cd disting-nt-mcp
uv sync
cp .env.example .env  # edit with your MIDI port names
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DISTING_NT_OUTPUT_PORT` | `Disting NT` | MIDI output port (substring match) |
| `DISTING_NT_INPUT_PORT` | `Disting NT` | MIDI input port (substring match) |
| `DISTING_NT_SYSEX_ID` | `0` | SysEx device ID (0-127, matches module setting) |
| `DISTING_NT_MIDI_CHANNEL` | `1` | MIDI channel for standard messages (1-16) |
| `DISTING_NT_AUTO_CONNECT` | `true` | Connect on server start |

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "disting-nt": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/disting-nt-mcp", "python", "server.py"]
    }
  }
}
```

## Tools (57)

### Connection (3)
| Tool | Description |
|------|-------------|
| `connect_disting_nt` | Connect to Disting NT MIDI ports (auto-detects) |
| `disconnect_disting_nt` | Disconnect from MIDI ports |
| `list_midi_ports` | List all available MIDI I/O ports |

### Algorithm Library (3)
| Tool | Description |
|------|-------------|
| `get_num_algorithms_in_library` | Total algorithms available in the library |
| `get_algorithm_info` | Query a library algorithm by index: GUID, name, specs |
| `add_algorithm` | Load an algorithm by GUID with optional spec values |

### Algorithm Slots (4)
| Tool | Description |
|------|-------------|
| `get_loaded_algorithm_count` | Count occupied algorithm slots |
| `get_loaded_algorithm` | Query what algorithm is in a slot: GUID, name |
| `remove_algorithm` | Remove an algorithm from a slot |
| `move_algorithm` | Reorder algorithms by moving a slot |

### Presets (5)
| Tool | Description |
|------|-------------|
| `get_preset_name` | Get current preset name |
| `set_preset_name` | Set preset name |
| `load_preset` | Load a preset by name (optionally append) |
| `save_preset` | Save current preset state |
| `new_preset` | Clear all slots (new preset) |

### Parameters (8)
| Tool | Description |
|------|-------------|
| `get_num_parameters` | Count parameters for a slot |
| `get_parameter_info` | Get param info: name, min, max, default, unit, flags |
| `get_parameter_value` | Get a single parameter value |
| `get_parameter_value_string` | Get formatted value text |
| `get_all_parameter_values` | Bulk read all values for a slot |
| `set_parameter_value` | Set a parameter value |
| `get_enum_strings` | Get enum option names for a parameter |
| `get_unit_strings` | Get the unit name table |

### CV/MIDI/I2C Mapping (5)
| Tool | Description |
|------|-------------|
| `get_mappings` | Get CV/MIDI/I2C mappings for a parameter |
| `set_cv_mapping` | Assign a CV input to a parameter |
| `set_midi_mapping` | Assign a MIDI CC to a parameter |
| `set_i2c_mapping` | Assign an I2C CC to a parameter |
| `auto_map_midi_cc` | Auto-map a MIDI CC using full parameter range |
| `list_active_mappings` | Scan all parameters and list active mappings |

### Display (4)
| Tool | Description |
|------|-------------|
| `take_screenshot` | Capture the 256x64 display as ASCII art |
| `set_display_mode` | Switch display mode |
| `set_focus` | Focus display on a specific algorithm slot |
| `set_slot_name` | Set a custom label for a slot |

### Routing & System (5)
| Tool | Description |
|------|-------------|
| `get_routing` | Get signal routing info for an algorithm |
| `get_cpu_usage` | CPU usage per core and per slot |
| `get_firmware_version` | Query firmware version string |
| `set_clock` | Set the real-time clock |
| `wake` | Wake from sleep |
| `reboot` | Reboot the module |

### Lua Scripting (2)
| Tool | Description |
|------|-------------|
| `execute_lua` | Execute Lua code immediately |
| `install_lua` | Install a Lua script to a specific slot |

### Tuning (2)
| Tool | Description |
|------|-------------|
| `install_scala` | Upload a Scala tuning file |
| `install_kbm` | Upload a keyboard mapping file |

### MIDI Messaging (5)
| Tool | Description |
|------|-------------|
| `send_note` | Send Note On/Off |
| `send_cc` | Send a MIDI CC message |
| `send_chord` | Send multiple notes simultaneously |
| `send_pitch_bend` | Send 14-bit pitch bend |
| `send_program_change` | Send Program Change with optional bank select |

### MIDI Monitoring (3)
| Tool | Description |
|------|-------------|
| `start_midi_monitor` | Start logging incoming MIDI messages |
| `stop_midi_monitor` | Stop logging |
| `get_midi_log` | Get recent messages from the log |

### SysEx & Raw (3)
| Tool | Description |
|------|-------------|
| `send_sysex` | Send a raw SysEx message |
| `receive_sysex` | Listen for a single incoming SysEx |
| `send_raw` | Send raw MIDI bytes directly |

### Safety & Status (2)
| Tool | Description |
|------|-------------|
| `all_notes_off` | Send All Notes Off (CC#123) |
| `midi_panic` | Emergency panic — silence everything |
| `query_status` | Full status: connection, firmware, preset, CPU, algorithms |

## Architecture

```
server.py      — FastMCP tool definitions (57 tools)
engine.py      — DistingNTEngine: MIDI connection + SysEx protocol
protocol.py    — Disting NT SysEx command encoding/decoding
config.py      — Configuration from environment
```

## Note

When using the [es-orchestrator-mcp](https://github.com/Ziforge/es-orchestrator-mcp), stop this server — macOS cannot share MIDI output ports between processes.
