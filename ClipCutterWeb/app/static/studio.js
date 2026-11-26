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
 $("result-request").onchange=()=>{const id=$("result-request").value;if(id)showOutputs(id);else{selected=null;++seq;if(kind==="extractor")$("output-controls").hidden=true;$("person-results").replaceChildren();$("output-list").replaceChildren();const video=$("output-preview");video.pause();video.removeAttribute("src");video.load();video.hidden=true;$("output-status").textContent="Select a request.";}};
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
   const drive=refMode.value==="drive",library=refMode.value==="library";
   $("reference-drive").hidden=!drive;$("reference-upload").hidden=drive||library;$("reference-details").hidden=drive||library;$("reference-library-control").hidden=!library;$("reference-library-summary").hidden=!library;
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
   const library=refMode?.value==="library",chosen=library?selectedIdentity:null;
   if(library&&!chosen&&(p.settings.mode==="reference"||p.settings.framing!=="whole")){status.textContent="Choose a reference identity.";return;}
   const fingerprint=JSON.stringify([p,chosen,files.map(f=>[f.name,f.size,f.lastModified])]);
   if(lastPayload!==fingerprint||!key){key=crypto.randomUUID().replaceAll("-","");lastPayload=fingerprint;}
   saving=true;$("save-request").disabled=true;status.textContent="Saving request…";
   try{const r=chosen?await api("/identity-requests","POST",{identity_id:chosen.id,request:{...p,request_id:key}}):files.length?await uploadRequest({...p,request_id:key},files):await api("/requests","POST",{...p,request_id:key});status.textContent="Saved "+r.id.slice(0,8)+" — "+r.message;key=null;refsSelected=[];drawReferences();setView("queue");await refresh();}
   catch(err){status.textContent=err.message;}finally{saving=false;$("save-request").disabled=false;}
 });
 let selectedIdentity=null,libraryItems=[],editingIdentity=null,libraryBusy=false,activeUpload=null,cancelUpload=false;
 function button(label,fn){const b=put("button",label);b.type="button";b.className="studio-secondary";b.onclick=fn;return b;}

 if(kind==="extractor"){
   const dialog=$("identity-dialog"),note=$("identity-status"),grid=$("identity-grid"),images=$("identity-images");
   const value=id=>$(id).value.trim(),selection=()=>[...images.querySelectorAll("input[data-image]:checked")].map(x=>x.value);
   const setNote=x=>note.textContent=x;
   async function loadLibrary(){
     libraryItems=(await api("/identities")).identities;
     if(selectedIdentity){const next=libraryItems.find(x=>x.id===selectedIdentity.id);if(next){selectedIdentity=next;applyChoice(next);}else{selectedIdentity=null;$("reference-identity-label").textContent="Choose identity";$("reference-library-summary").textContent="";}}
     if(editingIdentity&&!libraryItems.some(x=>x.id===editingIdentity))editingIdentity=null;
     drawLibrary();
   }
   function applyChoice(item){
     selectedIdentity=item;$("reference-identity-label").textContent=item.name;
     $("reference-library-summary").textContent=item.images.length+" reference images · "+item.slug+"_###.mp4 naming";
   }
   function drawLibrary(){
     const q=value("identity-search").toLowerCase();grid.replaceChildren();
     for(const item of libraryItems.filter(x=>x.name.toLowerCase().includes(q))){
       const b=button(item.name+" · "+item.images.length+" images",()=>{editingIdentity=item.id;drawLibrary();});
       b.setAttribute("aria-pressed",String(item.id===editingIdentity));grid.append(b);
     }
     const item=libraryItems.find(x=>x.id===editingIdentity);$("identity-editor").hidden=!item;if(!item)return;
     $("identity-selected-name").textContent=item.name+" · "+item.images.length+" / 12 images";
     $("identity-rename-name").value=item.name;$("identity-use").disabled=!item.images.length||libraryBusy;images.replaceChildren();
     for(const image of item.images){
       const tile=put("div","");tile.className="studio-image-tile";
       const pic=document.createElement("img");pic.src="/api/v1/studio/identities/"+item.id+"/images/"+image.id;pic.alt=image.name;pic.loading="lazy";
       const choice=document.createElement("input");choice.type="checkbox";choice.dataset.image="";choice.value=image.id;choice.setAttribute("aria-label","Select "+image.name);
       const name=document.createElement("input");name.value=image.name;name.maxLength=100;name.setAttribute("aria-label","Image name");
       const replacement=document.createElement("input");replacement.type="file";replacement.accept=".jpg,.jpeg,.png,.webp";replacement.hidden=true;
       replacement.onchange=()=>{if(replacement.files.length)uploadFiles([replacement.files[0]],image.id);};
       const tools=put("div","");tools.className="studio-actions";
       tools.append(choice,button("Rename",()=>act(async()=>api("/identities/"+item.id+"/images/"+image.id,"PATCH",{name:name.value}))),button("Replace",()=>replacement.click()),button("Delete",()=>act(async()=>api("/identities/"+item.id+"/images/delete","POST",{ids:[image.id]}))));
       tile.append(pic,name,tools,replacement);images.append(tile);
     }
   }
   async function act(fn){if(libraryBusy)return;libraryBusy=true;setNote("Working…");try{await fn();await loadLibrary();setNote("Saved.");}catch(e){setNote(e.message);}finally{libraryBusy=false;const item=libraryItems.find(x=>x.id===editingIdentity);$("identity-use").disabled=!item?.images.length;}}
   async function multipart(payload,files,onprogress){
     if(!csrf){const r=await fetch("/api/v1/auth/csrf",{cache:"no-store"});if(!r.ok)throw Error("Session unavailable");csrf=(await r.json()).csrf_token;}
     const data=new FormData();data.append("payload",JSON.stringify(payload));files.forEach(f=>data.append("images",f));
     return new Promise((resolve,reject)=>{
       const xhr=new XMLHttpRequest();activeUpload=xhr;xhr.open("POST","/api/v1/studio/requests/upload");xhr.setRequestHeader("X-CSRF-Token",csrf);
       xhr.upload.onprogress=e=>{if(e.lengthComputable)onprogress(Math.round(e.loaded/e.total*100));};
       xhr.onload=()=>{let d;try{d=JSON.parse(xhr.responseText);}catch{d={};}if(xhr.status===201)resolve(d);else{if([401,403].includes(xhr.status))csrf=null;reject(Error(typeof d.detail==="string"?d.detail:"Upload failed ("+xhr.status+")"));}};
       xhr.onerror=()=>reject(Error("Upload interrupted; refresh library"));xhr.onabort=()=>reject(Error("Upload cancelled; refresh library"));xhr.send(data);
     }).finally(()=>{activeUpload=null;});
   }
   async function uploadFiles(files,replaceId=null){
     if(libraryBusy||!editingIdentity||!files.length)return;
     const id=editingIdentity, item=libraryItems.find(x=>x.id===id);
     if(files.length+item.images.length-(replaceId?1:0)>12||files.some(f=>!f.size||f.size>10*1024**2||!/\.(jpe?g|png|webp)$/i.test(f.name))){setNote("Up to 12 images, 10 MiB each.");return;}
     libraryBusy=true;cancelUpload=false;$("identity-use").disabled=true;$("identity-cancel-upload").hidden=false;const progress=$("identity-upload-progress");progress.replaceChildren();
     let done=0,failed=0;
     try{
       for(const file of files){
         if(cancelUpload)break;
         const row=put("div",file.name+" — Waiting");progress.append(row);
         try{await multipart({library_action:"upload",identity_id:id,replace_id:replaceId},[file],pct=>row.textContent=file.name+" — "+pct+"%");row.textContent=file.name+" — Saved";done++;}
         catch(e){row.textContent=file.name+" — "+e.message;failed++;}
       }
       await loadLibrary();setNote(done+" saved · "+failed+" failed"+(cancelUpload?" · Remaining cancelled":""));
     }catch(e){setNote(e.message);}finally{libraryBusy=false;$("identity-cancel-upload").hidden=true;$("identity-files").value="";$("identity-use").disabled=!(libraryItems.find(x=>x.id===editingIdentity)?.images.length);}
   }
   $("reference-library-open").onclick=async()=>{if(saving)return;dialog.showModal();try{await loadLibrary();if(selectedIdentity){editingIdentity=selectedIdentity.id;drawLibrary();}}catch(e){setNote(e.message);}};
   $("identity-close").onclick=()=>dialog.close();
   $("identity-search").oninput=drawLibrary;
   $("identity-refresh").onclick=()=>act(async()=>{});
   $("identity-add").onclick=()=>act(async()=>{const result=await api("/identities","POST",{name:value("identity-new-name")});editingIdentity=result.id;$("identity-new-name").value="";});
   $("identity-rename").onclick=()=>act(async()=>api("/identities/"+editingIdentity,"PATCH",{name:value("identity-rename-name")}));
   $("identity-delete").onclick=()=>act(async()=>{await api("/identities/"+editingIdentity,"DELETE");editingIdentity=null;});
   $("identity-files").onchange=()=>uploadFiles([...$("identity-files").files]);
   $("identity-cancel-upload").onclick=()=>{cancelUpload=true;activeUpload?.abort();};
   $("identity-import").onclick=()=>act(async()=>{setNote("Importing and verifying Drive images…");await multipart({library_action:"import",identity_id:editingIdentity,link:value("identity-drive-link")},[],()=>{});$("identity-drive-link").value="";});
   $("identity-select-all").onclick=()=>images.querySelectorAll("input[data-image]").forEach(x=>x.checked=true);
   $("identity-deselect-all").onclick=()=>images.querySelectorAll("input[data-image]").forEach(x=>x.checked=false);
   $("identity-delete-selected").onclick=()=>act(async()=>{const ids=selection();if(!ids.length)throw Error("Select images first");await api("/identities/"+editingIdentity+"/images/delete","POST",{ids});});
   $("identity-use").onclick=()=>{const item=libraryItems.find(x=>x.id===editingIdentity);if(libraryBusy||!item?.images.length)return;applyChoice(item);dialog.close();};
 }
 function outputSelection(){return [...$("output-list").querySelectorAll("input[data-output]:checked")].map(x=>x.value);}
 async function manageOutput(job,data){
   const note=$("output-status");try{await api("/requests/"+job+"/outputs/manage","POST",data);await showOutputs(job);}catch(e){note.textContent=e.message;}
 }
 async function downloadZip(job){
   const ids=outputSelection(),note=$("output-status");if(!ids.length){note.textContent="Select clips first.";return;}
   try{
     if(!csrf){const r=await fetch("/api/v1/auth/csrf",{cache:"no-store"});if(!r.ok)throw Error("Session unavailable");csrf=(await r.json()).csrf_token;}
     note.textContent="Preparing ZIP…";$("output-zip").disabled=true;
     const r=await fetch("/api/v1/studio/requests/"+job+"/outputs/zip",{method:"POST",headers:{"X-CSRF-Token":csrf,"Content-Type":"application/json"},body:JSON.stringify({ids}),credentials:"same-origin"});
     if(!r.ok){const d=await r.json().catch(()=>({}));throw Error(d.detail||"ZIP unavailable");}
     const url=URL.createObjectURL(await r.blob()),a=put("a","Download");a.href=url;a.download="clips-"+job.slice(0,8)+".zip";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);note.textContent="ZIP prepared.";
   }catch(e){note.textContent=e.message;}finally{$("output-zip").disabled=false;}
 }
 if(kind==="extractor"){
   $("output-select-all").onclick=()=>$("output-list").querySelectorAll("input[data-output]").forEach(x=>x.checked=true);
   $("output-deselect-all").onclick=()=>$("output-list").querySelectorAll("input[data-output]").forEach(x=>x.checked=false);
   $("output-delete-selected").onclick=()=>{const ids=outputSelection();if(selected&&ids.length)manageOutput(selected,{action:"delete",ids});else $("output-status").textContent="Select clips first.";};
   $("output-zip").onclick=()=>{if(selected)downloadZip(selected);};
 }
 async function showOutputs(job){
   selected=job;const stamp=++seq;extras.delete("review-panel");setView("results");
   $("result-request").value=job;$("person-results").replaceChildren();
   const list=$("output-list"), video=$("output-preview");if(kind==="extractor")$("output-controls").hidden=true;
   video.pause();video.removeAttribute("src");video.load();video.hidden=true;list.replaceChildren();$("output-status").textContent="Loading…";
   try{const data=await api("/requests/"+job+"/outputs");if(stamp!==seq)return;
     const clips=data.outputs.filter(f=>f.media_type==="video/mp4"),known=clips.every(f=>Number.isFinite(f.duration_ms));
     $("output-status").textContent=data.outputs.length?(kind==="extractor"?(data.identity?data.identity+" · ":"")+clips.length+" clips"+(known&&clips.length?" · "+(clips.reduce((n,f)=>n+f.duration_ms,0)/1000).toFixed(2)+" seconds":"")+" · ":"")+"Verified files for "+job.slice(0,8):"No verified outputs available for this request.";
     if(kind==="extractor"){$("output-controls").hidden=!clips.length;$("output-delete-selected").disabled=!data.editable;}
     for(const file of data.outputs){const row=put("div","");row.className="studio-output";const id=file.id||file.name;
       if(kind==="extractor"&&file.media_type==="video/mp4"){const check=document.createElement("input");check.type="checkbox";check.dataset.output="";check.value=id;check.setAttribute("aria-label","Select "+file.name);row.append(check);}
       row.append(put("span",file.name+" · "+(file.size/1024**2).toFixed(2)+" MiB"+(Number.isFinite(file.duration_ms)?" · "+(file.duration_ms/1000).toFixed(2)+" s":"")));
       const href="/api/v1/studio/requests/"+job+"/outputs/"+encodeURIComponent(id),a=put("a","Download");a.href=href;row.append(a);
       if(file.media_type==="video/mp4"){
         row.append(button("Preview",()=>{video.src=href+"?preview=true";video.hidden=false;}));
         if(kind==="extractor"&&data.editable){const name=document.createElement("input");name.value=file.name;name.maxLength=128;name.setAttribute("aria-label","Rename clip");row.append(name,button("Rename",()=>manageOutput(job,{action:"rename",ids:[id],name:name.value})),button("Delete",()=>manageOutput(job,{action:"delete",ids:[id]})));}
       }list.append(row);}
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
   extras.add("review-panel");if(kind==="extractor")$("output-controls").hidden=true;setView("results");rows.replaceChildren();note.textContent="Loading scan…";approve.disabled=true;
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
 const deleting=new Set(), deleted=new Set();
 async function refresh(){
   if(refreshing||document.hidden)return;refreshing=true;
   try{const data=await api("/requests?kind="+kind),rows=$("request-rows");rows.replaceChildren();queueState(data.paused);
     const picker=$("result-request"), prior=picker.value;let complete=data.requests.filter(j=>j.state==="completed"&&!deleted.has(j.id));
     if(kind==="extractor"){const filter=$("output-identity-filter"),old=filter.value;filter.replaceChildren(new Option("All identities",""));for(const [id,name] of new Map(complete.filter(j=>j.identity_id).map(j=>[j.identity_id,j.identity_name])).entries())filter.add(new Option(name,id));if([...filter.options].some(o=>o.value===old))filter.value=old;if(filter.value)complete=complete.filter(j=>j.identity_id===filter.value);}
     picker.replaceChildren(new Option("Select a request",""));for(const job of complete)picker.add(new Option((job.identity_name?job.identity_name+" · ":"")+job.id.slice(0,8),job.id));if([...picker.options].some(o=>o.value===prior))picker.value=prior;
     if(!data.requests.some(item=>!deleted.has(item.id))){const tr=document.createElement("tr"),td=put("td","No requests yet.");td.colSpan=5;tr.append(td);rows.append(tr);}
     for(const job of data.requests.filter(item=>!deleted.has(item.id))){const tr=document.createElement("tr");tr.dataset.requestId=job.id;
       [job.id.slice(0,8),job.state.replaceAll("_"," "),job.progress===null?"—":job.progress+"%",job.message].forEach(t=>tr.append(put("td",t)));
       const actions=document.createElement("td");actions.append(button("Outputs",()=>showOutputs(job.id)));
       if(job.state==="batch_expanded")actions.append(button("Batch videos",()=>showBatch(job.id)));
       if(job.state==="review")actions.append(button("Review ranges",()=>showReview(job.id)));
       if(job.state==="failed"&&(job.message.startsWith("Drive intake:")||job.message.startsWith("YouTube intake:")))actions.append(button("Retry intake",async()=>{try{await api("/requests/"+job.id+"/intake","POST");status.textContent="Input intake requested";await refresh();}catch(err){status.textContent=err.message;}}));
       if(["awaiting_input","ready","failed","cancelled","completed"].includes(job.state)){
         const remove=button(deleting.has(job.id)?"Deleting…":"Delete",async()=>{
           if(deleting.has(job.id)||deleted.has(job.id))return;
           deleting.add(job.id);remove.disabled=true;remove.textContent="Deleting…";
           try{
             await api("/requests/"+job.id,"DELETE");
             deleted.add(job.id);
             // Remove only after the server accepts deletion, including during a concurrent refresh.
             $("request-rows").querySelectorAll("tr[data-request-id]").forEach(row=>{if(row.dataset.requestId===job.id)row.remove();});
             for(const option of [...$("result-request").options])if(option.value===job.id)option.remove();
             if(selected===job.id){selected=null;++seq;$("person-results").replaceChildren();$("output-list").replaceChildren();$("output-preview").pause();$("output-preview").removeAttribute("src");$("output-preview").load();$("output-preview").hidden=true;$("output-status").textContent="Request deleted.";}
             status.textContent="Request deleted.";await refresh();
           }catch(err){status.textContent=err.message;remove.disabled=false;remove.textContent="Delete";}
           finally{deleting.delete(job.id);if(!deleted.has(job.id))await refresh();}
         });
         remove.disabled=deleting.has(job.id);actions.append(remove);
       }
       if(job.state==="awaiting_input")actions.append(button("Cancel",async()=>{try{await api("/requests/"+job.id+"/cancel","POST");await refresh();if(selected===job.id)await showOutputs(job.id);}catch(err){status.textContent=err.message;}}));
       tr.append(actions);rows.append(tr);}
   }catch(err){status.textContent="Refresh failed: "+err.message;}finally{refreshing=false;}
 }
 let queueBusy=false;
 function queueState(paused){$("queue-status").textContent=paused?"Paused":"Active";$("queue-pause").disabled=queueBusy||paused;$("queue-resume").disabled=queueBusy||!paused;}
 async function queueCommand(action){if(queueBusy)return;queueBusy=true;$("queue-pause").disabled=$("queue-resume").disabled=true;try{const data=await api("/queue/"+action,"POST");queueBusy=false;queueState(data.paused);status.textContent=data.paused?"Queue paused; active work may finish.":"Queue resumed";}catch(err){status.textContent=err.message;}finally{queueBusy=false;await refresh();}}
 $("queue-pause").onclick=()=>queueCommand("pause");$("queue-resume").onclick=()=>queueCommand("resume");
 if(kind==="extractor")$("output-identity-filter").onchange=()=>{selected=null;++seq;$("output-list").replaceChildren();$("output-controls").hidden=true;$("output-preview").pause();$("output-preview").hidden=true;$("result-request").value="";refresh();};
 setView("new");
 refresh();const timer=setInterval(refresh,10000);window.addEventListener("pagehide",()=>clearInterval(timer),{once:true});
})();
