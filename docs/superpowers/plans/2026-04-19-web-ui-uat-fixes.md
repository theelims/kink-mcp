# Web UI UAT Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 2 UAT bugs and implement 10 UX improvements from the web UI UAT findings document.

**Architecture:** Changes span 4 Python source files and 2 test files. Backend changes (`forget_device`, `lovense_model`, `set_pain_limit` config gate) are tested with pytest. All frontend changes are within the `_HTML` string in `kink_mcp/ui.py` — CSS, HTML elements, and inline JS. Because the UI re-renders every second via `poll()`, confirmation button states (UI-03, UI-01) must be tracked in JS variables that survive re-renders rather than as DOM attributes.

**Tech Stack:** Python 3.10+, pytest, aiohttp, FastMCP, vanilla JS (inline in Python string)

---

## File Structure

| File | Changes |
|------|---------|
| `kink_mcp/ui.py` | BUG-001, BUG-002, UI-01 (route + UI), UI-02, UI-03, UI-04 (remove restart note), UI-05, UI-06, UI-07, UI-08, UI-10 |
| `kink_mcp/device.py` | UI-01 (`forget_device` method), UI-09 (`lovense_model` import + use in `connect()`) |
| `kink_mcp/lovense.py` | UI-09 (`lovense_model` utility function) |
| `kink_mcp/server.py` | UI-04 (always-register `set_pain_limit` with config gate) |
| `tests/test_device_manager.py` | UI-01 (tests for `forget_device`) |
| `tests/test_lovense.py` | UI-09 (create: tests for `lovense_model`) |
| `README.md` | UI-04 (remove "restart required"), UI-01 (add Forget feature) |

---

### Task 1: Bug Fixes (BUG-001 + BUG-002)

**Files:**
- Modify: `kink_mcp/ui.py`

**BUG-001:** `doScan()` uses `btn.textContent` to set emoji labels. `textContent` doesn't interpret HTML entities, so `&#9203;` and `&#128269;` render as literal text instead of emoji. Fix: use `innerHTML`.

**BUG-002:** `renderMatrix()` truncates the Coyote UUID with `d.address.slice(-8)`, showing only the last 8 characters. Fix: show the full address.

- [ ] **Step 1: Fix scan button textContent → innerHTML**

In `kink_mcp/ui.py`, replace the two `textContent` assignments in `doScan()`:

```diff
- btn.disabled=true;btn.textContent='&#9203; Scanning...';
+ btn.disabled=true;btn.innerHTML='&#9203; Scanning...';
```

```diff
- finally{btn.disabled=false;btn.textContent='&#128269; Scan for Devices';}
+ finally{btn.disabled=false;btn.innerHTML='&#128269; Scan for Devices';}
```

No other `textContent` assignments use HTML entities in this file (verified).

- [ ] **Step 2: Fix UUID truncation in pain limit view**

In `kink_mcp/ui.py`, in the `renderMatrix()` function, remove `.slice(-8)`:

```diff
- ${esc(d.address.slice(-8))}
+ ${esc(d.address)}
```

- [ ] **Step 3: Commit**

```bash
git add kink_mcp/ui.py
git commit -m "fix: scan button emoji rendering + full UUID in pain limit view"
```

---

### Task 2: Forget Device Backend (UI-01)

**Files:**
- Modify: `kink_mcp/device.py`
- Modify: `tests/test_device_manager.py`

Add `forget_device()` method to `DeviceManager` that removes an offline device from `_device_meta`, cleans up its aliases from `_alias_map`, and removes any stale device object from `_devices`. Refuses if the device is currently connected.

- [ ] **Step 1: Write failing tests for `forget_device`**

Append to `tests/test_device_manager.py`:

