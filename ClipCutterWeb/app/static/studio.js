(() => {
 const $=id=>document.getElementById(id), root=$("studio"), form=$("studio-form"), kind=root.dataset.kind;
 let csrf=null, key=null, lastPayload=null, saving=false, refreshing=false, selected=null, seq=0, refsSelected=[], previewUrls=[];
 const status=$("studio-status");
 const extras=new Set();
 form.addEventListener("invalid",e=>{const section=e.target.closest("details");if(section)section.open=true;},true);
 function setView(view){
   root.querySelectorAll("[data-view]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.view===view)));
   root.querySelectorAll("[data-panel]").forEach(p=>p.hidden=p.dataset.panel!==view||(p.hasAttribute("data-extra")&&!extras.has(p.id)));
   if(view!=="results")$("output-preview").pause();
 }
 root.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>setView(b.dataset.view));
 $("result-request").onchange=()=>{const id=$("result-request").value;if(id)showOutputs(id);else{selected=null;++seq;$("person-results").replaceChildren();$("output-list").replaceChildren();const video=$("output-preview");video.pause();video.removeAttribute("src");video.load();video.hidden=true;$("output-status").textContent="Select a request.";}};
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
   const sync=()=>{const manual=mode.value==="manual";$("manual-ranges").hidden=!manual;refs.required=form.elements.reference_mode.value==="drive"&&(!manual||form.elements.framing.value!=="whole");$("range-list").querySelectorAll("input").forEach(i=>i.disabled=!manual);form.elements.minimum.disabled=form.elements.maximum.disabled=!strict.checked;};
   $("add-range").onclick=()=>fields($("range-list"),["Start (s)","End (s)"],[0,2],1000);
   $("add-range").click();mode.onchange=sync;form.elements.framing.onchange=sync;strict.onchange=sync;sync();
 }else $("add-region").onclick=()=>fields($("region-list"),["X","Y","Width","Height"],[0,0,.25,.25],32);
 function syncSource(){
   let yt=false;try{yt=["www.youtube.com","youtube.com","m.youtube.com","youtu.be"].includes(new URL(form.elements.source.value.trim()).hostname);}catch{}
   if(kind==="extractor"){
     const audio=form.elements.include_audio;
     if(yt)audio.value="false";
     audio.disabled=yt;
   }
 }
 form.elements.source.addEventListener("input",syncSource);syncSource();
 const refMode=form.elements.reference_mode, fileInput=$("reference-files");
 function syncReferences(){
   const drive=refMode.value==="drive";
   $("reference-drive").hidden=!drive;$("reference-upload").hidden=drive;$("reference-details").hidden=drive;
   form.elements.reference_link.disabled=!drive;
   form.elements.reference_link.required=drive&&kind==="extractor"&&(form.elements.mode.value!=="manual"||form.elements.framing.value!=="whole");
 }
 if(refMode){refMode.onchange=syncReferences;syncReferences();$("reference-browse").onclick=()=>{if(!saving)fileInput.click();};}
 function drawReferences(){
   if(!fileInput)return;
   $("reference-count").textContent=refsSelected.length?refsSelected.length+" image"+(refsSelected.length===1?"":"s")+" selected":"Choose images";
   previewUrls.forEach(URL.revokeObjectURL);previewUrls=[];$("reference-preview").replaceChildren();
   refsSelected.forEach((file,i)=>{
     const row=put("div","");const img=document.createElement("img");img.width=44;img.height=44;img.style.objectFit="cover";
     img.src=URL.createObjectURL(file);previewUrls.push(img.src);
     row.append(img,put("span",file.name),button("Remove",()=>{if(saving)return;refsSelected.splice(i,1);drawReferences();}));$("reference-preview").append(row);
   });
 }
 if(fileInput)fileInput.onchange=()=>{
   const files=[...refsSelected,...fileInput.files];fileInput.value="";
   if(files.length>12||files.some(f=>!f.size||f.size>10*1024**2||!/\.(jpe?g|png|webp)$/i.test(f.name))||files.reduce((n,f)=>n+f.size,0)>120*1024**2){status.textContent="Choose up to 12 JPG, PNG or WEBP images, 10 MiB each, 120 MiB total.";return;}
   refsSelected=files;drawReferences();status.textContent="";
 };
 async function uploadRequest(p,files){
   if(!csrf){const r=await fetch("/api/v1/auth/csrf",{cache:"no-store"});if(!r.ok)throw Error("Session unavailable");csrf=(await r.json()).csrf_token;}
   const body=new FormData();body.append("payload",JSON.stringify(p));files.forEach(f=>body.append("images",f));
   return new Promise((resolve,reject)=>{
     const xhr=new XMLHttpRequest();xhr.open("POST","/api/v1/studio/requests/upload");xhr.setRequestHeader("X-CSRF-Token",csrf);xhr.setRequestHeader("Accept","application/json");
     xhr.upload.onprogress=e=>{if(e.lengthComputable)status.textContent="Uploading references: "+Math.round(e.loaded/e.total*100)+"%";};
     xhr.onload=()=>{let data;try{data=JSON.parse(xhr.responseText);}catch{data={};}if(xhr.status===201)resolve(data);else{if([401,403].includes(xhr.status))csrf=null;reject(Error(typeof data.detail==="string"?data.detail:"Upload failed ("+xhr.status+")"));}};
     xhr.onerror=()=>reject(Error("Reference upload interrupted"));xhr.send(body);
   });
 }
 function payload(){
   const f=new FormData(form), get=k=>f.get(k), num=k=>Number(get(k)), bool=k=>get(k)==="true", opt=k=>String(get(k)||"").trim()||null;
   const input={source:String(get("source")).trim(),source_kind:"auto",output_folder:opt("output_folder")};
   let settings={kind,reference_link:refMode?.value==="drive"?opt("reference_link"):null};
   if(kind==="extractor")Object.assign(settings,{mode:get("mode"),threshold:num("threshold"),scan_quality:get("scan_quality"),cut_mode:get("cut_mode"),stitched:bool("stitched"),include_audio:form.elements.include_audio.disabled?false:bool("include_audio"),quality:num("quality"),max_short_side:num("max_short_side"),framing:get("framing"),ranges:get("mode")==="manual"?values("range-list").map(([a,b])=>({start_ms:Math.round(a*1000),end_ms:Math.round(b*1000)})):[],minimum_ms:$("strict-limits").checked?Math.round(num("minimum")*1000):null,maximum_ms:$("strict-limits").checked?Math.round(num("maximum")*1000):null});
   else Object.assign(settings,{sample_interval_ms:num("sample_interval_ms"),similarity_threshold:num("similarity_threshold"),ignore_background_faces:form.elements.ignore_background_faces.checked,ignore_static_faces:form.elements.ignore_static_faces.checked,ignore_regions:values("region-list").map(([x,y,w,h])=>({x,y,w,h}))});
   return {input,settings};
 }
 form.addEventListener("submit",async e=>{
   e.preventDefault();if(saving)return;
   const p=payload(), files=refMode?.value==="upload"?[...refsSelected]:[];
   if(refMode?.value==="upload"&&kind==="extractor"&&(p.settings.mode==="reference"||p.settings.framing!=="whole")&&!files.length){status.textContent="Select reference images.";return;}
   const fingerprint=JSON.stringify([p,files.map(f=>[f.name,f.size,f.lastModified])]);
   if(lastPayload!==fingerprint||!key){key=crypto.randomUUID().replaceAll("-","");lastPayload=fingerprint;}
   saving=true;$("save-request").disabled=true;status.textContent="Saving request…";
   try{const r=files.length?await uploadRequest({...p,request_id:key},files):await api("/requests","POST",{...p,request_id:key});status.textContent="Saved "+r.id.slice(0,8)+" — "+r.message;key=null;refsSelected=[];drawReferences();setView("queue");await refresh();}
   catch(err){status.textContent=err.message;}finally{saving=false;$("save-request").disabled=false;}
 });
 function button(label,fn){const b=put("button",label);b.type="button";b.className="studio-secondary";b.onclick=fn;return b;}
 async function showOutputs(job){
   selected=job;const stamp=++seq;extras.delete("review-panel");setView("results");
   $("result-request").value=job;$("person-results").replaceChildren();
   const list=$("output-list"), video=$("output-preview");
   video.pause();video.removeAttribute("src");video.load();video.hidden=true;list.replaceChildren();$("output-status").textContent="Loading…";
   try{const data=await api("/requests/"+job+"/outputs");if(stamp!==seq)return;
     $("output-status").textContent=data.outputs.length?"Verified files for "+job.slice(0,8):"No verified outputs available for this request.";
     for(const file of data.outputs){const row=put("div","");row.className="studio-output";row.append(put("span",file.name+" · "+file.size+" bytes"));
       const href="/api/v1/studio/requests/"+job+"/outputs/"+encodeURIComponent(file.name),a=put("a","Download");a.href=href;row.append(a);
       if(file.media_type==="video/mp4")row.append(button("Preview",()=>{video.src=href+"?preview=true";video.hidden=false;}));list.append(row);}
     if(kind==="analyzer"&&data.outputs.some(f=>f.name==="analysis.json"))await showPeople(job,stamp);
   }catch(err){if(stamp===seq)$("output-status").textContent=err.message;}
 }
 async function showPeople(job,stamp){
   const pane=$("person-results");
   try{
     const r=await fetch("/api/v1/studio/requests/"+job+"/outputs/analysis.json",{credentials:"same-origin",cache:"no-store"});
     if(!r.ok)throw Error("Analysis summary unavailable");
     const data=await r.json();if(stamp!==seq)return;
     if(!Array.isArray(data.people))throw Error("Invalid analysis summary");
     pane.append(put("h3","Detected persons: "+data.people.filter(p=>!p.filtered).length));
     if(!data.people.length)pane.append(put("p","No persons detected."));
     for(const p of data.people){
       const segs=Array.isArray(p.segments)?p.segments.filter(x=>Array.isArray(x)&&x.length===2&&x.every(Number.isFinite)&&x[1]>=x[0]):[];
       const duration=segs.reduce((n,x)=>n+x[1]-x[0],0);
       const row=put("div","");row.className="studio-output";
       row.append(put("strong",String(p.name||p.id||"Person")),put("span",p.filtered?"Filtered":"Appearance: "+duration.toFixed(2)+" s"),put("span",segs.length+" ranges"));
       if(segs.length){const detail=document.createElement("details");detail.append(put("summary","Appearance ranges"));for(const [a,b] of segs)detail.append(put("div",a.toFixed(2)+" – "+b.toFixed(2)+" s"));row.append(detail);}
       pane.append(row);
     }
   }catch(e){if(stamp===seq)pane.textContent=e.message;}
 }
 async function showReview(job){
   const pane=$("review-panel"), rows=$("review-ranges"), note=$("review-status"), approve=$("review-approve");
   selected=null;$("result-request").value="";$("person-results").replaceChildren();$("output-list").replaceChildren();const video=$("output-preview");video.pause();video.removeAttribute("src");video.load();video.hidden=true;$("output-status").textContent="Select a completed request to inspect its outputs.";
   extras.add("review-panel");setView("results");rows.replaceChildren();note.textContent="Loading scan…";approve.disabled=true;
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
   const pane=$("batch-panel"), rows=$("batch-members");extras.add("batch-panel");setView("queue");rows.replaceChildren();
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
     const picker=$("result-request"), prior=picker.value;picker.replaceChildren(new Option("Select a request",""));for(const job of data.requests.filter(j=>j.state==="completed"))picker.add(new Option(job.id.slice(0,8),job.id));if([...picker.options].some(o=>o.value===prior))picker.value=prior;
     if(!data.requests.length){const tr=document.createElement("tr"),td=put("td","No requests yet.");td.colSpan=5;tr.append(td);rows.append(tr);}
     for(const job of data.requests){const tr=document.createElement("tr");
       [job.id.slice(0,8),job.state.replaceAll("_"," "),job.progress===null?"—":job.progress+"%",job.message].forEach(t=>tr.append(put("td",t)));
       const actions=document.createElement("td");actions.append(button("Outputs",()=>showOutputs(job.id)));
       if(job.state==="batch_expanded")actions.append(button("Batch videos",()=>showBatch(job.id)));
       if(job.state==="review")actions.append(button("Review ranges",()=>showReview(job.id)));
       if(job.state==="awaiting_input"||job.state==="staging"||(job.state==="failed"&&(job.message.startsWith("Drive intake:")||job.message.startsWith("YouTube intake:"))))actions.append(button(job.state==="awaiting_input"?"Download input":"Retry intake",async()=>{try{await api("/requests/"+job.id+"/intake","POST");status.textContent="Input intake requested";await refresh();}catch(err){status.textContent=err.message;}}));
       if(["awaiting_input","ready","failed","cancelled","completed"].includes(job.state))actions.append(button("Delete",async()=>{if(!confirm("Delete this request from the queue? Active GPU attempts cannot be deleted."))return;try{await api("/requests/"+job.id,"DELETE");if(selected===job.id){selected=null;++seq;$("person-results").replaceChildren();$( "output-list").replaceChildren();$("output-preview").pause();$("output-preview").removeAttribute("src");$("output-preview").load();$("output-preview").hidden=true;$("output-status").textContent="Request deleted.";}await refresh();}catch(err){status.textContent=err.message;}}));
       if(job.state==="awaiting_input")actions.append(button("Cancel",async()=>{try{await api("/requests/"+job.id+"/cancel","POST");await refresh();if(selected===job.id)await showOutputs(job.id);}catch(err){status.textContent=err.message;}}));
       tr.append(actions);rows.append(tr);}
   }catch(err){status.textContent="Refresh failed: "+err.message;}finally{refreshing=false;}
 }
 $("refresh-requests").onclick=refresh;
 setView("new");
 refresh();const timer=setInterval(refresh,10000);window.addEventListener("pagehide",()=>clearInterval(timer),{once:true});
})();
