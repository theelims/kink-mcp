"""MCP Server for DG-Lab Coyote and Lovense devices."""

import json
import logging

from mcp.server.fastmcp import FastMCP

from .device import CoyoteDevice, DeviceManager
from .waves import get_frames, load_waves, save_wave, steps_to_frames

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "DG-Lab Coyote & Lovense",
    instructions=(
        "Control DG-Lab Coyote electro-stimulation devices and Lovense vibrator toys via Bluetooth. "
        "\n\n"
        "COYOTE (e-stim): each device has two channels (A and B), each gets its own alias. "
        "Use set_strength, adjust_strength, set_strength_limit, play_wave, design_wave, stop_wave. "
        "Typical flow: scan → connect(address, alias_a, alias_b) → set_strength → play_wave. "
        "\n\n"
        "LOVENSE (vibration): each toy has one channel. alias_b is not needed. "
        "Use vibrate(alias, strength) to set intensity 0–100% (0 = stop). "
        "Typical flow: scan → connect(address, alias_a) → vibrate(alias, strength). "
        "\n\n"
        "GENERAL: Strength range 0–100%. Always start low (5–10%) and increase gradually. "
        "loop=0 means infinite loop; loop=N plays the wave N times then stops. "
        "Read the devices://status resource for a live snapshot of all connected devices before issuing commands. "
        "Read waves://library for all available wave names and descriptions. "
        "To create a custom wave: design_wave(steps, name, description) saves it to the library, "
        "then play_wave(alias, name) plays it. "
        "Read waves://guide for a full explanation of wave parameters and how they feel."
        "Call live_status() for a live snapshot of all connected devices before issuing commands."
    ),
)

manager = DeviceManager()


@mcp.tool()
def live_status() -> str:
    """Live session snapshot: alias routing, current state, and activity timers.

    Call this before issuing any commands to see what devices and aliases are connected.
    """
    s = manager.get_all_status()
    session = s.get("session", {})
    lines = [
        f"Session running since: {session.get('running_since') or 'not started'}",
        f"Connected devices: {s['connected_devices']}",
        "",
    ]
    if not s["aliases"]:
        lines.append("No aliases registered. Call connect() first.")
        return "\n".join(lines)

    for alias, channels in s["aliases"].items():
        for ch in channels:
            dtype = ch["device_type"]
            last = ch.get("last_activity") or "never"
            if dtype == "lovense":
                tools = "vibrate()"
                state = f"strength={ch['strength_pct']}%"
            else:
                wave = "wave active" if ch["wave_active"] else "no wave"
                tools = "set_strength / adjust_strength / set_strength_limit / play_wave / design_wave / stop_wave"
                state = f"strength={ch['strength_pct']}%  limit={ch['limit_pct']}%  {wave}"
            batt = f"{ch['battery']}%" if ch["battery"] >= 0 else "unknown"
            conn = "connected" if ch["connected"] else "DISCONNECTED"
            lines += [
                f"alias '{alias}'  [{dtype}]  {conn}  battery={batt}",
                f"  state:         {state}",
                f"  last activity: {last}",
                f"  tools:         {tools}",
                "",
            ]
    return "\n".join(lines)


@mcp.resource("waves://library")
def wave_library() -> str:
    """All available waveforms with descriptions. Read before calling play_wave."""
    waves = load_waves()
    lines = [f"{name}: {data['description']}" for name, data in waves.items()]
    return "\n".join(lines)


@mcp.resource("waves://guide")
def wave_guide() -> str:
    """How to design waveforms: parameter reference and sensation guide."""
    return """\
# Waveform Design Guide

## Workflow
1. design_wave(steps, name, description) — saves a wave to the library
2. play_wave(alias, name) — plays any library wave on a device channel

## Step parameters

### freq (10–1000 ms)
The period of each pulse. Controls how "sharp" or "soft" the sensation feels.
- 10 ms  — very high frequency; feels like a sharp, electric tingle or buzz
- 20–50 ms — medium frequency; a distinct, firm pulse
- 100–300 ms — low frequency; slow, deep thumps
- 500–1000 ms — very low; almost like individual beats, widely spaced

Lower freq = higher frequency pulses = sharper, more intense character.
Higher freq = slower pulses = softer, more diffuse sensation.

### intensity (0–100)
How strong the pulse is within each frame.
- 0    — silent (no output)
- 1–30 — subtle, barely perceptible
- 30–60 — moderate, clearly felt
- 60–90 — strong
- 100  — maximum intensity for that frame

Note: overall output level is also controlled by set_strength on the channel.
Intensity here shapes the *pattern*; strength scales the *volume*.

### repeat (default 1)
How many consecutive 100ms frames this step occupies.
Use repeat to hold a level steady without listing the same step multiple times.

## Sensation patterns

| Pattern          | Steps sketch                                          | Feel                        |
|------------------|-------------------------------------------------------|-----------------------------|
| Ramp up          | intensity 0→100 over many steps                       | Gradual build               |
| Ramp down        | intensity 100→0                                       | Fade out                    |
| Pulse burst      | high intensity, repeat=2, then intensity=0, repeat=3  | Sharp hit then silence      |
| Oscillation      | alternate high/low intensity                          | Rhythmic, wave-like         |
| Frequency sweep  | freq 10→500 while intensity stays constant            | Character shifts soft→sharp |
| Hold             | one step with repeat=N                                | Steady, constant output     |

## Tips
- Start with intensity 0 and ramp up — it feels less abrupt.
- Short patterns (6–12 steps) loop more noticeably than long ones.
- Vary freq and intensity together for complex sensations.
- Use loop=0 for continuous patterns; loop=N for finite bursts.
"""


