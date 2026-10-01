const moods = ["😔","😕","😐","🙂","😊","😄","🤩"];
let entries = [];
let selectedMood = 4;
let selectedPhoto = null;
let calendarDate = new Date();

const $ = id => document.getElementById(id);
const api = async (url, options={}) => {
  const r = await fetch(url, options);
  if(!r.ok){ let msg="Something went wrong"; try{msg=(await r.json()).detail||msg}catch{}; throw new Error(msg)}
  return r.json();
};

function todayISO(){
  const d=new Date(), off=d.getTimezoneOffset();
  return new Date(d.getTime()-off*60000).toISOString().slice(0,10);
}
function moodEmoji(n){return moods[Math.max(1,Math.min(7,n))-1]}
function formatDate(s){return new Date(s+"T12:00:00").toLocaleDateString(undefined,{weekday:"long",month:"long",day:"numeric",year:"numeric"})}
function formatTime(s){return new Date(s).toLocaleTimeString(undefined,{hour:"numeric",minute:"2-digit"})}

function renderMoodPicker(){
  $("moodPicker").innerHTML=moods.map((m,i)=>`<button class="mood-btn ${selectedMood===i+1?"selected":""}" data-mood="${i+1}">${m}</button>`).join("");
  document.querySelectorAll(".mood-btn").forEach(b=>b.onclick=()=>{selectedMood=+b.dataset.mood;renderMoodPicker()});
}
function resetComposer(){
  $("entryTitle").value=""; $("entryContent").value=""; $("entryDate").value=todayISO();
  $("themeSelect").value="auto"; $("lockToggle").checked=false; selectedMood=4; selectedPhoto=null;
  $("photoInput").value=""; $("photoPreview").classList.add("hidden"); renderMoodPicker();
}
async function load(){
  entries=await api("/api/entries");
  $("entryCount").textContent=`${entries.length} ${entries.length===1?"entry":"entries"}`;
  const stats=await api("/api/stats"); $("daysStat").textContent=stats.days; renderEntries(); renderMoodDashboard(stats);
}
function renderEntries(){
  if(!entries.length){$("entries").innerHTML='<div class="empty">Your pages are waiting for their first story.<br><br>Start with something small.</div>';return}
  $("entries").innerHTML=entries.map(e=>{
    if(e.locked) return `<article class="entry locked-entry"><span class="mood-chip">🔒</span><strong>Locked entry</strong><span>${formatDate(e.entry_date)} · ${formatTime(e.created_at)}</span><button class="primary small unlock-btn" data-id="${e.id}" style="margin-top:12px">Unlock</button></article>`;
    const safeTitle=escapeHtml(e.title||"Untitled day");
    return `<article class="entry">
      <div class="entry-top"><div><div class="entry-date">${formatDate(e.entry_date)} · ${formatTime(e.created_at)}</div><h3>${safeTitle}</h3></div><span class="mood-chip">${moodEmoji(e.mood)}</span></div>
      ${e.photo_path?`<img class="entry-photo" src="${e.photo_path}" alt="Diary photo">`:""}
      <p>${escapeHtml(e.content)}</p>
      <div class="entry-actions"><button class="text-btn delete-btn" data-id="${e.id}">Delete</button></div>
    </article>`
  }).join("");
  document.querySelectorAll(".delete-btn").forEach(b=>b.onclick=()=>deleteEntry(b.dataset.id));
  document.querySelectorAll(".unlock-btn").forEach(b=>b.onclick=()=>openUnlock(b.dataset.id));
}
function escapeHtml(s){return s.replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]))}

async function save(){
  const content=$("entryContent").value.trim();
  if(!content){$("entryContent").focus();return}
  const fd=new FormData();
  fd.append("title",$("entryTitle").value);
  fd.append("content",content); fd.append("entry_date",$("entryDate").value||todayISO());
  fd.append("mood",selectedMood); fd.append("theme",$("themeSelect").value);
  if($("lockToggle").checked){
    const password=prompt("Set a password for this entry:");
    if(!password){return}
    fd.append("password",password);
  }
  if(selectedPhoto)fd.append("photo",selectedPhoto);
  $("saveBtn").disabled=true;
  try{await api("/api/entries",{method:"POST",body:fd});resetComposer();await load();window.scrollTo({top:0,behavior:"smooth"})}
  catch(e){alert(e.message)} finally{$("saveBtn").disabled=false}
}