```python
# --- forget_device ---

def test_forget_device_removes_meta():
    m = _make_manager()
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "left", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    m.forget_device("AA:BB:CC")
    assert "AA:BB:CC" not in m._device_meta


def test_forget_device_unknown_raises():
    m = _make_manager()
    with pytest.raises(ValueError, match="Unknown device"):
        m.forget_device("FF:FF:FF")


def test_forget_device_connected_raises():
    m = _make_manager()
    dev = _make_mock_device("AA:BB:CC", connected=True)
    m._devices.append(dev)
    m._alias_map["left"] = [(dev, "A")]
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "left", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    with pytest.raises(ValueError, match="Cannot forget a connected"):
        m.forget_device("AA:BB:CC")


def test_forget_device_cleans_aliases():
    m = _make_manager()
    m._alias_map["left"] = []
    m._alias_map["right"] = []
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "left", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    m.forget_device("AA:BB:CC")
    assert "AA:BB:CC" not in m._device_meta
    assert "left" not in m._alias_map
    assert "right" not in m._alias_map


def test_forget_device_keeps_shared_alias_for_other_device():
    m = _make_manager()
    dev = _make_mock_device("DD:EE:FF", connected=True)
    m._devices.append(dev)
    m._alias_map["shared"] = [(dev, "A")]
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "shared", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    m._device_meta["DD:EE:FF"] = {
        "address": "DD:EE:FF", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "shared", "alias_b": "other",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    m.forget_device("AA:BB:CC")
    assert "AA:BB:CC" not in m._device_meta
    assert "shared" in m._alias_map
    assert len(m._alias_map["shared"]) == 1


def test_forget_device_removes_disconnected_dev_object():
    m = _make_manager()
    dev = _make_mock_device("AA:BB:CC", connected=False)
    m._devices.append(dev)
    m._alias_map["left"] = [(dev, "A")]
    m._alias_map["right"] = [(dev, "B")]
    m._device_meta["AA:BB:CC"] = {
        "address": "AA:BB:CC", "name": "Coyote V3",
        "device_type": "coyote", "version": "v3",
        "alias_a": "left", "alias_b": "right",
        "limit_a_pct": 50, "limit_b_pct": 50,
    }
    m.forget_device("AA:BB:CC")
    assert "AA:BB:CC" not in m._device_meta
    assert dev not in m._devices
    assert "left" not in m._alias_map
    assert "right" not in m._alias_map
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_device_manager.py -k forget -v`
Expected: FAIL — `forget_device` not defined

- [ ] **Step 3: Implement `forget_device`**

In `kink_mcp/device.py`, add the following method to `DeviceManager` class, after the `rename_alias` method (after line 718):

```python
    def forget_device(self, address: str) -> None:
        """Remove an offline device from tracking, clearing its metadata and aliases."""
        if address not in self._device_meta:
            raise ValueError(f"Unknown device '{address}'.")
        dev = next((d for d in self._devices if d.state.address == address), None)
        if dev is not None and dev.state.connected:
            raise ValueError("Cannot forget a connected device. Disconnect it first.")
        meta = self._device_meta[address]
        for alias_key in ("alias_a", "alias_b"):
            alias = meta.get(alias_key)
            if not alias or alias not in self._alias_map:
                continue
            if dev is not None:
                entries = [(d, ch) for d, ch in self._alias_map[alias] if d is not dev]
            else:
                entries = [(d, ch) for d, ch in self._alias_map[alias]
                           if d.state.address != address]
            if entries:
                self._alias_map[alias] = entries
            else:
                del self._alias_map[alias]
                self._alias_last_activity.pop(alias, None)
        if dev is not None:
            self._devices.remove(dev)
        del self._device_meta[address]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_device_manager.py -k forget -v`
Expected: 6 PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass (20 total: 14 existing + 6 new)

- [ ] **Step 6: Commit**

```bash
git add kink_mcp/device.py tests/test_device_manager.py
git commit -m "feat: add forget_device method to DeviceManager"
```

---

### Task 3: Inline Confirmations + Forget UI (UI-01 + UI-03)

**Files:**
- Modify: `kink_mcp/ui.py`

Add the `/api/forget` route, the Forget button for offline devices (UI-01), and replace the `confirm()` dialog on Disconnect with a two-step inline confirmation (UI-03). Both confirmation patterns use JS state variables that survive the 1-second re-render cycle.

- [ ] **Step 1: Add `handle_forget` route handler**

In `kink_mcp/ui.py`, add the following route handler after `handle_rename` (after the `handle_rename` function, before `handle_pain_limit`):

