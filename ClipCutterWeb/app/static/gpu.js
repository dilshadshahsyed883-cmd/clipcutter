(() => {
  const $ = id => document.getElementById(id), form = $("gpu-form"), fields = $("gpu-fields");
  const stringKeys = ["salad_organization","salad_project","salad_container_group","worker_gateway"];
  const numberKeys = ["image_pull_threshold","image_pull_seconds","salad_max_reallocations","salad_reallocate_cooldown","parallel"];
  let csrf = null, saving = false, refreshing = false, acting = false, configured = false;
  async function api(path, method="GET", data) {
    const headers = {Accept:"application/json"};
    if (method !== "GET") {
      if (!csrf) {
        const response = await fetch("/api/v1/auth/csrf",{cache:"no-store",credentials:"same-origin"});
        if (!response.ok) throw Error("Session unavailable");
        csrf = (await response.json()).csrf_token;
      }
      headers["X-CSRF-Token"] = csrf; headers["Content-Type"]="application/json";
    }
    const response=await fetch("/api/v1/gpu"+path,{method,headers,cache:"no-store",credentials:"same-origin",body:data===undefined?undefined:JSON.stringify(data)});
    if (!response.ok) {
      if ([401,403].includes(response.status)) csrf=null;
      const body=await response.json().catch(()=>({}));
      throw Error(typeof body.detail==="string"?body.detail:"GPU request failed ("+response.status+")");
    }
    return response.json();
  }
  function rule() {
    const f=form.elements;
    $("gpu-rule").textContent="Keep the instance if image download reaches "+f.image_pull_threshold.value+"% within "+f.image_pull_seconds.value+" seconds. Otherwise reallocate up to "+f.salad_max_reallocations.value+" times per cycle, with "+f.salad_reallocate_cooldown.value+" seconds between attempts; after an exhausted cycle wait 5 minutes and retry automatically.";
  }
  function apply(cfg) {
    for (const k of [...stringKeys,...numberKeys,"auto_start"]) form.elements[k].value=String(cfg[k]);
    for (const k of ["salad_key","worker_key"]) form.elements[k].value="";
    for (const k of ["clear_salad_key","clear_worker_key"]) form.elements[k].checked=false;
    $("gpu-salad-key-state").textContent=cfg.salad_key_configured?"Key configured":"Key not configured";
    $("gpu-worker-key-state").textContent=cfg.worker_key_configured?"Token configured":"Token not configured";
    $("gpu-capability").textContent=cfg.message;
    configured=Boolean(cfg.group_configured&&cfg.salad_key_configured);
    fields.disabled=false; $("gpu-refresh").disabled=!configured;
    controls(cfg);
    rule();
  }
  function controls(cfg){
    const enabled=cfg.dispatch_enabled===true,s=cfg.scheduler||{};
    for(const action of ["start","stop","retry","pause","resume"]){
      const queueAction=action==="pause"||action==="resume";
      $("gpu-"+action).disabled=acting||(!queueAction&&!enabled)||(["start","stop"].includes(action)&&cfg.auto_start)||(action==="pause"&&s.paused)||(action==="resume"&&(!s.paused||s.action==="stop"));
    }
    $("gpu-capability").textContent=(enabled?"Scheduler enabled":"Scheduler gated")+" · Queue: "+(s.paused?"Paused":"Active")+" · "+(s.status||"offline");
    $("gpu-capability").title=cfg.message;
  }
  for(const action of ["start","stop","retry","pause","resume"]){
    $("gpu-"+action).onclick=async()=>{
      if(acting)return;acting=true;
      for(const name of ["start","stop","retry","pause","resume"])$("gpu-"+name).disabled=true;
      try{await api("/actions/"+action,"POST");$("gpu-action-status").textContent="Action accepted.";}
      catch(e){$("gpu-action-status").textContent=e.message;}
      finally{acting=false;try{controls(await api("/config"));}catch(e){$("gpu-action-status").textContent=e.message;}}
    };
  }
  form.addEventListener("input",rule);
  form.addEventListener("submit",async event=>{
    event.preventDefault(); if(saving)return;
    const data={}, f=form.elements;
    for(const k of stringKeys)data[k]=f[k].value.trim();
    for(const k of numberKeys)data[k]=Number(f[k].value);
    for(const k of ["salad_key","worker_key"])data[k]=f[k].value;
    for(const k of ["clear_salad_key","clear_worker_key"])data[k]=f[k].checked;
    data.auto_start=f.auto_start.value==="true";
    saving=true;fields.disabled=true;
    $("gpu-save-status").textContent="Saving…";
    try{const cfg=await api("/config","POST",data);apply(cfg);$("gpu-save-status").textContent=cfg.dispatch_enabled?"Saved.":"Saved. GPU scheduler not active.";$("gpu-status").textContent="Status not checked for saved configuration.";$("gpu-instances").replaceChildren();}
    catch(error){$("gpu-save-status").textContent=error.message;}
    finally{fields.disabled=false;saving=false;}
  });
  async function refreshStatus(live=false){
    if(refreshing||saving||!configured||document.hidden)return;refreshing=true;$("gpu-refresh").disabled=true;
    if(!$("gpu-instances").children.length)$("gpu-status").textContent="Checking SaladCloud…";
    try{
      const result=await api(live?"/status":"/status/cached");
      $("gpu-status").textContent=(result.observed_at?"Last checked: "+new Date(result.observed_at*1000).toLocaleString()+" | ":"")+"Group: "+result.status+" | replicas: "+(result.replicas??"unknown")+" | autostart: "+(result.autostart_policy??"unknown")+" | "+(result.dedicated_group_compatible?"Dedicated group settings valid":"Blocked: "+(result.group_blocker||"group settings not verified"));
      $("gpu-instances").replaceChildren();
      for(const item of result.instances){const tr=document.createElement("tr");
        for(const val of [item.id,item.state,item.pulling_progress===null?null:item.pulling_progress+"%",item.ready,item.update_time]){const td=document.createElement("td");td.textContent=String(val??"Unknown");tr.append(td);}
        $("gpu-instances").append(tr);
      }
    }catch(error){$("gpu-status").textContent="Status unavailable: "+error.message;$("gpu-instances").replaceChildren();}
    finally{refreshing=false;$("gpu-refresh").disabled=!configured;}
  }
  $("gpu-refresh").addEventListener("click",()=>refreshStatus(true));
  api("/config").then(cfg=>{apply(cfg);return refreshStatus();}).catch(error=>{$("gpu-capability").textContent=error.message;});
  const timer=setInterval(async()=>{if(!document.hidden&&!saving){try{controls(await api("/config"));}catch(e){for(const a of ["start","stop","retry","pause","resume"])$("gpu-"+a).disabled=true;}}},10000);
  const statusTimer=setInterval(()=>refreshStatus(false),10000);
  window.addEventListener("pagehide",()=>{clearInterval(timer);clearInterval(statusTimer);},{once:true});
})();
