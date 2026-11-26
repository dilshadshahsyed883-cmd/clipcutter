(() => {
 const $=id=>document.getElementById(id), root=$("studio"), form=$("studio-form"), kind=root.dataset.kind;
 let csrf=null, key=null, lastPayload=null, saving=false, refreshing=false, selected=null, seq=0;
 const status=$("studio-status");
 const put=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};
 async function api(path,method="GET",body){
   const headers={Accept:"application/json"};
   if(method!=="GET"){
     if(!csrf){const r=await fetch("/api/v1/auth/csrf",{cache:"no-store"});if(!r.ok)throw Error("Session unavailable");csrf=(await r.json()).csrf_token;}
     headers["X-CSRF-Token"]=csrf;headers["Content-Type"]="application/json";
   }
   const r=await fetch("/api/v1/studio"+path,{method,headers,credentials:"same-origin",cache:"no-store",body:body===undefined?undefined:JSON.stringify(body)});
   if(!r.ok){if(r.status===401||r.status===403)csrf=null;const b=await r.json().catch(()=>({}));throw Error(Array.isArray(b.detail)?b.detail.map(x=>x.msg).join("; "):b.detail||"Request failed ("+r.status+")");}
   return r.json();
 }
 function fields(parent,labels,defaults,max){
   if(parent.children.length>=max)return;
   const row=document.createElement("div");row.className="studio-fields";
   labels.forEach((text,i)=>{const label=put("label",text),input=document.createElement("input");input.type="number";input.min="0";input.step=".001";input.required=true;input.value=defaults[i];label.append(input);row.append(label);});
   const remove=put("button","Remove");remove.type="button";remove.className="studio-secondary";remove.onclick=()=>row.remove();row.append(remove);parent.append(row);
 }
 const values=id=>Array.from($(id).children).map(r=>Array.from(r.querySelectorAll("input")).map(i=>Number(i.value)));
 if(kind==="extractor"){
   const mode=form.elements.mode, refs=form.elements.reference_link, strict=$("strict-limits");
   const sync=()=>{const manual=mode.value==="manual";$("manual-ranges").hidden=!manual;refs.required=!manual||form.elements.framing.value!=="whole";$("range-list").querySelectorAll("input").forEach(i=>i.disabled=!manual);form.elements.minimum.disabled=form.elements.maximum.disabled=!strict.checked;};
   $("add-range").onclick=()=>fields($("range-list"),["Start (s)","End (s)"],[0,2],1000);
   $("add-range").click();mode.onchange=sync;form.elements.framing.onchange=sync;strict.onchange=sync;sync();
 }else $("add-region").onclick=()=>fields($("region-list"),["X","Y","Width","Height"],[0,0,.25,.25],32);
 function payload(){
   const f=new FormData(form), get=k=>f.get(k), num=k=>Number(get(k)), bool=k=>get(k)==="true", opt=k=>String(get(k)||"").trim()||null;
   const input={source:String(get("source")).trim(),source_kind:get("source_kind"),output_folder:opt("output_folder")};
   let settings={kind,reference_link:opt("reference_link")};
   if(kind==="extractor")Object.assign(settings,{mode:get("mode"),threshold:num("threshold"),scan_quality:get("scan_quality"),cut_mode:get("cut_mode"),stitched:bool("stitched"),include_audio:bool("include_audio"),quality:num("quality"),max_short_side:num("max_short_side"),framing:get("framing"),ranges:get("mode")==="manual"?values("range-list").map(([a,b])=>({start_ms:Math.round(a*1000),end_ms:Math.round(b*1000)})):[],minimum_ms:$("strict-limits").checked?Math.round(num("minimum")*1000):null,maximum_ms:$("strict-limits").checked?Math.round(num("maximum")*1000):null});
   else Object.assign(settings,{sample_interval_ms:num("sample_interval_ms"),similarity_threshold:num("similarity_threshold"),ignore_background_faces:form.elements.ignore_background_faces.checked,ignore_static_faces:form.elements.ignore_static_faces.checked,ignore_regions:values("region-list").map(([x,y,w,h])=>({x,y,w,h}))});
   return {input,settings};
 }
 form.addEventListener("submit",async e=>{
   e.preventDefault();if(saving)return;
   const p=payload(), fingerprint=JSON.stringify(p);
   if(lastPayload!==fingerprint||!key){key=crypto.randomUUID().replaceAll("-","");lastPayload=fingerprint;}
   saving=true;$("save-request").disabled=true;status.textContent="Saving request…";
   try{const r=await api("/requests","POST",{...p,request_id:key});status.textContent="Saved "+r.id.slice(0,8)+" — "+r.message;key=null;await refresh();}
   catch(err){status.textContent=err.message;}finally{saving=false;$("save-request").disabled=false;}
 });
 function button(label,fn){const b=put("button",label);b.type="button";b.className="studio-secondary";b.onclick=fn;return b;}
 async function showOutputs(job){
   selected=job;const stamp=++seq;
   const list=$("output-list"), video=$("output-preview");
   video.pause();video.removeAttribute("src");video.load();video.hidden=true;list.replaceChildren();$("output-status").textContent="Loading…";
   try{const data=await api("/requests/"+job+"/outputs");if(stamp!==seq)return;
     $("output-status").textContent=data.outputs.length?"Verified files for "+job.slice(0,8):"No verified outputs available for this request.";
     for(const file of data.outputs){const row=put("div","");row.className="studio-output";row.append(put("span",file.name+" · "+file.size+" bytes"));
       const href="/api/v1/studio/requests/"+job+"/outputs/"+encodeURIComponent(file.name),a=put("a","Download");a.href=href;row.append(a);
       if(file.media_type==="video/mp4")row.append(button("Preview",()=>{video.src=href+"?preview=true";video.hidden=false;}));list.append(row);}
   }catch(err){if(stamp===seq)$("output-status").textContent=err.message;}
 }
 async function showReview(job){
   const pane=$("review-panel"), rows=$("review-ranges"), note=$("review-status"), approve=$("review-approve");
   pane.hidden=false;rows.replaceChildren();note.textContent="Loading scan…";approve.disabled=true;
   const stamp=++seq;
   try{
     const data=await api("/requests/"+job+"/review");if(stamp!==seq)return;
     note.textContent="Source duration: "+(data.duration_ms/1000)+" s. Review the start/end times. "+(data.ready_for_approval?"":"Waiting for verified scan acknowledgement.");
     for(const r of data.ranges)fields(rows,["Start (s)","End (s)"],[r.start_ms/1000,r.end_ms/1000],1000);
     $("review-add").onclick=()=>fields(rows,["Start (s)","End (s)"],[0,Math.min(2,data.duration_ms/1000)],1000);
     approve.disabled=!data.ready_for_approval;
     approve.onclick=async()=>{
       approve.disabled=true;
       try{
         const ranges=values("review-ranges").map(([a,b])=>({start_ms:Math.round(a*1000),end_ms:Math.round(b*1000)}));
         if(!ranges.length||ranges.some(r=>!Number.isFinite(r.start_ms)||!Number.isFinite(r.end_ms)||r.start_ms<0||r.end_ms<=r.start_ms||r.end_ms>data.duration_ms))throw Error("Enter valid source ranges");
         await api("/requests/"+job+"/review","POST",{scan_sha256:data.scan_sha256,ranges});
         note.textContent="Approved; export queued.";await refresh();
       }catch(e){note.textContent=e.message;approve.disabled=false;}
     };
   }catch(e){note.textContent=e.message;}
 }
 async function showBatch(job){
   const pane=$("batch-panel"), rows=$("batch-members");pane.hidden=false;rows.replaceChildren();
   try{
     const data=await api("/requests/"+job+"/batch");
     for(const member of data.requests){
       const row=put("div","");row.className="studio-output";
       row.append(put("span",member.ordinal+". "+member.label+" — "+member.state));
       row.append(button("Outputs",()=>showOutputs(member.id)));
       if(member.state==="review")row.append(button("Review",()=>showReview(member.id)));
       rows.append(row);
     }
   }catch(e){rows.textContent=e.message;}
 }
 async function refresh(){
   if(refreshing||document.hidden)return;refreshing=true;
   try{const data=await api("/requests?kind="+kind),rows=$("request-rows");rows.replaceChildren();
     if(!data.requests.length){const tr=document.createElement("tr"),td=put("td","No requests yet.");td.colSpan=5;tr.append(td);rows.append(tr);}
     for(const job of data.requests){const tr=document.createElement("tr");
       [job.id.slice(0,8),job.state.replaceAll("_"," "),job.progress===null?"—":job.progress+"%",job.message].forEach(t=>tr.append(put("td",t)));
       const actions=document.createElement("td");actions.append(button("Outputs",()=>showOutputs(job.id)));
       if(job.state==="batch_expanded")actions.append(button("Batch videos",()=>showBatch(job.id)));
       if(job.state==="review")actions.append(button("Review ranges",()=>showReview(job.id)));
       if(job.state==="awaiting_input"||job.state==="staging"||(job.state==="failed"&&job.message.startsWith("Drive intake:")))actions.append(button(job.state==="awaiting_input"?"Download input":"Retry intake",async()=>{try{await api("/requests/"+job.id+"/intake","POST");status.textContent="Drive intake requested";await refresh();}catch(err){status.textContent=err.message;}}));
       if(job.state==="awaiting_input")actions.append(button("Cancel",async()=>{try{await api("/requests/"+job.id+"/cancel","POST");await refresh();if(selected===job.id)await showOutputs(job.id);}catch(err){status.textContent=err.message;}}));
       tr.append(actions);rows.append(tr);}
   }catch(err){status.textContent="Refresh failed: "+err.message;}finally{refreshing=false;}
 }
 $("refresh-requests").onclick=refresh;
 api("/capabilities").then(d=>$("studio-capabilities").textContent=d.message).catch(e=>$("studio-capabilities").textContent=e.message);
 refresh();const timer=setInterval(refresh,10000);window.addEventListener("pagehide",()=>clearInterval(timer),{once:true});
})();
