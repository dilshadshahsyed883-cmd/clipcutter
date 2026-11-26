(() => {
  const $=id=>document.getElementById(id);
  const form=$("extractor-options"), video=$("extractor-preview"), input=$("source-preview");
  let url=null, valid=null, revision=0;
  input.addEventListener("change",()=>{
    video.removeAttribute("src");video.load();
    if(url)URL.revokeObjectURL(url);
    url=null;
    if(input.files[0]){url=URL.createObjectURL(input.files[0]);video.src=url;$("preview-status").textContent="Local preview only; media stays in this browser.";}
  });
  window.addEventListener("pagehide",()=>{if(url)URL.revokeObjectURL(url);},{once:true});
  video.addEventListener("error",()=>{$("preview-status").textContent="Browser cannot preview this video. Worker compatibility is not established."});
  function invalidate(){revision++;valid=null;$("save-options").disabled=true;$("extractor-status").textContent="";}
  form.addEventListener("input",invalidate);
  $("strict-limits").addEventListener("change",()=>{$("limit-fields").hidden=!$("strict-limits").checked;});
  form.addEventListener("submit",async e=>{
    e.preventDefault();invalidate();const stamp=revision;
    const f=new FormData(form), bool=k=>f.get(k)==="true";
    const payload={threshold:Number(f.get("threshold")),scan_quality:f.get("scan_quality"),mode:f.get("mode"),
      stitched:bool("stitched"),include_audio:bool("include_audio"),quality:Number(f.get("quality")),
      max_short_side:Number(f.get("max_short_side")),framing:f.get("framing"),
      minimum_ms:$("strict-limits").checked?Math.round(Number(f.get("minimum"))*1000):null,
      maximum_ms:$("strict-limits").checked?Math.round(Number(f.get("maximum"))*1000):null};
    const status=$("extractor-status");
    status.textContent="Validating…";
    try{
      const csrf=await fetch("/api/v1/auth/csrf",{cache:"no-store",credentials:"same-origin"});
      if(!csrf.ok)throw new Error("Session unavailable");
      const token=(await csrf.json()).csrf_token;
      const response=await fetch("/api/v1/extractor/options",{method:"POST",credentials:"same-origin",cache:"no-store",
        headers:{"Content-Type":"application/json","X-CSRF-Token":token},body:JSON.stringify(payload)});
      const data=await response.json();
      if(stamp!==revision)return;
      if(!response.ok)throw new Error(Array.isArray(data.detail)?data.detail.map(x=>x.msg).join("; "):"Settings validation failed");
      valid=data.options;$("save-options").disabled=false;status.textContent="Settings valid. No processing job submitted.";
    }catch(err){if(stamp===revision)status.textContent=err.message;}
  });
  $("save-options").addEventListener("click",()=>{
    if(!valid)return;
    const blob=new Blob([JSON.stringify(valid,null,2)],{type:"application/json"});
    const href=URL.createObjectURL(blob), a=document.createElement("a");
    a.href=href;a.download="extractor-options.json";a.click();setTimeout(()=>URL.revokeObjectURL(href),1000);
  });
})();
