"""MCP Server for DG-Lab Coyote and Lovense devices."""

import asyncio
import json
import logging
import sys

from mcp.server.fastmcp import FastMCP

from .config import load_config, save_config
from .device import CoyoteDevice, DeviceManager
from .waves import get_frames, load_waves, steps_to_frames

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config is loaded once in main() and stored here for the MCP resource callbacks.
_config: dict = {}
_ui_url: str = ""

mcp = FastMCP(
    "DG-Lab Coyote & Lovense",
    instructions=(
        "Control DG-Lab Coyote electro-stimulation devices and Lovense vibration toys via Bluetooth. "
        "\n\n"
        "DEVICE MANAGEMENT is handled by the web UI — NOT by AI tools. "
        "Read the ui://url resource to get the control panel link and share it with the user "
        "so they can scan, connect, and disconnect devices before issuing commands. "
        "\n\n"
        "COYOTE (e-stim): each device has two channels (A and B), each with its own alias. "
        "Use set_strength, adjust_strength, play_wave, design_wave, stop_wave. "
        "Typical flow: user connects via UI → set_strength → play_wave. "
        "\n\n"
        "LOVENSE (vibration): each toy has one channel. "
        "Use vibrate(alias, strength) to set intensity 0–100% (0 = stop). "
        "\n\n"
        "GENERAL: Strength range 0–100%. Always start low (5–10%) and increase gradually. "
        "Available Coyote wave presets: breath, tide, pulse_low, pulse_mid, pulse_high, tap. "
        "loop=0 means infinite loop; loop=N plays the wave N times then stops. "
        "Read the devices://status resource for a live snapshot of all connected devices. "
        "Read waves://library for all available wave names and descriptions. "
        "Read waves://guide for a full explanation of wave parameters and how they feel."
    ),
)

manager = DeviceManager()


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("ui://url")
def ui_url_resource() -> str:
    """URL of the local web control panel. Share this link with the user."""
    return _ui_url


@mcp.resource("devices://status")
def live_status() -> str:
    """Live session snapshot: alias routing, current state, and activity timers."""
    s = manager.get_all_status()
    session = s.get("session", {})
    lines = [
        f"Web UI: {_ui_url}",
        f"Session running since: {session.get('running_since') or 'not started'}",
        f"Connected devices: {s['connected_devices']}",
        "",
    ]
    if not s["aliases"]:
        lines.append(
            "No aliases registered. Ask the user to open the web UI and connect their devices."
        )
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
                tools = "set_strength / adjust_strength / play_wave / design_wave / stop_wave"
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


# ---------------------------------------------------------------------------
# Tools — strength & wave control (unchanged from before)
# ---------------------------------------------------------------------------

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
        manager.set_strength(alias, value)
    except ValueError as e:
        return f"Error: {e}"
    entries = manager._alias_map.get(alias, [])
    wave_active = any(
        (dev.state.wave_a if ch == "A" else dev.state.wave_b)
        for dev, ch in entries
        if isinstance(dev, CoyoteDevice) and dev.state.connected
    )
    msg = f"'{alias}' strength set to {value}%."
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
        manager.adjust_strength(alias, delta)
    except ValueError as e:
        return f"Error: {e}"
    direction = "increased" if delta > 0 else "decreased"
    entries = manager._alias_map.get(alias, [])
    wave_active = any(
        (dev.state.wave_a if ch == "A" else dev.state.wave_b)
        for dev, ch in entries
        if isinstance(dev, CoyoteDevice) and dev.state.connected
    )
    msg = f"'{alias}' strength {direction} by {abs(delta)}%."
    if not wave_active:
        msg += " Note: no active waveform on this alias — consider sending a wave for output."
    return msg


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
    """Play a preset waveform on a Coyote channel or group of synced channels.

    Args:
        alias: Channel alias assigned at connect time
        preset: Preset name — breath, tide, pulse_low, pulse_mid, pulse_high, tap
        loop: 0 = loop infinitely (default); N = play exactly N times then stop
        strength: Optional strength percentage (0–100) to set before playing.
    """
    if strength is not None:
        if strength < 0 or strength > 100:
            return "Error: Strength must be 0–100."
        try:
            manager.set_strength(alias, strength)
        except ValueError as e:
            return f"Error: {e}"
    try:
        frames = get_frames(preset)
    except (KeyError, ValueError) as e:
        return f"Error: Unknown preset '{preset}'. {e}"
    try:
        manager.send_wave(alias, frames, loop=loop)
    except ValueError as e:
        return f"Error: {e}"
    loop_desc = "looping" if loop == 0 else f"{loop}x"
    strength_desc = f", strength={strength}%" if strength is not None else ""
    return f"Preset '{preset}' playing on '{alias}' ({loop_desc}{strength_desc})."