```python
async def handle_forget(request: web.Request) -> web.Response:
    manager: DeviceManager = request.app["manager"]
    config: dict = request.app["config"]
    try:
        body = await request.json()
        manager.forget_device(body["address"])
        _sync_config(manager, config)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)
```

- [ ] **Step 2: Register the forget route**

In `kink_mcp/ui.py`, in the `create_app` function, add after the rename route registration:

```diff
  app.router.add_post("/api/rename", handle_rename)
+ app.router.add_post("/api/forget", handle_forget)
  app.router.add_post("/api/pain_limit", handle_pain_limit)
```

- [ ] **Step 3: Add confirmation state variables and handler functions**

In `kink_mcp/ui.py`, in the `<script>` section, add after the existing state variables (`let cdev=null,renS=null;`):

```javascript
let _disConfirm=null;
let _forgetConfirm=null;
```

Then replace the current `doDis` function:

```javascript
async function doDis(addr){
  if(!confirm('Disconnect this device?'))return;
  await fetch('/api/disconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({address:addr})});
  poll();
}
```

With:

```javascript
function doDis(addr){
  if(_disConfirm&&_disConfirm.addr===addr){
    clearTimeout(_disConfirm.timer);_disConfirm=null;
    fetch('/api/disconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({address:addr})}).then(()=>poll());
    return;
  }
  if(_disConfirm){clearTimeout(_disConfirm.timer);}
  _disConfirm={addr,timer:setTimeout(()=>{_disConfirm=null;render();},3000)};
  render();
}
```

And add the `doForget` function after `doDis`:

```javascript
function doForget(addr){
  if(_forgetConfirm&&_forgetConfirm.addr===addr){
    clearTimeout(_forgetConfirm.timer);_forgetConfirm=null;
    fetch('/api/forget',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({address:addr})}).then(()=>poll());
    return;
  }
  if(_forgetConfirm){clearTimeout(_forgetConfirm.timer);}
  _forgetConfirm={addr,timer:setTimeout(()=>{_forgetConfirm=null;render();},3000)};
  render();
}
```

- [ ] **Step 4: Rewrite `renderDevices` with Forget button and confirmation states**

Replace the current `renderDevices` function:

