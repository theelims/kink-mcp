# DG-MCP Web UI — Design Spec

**Date:** 2026-04-18
**Status:** Approved

---

## Overview

Add a local web-based control panel to DG-MCP. Device management (scan, connect, disconnect, alias rename) moves exclusively to the UI. The LLM retains only the controls it needs to operate already-connected devices. `set_strength_limit` is renamed `set_pain_limit` and hidden from the LLM by default, with a persistent global toggle to re-expose it.

---

## Architecture

### Single process, shared asyncio event loop

`main()` is modified to start two coroutines via `asyncio.gather()`:

1. **MCP stdio server** — `mcp.run_stdio_async()` (existing)
2. **aiohttp HTTP server** — serves the UI on a random available port

Both coroutines share the same `DeviceManager` instance directly — no IPC, no threads, no serialization overhead.

**New dependency:** `aiohttp`

### HTTP server responsibilities

- `GET /` — serve the single-page UI (inline HTML/CSS/JS, no build step)
- `GET /api/status` — return current state as JSON (polled every ~1 s by the UI)
- `POST /api/scan` — trigger a BLE scan, return found devices
- `POST /api/connect` — connect a device and assign aliases
- `POST /api/disconnect` — disconnect a single device by address
- `POST /api/rename` — rename a channel alias
- `POST /api/pain_limit` — set pain limit for an alias
- `POST /api/pain_limit_toggle` — toggle global LLM exposure of `set_pain_limit`

### URL surfacing

On startup, the port is chosen at random (first available), and the URL is printed to **stderr**:

```
DG-MCP UI: http://localhost:<port>
```

An MCP resource `ui://url` is registered, returning the full URL as a string. The LLM can read this resource and share the link with the user.

---

## UI Layout

Single-page app with three sections stacked vertically.

### 1. Header bar

- App name `⚡ DG-MCP`
- Live URL display (`http://localhost:<port>`)
- Connected device count badge

### 2. Top row — two columns

**Left column: Connected Devices**

Flat list, one row per device:

| Element | Detail |
|---|---|
| Status dot | Green `●` = connected, amber `●` = low battery (<30%), red `✗` = offline |
| Device type + version | e.g. `COYOTE V3` |
| BLE address | Shown in muted colour |
| Battery % | Right-aligned; amber when low |
| Alias badges | One per channel, labelled `A: <alias>` / `B: <alias>`. Each badge has a faint ✎ pencil icon. Clicking opens the rename popup. |
| Action button | Connected → `Disconnect` (red). Offline → `↺ Retry` (blue). |

**Alias rename popup**

- Triggered by clicking any alias badge on a connected device
- Anchored below the clicked badge
- Pre-filled input with the current alias name
- `Save` / `Cancel` buttons
- Only one popup open at a time; clicking outside or pressing Escape dismisses it
- On Save: alias updated immediately in device list, Pain Limit matrix, and persisted to config
- Aliases on offline devices are not clickable

**Right column: Scan & Connect**

- `🔍 Scan for Devices` button — triggers a BLE scan; results appear in a list below
- Each found device shows name + address + `Connect` button
- Clicking `Connect` expands an inline form:
  - Text input for Alias A
  - Text input for Alias B (shown for Coyote; hidden/omitted for Lovense)
  - `🔗 Connect` confirm button

### 3. Pain Limit matrix

Full-width strip below the top row.

**Header row:** `PAIN LIMIT` label on the left; global LLM toggle on the right.

**Global LLM toggle:**

```
Expose set_pain_limit to LLM  [toggle]
```

- Single toggle, OFF by default
- Affects all aliases — no per-alias cherry-picking
- State persists across restarts (see Persistence)
- When ON: `set_pain_limit` is registered as an MCP tool and available to the LLM
- When OFF: `set_pain_limit` is not registered; the LLM cannot call it

**Matrix body:** one row per device, two columns for channels A and B.

