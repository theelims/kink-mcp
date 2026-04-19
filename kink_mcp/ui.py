"""aiohttp web UI server for kink-mcp."""

import asyncio
import json
import socket

from aiohttp import web

from .device import DeviceManager

# ---------------------------------------------------------------------------
# HTML payload — single-page control panel
# ---------------------------------------------------------------------------

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>kink-mcp Control Panel</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;font-size:14px;padding:14px;min-height:100vh}
h1{font-size:16px;font-weight:700;color:#a78bfa}
.header{background:#1e293b;padding:8px 14px;border-radius:8px;display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.badge{font-size:12px;color:#94a3b8}.badge .ok{color:#34d399}
.top-row{display:grid;grid-template-columns:1fr 270px;gap:12px;margin-bottom:12px}
.panel{background:#1e293b;border-radius:8px;padding:12px}
.panel-title{font-size:11px;font-weight:600;letter-spacing:.06em;color:#818cf8;text-transform:uppercase;margin-bottom:10px}
.device-row{background:#0f172a;border-radius:6px;padding:8px 12px;border-left:3px solid #334155;display:flex;align-items:center;gap:10px;margin-bottom:6px}
.device-row.ok{border-color:#34d399}.device-row.warn{border-color:#f59e0b}.device-row.err{border-color:#ef4444;opacity:.72}
.device-info{flex:1;min-width:0}
.dname{font-size:11px;font-weight:600}.dname.ok{color:#34d399}.dname.warn{color:#f59e0b}.dname.err{color:#ef4444}
.daddr{font-size:10px;color:#475569;margin-left:6px}
.dbatt{font-size:10px;color:#94a3b8;float:right}
.aliases{margin-top:4px}
.abadge{display:inline-block;background:#312e81;color:#a5b4fc;padding:1px 7px;border-radius:3px;font-size:10px;margin-right:4px;cursor:pointer;user-select:none}
.abadge:hover{background:#4338ca;outline:1px solid #a78bfa}
.abadge.off{background:#1c1917;color:#78716c;cursor:default}
.btn{border:none;padding:3px 10px;border-radius:4px;font-size:11px;cursor:pointer;white-space:nowrap}
.btn-danger{background:#7f1d1d;color:#fca5a5}.btn-blue{background:#1e3a5f;color:#93c5fd}
.btn-primary{background:#6366f1;color:white}.btn-success{background:#059669;color:white}
.btn-lg{padding:7px;width:100%;font-size:13px;font-weight:600;border-radius:6px}
.sr{font-size:12px;display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid #1e293b}
.sr:last-child{border-bottom:none}
.cf input{width:100%;background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:5px 8px;border-radius:4px;font-size:12px;margin-bottom:5px}
.cf input:focus{outline:1px solid #6366f1}
.mhdr{display:grid;grid-template-columns:200px 1fr 1fr;gap:8px;margin-bottom:4px;font-size:10px;color:#94a3b8;text-align:center;font-weight:600;text-transform:uppercase}
.mhdr .lc{text-align:left}
.mrow{display:grid;grid-template-columns:200px 1fr 1fr;gap:8px;margin-bottom:6px;align-items:center}
.mrow.off{opacity:.45}
.mlbl{font-size:12px;color:#94a3b8}
.mcell{background:#0f172a;padding:6px 10px;border-radius:5px;text-align:center}
.malias{font-size:10px;color:#a5b4fc;margin-bottom:3px}
.mcell input[type=range]{width:100%;accent-color:#a78bfa;cursor:pointer}
.mcell input[type=range]:disabled{accent-color:#475569;cursor:default}
.mval{font-size:12px;font-weight:600}
.tw{display:flex;align-items:center;gap:8px;font-size:12px;color:#94a3b8;cursor:pointer}
.tw code{background:#0f172a;padding:1px 5px;border-radius:3px;color:#a78bfa;font-size:11px}
.tog{width:36px;height:20px;background:#334155;border-radius:10px;position:relative;flex-shrink:0;transition:background .2s}
.tog.on{background:#6366f1}
.togk{width:16px;height:16px;background:#94a3b8;border-radius:8px;position:absolute;top:2px;left:2px;transition:left .2s}
.tog.on .togk{left:18px;background:white}
#rpop{display:none;position:fixed;background:#1e293b;border:1px solid #6366f1;border-radius:8px;padding:12px;width:230px;box-shadow:0 8px 24px rgba(0,0,0,.6);z-index:100}
#rpop .rt{font-size:11px;color:#94a3b8;margin-bottom:8px}
#rpop input{width:100%;background:#0f172a;border:1px solid #6366f1;color:#e2e8f0;padding:5px 8px;border-radius:4px;font-size:13px;outline:none}
#rpop .ra{display:flex;gap:6px;margin-top:8px}
#rpop .ra button{flex:1}
.hidden{display:none!important}
</style>
</head>
<body>
<div class="header">
  <h1>&#9889; kink-mcp</h1>
  <span class="badge" id="sbadge">Loading...</span>
</div>
<div class="top-row">
  <div class="panel">
    <div class="panel-title">Connected Devices</div>
    <div id="dlist"></div>
  </div>
  <div class="panel">
    <div class="panel-title">Scan &amp; Connect</div>
    <button class="btn btn-primary btn-lg" id="scanbtn" onclick="doScan()">&#128269; Scan for Devices</button>
    <div id="scanst" style="font-size:11px;color:#94a3b8;margin-top:6px;"></div>
    <div id="scanres" style="margin-top:8px;"></div>
    <div id="cform" class="cf hidden" style="margin-top:10px;">
      <div style="font-size:11px;color:#94a3b8;margin-bottom:6px;" id="clbl"></div>
      <div id="cerr" style="font-size:11px;color:#f87171;margin-bottom:4px;display:none;"></div>
      <input id="iaa" placeholder="Alias A (channel A)">
      <input id="iab" placeholder="Alias B (channel B)">
      <button class="btn btn-success" id="cbtn" style="width:100%;padding:6px;" onclick="doConnect()">&#128279; Connect</button>
      <button class="btn" style="width:100%;padding:4px;margin-top:4px;background:#1e293b;color:#94a3b8;border:1px solid #334155;" onclick="cancelCon()">Cancel</button>
    </div>
  </div>
</div>
<div class="panel">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
    <div class="panel-title" style="margin-bottom:0">Pain Limit</div>
    <div class="tw" onclick="togglePL()">
      <span>Expose <code>set_pain_limit</code> to LLM</span>
      <div class="tog" id="pltog"><div class="togk"></div></div>
    </div>
  </div>
  <div class="mhdr"><div class="lc"></div><div>Channel A</div><div>Channel B</div></div>
  <div id="pmatrix"></div>
</div>
<div id="rpop">
  <div class="rt" id="rtitle"></div>
  <input type="text" id="rinput" onkeydown="if(event.key==='Enter')saveRename();if(event.key==='Escape')closeRen();">
  <div id="rwarn" style="font-size:11px;color:#f59e0b;margin-top:4px;display:none;"></div>
  <div class="ra">
    <button class="btn btn-primary" onclick="saveRename()">Save</button>
    <button class="btn" style="background:#1e293b;color:#94a3b8;border:1px solid #334155;" onclick="closeRen()">Cancel</button>
  </div>
</div>
<script>
let S={devices:[],pain_limit_exposed_to_llm:false};
let cdev=null,renS=null;
let _disConfirm=null;
let _forgetConfirm=null;
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
async function poll(){try{const r=await fetch('/api/status');if(!r.ok)return;S=await r.json();render();}catch(e){}}
setInterval(poll,1000);poll();
function render(){renderBadge();renderDevices();renderMatrix();renderToggle();}
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
function renderMatrix(){
  const el=document.getElementById('pmatrix');
  const coys=S.devices.filter(d=>d.device_type==='coyote');
  if(!coys.length){el.innerHTML='<div style="font-size:12px;color:#475569;">No Coyote devices.</div>';return;}
  el.innerHTML=coys.map(d=>{
    const dis=d.connected?'':'disabled';
    const la=d.limit_a??100;const lb=d.limit_b??100;
    const ca=`<div class="mcell"><div class="malias">${esc(d.alias_a)}</div><input type="range" min="0" max="100" value="${la}" ${dis} oninput="this.nextElementSibling.textContent=this.value+'%';debouncePL('${esc(d.alias_a)}',+this.value)" onchange="setPL('${esc(d.alias_a)}',+this.value)"><div class="mval">${la}%</div></div>`;
    const cb=d.alias_b?`<div class="mcell"><div class="malias">${esc(d.alias_b)}</div><input type="range" min="0" max="100" value="${lb}" ${dis} oninput="this.nextElementSibling.textContent=this.value+'%';debouncePL('${esc(d.alias_b)}',+this.value)" onchange="setPL('${esc(d.alias_b)}',+this.value)"><div class="mval">${lb}%</div></div>`:'<div class="mcell" style="opacity:.3"><div class="malias">&mdash;</div></div>';
    const dot=d.connected?(d.battery>=0&&d.battery<30?'&#9679;':'&#9679;'):'&#10007;';
    const dotcol=d.connected?(d.battery>=0&&d.battery<30?'#f59e0b':'#34d399'):'#ef4444';
    return `<div class="mrow${d.connected?'':' off'}"><div class="mlbl"><span style="color:${dotcol}">${dot}</span> ${esc(d.device_type)} ${esc(d.version)} &middot; ${esc(d.address)}</div>${ca}${cb}</div>`;
  }).join('');
}
function renderToggle(){
  const el=document.getElementById('pltog');
  S.pain_limit_exposed_to_llm?el.classList.add('on'):el.classList.remove('on');
}
async function doScan(){
  const btn=document.getElementById('scanbtn');
  btn.disabled=true;btn.innerHTML='&#9203; Scanning...';
  document.getElementById('scanst').textContent='';
  document.getElementById('scanres').innerHTML='';
  cancelCon();
  try{
    const r=await fetch('/api/scan',{method:'POST'});
    const d=await r.json();
    if(d.error){document.getElementById('scanst').textContent=d.error;}
    else if(!d.length){document.getElementById('scanst').textContent='No devices found.';}
    else{
      document.getElementById('scanst').textContent=`Found ${d.length} device${d.length>1?'s':''}.`;
      document.getElementById('scanres').innerHTML=d.map(x=>`<div class="sr" data-addr="${esc(x.address)}"><span>${esc(x.name)} <span style="color:#475569;font-size:11px">${esc(x.address)}</span></span><button class="btn btn-primary" onclick="showCF('${esc(x.address)}','${esc(x.name)}','${esc(x.type||x.version)}')">Connect</button></div>`).join('');
    }
  }catch(e){document.getElementById('scanst').textContent='Scan failed.';}
  finally{btn.disabled=false;btn.innerHTML='&#128269; Scan for Devices';}
}
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
function cancelCon(){cdev=null;document.getElementById('cform').classList.add('hidden');document.getElementById('cerr').style.display='none';const cbtn=document.getElementById('cbtn');cbtn.disabled=false;cbtn.innerHTML='&#128279; Connect';}
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
async function doRetry(addr){
  try{
    const r=await fetch('/api/retry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({address:addr})});
    const d=await r.json();
    if(d.error)alert(d.error);
    poll();
  }catch(e){alert('Retry failed.');}
}
function openRen(alias,addr,ch,ev){
  renS={alias,addr,ch};
  document.getElementById('rtitle').textContent=`Rename alias "${alias}" (Ch ${ch})`;
  const inp=document.getElementById('rinput');
  inp.value=alias;
  const pop=document.getElementById('rpop');
  pop.style.display='block';
  const rect=ev.target.getBoundingClientRect();
  pop.style.left=Math.min(rect.left,window.innerWidth-245)+'px';
  pop.style.top=(rect.bottom+window.scrollY+6)+'px';
  inp.focus();inp.select();
  ev.stopPropagation();
}
function closeRen(){renS=null;document.getElementById('rpop').style.display='none';}
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
async function saveRename(){
  if(!renS)return;
  const nv=document.getElementById('rinput').value.trim();
  if(!nv){alert('Alias cannot be empty.');return;}
  if(nv===renS.alias){closeRen();return;}
  try{
    const r=await fetch('/api/rename',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old_alias:renS.alias,new_alias:nv})});
    const d=await r.json();
    if(d.error){alert(d.error);return;}
    closeRen();poll();
  }catch(e){alert('Rename failed.');}
}
let _plTimer=null;
function debouncePL(alias,val){clearTimeout(_plTimer);_plTimer=setTimeout(()=>setPL(alias,val),300);}
async function setPL(alias,limit){
  await fetch('/api/pain_limit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({alias,limit})});
}
async function togglePL(){
  const nv=!S.pain_limit_exposed_to_llm;
  S.pain_limit_exposed_to_llm=nv;
  renderToggle();
  await fetch('/api/pain_limit_toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({exposed:nv})});
}
document.addEventListener('click',e=>{
  const p=document.getElementById('rpop');
  if(p.style.display!=='none'&&!p.contains(e.target))closeRen();
});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_free_port() -> int:
    """Bind to port 0, let the OS assign a free port, return it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def _sync_config(manager: DeviceManager, config: dict) -> None:
    """Overwrite config['devices'] from manager._device_meta and save."""
    from .config import save_config

    config["devices"] = [
        {
            "address": addr,
            "name": meta["name"],
            "device_type": meta["device_type"],
            "version": meta.get("version", ""),
            "alias_a": meta["alias_a"],
            "alias_b": meta.get("alias_b"),
            "limit_a_pct": meta.get("limit_a_pct", 100),
            "limit_b_pct": meta.get("limit_b_pct"),
        }
        for addr, meta in manager._device_meta.items()
    ]
    save_config(config)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

async def handle_root(request: web.Request) -> web.Response:
    return web.Response(text=_HTML, content_type="text/html")


async def handle_status(request: web.Request) -> web.Response:
    manager: DeviceManager = request.app["manager"]
    config: dict = request.app["config"]
    return web.json_response({
        "devices": manager.get_device_list(),
        "pain_limit_exposed_to_llm": config.get("pain_limit_exposed_to_llm", False),
    })


async def handle_scan(request: web.Request) -> web.Response:
    manager: DeviceManager = request.app["manager"]
    try:
        results = await manager.scan(timeout=5.0)
        return web.json_response(results)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_connect(request: web.Request) -> web.Response:
    manager: DeviceManager = request.app["manager"]
    config: dict = request.app["config"]
    try:
        body = await request.json()
        address = body["address"]
        alias_a = body["alias_a"]
        alias_b = body.get("alias_b") or None

        stored = manager._device_meta.get(address, {})
        limit_a = stored.get("limit_a_pct", 100)
        limit_b = stored.get("limit_b_pct", 100)

        a, b = await manager.connect(address, alias_a=alias_a, alias_b=alias_b)

        if limit_a < 100:
            await manager.set_pain_limit(alias_a, limit_a)
        if b and limit_b < 100:
            await manager.set_pain_limit(b, limit_b)

        _sync_config(manager, config)
        return web.json_response({"alias_a": a, "alias_b": b})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_disconnect(request: web.Request) -> web.Response:
    manager: DeviceManager = request.app["manager"]
    config: dict = request.app["config"]
    try:
        body = await request.json()
        await manager.disconnect_one(body["address"])
        _sync_config(manager, config)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_retry(request: web.Request) -> web.Response:
    manager: DeviceManager = request.app["manager"]
    config: dict = request.app["config"]
    try:
        body = await request.json()
        address = body["address"]
        meta = manager._device_meta.get(address)
        if not meta:
            return web.json_response({"error": f"Unknown device {address}"}, status=404)
        alias_a = meta["alias_a"]
        alias_b = meta.get("alias_b")
        limit_a = meta.get("limit_a_pct", 100)
        limit_b = meta.get("limit_b_pct", 100)
        del manager._device_meta[address]
        a, b = await manager.connect(address, alias_a=alias_a, alias_b=alias_b)
        if limit_a < 100:
            await manager.set_pain_limit(a, limit_a)
        if b and limit_b is not None and limit_b < 100:
            await manager.set_pain_limit(b, limit_b)
        _sync_config(manager, config)
        return web.json_response({"alias_a": a, "alias_b": b})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_rename(request: web.Request) -> web.Response:
    manager: DeviceManager = request.app["manager"]
    config: dict = request.app["config"]
    try:
        body = await request.json()
        manager.rename_alias(body["old_alias"], body["new_alias"])
        _sync_config(manager, config)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


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


async def handle_pain_limit(request: web.Request) -> web.Response:
    manager: DeviceManager = request.app["manager"]
    config: dict = request.app["config"]
    try:
        body = await request.json()
        await manager.set_pain_limit(body["alias"], int(body["limit"]))
        _sync_config(manager, config)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_pain_limit_toggle(request: web.Request) -> web.Response:
    config: dict = request.app["config"]
    from .config import save_config
    try:
        body = await request.json()
        config["pain_limit_exposed_to_llm"] = bool(body["exposed"])
        save_config(config)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


# ---------------------------------------------------------------------------
# App factory + runner
# ---------------------------------------------------------------------------

def create_app(manager: DeviceManager, config: dict) -> web.Application:
    app = web.Application()
    app["manager"] = manager
    app["config"] = config
    app.router.add_get("/", handle_root)
    app.router.add_get("/api/status", handle_status)
    app.router.add_post("/api/scan", handle_scan)
    app.router.add_post("/api/connect", handle_connect)
    app.router.add_post("/api/disconnect", handle_disconnect)
    app.router.add_post("/api/retry", handle_retry)
    app.router.add_post("/api/rename", handle_rename)
    app.router.add_post("/api/forget", handle_forget)
    app.router.add_post("/api/pain_limit", handle_pain_limit)
    app.router.add_post("/api/pain_limit_toggle", handle_pain_limit_toggle)
    return app


async def run_web_server(app: web.Application, port: int) -> None:
    """Start the aiohttp server and keep it running."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", port)
    await site.start()
    await asyncio.Event().wait()  # run until cancelled
