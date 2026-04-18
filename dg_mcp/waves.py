"""Waveform library for DG-Lab Coyote 3.0 (V3 format).

Wave definitions are stored in a JSON file at ~/.local/share/dg-mcp/waves.json.
On first run the file is created with the built-in presets.
"""

import json
from dataclasses import dataclass
from pathlib import Path

WAVES_FILE = Path.home() / ".local" / "share" / "dg-mcp" / "waves.json"

_DEFAULTS: dict = {
    "breath": {
        "description": "Slow rhythmic rise and fall, mimicking a breathing pattern",
        "steps": [
            {"freq": 10, "intensity": 0},
            {"freq": 10, "intensity": 20},
            {"freq": 10, "intensity": 40},
            {"freq": 10, "intensity": 60},
            {"freq": 10, "intensity": 80},
            {"freq": 10, "intensity": 100},
            {"freq": 10, "intensity": 100},
            {"freq": 10, "intensity": 100},
            {"freq": 10, "intensity": 0},
            {"freq": 10, "intensity": 0},
            {"freq": 10, "intensity": 0},
            {"freq": 10, "intensity": 0},
        ],
    },
    "tide": {
        "description": "Gradual wave that builds and ebbs twice with rising frequency, like ocean tides",
        "steps": [
            {"freq": 10, "intensity": 0},
            {"freq": 11, "intensity": 16},
            {"freq": 13, "intensity": 33},
            {"freq": 14, "intensity": 50},
            {"freq": 16, "intensity": 66},
            {"freq": 18, "intensity": 83},
            {"freq": 19, "intensity": 100},
            {"freq": 21, "intensity": 92},
            {"freq": 22, "intensity": 84},
            {"freq": 24, "intensity": 76},
            {"freq": 26, "intensity": 68},
            {"freq": 26, "intensity": 0},
            {"freq": 27, "intensity": 16},
            {"freq": 29, "intensity": 33},
            {"freq": 30, "intensity": 50},
            {"freq": 32, "intensity": 66},
            {"freq": 34, "intensity": 83},
            {"freq": 35, "intensity": 100},
            {"freq": 37, "intensity": 92},
            {"freq": 38, "intensity": 84},
            {"freq": 40, "intensity": 76},
            {"freq": 42, "intensity": 68},
            {"freq": 10, "intensity": 0},
        ],
    },
    "pulse_low": {
        "description": "Steady gentle continuous pulse",
        "steps": [{"freq": 10, "intensity": 30, "repeat": 10}],
    },
    "pulse_mid": {
        "description": "Steady moderate continuous pulse",
        "steps": [{"freq": 10, "intensity": 60, "repeat": 10}],
    },
    "pulse_high": {
        "description": "Steady intense continuous pulse",
        "steps": [{"freq": 10, "intensity": 100, "repeat": 10}],
    },
    "tap": {
        "description": "Sharp double-tap with pauses — rhythmic intermittent pulses",
        "steps": [
            {"freq": 10, "intensity": 100},
            {"freq": 10, "intensity": 0},
            {"freq": 10, "intensity": 0},
            {"freq": 10, "intensity": 100},
            {"freq": 10, "intensity": 0},
            {"freq": 10, "intensity": 0},
        ],
    },
}


@dataclass
class WaveFrame:
    """A single 100ms wave frame with 4 sub-frames (25ms each)."""
    freq: tuple[int, int, int, int]
    intensity: tuple[int, int, int, int]


def load_waves() -> dict:
    """Load wave library from JSON, creating it with defaults if missing."""
    if not WAVES_FILE.exists():
        WAVES_FILE.parent.mkdir(parents=True, exist_ok=True)
        WAVES_FILE.write_text(json.dumps(_DEFAULTS, indent=2))
        return dict(_DEFAULTS)
    return json.loads(WAVES_FILE.read_text())


def save_wave(name: str, steps: list[dict], description: str) -> None:
    """Add or overwrite a wave entry in the JSON library."""
    waves = load_waves()
    waves[name] = {"description": description, "steps": steps}
    WAVES_FILE.write_text(json.dumps(waves, indent=2))


def get_frames(name: str) -> list[WaveFrame]:
    """Return WaveFrames for a named wave from the library."""
    waves = load_waves()
    if name not in waves:
        raise ValueError(f"Unknown wave: '{name}'. Available: {list(waves.keys())}")
    return steps_to_frames(waves[name]["steps"])


def steps_to_frames(steps: list[dict]) -> list[WaveFrame]:
    """Convert a list of step dicts to WaveFrames.

    Each step is a dict with:
        - freq: wave period in ms (10~1000). V3 encoding happens at write time.
        - intensity: wave intensity (0~100)
        - repeat: optional, repeat this step N times (default 1)
    """
    frames = []
    for step in steps:
        f = max(10, min(1000, step["freq"]))
        i = max(0, min(100, step.get("intensity", 0)))
        repeat = max(1, step.get("repeat", 1))
        frame = WaveFrame(freq=(f, f, f, f), intensity=(i, i, i, i))
        frames.extend([frame] * repeat)
    return frames


def custom_wave_to_frames(
    freq: int = 10,
    intensity: int = 50,
    count: int = 10,
) -> list[WaveFrame]:
    """Create a simple custom waveform with uniform freq/intensity.

    Args:
        freq: Wave period in ms (10~1000). V3 encoding happens at write time.
        intensity: Wave intensity (0~100)
        count: Number of 100ms frames
    """
    return [
        WaveFrame(
            freq=(freq, freq, freq, freq),
            intensity=(intensity, intensity, intensity, intensity),
        )
    ] * count