| Column | Content |
|---|---|
| Device label | Status dot, device type, last 3 bytes of address |
| Channel A cell | Alias name, range slider (0–100%), numeric readout |
| Channel B cell | Same — empty/hidden for Lovense (single-channel devices) |

Lovense devices only have one channel; Channel B cell is omitted for those rows.

Offline device rows are greyed out (opacity ~45%), sliders disabled, values retained from last session.

Changes to sliders are sent immediately via `POST /api/pain_limit` and persisted.

---

## MCP Tool Changes

### Removed from MCP (UI-only)

| Old tool | New home |
|---|---|
| `scan()` | UI: Scan button |
| `connect()` | UI: Connect form |
| `disconnect()` | UI: Disconnect button (per device) |

The LLM receives a system instruction update noting that device management is handled by the UI and the `ui://url` resource provides the control panel link.

### Renamed

`set_strength_limit` → `set_pain_limit` everywhere (Python function name, MCP tool name, docstring, README).

### Conditionally registered

`set_pain_limit` is registered as an MCP tool **only when the global toggle is ON**. The server reads the persisted toggle state at startup and registers (or skips) the tool accordingly.

Since MCP tool lists are fixed at server startup, toggling in the UI requires a **server restart** to take effect. The UI communicates this clearly:

> "Restart DG-MCP for the change to take effect."

---

## Persistence

**Config file location:**

| Platform | Path |
|---|---|
| Windows | `%APPDATA%\dg-mcp\config.json` |
| macOS / Linux | `~/.config/dg-mcp/config.json` |

**Config schema:**

```json
{
  "pain_limit_exposed_to_llm": false,
  "devices": [
    {
      "address": "AA:BB:CC:DD:EE:FF",
      "alias_a": "left_thigh",
      "alias_b": "right_thigh",
      "pain_limit_a": 50,
      "pain_limit_b": 50
    }
  ]
}
```

- Written on every connect, disconnect, alias rename, pain limit change, and toggle change
- Read on startup before the MCP tool list is built

---

## Auto-reconnect on Startup

On startup, for each device in the persisted device list:

1. Run a BLE scan (single scan covering all persisted addresses, timeout 10 s)
2. For each found device, call `manager.connect()` with the persisted aliases
3. Apply persisted pain limits after successful connection

**Error handling for missing devices:**

- Devices not found within the scan window are marked **offline** in the `DeviceManager` state
- They appear in the UI device list with a red `✗` badge and a `↺ Retry` button
- Their Pain Limit matrix row is greyed out with sliders disabled (values retained)
- The MCP `devices://status` resource reflects the offline state so the LLM can surface it
- Clicking `↺ Retry` triggers a targeted 10 s scan for that specific address and reconnects if found
- No automatic background retry loop — reconnect is always user-initiated

---

## MCP Resource Changes

| Resource | Change |
|---|---|
| `devices://status` | Updated to reflect offline devices and omit scan/connect/disconnect instructions |
| `ui://url` | **New** — returns `http://localhost:<port>` as plain text |

---

## README Changes

- Update tool table: remove `scan`, `connect`, `disconnect`, `set_strength_limit`; add `set_pain_limit` (with note: hidden from LLM by default)
- Add "Web UI" section: how to open it, what it controls, the URL resource
- Update flow examples to note that scan/connect are done via UI
- Update project structure to include `ui.html` or equivalent

---

## Files Affected

| File | Change |
|---|---|
| `dg_mcp/server.py` | Remove scan/connect/disconnect tools; rename set_strength_limit; add conditional set_pain_limit; add aiohttp server; add ui://url resource; modify main() |
| `dg_mcp/config.py` | **New** — config read/write (platform path, JSON schema) |
| `dg_mcp/ui.py` | **New** — aiohttp app, route handlers, HTML payload |
| `dg_mcp/device.py` | Add `disconnect_one(address)` method to DeviceManager |
| `pyproject.toml` | Add `aiohttp` dependency |
| `README.md` | Update as described above |