@mcp.tool()
async def scan(timeout: float = 5.0) -> str:
    """Scan for nearby DG-Lab Coyote and Lovense devices.

    Args:
        timeout: Scan duration in seconds (default 5)

    Returns:
        JSON list of found devices with name, address, and type/version.
    """
    results = await manager.scan(timeout=timeout)
    if not results:
        return "No devices found. Make sure the device is powered on and Bluetooth is enabled."
    return json.dumps(results, ensure_ascii=False)


@mcp.tool()
async def connect(address: str, alias_a: str, alias_b: str | None = None) -> str:
    """Connect to a Coyote or Lovense device and assign channel alias(es).

    Device type is detected automatically. Aliases are free-form labels (e.g. 'left_thigh', 'toy').
    For Coyote devices both alias_a (channel A) and alias_b (channel B) are required.
    For Lovense toys only alias_a is needed.

    Args:
        address: BLE address from scan results (e.g. "AA:BB:CC:DD:EE:FF")
        alias_a: Label for channel A (Coyote) or the vibration channel (Lovense)
        alias_b: Label for channel B — required for Coyote, omit for Lovense
    """
    try:
        a, b = await manager.connect(address, alias_a=alias_a, alias_b=alias_b)
        dev = manager._devices[-1]
        battery = dev.state.battery
        battery_str = f"{battery}%" if battery >= 0 else "unknown"
        if b is None:
            return (
                f"Connected to {address}. Battery: {battery_str}. "
                f"Vibration channel → '{a}'."
            )
        return (
            f"Connected to {address}. Battery: {battery_str}. "
            f"Channel A → '{a}', Channel B → '{b}'."
        )
    except Exception as e:
        return f"Connection failed: {e}"


@mcp.tool()
async def disconnect() -> str:
    """Disconnect from ALL connected devices and clear all aliases."""
    await manager.disconnect_all()
    return "All devices disconnected."


@mcp.tool()
async def set_strength(alias: str, value: int) -> str:
    """Set the absolute strength of a Coyote channel or group of synced channels.

    SAFETY: Start with low values (5–10%) and increase gradually.

    Args:
        alias: Channel alias assigned at connect time (e.g. "left_thigh")
        value: Strength percentage (0–100)
    """
    if value < 0 or value > 100:
        return "Error: Strength must be 0–100."
    try:
        effective = manager.set_strength(alias, value)
    except ValueError as e:
        return f"Error: {e}"
    entries = manager._alias_map.get(alias, [])
    wave_active = any(
        (dev.state.wave_a if ch == "A" else dev.state.wave_b)
        for dev, ch in entries
        if isinstance(dev, CoyoteDevice) and dev.state.connected
    )
    msg = f"'{alias}' strength set to {value}%."
    if effective < value:
        msg += f" Note: output limited to {effective}% by pain endurance limit."
    if not wave_active:
        msg += " Note: no active waveform on this alias — consider sending a wave for output."
    return msg


@mcp.tool()
async def adjust_strength(alias: str, delta: int) -> str:
    """Increase or decrease the strength of a Coyote channel or group of synced channels.

    Args:
        alias: Channel alias assigned at connect time
        delta: Percentage to change (positive = increase, negative = decrease)
    """
    try:
        intended, effective = manager.adjust_strength(alias, delta)
    except ValueError as e:
        return f"Error: {e}"
    direction = "increased" if delta > 0 else "decreased"
    entries = manager._alias_map.get(alias, [])
    wave_active = any(
        (dev.state.wave_a if ch == "A" else dev.state.wave_b)
        for dev, ch in entries
        if isinstance(dev, CoyoteDevice) and dev.state.connected
    )
    msg = f"'{alias}' strength {direction} by {abs(delta)}% (now at {effective}%)."
    if effective < intended:
        msg += f" Note: output limited to {effective}% by pain endurance limit."
    if not wave_active:
        msg += " Note: no active waveform on this alias — consider sending a wave for output."
    return msg


