# Web UI UAT Findings — Follow-up Spec

**Date:** 2026-04-18  
**Tested build:** commit `f2cadc2` (feat: rewrite server — web UI integration)  
**Test URL:** `http://localhost:61331/`  
**Design contract:** `docs/superpowers/plans/2026-04-18-web-ui.md`  
**Test results:** `~/.claude/plans/write-a-plan-for-eager-nebula.md`

**Result summary:** 46 PASS / 2 FAIL / 1 SKIP (49 tests)

---

## Bug Fixes Required

### BUG-001 — Scan button label renders raw HTML entities

**File:** `kink_mcp/ui.py`  
**Severity:** Medium  
**Affected lines:** 162, 176

**Description:**  
`doScan()` uses `btn.textContent` to update the scan button label during and after a scan. `textContent` treats the assigned string as plain text — HTML entities are not interpreted. The strings `'&#9203; Scanning...'` and `'&#128269; Scan for Devices'` render as literal character sequences in the browser instead of the intended emoji (⏳ and 🔍).

The initial button label is set correctly by the HTML parser and displays the emoji fine. Only the two JS-controlled states are broken.

**Evidence:**

- During scan: `btn.textContent === "&#9203; Scanning..."`, `btn.innerHTML === "&amp;#9203; Scanning..."` (double-escaped)
- After scan: `btn.textContent === "&#128269; Scan for Devices"`, `btn.innerHTML === "&amp;#128269; Scan for Devices"`
- Screenshots: `ss_5115xxgei` (loading), `ss_9726pk1hi` (restored), `ss_9087e83yj` (final)

**Fix:**  
Replace `textContent` with `innerHTML` on both affected lines:

```diff
- btn.disabled=true;btn.textContent='&#9203; Scanning...';
+ btn.disabled=true;btn.innerHTML='&#9203; Scanning...';
```

```diff
- finally{btn.disabled=false;btn.textContent='&#128269; Scan for Devices';}
+ finally{btn.disabled=false;btn.innerHTML='&#128269; Scan for Devices';}
```

**Note:** Scan for other `textContent` assignments in `ui.py` that use HTML entities — if any exist, apply the same fix.

### BUG-002 — Coyote UUID truncated in PAIN LIMIT view.

**File:** `kink_mcp/ui.py`  
**Severity:** LOW

**Description:**  
The UUID of the Coyote is only shown partially (last 3 blocks).

**Fix**
Do not truncate the UUID and show the full length with all 6 blocks.

## Unverified Test (T-032)

### Lovense connect form hides Alias B input

**Test:** When clicking "Connect" on a Lovense device in scan results, the Alias B input should be hidden (`display:none`) since Lovense toys are single-channel.

**Why skipped:** Both Lovense devices were already connected at session start and do not appear in scan results. No additional Lovense device was available in BLE range to test with.

**Code under test** (line ~850 in `ui.py`):

```javascript
document.getElementById("iab").style.display =
  dtype === "lovense" ? "none" : "block";
```

**Verification needed:** Run a scan with at least one Lovense device powered on but not yet connected. Click its "Connect" button. Confirm Alias B input is hidden.

---

## Areas for Improvement

These are UX gaps and design limitations discovered during testing. They do not represent implementation bugs — the build matches the spec — but they represent friction points a real user would encounter. Each item is written as a self-contained requirement suitable for a follow-up planning session.

---

### UI-01 — No way to remove/forget offline devices

**Observed behaviour:** Devices saved to config appear permanently in the Connected Devices list, even after repeated failed reconnection attempts. The only available action for an offline device is "Retry". There is no delete or forget action.

**User impact:** A user who replaces, sells, or retires a device has no UI path to remove it. The list grows stale indefinitely.

**Proposed behaviour:**

- Add a "Remove" or "Forget" button to offline device rows (those in the red `.err` state — i.e. in `_device_meta` but not in `_devices`).
- On click: remove the device from `_device_meta`, call `_sync_config()` to persist, and update the UI via poll.
- Optionally confirm with an inline toggle ("Sure?") rather than a `confirm()` dialog (see UI-03).

**API needed:** `POST /api/forget` `{ "address": "..." }` → removes from `_device_meta` and config.

---

### UI-02 — Scan results not cached; re-scan required for each device

**Observed behaviour:** Clicking "Connect" on a scan result and completing a connection clears the scan results and status message. To connect the next device the user must trigger a full scan again. With 4 devices (2 Coyote + 2 Lovense), this means 4 separate ~5s scan cycles.

**User impact:** Multi-device setup is tedious. Each scan cycle blocks the UI for ~5s.

**Proposed behaviour:**

- After a successful connection, keep the scan results list visible and remove only the row corresponding to the just-connected device.
- The "Scan for Devices" button initiating a fresh scan (which clears and repopulates the list) is still the explicit user action to refresh results.
- Alternatively: after connect, re-scan automatically in the background and update the list without clearing it first.

**Implementation note:** `cancelCon()` currently clears `#scanres` and `#scanst`. Decouple this — `cancelCon()` should only hide the connect form, not wipe the scan results.

---

### UI-03 — Disconnect uses blocking `confirm()` dialog

**Observed behaviour:** The Disconnect button calls `confirm('Disconnect this device?')`, a native browser modal that blocks all browser events until dismissed. This makes the feature impossible to automate and breaks in any environment where native dialogs are suppressed.

**User impact:** Jarring native dialog inconsistent with the rest of the UI's style. Blocks browser automation and testing.

**Proposed behaviour:**  
Replace the `confirm()` with a two-step inline confirmation:

