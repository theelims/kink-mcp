# 🐺 DG-MCP — Let AI Control the Coyote & Lovense

> 🔌 A DG-Lab Coyote and Lovense device controller based on MCP (Model Context Protocol), enabling AI like Claude to control the devices directly via Bluetooth.

## ✨ Features

- 🦷 **Direct BLE Connection** — No app required; connect directly to devices via computer Bluetooth
- 🤖 **MCP Protocol** — Plug-and-play with AI clients like Claude Desktop / Claude Code
- 🔀 **V2 & V3 Simultaneously** — Connect a Coyote 2 and Coyote 3 at the same time; device type is auto-detected
- 📳 **Lovense Support** — Control Lovense vibration toys (Domi, Hush, Lush, Ferri, …) alongside Coyote devices
- 🔌 **Multi-Device** — Connect multiple devices at once; each channel gets a descriptive alias
- 🏷️ **Alias System** — Channels are identified by labels you choose (e.g. `"left_thigh"`, `"toy"`); shared aliases sync multiple channels automatically
- 🎛️ **11 Tools** — Scan, connect, strength control, waveform playback, custom waveform design, vibration, status query
- 🌊 **Wave Library** — 6 built-in presets; design and save unlimited custom waves via `design_wave`
- 📚 **3 Resources** — Live device status, wave library listing, wave design guide
- 🔒 **Pain Endurance Limit** — Configurable ceiling to prevent AI from exceeding user-defined intensity

- ⏱️ **Session Timer** — Track session start time and per-alias last-activity timestamps

## 📦 Installation

### Prerequisites