@mcp.tool()
async def set_strength_limit(alias: str, limit: int) -> str:
    """Set the pain endurance limit for a Coyote channel or group of synced channels.

    Prevents the strength from exceeding this value. Setting a limit before
    starting output is strongly recommended.

    Args:
        alias: Channel alias assigned at connect time
        limit: Maximum strength percentage (0–100)
    """
    if limit < 0 or limit > 100:
        return "Error: Limit must be 0–100."
    try:
        await manager.set_strength_limit(alias, limit)
    except ValueError as e:
        return f"Error: {e}"
    return f"'{alias}' pain endurance limit set to {limit}%."


@mcp.tool()
async def vibrate(alias: str, strength: int) -> str:
    """Set vibration intensity on a Lovense toy.

    Args:
        alias: Alias assigned at connect time
        strength: Vibration intensity (0–100, 0 = stop)
    """
    if strength < 0 or strength > 100:
        return "Error: Strength must be 0–100."
    try:
        await manager.vibrate(alias, strength)
    except ValueError as e:
        return f"Error: {e}"
    return f"'{alias}' vibrating at {strength}%." if strength > 0 else f"'{alias}' stopped."


@mcp.tool()
async def play_wave(
    alias: str,
    preset: str,
    loop: int = 0,
    strength: int | None = None,
) -> str:
    """Play a wave from the library on a Coyote channel or group of synced channels.

    See waves://library for all available wave names and descriptions.

    Args:
        alias: Channel alias assigned at connect time
        preset: Wave name from the library (e.g. "breath", "tide", or any designed wave)
        loop: 0 = loop infinitely (default); N = play exactly N times then stop
        strength: Optional strength percentage (0–100) to set before playing.
                  If omitted, current strength is kept.
    """
    strength_desc = ""
    if strength is not None:
        if strength < 0 or strength > 100:
            return "Error: Strength must be 0–100."
        try:
            effective = manager.set_strength(alias, strength)
        except ValueError as e:
            return f"Error: {e}"
        strength_desc = f", strength={strength}%"
        if effective < strength:
            strength_desc += f" (limited to {effective}% by pain endurance limit)"

    try:
        frames = get_frames(preset)
    except ValueError as e:
        return str(e)

    try:
        manager.send_wave(alias, frames, loop=loop)
    except ValueError as e:
        return f"Error: {e}"

    loop_desc = "looping" if loop == 0 else f"{loop}x"
    return f"Preset '{preset}' playing on '{alias}' ({loop_desc}{strength_desc})."


@mcp.tool()
async def design_wave(
    steps: list[dict],
    name: str,
    description: str,
) -> str:
    """Design a custom waveform and save it to the wave library for later playback.

    After saving, use play_wave(alias, name) to play it on a device channel.
    See waves://guide for a full explanation of parameters and sensation patterns.

    Args:
        steps: List of step objects, each with:
            - freq: wave period in ms (10–1000, lower = higher frequency / sharper feel)
            - intensity: wave intensity (0–100, 0=silent, 100=strongest)
            - repeat: optional, repeat this step N times (default 1)
        name: Unique name for this wave (used with play_wave)
        description: Short description of what this wave does or feels like

    Example steps for a gradual ramp up then sudden drop:
        [
            {"freq": 10, "intensity": 0},
            {"freq": 10, "intensity": 25},
            {"freq": 10, "intensity": 50},
            {"freq": 10, "intensity": 75},
            {"freq": 10, "intensity": 100, "repeat": 3},
            {"freq": 10, "intensity": 0, "repeat": 2}
        ]
    """
    if not steps:
        return "Error: steps list cannot be empty."
    if not name:
        return "Error: name cannot be empty."
    try:
        steps_to_frames(steps)  # validate before saving
    except (KeyError, TypeError) as e:
        return f"Error: Invalid step format: {e}. Each step needs 'freq' and 'intensity'."
    save_wave(name, steps, description)
    return f"Wave '{name}' saved to library. Use play_wave(alias, '{name}') to play it."


@mcp.tool()
async def stop_wave(alias: str | None = None) -> str:
    """Stop waveform output on a Coyote channel.

    Args:
        alias: Channel alias to stop, or omit to stop all channels on all devices.
    """
    try:
        manager.stop_wave(alias)
    except ValueError as e:
        return f"Error: {e}"
    target = f"'{alias}'" if alias is not None else "all channels"
    return f"Wave stopped on {target}."


@mcp.tool()
async def get_status() -> str:
    """Get current status of all connected devices, grouped by alias."""
    status = manager.get_all_status()
    return json.dumps(status, ensure_ascii=False)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
