(() => {
  const $ = id => document.getElementById(id), form = $("gpu-form"), fields = $("gpu-fields");
  const stringKeys = ["salad_organization","salad_project","salad_container_group","worker_gateway"];
  const numberKeys = ["image_pull_threshold","image_pull_seconds","salad_max_reallocations","salad_reallocate_cooldown","parallel"];
  let csrf = null, saving = false, refreshing = false;
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
    fields.disabled=false; $("gpu-refresh").disabled=!(cfg.group_configured&&cfg.salad_key_configured);
    rule();
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
    try{apply(await api("/config","POST",data));$("gpu-save-status").textContent="Saved. GPU actions remain gated.";$("gpu-status").textContent="Status not checked for saved configuration.";$("gpu-instances").replaceChildren();}
    catch(error){$("gpu-save-status").textContent=error.message;}
    finally{fields.disabled=false;saving=false;}
  });
  $("gpu-refresh").addEventListener("click",async()=>{
    if(refreshing||saving)return;refreshing=true;$("gpu-refresh").disabled=true;fields.disabled=true;
    $("gpu-status").textContent="Checking SaladCloud…";$("gpu-instances").replaceChildren();
    try{
      const result=await api("/status");
      $("gpu-status").textContent="Group: "+result.status+" | replicas: "+(result.replicas??"unknown")+" | autostart: "+(result.autostart_policy??"unknown")+" | "+(result.dedicated_group_compatible?"Dedicated group settings valid":"Dedicated group settings not verified");
      for(const item of result.instances){const tr=document.createElement("tr");
        for(const val of [item.id,item.state,item.pulling_progress===null?null:item.pulling_progress+"%",item.ready,item.update_time]){const td=document.createElement("td");td.textContent=String(val??"Unknown");tr.append(td);}
        $("gpu-instances").append(tr);
      }
    }catch(error){$("gpu-status").textContent=error.message;}
    finally{refreshing=false;fields.disabled=false;$("gpu-refresh").disabled=false;}
  });
  api("/config").then(apply).catch(error=>{$("gpu-capability").textContent=error.message;});
})();