async function deleteEntry(id){
  if(!confirm("Delete this diary entry? This cannot be undone."))return;
  await api("/api/entries/"+id,{method:"DELETE"}); await load();
}
function openUnlock(id){
  $("modalContent").innerHTML=`<h2>🔒 Private page</h2><p>This entry is protected by a password.</p><input id="unlockPass" type="password" placeholder="Password"><button id="unlockSubmit" class="primary" style="width:100%">Unlock entry</button>`;
  $("modal").classList.remove("hidden"); $("unlockPass").focus();
  $("unlockSubmit").onclick=async()=>{
    try{
      const e=await api("/api/entries/"+id+"/unlock",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:$("unlockPass").value})});
      $("modalContent").innerHTML=`<h2>${escapeHtml(e.title||"Untitled")}</h2><p>${formatDate(e.entry_date)} · ${formatTime(e.created_at)}</p>${e.photo_path?`<img class="entry-photo" src="${e.photo_path}">`:""}<p style="white-space:pre-wrap;font:16px/1.8 'Playfair Display'">${escapeHtml(e.content)}</p>`;
    }catch(err){alert(err.message)}
  }
}

async function renderCalendar(){
  const y=calendarDate.getFullYear(),m=calendarDate.getMonth()+1;
  $("calendarTitle").textContent=calendarDate.toLocaleDateString(undefined,{month:"long",year:"numeric"});
  const data=await api(`/api/calendar/${y}/${m}`);
  const map=Object.fromEntries(data.map(x=>[x.entry_date,x]));
  const first=new Date(y,m-1,1), days=new Date(y,m,0).getDate();
  let monday=(first.getDay()+6)%7, html="";
  for(let i=0;i<monday;i++)html+="<div></div>";
  for(let d=1;d<=days;d++){
    const iso=`${y}-${String(m).padStart(2,"0")}-${String(d).padStart(2,"0")}`, item=map[iso];
    const today=iso===todayISO();
    html+=`<div class="cal-day ${item?"written":""} ${today?"today":""}"><span>${d}</span>${item?`<span class="mood">${moodEmoji(item.mood)}</span>`:""}</div>`;
  }
  $("calendarGrid").innerHTML=html;
}
function renderMoodDashboard(stats){
  $("moodEntries").textContent=stats.entries;
  const counts=Object.fromEntries(stats.moods.map(x=>[x.mood,x.c]));
  const max=Math.max(1,...Object.values(counts));
  $("moodBars").innerHTML=moods.map((m,i)=>`<div class="bar-row"><span>${m}</span><div class="bar-track"><div class="bar-fill" style="width:${((counts[i+1]||0)/max)*100}%"></div></div><span>${counts[i+1]||0}</span></div>`).join("");
}

function setView(view){
  document.querySelectorAll(".view").forEach(x=>x.classList.add("hidden"));
  $(`${view}View`).classList.remove("hidden");
  document.querySelectorAll(".nav-btn").forEach(b=>b.classList.toggle("active",b.dataset.view===view));
  if(view==="calendar")renderCalendar();
  if(view==="mood")api("/api/stats").then(renderMoodDashboard);
  window.scrollTo({top:0,behavior:"smooth"});
}

$("todayLabel").textContent=new Date().toLocaleDateString(undefined,{weekday:"long",month:"long",day:"numeric"});
$("entryDate").value=todayISO(); renderMoodPicker(); load();
document.querySelectorAll(".nav-btn").forEach(b=>b.onclick=()=>setView(b.dataset.view));
$("newBtn").onclick=()=>{setView("journal");resetComposer();$("entryContent").focus()};
$("saveBtn").onclick=save;
$("entryContent").addEventListener("keydown",e=>{if((e.ctrlKey||e.metaKey)&&e.key==="Enter")save()});
$("photoInput").onchange=e=>{selectedPhoto=e.target.files[0];if(selectedPhoto){$("previewImg").src=URL.createObjectURL(selectedPhoto);$("photoPreview").classList.remove("hidden")}};
$("removePhoto").onclick=()=>{selectedPhoto=null;$("photoInput").value="";$("photoPreview").classList.add("hidden")};
$("prevMonth").onclick=()=>{calendarDate.setMonth(calendarDate.getMonth()-1);renderCalendar()};
$("nextMonth").onclick=()=>{calendarDate.setMonth(calendarDate.getMonth()+1);renderCalendar()};
$("modalClose").onclick=()=>$("modal").classList.add("hidden");
$("modal").onclick=e=>{if(e.target.id==="modal")$("modal").classList.add("hidden")};
$("themeToggle").onclick=()=>{
  const dark=document.body.dataset.theme!=="dark";document.body.dataset.theme=dark?"dark":"light";
  localStorage.setItem("diary-theme",document.body.dataset.theme);
};
document.body.dataset.theme=localStorage.getItem("diary-theme")||"light";
