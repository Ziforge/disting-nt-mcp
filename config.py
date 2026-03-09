"""Configuration for Disting NT MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class DistingNTConfig:
    """Configuration loaded from environment / .env file."""

    output_port: str = ""
    input_port: str = ""
    sysex_id: int = 0  # 0-127, matches module's MIDI channel setting
    midi_channel: int = 1  # 1-16 for standard MIDI messages
    auto_connect: bool = False

    @classmethod
    def from_env(cls, env_path: str | None = None) -> DistingNTConfig:
        load_dotenv(env_path)
        return cls(
            output_port=os.getenv("DISTING_NT_OUTPUT_PORT", ""),
            input_port=os.getenv("DISTING_NT_INPUT_PORT", ""),
            sysex_id=int(os.getenv("DISTING_NT_SYSEX_ID", "0")),
            midi_channel=int(os.getenv("DISTING_NT_MIDI_CHANNEL", "1")),
            auto_connect=os.getenv("DISTING_NT_AUTO_CONNECT", "false").lower()
            in ("true", "1", "yes"),
        )