```javascript
function renderDevices(){
  const el=document.getElementById('dlist');
  if(!S.devices.length){el.innerHTML='<div style="font-size:12px;color:#475569;">No devices. Use Scan &amp; Connect.</div>';return;}
  el.innerHTML=S.devices.map(d=>{
    const warn=d.battery>=0&&d.battery<30;
    const cls=d.connected?(warn?'warn':'ok'):'err';
    const dot=d.connected?(warn?'&#9679;':'&#9679;'):'&#10007;';
    const batt=d.battery>=0?`&#128267; ${d.battery}%`:(d.connected?'':'not found');
    const ba=d.connected?`<span class="abadge" onclick="openRen('${esc(d.alias_a)}','${esc(d.address)}','A',event)">A: ${esc(d.alias_a)} &#9998;</span>`:`<span class="abadge off">A: ${esc(d.alias_a)}</span>`;
    const bb=d.alias_b?(d.connected?`<span class="abadge" onclick="openRen('${esc(d.alias_b)}','${esc(d.address)}','B',event)">B: ${esc(d.alias_b)} &#9998;</span>`:`<span class="abadge off">B: ${esc(d.alias_b)}</span>`):'';
    const abtn=d.connected?`<button class="btn btn-danger" onclick="doDis('${esc(d.address)}')">Disconnect</button>`:`<button class="btn btn-blue" onclick="doRetry('${esc(d.address)}')">&#8635; Retry</button>`;
    return `<div class="device-row ${cls}"><div class="device-info"><span class="dname ${cls}">${dot} ${esc(d.device_type.toUpperCase())} ${esc(d.version.toUpperCase())}</span><span class="daddr">${esc(d.address)}</span><span class="dbatt">${batt}</span><div class="aliases">${ba}${bb}</div></div>${abtn}</div>`;
  }).join('');
}
```

With:

```javascript
function renderDevices(){
  const el=document.getElementById('dlist');
  if(!S.devices.length){el.innerHTML='<div style="font-size:12px;color:#475569;">No devices. Use Scan &amp; Connect.</div>';return;}
  el.innerHTML=S.devices.map(d=>{
    const warn=d.battery>=0&&d.battery<30;
    const cls=d.connected?(warn?'warn':'ok'):'err';
    const dot=d.connected?(warn?'&#9679;':'&#9679;'):'&#10007;';
    const batt=d.battery>=0?`&#128267; ${d.battery}%`:(d.connected?'':'not found');
    const ba=d.connected?`<span class="abadge" onclick="openRen('${esc(d.alias_a)}','${esc(d.address)}','A',event)">A: ${esc(d.alias_a)} &#9998;</span>`:`<span class="abadge off">A: ${esc(d.alias_a)}</span>`;
    const bb=d.alias_b?(d.connected?`<span class="abadge" onclick="openRen('${esc(d.alias_b)}','${esc(d.address)}','B',event)">B: ${esc(d.alias_b)} &#9998;</span>`:`<span class="abadge off">B: ${esc(d.alias_b)}</span>`):'';
    let abtn;
    if(d.connected){
      abtn=_disConfirm&&_disConfirm.addr===d.address
        ?`<button class="btn" style="background:#b45309;color:white" onclick="doDis('${esc(d.address)}')">Sure?</button>`
        :`<button class="btn btn-danger" onclick="doDis('${esc(d.address)}')">Disconnect</button>`;
    }else{
      const fbtn=_forgetConfirm&&_forgetConfirm.addr===d.address
        ?`<button class="btn" style="background:#b45309;color:white;margin-left:4px" onclick="doForget('${esc(d.address)}')">Sure?</button>`
        :`<button class="btn btn-danger" style="margin-left:4px" onclick="doForget('${esc(d.address)}')">Forget</button>`;
      abtn=`<button class="btn btn-blue" onclick="doRetry('${esc(d.address)}')">&#8635; Retry</button>${fbtn}`;
    }
    return `<div class="device-row ${cls}"><div class="device-info"><span class="dname ${cls}">${dot} ${esc(d.device_type.toUpperCase())} ${esc(d.version.toUpperCase())}</span><span class="daddr">${esc(d.address)}</span><span class="dbatt">${batt}</span><div class="aliases">${ba}${bb}</div></div>${abtn}</div>`;
  }).join('');
}
```

- [ ] **Step 5: Commit**

```bash
git add kink_mcp/ui.py
git commit -m "feat: forget offline devices + inline disconnect confirmation"
```

---

### Task 4: Live set_pain_limit Toggle (UI-04)

**Files:**
- Modify: `kink_mcp/server.py`
- Modify: `kink_mcp/ui.py`

Always register `set_pain_limit` as an MCP tool, but gate its execution at call time. If `pain_limit_exposed_to_llm` is `False`, return an error message instead of executing. This eliminates the need for a server restart when toggling the setting. Remove the restart warning note from the UI.

- [ ] **Step 1: Replace conditional registration with always-registered tool**

In `kink_mcp/server.py`, replace the entire `_register_pain_limit_tool()` function (lines 342-360) and the `set_pain_limit` function it contains:

```python
def _register_pain_limit_tool() -> None:
    @mcp.tool()
    async def set_pain_limit(alias: str, limit: int) -> str:
        """Set the pain (strength) soft limit for a Coyote channel or group of synced channels.

        Prevents the strength from exceeding this value. The user has enabled this tool
        via the web UI. Ask for confirmation before lowering a limit already in use.

        Args:
            alias: Channel alias assigned at connect time
            limit: Maximum strength percentage (0–100)
        """
        if limit < 0 or limit > 100:
            return "Error: Limit must be 0–100."
        try:
            await manager.set_pain_limit(alias, limit)
        except ValueError as e:
            return f"Error: {e}"
        return f"'{alias}' pain limit set to {limit}%."
```

With a regular `@mcp.tool()` that gates on the config:

```python
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
```

- [ ] **Step 2: Remove conditional registration call in `_main()`**

In `kink_mcp/server.py`, in the `_main()` function, remove the conditional registration:

```diff
  _config = load_config()
-
- if _config.get("pain_limit_exposed_to_llm", False):
-     _register_pain_limit_tool()
-
  port = find_free_port()