1. First click: button text changes to "Sure?" with a different colour (e.g. amber).
2. A second click within ~3s confirms disconnect; clicking anywhere else cancels.
3. If not confirmed within 3s, button reverts to "Disconnect".

**Implementation:** No server changes needed. Pure JS state on the button element.

---

### UI-04 — LLM toggle requires full server restart

**Observed behaviour:** Toggling "Expose `set_pain_limit` to LLM" shows a restart warning because `set_pain_limit` is registered as an MCP tool conditionally at startup — live registration/deregistration is not supported by FastMCP.

**User impact:** Changing a common safety setting requires a full process restart, disconnecting all active BLE devices in the process.

**Proposed behaviour (option A — preferred):** Investigate whether FastMCP supports runtime tool registration. If it does, register/deregister `set_pain_limit` dynamically without a restart.

**Proposed behaviour (option B — fallback):** Always register `set_pain_limit` as an MCP tool, but gate its execution at call time: if `config["pain_limit_exposed_to_llm"]` is `False`, return an error string `"set_pain_limit is disabled. Enable it in the web UI."` instead of executing. No restart required; the toggle takes effect immediately.

**Note:** Option B is simpler and removes the restart note entirely. The MCP tool is always visible to the LLM but non-functional when toggled off.

---

### UI-05 — Pain limit slider sends value only on mouse-up (`change` event)

**Observed behaviour:** The pain limit slider uses `onchange` to call `setPL()`. `onchange` fires only when the user releases the mouse button (or lifts a finger on touch). The displayed value label updates in real time via `oninput`, but the server state does not update until release.

**User impact:** If a device is actively running when the user drags the slider, the limit does not change mid-drag. The visual feedback is misleading — it shows a new value that is not yet in effect.

**Proposed behaviour:**  
Add a debounced `oninput` call that sends the update to the server during drag (e.g. debounce 300ms). Keep the existing `onchange` as a final confirmation call.

**Implementation note:** A simple debounce is sufficient:

```javascript
let _plTimer = null;
function debouncePL(alias, val) {
  clearTimeout(_plTimer);
  _plTimer = setTimeout(() => setPL(alias, val), 300);
}
```

Replace `onchange="setPL(...)"` with `oninput="debouncePL(...)"`.

---

### UI-06 — No visual feedback during BLE connection attempt

**Observed behaviour:** After clicking "Connect" in the connect form, the form remains visible and no spinner or loading indicator appears. The BLE connection takes ~10 seconds. During this time the UI looks frozen. The Connect button remains clickable, risking duplicate connection attempts.

**User impact:** Users may click Connect multiple times, not knowing whether the first attempt is in progress.

**Proposed behaviour:**

- Disable the Connect button immediately on click.
- Change its label to "Connecting…" (with a spinner or animated dots).
- Re-enable (and reset label) on success or error.
- Show an error message inside `#cform` if connection fails, rather than an `alert()`.

---

### UI-07 — No proactive battery warning in header

**Observed behaviour:** The device row border turns amber (`.warn`) when battery < 30%, but the status badge and header do not change. A user who has minimised or not looked at the panel recently gets no alert.

**Proposed behaviour:**  
When any connected device has battery < 30%, change the status badge indicator dot colour from green to amber and append a warning label, e.g.:  
`⚠ 3 devices connected (1 low battery)`

---

### UI-08 — Alias rename accepts duplicate names silently

**Observed behaviour:** The `/api/rename` endpoint and `rename_alias()` on `DeviceManager` accept any non-empty alias, including one already in use by another device or channel. Two channels sharing an alias causes MCP tool calls like `set_strength("name", 50)` to affect both channels simultaneously and silently. This is a deliberate design feature to sync two channels.

**User impact:** Potential unintended multi-channel activation. No warning in the UI.

**Proposed behaviour:**  
In `saveRename()` (JS), before calling the API, check whether the new alias already exists in `S.devices` (either as `alias_a` or `alias_b` of another device). If so, display an inline warning (not a blocking `alert()`): "This alias is already used by another channel — commands will be synced."  
Do not enforce uniqueness.

---

### UI-09 — Lovense device rows show no model name

**Observed behaviour:** The device type label is constructed as `d.device_type.toUpperCase() + ' ' + d.version.toUpperCase()`. For Lovense devices, `version` is stored as `""` (empty string) in `_device_meta`, so the row shows only `"LOVENSE"` with no model differentiation. This makes it hard to tell a Domi from a Gush when both are connected.

**Root cause:** `DeviceManager.connect()` for Lovense stores `version: ""` in `_device_meta`. The actual Lovense device type/model is available from the device object at connect time.

**Proposed behaviour:**  
Populate `version` (or a separate `model` field) with the Lovense device model name (e.g. `"Domi"`, `"Gush"`) when building `_device_meta` in `connect()`. Surface it in the device row label.

---

### UI-10 — Connect form does not pre-fill known device aliases

**Observed behaviour:** Alias A and Alias B inputs are always blank when the connect form opens, even if the device address is already in `_device_meta` (e.g. offline device being retried via the scan flow rather than the Retry button).

**User impact:** Returning users must retype aliases they've already assigned.

**Proposed behaviour:**  
In `showCF(addr, name, dtype)` (JS), look up `addr` in `S.devices` to check if the device has known aliases. If found, pre-fill `#iaa` with `alias_a` and `#iab` with `alias_b`. User can still change them before connecting.

**API note:** The client already receives the full device list (including offline ones) via `/api/status` → `S.devices`. No new API endpoint needed.