@mcp.tool()
async def design_wave(
    alias: str,
    steps: list[dict],
    loop: int = 0,
    strength: int | None = None,
) -> str:
    """Design and play a custom waveform by defining a sequence of steps on a Coyote channel.

    Args:
        alias: Channel alias assigned at connect time
        steps: List of step objects, each with:
            - freq: wave frequency in ms (10–1000, lower = higher frequency pulse)
            - intensity: wave intensity (0–100, 0=silent, 100=strongest)
            - repeat: optional, repeat this step N times (default 1)
        loop: 0 = loop infinitely (default); N = play exactly N times then stop
        strength: Optional strength percentage (0–100) to set before playing.
    """
    if strength is not None:
        if strength < 0 or strength > 100:
            return "Error: Strength must be 0–100."
        try:
            manager.set_strength(alias, strength)
        except ValueError as e:
            return f"Error: {e}"
    if not steps:
        return "Error: steps list cannot be empty."
    try:
        frames = steps_to_frames(steps)
    except (KeyError, TypeError) as e:
        return f"Error: Invalid step format: {e}. Each step needs 'freq' and 'intensity'."
    try:
        manager.send_wave(alias, frames, loop=loop)
    except ValueError as e:
        return f"Error: {e}"
    loop_desc = "looping" if loop == 0 else f"{loop}x"
    strength_desc = f", strength={strength}%" if strength is not None else ""
    return (
        f"Custom wave ({len(frames)} frames, {len(frames) * 100}ms) "
        f"playing on '{alias}' ({loop_desc}{strength_desc})."
    )


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


@mcp.tool()
async def set_pain_limit(alias: str, limit: int) -> str:
    """Set the pain (strength) soft limit for a Coyote channel or group of synced channels.

    Prevents the strength from exceeding this value. The user has enabled this tool
    via the web UI. Ask for confirmation before lowering a limit already in use.

    Args:
        alias: Channel alias assigned at connect time
        limit: Maximum strength percentage (0–100)
    """
    if not _config.get("pain_limit_exposed_to_llm", False):
        return "set_pain_limit is disabled. Enable it in the web UI."
    if limit < 0 or limit > 100:
        return "Error: Limit must be 0–100."
    try:
        await manager.set_pain_limit(alias, limit)
    except ValueError as e:
        return f"Error: {e}"
    return f"'{alias}' pain limit set to {limit}%."


# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------

async def _auto_reconnect(config: dict) -> None:
    """Try to reconnect all devices from the persisted device list."""
    devices = config.get("devices", [])
    if not devices:
        return

    async def _try_connect(dev_info: dict) -> None:
        address = dev_info["address"]
        alias_a = dev_info["alias_a"]
        alias_b = dev_info.get("alias_b")
        limit_a = dev_info.get("limit_a_pct", 100)
        limit_b = dev_info.get("limit_b_pct", 100)
        try:
            a, b = await manager.connect(address, alias_a=alias_a, alias_b=alias_b)
            if limit_a < 100:
                await manager.set_pain_limit(a, limit_a)
            if b and limit_b is not None and limit_b < 100:
                await manager.set_pain_limit(b, limit_b)
            logger.info("Auto-reconnected %s ('%s')", address, alias_a)
        except Exception as exc:
            logger.warning("Auto-reconnect failed for %s: %s", address, exc)
            manager.add_offline_device(dev_info)

    await asyncio.gather(*[_try_connect(d) for d in devices], return_exceptions=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    asyncio.run(_main())


async def _main() -> None:
    global _config, _ui_url

    from .ui import create_app, find_free_port, run_web_server

    _config = load_config()

    port = find_free_port()
    _ui_url = f"http://localhost:{port}"
    print(f"kink-mcp UI: {_ui_url}", file=sys.stderr, flush=True)

    app = create_app(manager, _config)

    await _auto_reconnect(_config)

    await asyncio.gather(
        mcp.run_stdio_async(),
        run_web_server(app, port),
    )


if __name__ == "__main__":
    main()