```

- [ ] **Step 3: Remove restart note from UI HTML**

In `kink_mcp/ui.py`, in the `_HTML` string, remove the restart note div:

```diff
- <div id="rnote" class="rnote">&#9888; Restart kink-mcp for this change to take effect.</div>
```

And remove the `.rnote` CSS class:

```diff
- .rnote{font-size:11px;color:#f59e0b;margin-top:6px;display:none}
```

- [ ] **Step 4: Remove restart note manipulation from JS**

In `kink_mcp/ui.py`, in the `togglePL()` JS function, remove the line that shows the restart note:

```diff
  async function togglePL(){
    const nv=!S.pain_limit_exposed_to_llm;
    S.pain_limit_exposed_to_llm=nv;
    renderToggle();
-   document.getElementById('rnote').style.display='block';
    await fetch('/api/pain_limit_toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({exposed:nv})});
  }
```

- [ ] **Step 5: Commit**

```bash
git add kink_mcp/server.py kink_mcp/ui.py
git commit -m "feat: always register set_pain_limit, gate at call time (no restart needed)"
```

---

### Task 5: Lovense Model Name (UI-09)

**Files:**
- Modify: `kink_mcp/lovense.py`
- Modify: `kink_mcp/device.py`
- Create: `tests/test_lovense.py`

Lovense devices are stored with `version: ""` in `_device_meta`, so the device list shows only "LOVENSE" with no model differentiation. Extract the model name from the BLE name (e.g. `"LVS-Domi"` → `"Domi"`) and store it as the `version` field.

- [ ] **Step 1: Write failing tests for `lovense_model`**

Create `tests/test_lovense.py`:

```python
"""Tests for lovense utility functions."""

from kink_mcp.lovense import lovense_model


def test_lovense_model_lvs_prefix():
    assert lovense_model("LVS-Domi") == "Domi"


def test_lovense_model_love_prefix():
    assert lovense_model("LOVE-Lush3") == "Lush3"


def test_lovense_model_no_prefix():
    assert lovense_model("Unknown") == "Unknown"


def test_lovense_model_empty_after_prefix():
    assert lovense_model("LVS-") == ""


def test_lovense_model_empty_string():
    assert lovense_model("") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_lovense.py -v`
Expected: FAIL — `ImportError: cannot import name 'lovense_model'`

- [ ] **Step 3: Implement `lovense_model`**

In `kink_mcp/lovense.py`, add the following function after the `is_lovense_name` function (after line 35):

```python
def lovense_model(name: str) -> str:
    """Extract the model identifier from a Lovense BLE name (e.g. 'LVS-Domi' → 'Domi')."""
    for prefix in LOVENSE_NAME_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_lovense.py -v`
Expected: 5 PASS

- [ ] **Step 5: Use `lovense_model` in `DeviceManager.connect()`**

In `kink_mcp/device.py`, update the import line (line 11):

```diff
- from .lovense import LovenseDevice, is_lovense_name, LOVENSE_NAME_PREFIXES
+ from .lovense import LovenseDevice, is_lovense_name, LOVENSE_NAME_PREFIXES, lovense_model
```

In `kink_mcp/device.py`, in the `connect()` method, in the Lovense branch, change the `version` field in `_device_meta`:

```diff
              "device_type": "lovense",
-             "version": "",
+             "version": lovense_model(name),
              "alias_a": alias_a,
```

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass (25 total: 20 existing + 5 new)

- [ ] **Step 7: Commit**

```bash
git add kink_mcp/lovense.py kink_mcp/device.py tests/test_lovense.py
git commit -m "feat: show Lovense model name in device list"
```

---

### Task 6: Scan/Connect UX Improvements (UI-02 + UI-06 + UI-10)

**Files:**
- Modify: `kink_mcp/ui.py`

Three improvements to the scan and connect flow:
- **UI-02:** After connecting a device, keep scan results and remove only the connected device's row (instead of clearing all results).
- **UI-06:** Disable the Connect button during BLE connection, show "Connecting…" text, show errors inline instead of `alert()`.
- **UI-10:** Pre-fill alias inputs with known aliases when connecting a device that's already in `S.devices` (e.g. offline device being reconnected via scan).

- [ ] **Step 1: Add error div and button ID to connect form HTML**

In `kink_mcp/ui.py`, in the `_HTML` string, modify the connect form to add an error div and a button ID:

```diff
  <div id="cform" class="cf hidden" style="margin-top:10px;">
    <div style="font-size:11px;color:#94a3b8;margin-bottom:6px;" id="clbl"></div>
+   <div id="cerr" style="font-size:11px;color:#f87171;margin-bottom:4px;display:none;"></div>
    <input id="iaa" placeholder="Alias A (channel A)">
    <input id="iab" placeholder="Alias B (channel B)">
-   <button class="btn btn-success" style="width:100%;padding:6px;" onclick="doConnect()">&#128279; Connect</button>
+   <button class="btn btn-success" id="cbtn" style="width:100%;padding:6px;" onclick="doConnect()">&#128279; Connect</button>
```

- [ ] **Step 2: Add `data-addr` attribute to scan result rows**

In `kink_mcp/ui.py`, in the `doScan()` function, modify the scan results rendering to add `data-addr`:

```diff
- document.getElementById('scanres').innerHTML=d.map(x=>`<div class="sr"><span>${esc(x.name)} <span style="color:#475569;font-size:11px">${esc(x.address)}</span></span><button class="btn btn-primary" onclick="showCF('${esc(x.address)}','${esc(x.name)}','${esc(x.type||x.version)}')">Connect</button></div>`).join('');
+ document.getElementById('scanres').innerHTML=d.map(x=>`<div class="sr" data-addr="${esc(x.address)}"><span>${esc(x.name)} <span style="color:#475569;font-size:11px">${esc(x.address)}</span></span><button class="btn btn-primary" onclick="showCF('${esc(x.address)}','${esc(x.name)}','${esc(x.type||x.version)}')">Connect</button></div>`).join('');
```

- [ ] **Step 3: Rewrite `doConnect` with inline errors, button state, and scan result caching**

Replace the current `doConnect` function:

```javascript
async function doConnect(){
  if(!cdev)return;
  const aa=document.getElementById('iaa').value.trim();
  const ab=document.getElementById('iab').value.trim();
  if(!aa){alert('Alias A is required.');return;}
  if(cdev.dtype!=='lovense'&&!ab){alert('Alias B is required for Coyote.');return;}
  try{
    const r=await fetch('/api/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({address:cdev.addr,alias_a:aa,alias_b:ab||null})});
    const d=await r.json();
    if(d.error){alert(d.error);return;}
    cancelCon();
    document.getElementById('scanres').innerHTML='';
    document.getElementById('scanst').textContent='';
    poll();
  }catch(e){alert('Connection failed.');}
}
```

With:

```javascript
async function doConnect(){
  if(!cdev)return;
  const errEl=document.getElementById('cerr');
  errEl.style.display='none';
  const aa=document.getElementById('iaa').value.trim();
  const ab=document.getElementById('iab').value.trim();
  if(!aa){errEl.textContent='Alias A is required.';errEl.style.display='block';return;}
  if(cdev.dtype!=='lovense'&&!ab){errEl.textContent='Alias B is required for Coyote.';errEl.style.display='block';return;}
  const cbtn=document.getElementById('cbtn');
  cbtn.disabled=true;cbtn.innerHTML='&#9203; Connecting...';
  try{
    const r=await fetch('/api/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({address:cdev.addr,alias_a:aa,alias_b:ab||null})});
    const d=await r.json();
    if(d.error){errEl.textContent=d.error;errEl.style.display='block';cbtn.disabled=false;cbtn.innerHTML='&#128279; Connect';return;}
    cancelCon();
    const row=document.querySelector('#scanres .sr[data-addr="'+cdev.addr+'"]');
    if(row)row.remove();
    poll();
  }catch(e){errEl.textContent='Connection failed.';errEl.style.display='block';cbtn.disabled=false;cbtn.innerHTML='&#128279; Connect';}
}
```

- [ ] **Step 4: Update `cancelCon` to reset error and button state**

Replace the current `cancelCon` function:

```javascript
function cancelCon(){cdev=null;document.getElementById('cform').classList.add('hidden');}
```

With:

```javascript
function cancelCon(){cdev=null;document.getElementById('cform').classList.add('hidden');document.getElementById('cerr').style.display='none';const cbtn=document.getElementById('cbtn');cbtn.disabled=false;cbtn.innerHTML='&#128279; Connect';}
```

- [ ] **Step 5: Update `showCF` to pre-fill aliases (UI-10) and reset error state**

Replace the current `showCF` function:

```javascript
function showCF(addr,name,dtype){
  cdev={addr,name,dtype};
  document.getElementById('clbl').textContent='Connect \u2014 '+name;
  document.getElementById('iab').style.display=dtype==='lovense'?'none':'block';
  document.getElementById('iaa').value='';document.getElementById('iab').value='';
  document.getElementById('cform').classList.remove('hidden');
  document.getElementById('iaa').focus();
}
```

With:

```javascript
function showCF(addr,name,dtype){
  cdev={addr,name,dtype};
  document.getElementById('clbl').textContent='Connect \u2014 '+name;
  document.getElementById('iab').style.display=dtype==='lovense'?'none':'block';
  const known=S.devices.find(d=>d.address===addr);
  document.getElementById('iaa').value=known?known.alias_a:'';
  document.getElementById('iab').value=known&&known.alias_b?known.alias_b:'';
  document.getElementById('cerr').style.display='none';
  document.getElementById('cbtn').disabled=false;
  document.getElementById('cbtn').innerHTML='&#128279; Connect';
  document.getElementById('cform').classList.remove('hidden');
  document.getElementById('iaa').focus();
}
```

- [ ] **Step 6: Commit**

```bash
git add kink_mcp/ui.py
git commit -m "feat: scan result caching, connection feedback, pre-fill aliases"
```

---

### Task 7: Debounced Pain Limit Slider (UI-05)

**Files:**
- Modify: `kink_mcp/ui.py`

The pain limit slider sends the value only on mouse-up (`onchange`). Add a debounced `oninput` handler (300ms) so the server state updates during drag.

- [ ] **Step 1: Add debounce function**

In `kink_mcp/ui.py`, in the `<script>` section, add after the `setPL` function:

```javascript
let _plTimer=null;
function debouncePL(alias,val){clearTimeout(_plTimer);_plTimer=setTimeout(()=>setPL(alias,val),300);}
```

- [ ] **Step 2: Update slider handlers in `renderMatrix`**

In `kink_mcp/ui.py`, in the `renderMatrix()` function, update both slider `oninput` attributes to call `debouncePL` (keep `onchange` as final confirmation):

For Channel A slider, change:
```diff
- oninput="this.nextElementSibling.textContent=this.value+'%'" onchange="setPL('${esc(d.alias_a)}',+this.value)"
+ oninput="this.nextElementSibling.textContent=this.value+'%';debouncePL('${esc(d.alias_a)}',+this.value)" onchange="setPL('${esc(d.alias_a)}',+this.value)"
```

For Channel B slider, change:
```diff
- oninput="this.nextElementSibling.textContent=this.value+'%'" onchange="setPL('${esc(d.alias_b)}',+this.value)"
+ oninput="this.nextElementSibling.textContent=this.value+'%';debouncePL('${esc(d.alias_b)}',+this.value)" onchange="setPL('${esc(d.alias_b)}',+this.value)"
```

- [ ] **Step 3: Commit**

```bash
git add kink_mcp/ui.py
git commit -m "feat: debounced pain limit slider for real-time updates"
```

---

### Task 8: Inline UI Feedback (UI-07 + UI-08)

**Files:**
- Modify: `kink_mcp/ui.py`

Two small feedback improvements:
- **UI-07:** When any connected device has battery < 30%, show a low-battery warning in the header badge.
- **UI-08:** When renaming an alias to one already in use, show an inline warning that commands will be synced.

- [ ] **Step 1: Update `renderBadge` for battery warning (UI-07)**

Replace the current `renderBadge` function:

```javascript
function renderBadge(){
  const n=S.devices.filter(d=>d.connected).length;
  document.getElementById('sbadge').innerHTML=n>0?`<span class="ok">&#9679; ${n} device${n>1?'s':''} connected</span>`:'<span style="color:#94a3b8">No devices connected</span>';
}
```

With:

```javascript
function renderBadge(){
  const n=S.devices.filter(d=>d.connected).length;
  const low=S.devices.filter(d=>d.connected&&d.battery>=0&&d.battery<30).length;
  if(n>0){
    const warn=low>0?` <span style="color:#f59e0b">&#9888; ${low} low battery</span>`:'';
    document.getElementById('sbadge').innerHTML=`<span class="ok">&#9679; ${n} device${n>1?'s':''} connected</span>${warn}`;
  }else{
    document.getElementById('sbadge').innerHTML='<span style="color:#94a3b8">No devices connected</span>';
  }
}
```

- [ ] **Step 2: Add warning div to rename popup (UI-08)**

In `kink_mcp/ui.py`, in the `_HTML` string, add a warning div inside the rename popup, after the input:

```diff
  <input type="text" id="rinput" onkeydown="if(event.key==='Enter')saveRename();if(event.key==='Escape')closeRen();">
+ <div id="rwarn" style="font-size:11px;color:#f59e0b;margin-top:4px;display:none;"></div>
  <div class="ra">
```

- [ ] **Step 3: Add duplicate alias check to rename input handler**

In `kink_mcp/ui.py`, in the `<script>` section, add after the `closeRen` function:

```javascript
document.getElementById('rinput').addEventListener('input',function(){
  if(!renS)return;
  const nv=this.value.trim();
  const warn=document.getElementById('rwarn');
  if(nv&&nv!==renS.alias){
    const dup=S.devices.some(d=>(d.alias_a===nv||d.alias_b===nv)&&d.address!==renS.addr);
    warn.style.display=dup?'block':'none';
    warn.textContent='This alias is already used — commands will be synced.';
  }else{warn.style.display='none';}
});
```

- [ ] **Step 4: Commit**

```bash
git add kink_mcp/ui.py
git commit -m "feat: low battery warning in header + duplicate alias warning"
```

---

### Task 9: README Update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update LLM toggle description (UI-04)**

In `README.md`, line 35, remove "restart required":

```diff
- - **LLM toggle** — expose `set_pain_limit` to the AI (off by default); restart required
+ - **LLM toggle** — expose `set_pain_limit` to the AI (off by default); takes effect immediately
```

- [ ] **Step 2: Add Forget feature to Web UI section**

In `README.md`, after the "Connected Devices" bullet in the Web UI section (after line 32), add:

```diff
  - **Connected Devices** — live list with battery, connection state, and per-device Disconnect
+ - **Forget offline devices** — remove retired/replaced devices from the device list
  - **Alias Rename** — click any alias badge to rename it on the fly
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README for live toggle and forget feature"
```

---

## Self-Review

### Spec Coverage

| Spec Item | Task |
|-----------|------|
| BUG-001 textContent → innerHTML | Task 1 |
| BUG-002 full UUID | Task 1 |
| UI-01 Forget device | Task 2 (backend) + Task 3 (frontend) |
| UI-02 Scan result caching | Task 6 |
| UI-03 Inline disconnect confirmation | Task 3 |
| UI-04 Live set_pain_limit toggle | Task 4 |
| UI-05 Debounced slider | Task 7 |
| UI-06 Connection feedback | Task 6 |
| UI-07 Battery warning | Task 8 |
| UI-08 Duplicate alias warning | Task 8 |
| UI-09 Lovense model name | Task 5 |
| UI-10 Pre-fill aliases | Task 6 |

All 12 items covered.

### Placeholder Scan

No TBD, TODO, "implement later", "add appropriate error handling", or "similar to Task N" patterns found.

### Type Consistency

- `forget_device(address: str)` → called by `handle_forget` with `body["address"]` (str) ✓
- `lovense_model(name: str) → str` → used in `_device_meta["version"]` (str) ✓
- `_disConfirm` / `_forgetConfirm` JS vars referenced consistently in `renderDevices`, `doDis`, `doForget` ✓
- `#cerr` div referenced in `doConnect`, `cancelCon`, `showCF` ✓
- `#cbtn` referenced in `doConnect`, `cancelCon`, `showCF` ✓
- `#rwarn` div referenced in input listener ✓
