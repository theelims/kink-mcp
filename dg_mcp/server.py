"""MCP Server for DG-Lab Coyote and Lovense devices."""

import json
import logging

from mcp.server.fastmcp import FastMCP

from .device import CoyoteDevice, DeviceManager
from .waves import PRESETS, preset_to_frames, steps_to_frames

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "DG-Lab Coyote & Lovense",
    instructions=(
        "Control DG-Lab Coyote pulse devices and Lovense vibration toys via Bluetooth. "
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
        "Available Coyote wave presets: breath, tide, pulse_low, pulse_mid, pulse_high, tap. "
        "loop=0 means infinite loop; loop=N plays the wave N times then stops. "
        "Read the devices://status resource for a live snapshot of all connected devices before issuing commands."
    ),
)

manager = DeviceManager()


@mcp.resource("devices://status")
def live_status() -> str:
    """Live session snapshot: alias routing, current state, and activity timers."""
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
async def set_strength_limit(alias: str, limit: int) -> str:
    """Set the strength soft limit for a Coyote channel or group of synced channels.

    Prevents the strength from exceeding this value. Setting a limit before
    starting output is recommended for safety.

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
    return f"'{alias}' strength limit set to {limit}%."


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
                  If omitted, current strength is kept.
    """
    if strength is not None:
        if strength < 0 or strength > 100:
            return "Error: Strength must be 0–100."
        try:
            manager.set_strength(alias, strength)
        except ValueError as e:
            return f"Error: {e}"

    try:
        frames = preset_to_frames(preset)
    except ValueError as e:
        return str(e)

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

    Creates any pattern: ramps, pulses, rhythms, etc. Each step is 100ms of output.

    Args:
        alias: Channel alias assigned at connect time
        steps: List of step objects, each with:
            - freq: wave frequency in ms (10–1000, lower = higher frequency pulse)
            - intensity: wave intensity (0–100, 0=silent, 100=strongest)
            - repeat: optional, repeat this step N times (default 1)
        loop: 0 = loop infinitely (default); N = play exactly N times then stop
        strength: Optional strength percentage (0–100) to set before playing.
                  If omitted, current strength is kept.

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


def main():
    mcp.run()


if __name__ == "__main__":
    main()