- 📡 Computer with Bluetooth (BLE support)
- 🔋 DG-Lab Coyote pulse device (V2 or V3) and/or a Lovense vibration toy
- 📦 [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager

## 🚀 Usage

### 1️⃣ Configure the MCP Client

#### 🖥️ Claude Desktop

Edit `claude_desktop_config.json`. The file location varies by operating system:

| OS | Path |
|----------|------|
| 🍎 macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| 🪟 Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| 🐧 Linux | `~/.config/Claude/claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "dg-lab": {
      "command": "uvx",
      "args": ["dg-mcp"]
    }
  }
}
```

#### 💻 Claude Code

```bash
claude mcp add dg-lab -- uvx dg-mcp
```

> 🗑️ Remove: `claude mcp remove dg-lab`

### 2️⃣ Power On and Connect

1. 🔋 Long-press the device power button to turn it on
2. 📡 Ensure your computer's Bluetooth is enabled (**no manual pairing needed**, BLE connects directly)
3. 🤖 In your AI conversation, say: "Scan and connect to my devices"

### 3️⃣ AI Handles the Rest

**Coyote flow:**
```
🔍 scan()                                              → Scan for nearby devices
🔗 connect(address, alias_a, alias_b)                  → Connect and name the channels
⚡ set_strength(alias, value)                          → Set channel strength (0–100%)
🌊 play_wave(alias, name)                              → Play any wave from the library
🎨 design_wave(steps, name, description)               → Save a custom wave to the library
   └─ then play_wave(alias, name)                      → Play the designed wave
```

**Lovense flow:**
```
🔍 scan()                                      → Scan for nearby devices
🔗 connect(address, alias_a)                   → Connect (no alias_b needed)
📳 vibrate(alias, strength)                    → Set vibration intensity (0–100%)
```

## 🏷️ Alias System

Each Coyote device has two channels (A and B). When you connect, you assign a **free-form alias** to each channel. Lovense toys have one channel and only need `alias_a`.

```
connect("AA:BB:CC:DD:EE:FF", alias_a="left_thigh", alias_b="right_thigh")  # Coyote
connect("CC:DD:EE:FF:00:11", alias_a="toy")                                 # Lovense
```

All subsequent commands use aliases instead of channel numbers:

```
set_strength("left_thigh", 15)
play_wave("left_thigh", "breath")
vibrate("toy", 40)
stop_wave("right_thigh")
```

### Shared Aliases (Sync)

Assigning the same alias to multiple channels causes them to receive every command together:

```
connect("AA:BB:CC:DD:EE:FF", alias_a="legs", alias_b="legs")  # both channels synced
set_strength("legs", 20)   # sets both channels at once
```

You can also sync channels across two different devices:

```
connect("AA:BB:CC:DD:EE:FF", alias_a="outer", alias_b="inner")
connect("CC:DD:EE:FF:00:11", alias_a="outer", alias_b="lower")
set_strength("outer", 25)  # sets both devices' 'outer' channels simultaneously
```

## 🎛️ MCP Tools Overview

| Tool | Description | Example |
|------|-------------|---------|
| 🔍 `scan` | Scan for nearby Coyote and Lovense devices | `scan(timeout=5)` |
| 🔗 `connect` | Connect and assign channel alias(es) | `connect("AA:BB:...", "left_thigh", "right_thigh")` |
| ❌ `disconnect` | Disconnect all devices | `disconnect()` |
| ⚡ `set_strength` | Set Coyote channel strength 0–100% | `set_strength("left_thigh", 10)` |
| ➕ `adjust_strength` | Increase or decrease Coyote strength | `adjust_strength("left_thigh", 5)` |
| 🔒 `set_strength_limit` | Set pain endurance limit 0–100% (Coyote) | `set_strength_limit("left_thigh", 50)` |
| 📳 `vibrate` | Set Lovense vibration intensity 0–100% | `vibrate("toy", 40)` |
| 🌊 `play_wave` | Play a wave from the library (Coyote) | `play_wave("left_thigh", preset="breath")` |
| 🎨 `design_wave` | Save a custom wave to the library | `design_wave(steps=[...], name="ramp", description="...")` |
| ⏹️ `stop_wave` | Stop waveform (omit alias to stop all) | `stop_wave("left_thigh")` / `stop_wave()` |
| 📊 `get_status` | Query all device and channel status (JSON) | `get_status()` |

**Resources:**
- `devices://status` — live human-readable snapshot of all connected devices; read before issuing commands
- `waves://library` — all available wave names and descriptions; read before calling `play_wave`
- `waves://guide` — wave parameter reference and sensation guide; read before calling `design_wave`

## 📳 Lovense Vibration Toys

Supported devices are identified by BLE name prefixes `LVS-` or `LOVE-`, covering models such as:
Domi, Hush 2, Lush 3, Ferri, Nora, Max 2, and other Lovense Gen 1/2 toys.

- Only the **primary vibration motor** is controlled via `vibrate(alias, strength)`.
- `strength=0` cleanly stops vibration.
- Gen 2 devices use Nordic UART; Gen 1 devices use the legacy FFF0 UUID set — detection is automatic.

## 🌊 Wave Library

Wave definitions are stored in `~/.local/share/dg-mcp/waves.json` and loaded at runtime.
Read `waves://library` for all available names and descriptions. Use `design_wave` to add your own.

Six built-in presets:

| Name | Feel |
|------|------|
| 🫁 `breath` | Slow rise and fall, like breathing |
| 🌊 `tide` | Gradual build and ebb twice, with rising frequency |
| 💤 `pulse_low` | Steady gentle pulse |
| ⚡ `pulse_mid` | Steady moderate pulse |
| 🔥 `pulse_high` | Steady intense pulse |
| 👆 `tap` | Sharp double-tap with pauses |

### play_wave — Play Any Library Wave

```
play_wave("left_thigh", preset="breath")            # loop infinitely (default)
play_wave("left_thigh", preset="tap", loop=3)       # play 3 times then stop
play_wave("left_thigh", preset="pulse_mid",
          strength=20, loop=0)                      # set strength=20% and loop
```

- `loop=0` — loop infinitely until `stop_wave` or a new wave command (default)
- `loop=N` — play exactly N full cycles then stop automatically
- `strength` — optional, sets strength (0–100%) before starting; omit to keep current

### 🎼 Design and Save Custom Waveforms

Use `design_wave` to save a named wave to the library, then `play_wave` to play it.
Read `waves://guide` for a full parameter reference and sensation guide.

```
# Step 1: save to library
design_wave(
    steps=[
        {"freq": 10, "intensity": 0},
        {"freq": 10, "intensity": 25},
        {"freq": 10, "intensity": 50},
        {"freq": 10, "intensity": 75},
        {"freq": 10, "intensity": 100, "repeat": 3},
        {"freq": 10, "intensity": 0,   "repeat": 2}
    ],
    name="ramp",
    description="Gradual ramp up then sudden drop"
)

# Step 2: play it
play_wave("left_thigh", preset="ramp", loop=0, strength=15)
```

- `freq`: Pulse period 10–1000ms (lower = higher frequency = sharper feel)
- `intensity`: Intensity 0–100 (0 = silent, 100 = maximum per frame)
- `repeat`: Number of 100ms frames for this step (default 1)

> 💡 Multiple aliases can play different waveforms simultaneously and independently

## ⏱️ Session Timer

Every `play_wave` or `vibrate` call records activity timestamps. These appear in `get_status()` and the `devices://status` resource:

- `session.running_since` — when the first activity occurred (resets on `disconnect`)
- per-alias `last_activity` — time since the alias last received a command

## ⚠️ Safety Notice

> 🚨 **Important! Please read carefully!**

1. ⚡ **Start at low intensity** — For first use, set strength to `5–10%` and increase gradually
2. 🔒 **Set a pain endurance limit** — Use `set_strength_limit` to cap the maximum strength before starting
3. 🚫 **Emergency stop** — Turn off the device power directly to immediately stop all output
4. 💓 **Restricted areas** — Do not place electrodes near the heart, neck, or head
5. 🤖 **AI is not human** — AI cannot perceive your actual experience; adjust or stop manually at any time

## 🏗️ Project Structure

```
DG-MCP/
├── 📄 pyproject.toml          # Project config + dependencies
├── 📦 dg_mcp/
│   ├── 📡 protocol.py         # BLE protocol constants and packet builders (V2 & V3)
│   ├── 🌊 waves.py            # Preset waveforms + custom waveforms
│   ├── 🦷 device.py           # BLE device management (CoyoteDevice + DeviceManager)
│   ├── 📳 lovense.py          # Lovense BLE device class
│   └── 🤖 server.py           # MCP Server (11 Tools + 3 resources)
```

## 🔧 Technical Details

- **Multi-Device**: Multiple Coyote (V2/V3) and Lovense devices can be connected simultaneously
- **Auto-Detection**: Device type is detected automatically from the BLE device name
- **BLE Library**: [bleak](https://github.com/hbldh/bleak) — cross-platform BLE
- **MCP SDK**: [mcp](https://modelcontextprotocol.io/) — Model Context Protocol
- **Write Loop**: Coyote control packets sent every 100ms per device
- **Time Formatting**: [humanize](https://python-humanize.readthedocs.io/) for human-readable activity timestamps

## 🖥️ Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| 🪟 Windows | ✅ Supported | Works out of the box |
| 🍎 macOS | ✅ Supported | Works out of the box |
| 🐧 Linux | ✅ Supported | Requires BlueZ |
| 🐧 WSL2 | ⚠️ Needs setup | Requires USB Bluetooth passthrough ([usbipd](https://github.com/dorssel/usbipd-win)) |

## 📜 Acknowledgements

- [DG-LAB-OPENSOURCE](https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE) — Official open-source BLE protocol
- [Model Context Protocol](https://modelcontextprotocol.io/) — MCP protocol specification

## 🚨 Disclaimer

> **This project is intended for educational and communication purposes only and must not be used for any illegal or improper purposes. Users assume all risks and responsibilities arising from the use of this project. The project author is not liable for any direct or indirect damages resulting from its use.**

## 📄 License

MIT
