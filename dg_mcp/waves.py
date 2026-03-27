"""Preset waveform data for DG-Lab Coyote 3.0 (V3 format).

Each preset is a list of (freq, intensity) tuples.
Each tuple represents 100ms of output (4 identical sub-frames of 25ms).
The waveforms loop continuously when played.
"""

from dataclasses import dataclass

# Presets from the official SDK example.md

BREATH: list[tuple[int, int]] = [
    (10, 0),
    (10, 20),
    (10, 40),
    (10, 60),
    (10, 80),
    (10, 100),
    (10, 100),
    (10, 100),
    (10, 0),
    (10, 0),
    (10, 0),
    (10, 0),
]

TIDE: list[tuple[int, int]] = [
    (10, 0),
    (11, 16),
    (13, 33),
    (14, 50),
    (16, 66),
    (18, 83),
    (19, 100),
    (21, 92),
    (22, 84),
    (24, 76),
    (26, 68),
    (26, 0),
    (27, 16),
    (29, 33),
    (30, 50),
    (32, 66),
    (34, 83),
    (35, 100),
    (37, 92),
    (38, 84),
    (40, 76),
    (42, 68),
    (10, 0),
]

# Continuous steady pulse at various intensities
PULSE_LOW: list[tuple[int, int]] = [(10, 30)] * 10
PULSE_MID: list[tuple[int, int]] = [(10, 60)] * 10
PULSE_HIGH: list[tuple[int, int]] = [(10, 100)] * 10

# Quick tap pattern
TAP: list[tuple[int, int]] = [
    (10, 100),
    (10, 0),
    (10, 0),
    (10, 100),
    (10, 0),
    (10, 0),
]

PRESETS: dict[str, list[tuple[int, int]]] = {
    "breath": BREATH,
    "tide": TIDE,
    "pulse_low": PULSE_LOW,
    "pulse_mid": PULSE_MID,
    "pulse_high": PULSE_HIGH,
    "tap": TAP,
}


@dataclass
class WaveFrame:
    """A single 100ms wave frame with 4 sub-frames (25ms each)."""
    freq: tuple[int, int, int, int]
    intensity: tuple[int, int, int, int]


def preset_to_frames(name: str) -> list[WaveFrame]:
    """Convert a preset name to a list of WaveFrames."""
    data = PRESETS.get(name)
    if data is None:
        raise ValueError(f"Unknown preset: {name}. Available: {list(PRESETS.keys())}")
    return [
        WaveFrame(
            freq=(f, f, f, f),
            intensity=(i, i, i, i),
        )
        for f, i in data
    ]


def custom_wave_to_frames(
    freq: int = 10,
    intensity: int = 50,
    count: int = 10,
) -> list[WaveFrame]:
    """Create a simple custom waveform with uniform freq/intensity.

    Args:
        freq: Wave frequency (encoded, 10~240)
        intensity: Wave intensity (0~100)
        count: Number of 100ms frames
    """
    return [
        WaveFrame(
            freq=(freq, freq, freq, freq),
            intensity=(intensity, intensity, intensity, intensity),
        )
    ] * count


def steps_to_frames(steps: list[dict]) -> list[WaveFrame]:
    """Convert a list of step dicts to WaveFrames.

    Each step is a dict with:
        - freq: wave frequency (10~1000ms, will be auto-encoded to 10~240)
        - intensity: wave intensity (0~100)
        - repeat: optional, repeat this step N times (default 1)

    Example:
        [
            {"freq": 10, "intensity": 0},
            {"freq": 10, "intensity": 50, "repeat": 3},
            {"freq": 20, "intensity": 100},
        ]
    """
    from .protocol import encode_frequency

    frames = []
    for step in steps:
        f = encode_frequency(step["freq"])
        i = max(0, min(100, step.get("intensity", 0)))
        repeat = max(1, step.get("repeat", 1))
        frame = WaveFrame(freq=(f, f, f, f), intensity=(i, i, i, i))
        frames.extend([frame] * repeat)
    return frames
