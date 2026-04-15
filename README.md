# 🐺 DG-MCP — Let AI Control the Coyote 3.0

> 🔌 A DG-Lab Coyote 3.0 pulse device controller based on MCP (Model Context Protocol), enabling AI like Claude to control the device directly via Bluetooth.

## ✨ Features

- 🦷 **Direct BLE Connection** — No app required; connect directly to the Coyote 3.0 via computer Bluetooth
- 🤖 **MCP Protocol** — Plug-and-play with AI clients like Claude Desktop / Claude Code
- 🎛️ **10 Tools** — Scan, connect, strength control, waveform playback, custom waveform design, status query
- 🌊 **6 Preset Waveforms** — Breath, tide, low/mid/high pulse, tap
- 🔒 **Safety Protection** — Soft strength limit to prevent AI misoperation

## 📦 Installation

### Prerequisites

- 📡 Computer with Bluetooth (BLE support)
- 🔋 DG-Lab Coyote 3.0 pulse device
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

1. 🔋 Long-press the Coyote 3.0 power button to turn it on
2. 📡 Ensure your computer's Bluetooth is enabled (**no manual pairing needed**, BLE connects directly)
3. 🤖 In your AI conversation, say: "Scan and connect to the Coyote device"

### 3️⃣ AI Handles the Rest

The AI will follow this flow:

```
🔍 scan()            → Scan for nearby Coyote devices
🔗 connect(address)  → Connect to the device
⚡ set_strength()    → Set channel strength
🌊 send_wave()       → Send a preset or custom waveform
🎨 design_wave()     → Design a multi-step waveform
```

## 🎛️ MCP Tools Overview

| Tool | Description | Example |
|------|-------------|---------|
| 🔍 `scan` | Scan for nearby Coyote devices | `scan(timeout=5)` |
| 🔗 `connect` | Connect to a device | `connect("AA:BB:CC:DD:EE:FF")` |
| ❌ `disconnect` | Disconnect | `disconnect()` |
| ⚡ `set_strength` | Set channel strength (0~200) | `set_strength("A", 10)` |
| ➕ `add_strength` | Increase or decrease strength | `add_strength("A", 5)` |
| 🔒 `set_strength_limit` | Set soft strength limit (persists after power off) | `set_strength_limit(50, 50)` |
| 🌊 `send_wave` | Send a preset or custom waveform | `send_wave("A", preset="breath")` |
| 🎨 `design_wave` | Design a multi-step waveform | `design_wave("A", steps=[...])` |
| ⏹️ `stop_wave` | Stop waveform (omit channel to stop all) | `stop_wave("A")` / `stop_wave()` |
| 📊 `get_status` | Query device status | `get_status()` |

## 🌊 Preset Waveforms

| Name | Description | Feel |
|------|-------------|------|
| 🫁 `breath` | Breath | Slow rise and fall, from nothing to strong and back |
| 🌊 `tide` | Tide | Gradually changing frequency, wave-like sensation |
| 💤 `pulse_low` | Low pulse | Gentle and continuous |
| ⚡ `pulse_mid` | Mid pulse | Moderate and continuous |
| 🔥 `pulse_high` | High pulse | Intense and continuous |
| 👆 `tap` | Tap | Rhythmic intermittent pulses |

### 🎨 Custom Waveform

In addition to presets, you can use `send_wave` to define a fixed frequency and intensity:

```
send_wave("A", frequency=100, intensity=50, duration_frames=10, loop=True)
```

- `frequency`: Waveform frequency 10~1000ms (lower value = higher frequency)
- `intensity`: Waveform intensity 0~100
- `duration_frames`: Duration in frames, each frame is 100ms (default 10 = 1 second)
- `loop`: Whether to loop (default `True`)

### 🎼 Design Multi-Step Waveforms

Use `design_wave` to create complex waveforms where frequency and intensity change over time. Each step lasts 100ms:

```
design_wave("A", steps=[
    {"freq": 10, "intensity": 0},
    {"freq": 10, "intensity": 25},
    {"freq": 10, "intensity": 50},
    {"freq": 10, "intensity": 75},
    {"freq": 10, "intensity": 100, "repeat": 3},
    {"freq": 10, "intensity": 0,   "repeat": 2}
], loop=True)
```

- `freq`: Pulse frequency 10~1000ms (lower value = higher frequency)
- `intensity`: Intensity 0~100 (0 = no output, 100 = maximum)
- `repeat`: Number of times to repeat this step (default 1)
- `loop`: Whether to loop (default `True`; set to `False` to play once and stop)

> 💡 Both A and B channels can play different waveforms simultaneously and independently

## ⚠️ Safety Notice

> 🚨 **Important! Please read carefully!**

1. ⚡ **Start at low intensity** — For first use, set strength to `5~10` and increase gradually
2. 🔒 **Set a soft limit** — Use `set_strength_limit` to cap the maximum strength and prevent accidents
3. 🚫 **Emergency stop** — Turn off the Coyote power directly to immediately stop all output
4. 💓 **Restricted areas** — Do not place electrodes near the heart, neck, or head
5. 🤖 **AI is not human** — AI cannot perceive your actual experience; adjust or stop manually at any time

## 🏗️ Project Structure

```
DG-MCP/
├── 📄 pyproject.toml          # Project config + dependencies
├── 📦 dg_mcp/
│   ├── 📡 protocol.py         # V3 BLE protocol (B0/BF commands)
│   ├── 🌊 waves.py            # Preset waveforms + custom waveforms
│   ├── 🦷 device.py           # BLE device management (scan/connect/control)
│   └── 🤖 server.py           # MCP Server (10 Tools)
```

## 🔧 Technical Details

- **Communication Protocol**: DG-Lab Coyote V3 BLE protocol
- **BLE Library**: [bleak](https://github.com/hbldh/bleak) — cross-platform BLE
- **MCP SDK**: [mcp](https://modelcontextprotocol.io/) — Model Context Protocol
- **B0 Command**: 20 bytes, written every 100ms, controls both A/B channel strength + waveform simultaneously
- **BF Command**: 7 bytes, sets the soft strength limit (persists after power off)

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
