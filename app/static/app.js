import {LocalProvider,ServerProvider,loadServerConnection,saveServerConnection,wipeServerSecrets,validateBackup} from "./providers.js";

const $=id=>document.getElementById(id);
const config=window.APP_CONFIG||{buildTarget:"shared",version:"8.7.0",defaultApiUrl:"",allowLocalMode:true};
let provider=null, currentMode="local", games=[], serverConfig=null, aiEnabled=false, rulesSearchEnabled=false, aiProvider="none", aiModel="", aiVisionModel="", rulesSearchProvider="none", autoEnrichEnabled=false, autoSearchProvider="none";
let importJobs=[], workerState={status:"offline",message:""}, queueTimer=null, queueFingerprint="", forceReleaseAfterSeconds=600, forceReleaseCancelGraceSeconds=15, diagnosticsChecked=false;
let collectionView=localStorage.getItem("brettspielregal-collection-view")==="shelf"?"shelf":"list", activeDetailGameId="", pendingFiles=[], pendingMagicImport=null;
const coverResources={list:{urls:[],observer:null},detail:{urls:[],observer:null}};
const DEFAULT_TAG_CATALOG={
  "Spielart":["Familienspiel","Kinderspiel","Kennerspiel","Expertenspiel","Partyspiel","Solospiel","Zweipersonenspiel","Kooperativ","Kompetitiv"],
  "Mechanik":["Deckbau","Kartenauswahl","Arbeitereinsatz","Plättchenlegen","Sets sammeln","Risikoabwägung","Handkartenmanagement","Gebietskontrolle","Kombinationsaufbau","Würfeln & Eintragen","Deduktion","Versteigerung","Stichspiel","Geschicklichkeit","Gedächtnis","Rätsel","Kampagne","Routenbau","Mehrheiten","Würfelspiel","Kartenspiel"],
  "Thema":["Fantasy","Science-Fiction","Abenteuer","Natur & Tiere","Historisch","Krimi","Wirtschaft","Weltraum","Eisenbahn","Städtebau","Landwirtschaft","Piraten","Horror"],
  "Eigenschaften":["Schnell gelernt","Kurze Partie","Lange Partie","Strategisch","Taktisch","Glückslastig","Hohe Interaktion","Wenig Interaktion","Asymmetrisch","Hoher Wiederspielwert","Reisetauglich"]
};
let tagCatalog=DEFAULT_TAG_CATALOG;
let selectedTagFilters=new Set((()=>{try{const v=JSON.parse(localStorage.getItem("brettspielregal-tag-filters")||"[]");return Array.isArray(v)?v:[];}catch{return [];}})());

const FIELD_MAP=[
  ["title","Titel","titleInput"],["description","Beschreibung","descriptionInput"],["min_players","Spieler min.","minPlayersInput"],
  ["max_players","Spieler max.","maxPlayersInput"],["play_time_min","Spieldauer","playTimeInput"],["min_age","Mindestalter","minAgeInput"],
  ["publisher","Verlag","publisherInput"],["storage_location","Lagerort","storageLocationInput"],["year","Jahr","yearInput"],["designer","Autor / Designer","designerInput"],
  ["ean","EAN / GTIN","eanInput"],["award","Auszeichnung","awardInput"],["cover_url","Cover","coverUrlInput"],
  ["tags","Tags","tagsInput"],["rules_url","Anleitungs-Link","rulesUrlInput"],["rules_text","Kurzregeln","rulesTextInput"],
  ["source_url","Quelle","sourceUrlInput"]
];
const FIELD_LABELS=Object.fromEntries(FIELD_MAP.map(([key,label])=>[key,label]));

function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));}
function nl2br(s){return esc(s).replace(/\n/g,"<br>");}
function modeLabel(){return currentMode==="server"?"Server":"Lokal";}
function isDocker(){return config.buildTarget==="docker";}
function selectedMode(){return isDocker()?"server":(localStorage.getItem("brettspielregal-mode")||"");}
function setModeValue(mode){if(!isDocker())localStorage.setItem("brettspielregal-mode",mode);currentMode=mode;releaseCovers("list");releaseCovers("detail");}
function setCollectionView(view){collectionView=view==="shelf"?"shelf":"list";localStorage.setItem("brettspielregal-collection-view",collectionView);renderGames();}
function updateViewButtons(){for(const [id,view] of [["viewListButton","list"],["viewShelfButton","shelf"]]){const b=$(id);b.classList.toggle("active",collectionView===view);b.setAttribute("aria-pressed",String(collectionView===view));}}
function researchAvailable(){return currentMode==="server"&&autoEnrichEnabled&&aiEnabled;}
function updateResearchControls(){
  const available=researchAvailable();
  const quick=$("quickCaptureUseAi");
  if(quick){quick.disabled=!available;if(!available)quick.checked=false;}
  const quickButton=$("submitQuickCaptureButton");
  if(quickButton)quickButton.textContent=quick?.checked?"Erfassen & recherchieren":"Nur erfassen";
  const newToggle=$("newGameAutoEnrich");
  if(newToggle){newToggle.disabled=!available;if(!available)newToggle.checked=false;}
}
function setBusy(button,busy,label="Bitte warten …"){if(!button)return;if(busy){button.dataset.oldText=button.textContent;button.textContent=label;button.disabled=true;}else{button.textContent=button.dataset.oldText||button.textContent;button.disabled=false;}}
function showBanner(message,type="info"){const el=$("statusBanner");if(!message){el.className="status-banner hidden";el.textContent="";return;}el.className=`status-banner${type==="error"?" error":""}`;el.textContent=message;}
function showMessage(title,message){$("messageTitle").textContent=title;$("messageBody").innerHTML=`<p>${nl2br(message)}</p>`;$("messageDialog").showModal();}
function normalizeUrl(url){return (url||"").trim().replace(/\/$/,"");}
function inputNumber(id){const v=$(id).value;return v===""?null:Number(v);}
function safeHttpsUrl(value){try{const u=new URL(String(value||""));return u.protocol==="https:"?u.href:"";}catch{return "";}}
function valueText(key,value){if(Array.isArray(value))return value.join(", ");if(value===null||value===undefined)return "";if(key==="play_time_min"&&value)return `${value} Min.`;if(key==="min_age"&&value!=="")return `ab ${value}`;return String(value);}
function catalogTags(){return Object.values(tagCatalog||{}).flat();}
function tagCategory(tag){for(const [category,tags] of Object.entries(tagCatalog||{}))if(tags.includes(tag))return category;return "Sonstige";}
function selectedTagsFromInput(){return $("tagsInput").value.split(",").map(x=>x.trim()).filter(Boolean);}
function setSelectedTags(tags){$("tagsInput").value=[...new Set((tags||[]).map(x=>String(x).trim()).filter(Boolean))].join(", ");renderTagPicker();}
function renderTagPicker(){
  const root=$("tagPicker");if(!root)return;
  const selected=new Set(selectedTagsFromInput());
  const groups=[];
  for(const [category,tags] of Object.entries(tagCatalog||{})){
    groups.push(`<div class="tag-picker-group"><strong>${esc(category)}</strong><div class="tag-picker-options">${tags.map(tag=>`<button type="button" class="tag-picker-chip ${selected.has(tag)?"active":""}" data-tag-pick="${esc(tag)}" aria-pressed="${selected.has(tag)}">${esc(tag)}</button>`).join("")}</div></div>`);
  }
  const known=new Set(catalogTags()),legacy=[...selected].filter(tag=>!known.has(tag));
  if(legacy.length)groups.push(`<div class="tag-picker-group tag-picker-legacy"><strong>Bestehende freie Tags</strong><p class="hint">Diese stammen aus älteren Einträgen. Antippen entfernt sie.</p><div class="tag-picker-options">${legacy.map(tag=>`<button type="button" class="tag-picker-chip active" data-tag-pick="${esc(tag)}" aria-pressed="true">${esc(tag)} ×</button>`).join("")}</div></div>`);
  root.innerHTML=groups.join("");
  root.querySelectorAll("[data-tag-pick]").forEach(b=>b.addEventListener("click",()=>{const tag=b.dataset.tagPick,current=new Set(selectedTagsFromInput());if(current.has(tag))current.delete(tag);else current.add(tag);$("tagsInput").value=[...current].join(", ");renderTagPicker();}));
}
function tagFilterMatches(game){
  if(!selectedTagFilters.size)return true;
  const gameTags=new Set(game.tags||[]),byCategory={};
  for(const tag of selectedTagFilters){const category=tagCategory(tag);(byCategory[category]||(byCategory[category]=[])).push(tag);}
  return Object.values(byCategory).every(tags=>tags.some(tag=>gameTags.has(tag)));
}
function renderTagFilters(){
  const root=$("tagFilterGroups");if(!root)return;
  const allowed=new Set(catalogTags());let pruned=false;for(const tag of [...selectedTagFilters])if(!allowed.has(tag)){selectedTagFilters.delete(tag);pruned=true;}if(pruned)localStorage.setItem("brettspielregal-tag-filters",JSON.stringify([...selectedTagFilters]));
  const counts={};for(const game of games)for(const tag of game.tags||[])counts[tag]=(counts[tag]||0)+1;
  const groups=[];
  for(const [category,tags] of Object.entries(tagCatalog||{})){
    const visible=tags.filter(tag=>(counts[tag]||0)>0||selectedTagFilters.has(tag));if(!visible.length)continue;
    groups.push(`<div class="tag-filter-group"><strong>${esc(category)}</strong><div class="tag-filter-options">${visible.map(tag=>`<button type="button" class="tag-filter-chip ${selectedTagFilters.has(tag)?"active":""}" data-tag-filter="${esc(tag)}" aria-pressed="${selectedTagFilters.has(tag)}">${esc(tag)} <span class="tag-count">${counts[tag]||0}</span></button>`).join("")}</div></div>`);
  }
  root.innerHTML=groups.join("")||'<p class="hint">Noch keine kontrollierten Tags in deiner Sammlung.</p>';
  root.querySelectorAll("[data-tag-filter]").forEach(b=>b.addEventListener("click",()=>{const tag=b.dataset.tagFilter;if(selectedTagFilters.has(tag))selectedTagFilters.delete(tag);else selectedTagFilters.add(tag);localStorage.setItem("brettspielregal-tag-filters",JSON.stringify([...selectedTagFilters]));renderGames();}));
  const count=$("tagFilterCount");count.textContent=String(selectedTagFilters.size);count.classList.toggle("hidden",selectedTagFilters.size===0);
}
function detailTagGroups(tags){
  const grouped={};for(const tag of tags||[]){const category=tagCategory(tag);(grouped[category]||(grouped[category]=[])).push(tag);}
  return Object.entries(grouped).map(([category,values])=>`<div class="detail-tag-group"><strong>${esc(category)}</strong><div class="detail-tag-chips">${values.map(tag=>detailChip(tag)).join("")}</div></div>`).join("");
}
function decodeBase64Url(value){
  const clean=String(value||"").replace(/-/g,"+").replace(/_/g,"/");
  const padded=clean+"=".repeat((4-clean.length%4)%4);
  const bytes=Uint8Array.from(atob(padded),c=>c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}
function readMagicImport(){
  try{
    const hash=new URLSearchParams(location.hash.startsWith("#")?location.hash.slice(1):location.hash);
    const encoded=hash.get("import");if(!encoded)return null;
    const payload=JSON.parse(decodeBase64Url(encoded));
    if(payload?.v!==1||typeof payload.text!=="string"||!payload.text.trim()||payload.text.length>24000)throw new Error("Ungültige Importdaten.");
    if(payload.source_url&& !safeHttpsUrl(payload.source_url))throw new Error("Ungültige Quell-URL im Import-Link.");
    if(payload.fallback&&typeof payload.fallback!=="object")throw new Error("Ungültige Fallback-Daten im Import-Link.");
    history.replaceState(null,"",location.pathname+location.search);
    return {text:payload.text.trim(),source_url:payload.source_url||"",fallback:payload.fallback||null};
  }catch(err){history.replaceState(null,"",location.pathname+location.search);showMessage("Import-Link ungültig",err.message||"Der Import-Link konnte nicht gelesen werden.");return null;}
}

async function makeServerProvider(){
  if(isDocker())return new ServerProvider("");
  const c=await loadServerConnection();
  const url=normalizeUrl(c.url||config.defaultApiUrl||"");
  if(!url)throw new Error("Für den Server-Modus ist noch keine Backend-URL eingerichtet.");
  const origin=new URL(url).origin;
  const allow=Array.isArray(config.allowedServerOrigins)?config.allowedServerOrigins:[];
  if(allow.length&&!allow.includes(origin))throw new Error("Diese Backend-Origin ist in der Frontend-Konfiguration nicht freigegeben.");
  return new ServerProvider(url,{clientId:c.clientId||"",clientSecret:c.clientSecret||""});
}
async function selectProvider(){
  currentMode=selectedMode()||"local";
  provider=currentMode==="local"?new LocalProvider():await makeServerProvider();
  $("modeBadge").textContent=modeLabel();
  document.querySelectorAll("[data-mode]").forEach(b=>b.classList.toggle("selected",b.dataset.mode===currentMode));
  $("transferControls").classList.toggle("hidden",isDocker());
  $("modeChooser").classList.toggle("hidden",isDocker()||!config.allowLocalMode);
}

async function refreshConfig(){
  try{
    const c=await provider.config();
    $("appTitle").textContent=c.title||"Brettspielregal";
    aiEnabled=!!c.ai_import_enabled;
    rulesSearchEnabled=!!c.rules_search_enabled;
    aiProvider=c.ai_provider||"none";
    aiModel=c.ai_model||"";
    aiVisionModel=c.ai_vision_model||"";
    rulesSearchProvider=c.rules_search_provider||"none";
    autoEnrichEnabled=!!c.auto_enrich_enabled;
    autoSearchProvider=c.auto_search_provider||"none";
    if(c.tag_catalog&&typeof c.tag_catalog==="object")tagCatalog=c.tag_catalog;
  }catch{aiEnabled=false;rulesSearchEnabled=false;aiProvider="none";aiModel="";aiVisionModel="";rulesSearchProvider="none";autoEnrichEnabled=false;autoSearchProvider="none";tagCatalog=DEFAULT_TAG_CATALOG;}
  $("aiImportRow").classList.toggle("hidden",currentMode!=="server"||!aiEnabled);
  $("rulesSearchButton").disabled=!rulesSearchEnabled;
  $("rulesSearchButton").title=rulesSearchProvider==="openai"?"Offizielle Anleitung mit serverseitiger Websuche verifizieren":"Anleitungs-Link auf der Quellseite suchen; externe Websuche ist deaktiviert";
  $("aiProviderLabel").textContent=currentMode==="server"?(aiEnabled?aiProvider:"deaktiviert"):"keine KI im lokalen Modus";
  $("aiModelLabel").textContent=currentMode==="server"&&aiEnabled&&aiModel?`Textmodell: ${aiModel}`:"";
  $("aiVisionModelLabel").textContent=currentMode==="server"&&aiEnabled&&aiVisionModel?`Bildmodell: ${aiVisionModel}`:"";
  $("aiSearchLabel").textContent=currentMode==="server"&&aiEnabled?`Externe Anleitungs-Websuche: ${rulesSearchProvider==="openai"?"OpenAI":"aus"}`:"";
  $("autoEnrichLabel").textContent=currentMode==="server"?`Hintergrund-Ergänzung: ${autoEnrichEnabled?"aktiv":"aus"}`:"";
  $("autoSearchLabel").textContent=currentMode==="server"&&autoEnrichEnabled?`Automatische Websuche: ${autoSearchProvider}`:"";
  const captureReady=currentMode==="server";
  const importReady=researchAvailable();
  $("queuePanel").classList.toggle("hidden",!importReady);
  $("importUnavailable").classList.toggle("hidden",importReady);
  $("quickCaptureInput").disabled=!captureReady;
  $("submitQuickCaptureButton").disabled=!captureReady;
  updateResearchControls();
  $("testAiButton").disabled=currentMode!=="server"||!aiEnabled;
  $("aiImageButton").disabled=currentMode!=="server"||!aiEnabled||aiProvider!=="ollama";
}
function latestJobForGame(gameId){
  return importJobs.find(j=>j.game_id===gameId)||null;
}
function secondsSince(value){
  if(!value)return Number.POSITIVE_INFINITY;
  const ms=Date.now()-Date.parse(value);
  return Number.isFinite(ms)?Math.max(0,ms/1000):Number.POSITIVE_INFINITY;
}
function jobStatusMeta(job){
  if(!job)return null;
  if(job.status==="running"&&job.cancel_requested)return {label:"Abbruch läuft",kind:"running"};
  const map={queued:["Wartet","queued"],running:["Wird ergänzt","running"],done:["Automatisch ergänzt","done"],review:["Vorschläge prüfen","review"],verified:["Geprüft","verified"],failed:["Importfehler","failed"],cancelled:["Abgebrochen","cancelled"]};
  const [label,kind]=map[job.status]||[job.status||"Status",""];
  return {label,kind};
}
function renderQueue(){
  const panel=$("queuePanel"), unavailable=$("importUnavailable");
  const ready=researchAvailable();
  const captureReady=currentMode==="server";
  panel.classList.toggle("hidden",!ready);unavailable.classList.toggle("hidden",ready);
  $("quickCaptureInput").disabled=!captureReady;$("submitQuickCaptureButton").disabled=!captureReady;
  updateResearchControls();
  const cleanupButton=$("cleanupQueueButton");
  if(cleanupButton) cleanupButton.disabled=!importJobs.some(j=>j.status!=="running");
  if(!ready){$("workerBadge").textContent="Nicht aktiv";$("workerBadge").classList.add("offline");return;}
  const active=importJobs.filter(j=>["queued","running"].includes(j.status));
  const attention=importJobs.filter(j=>["review","failed"].includes(j.status));
  $("queueSummary").textContent=active.length?`${active.length} Auftrag${active.length===1?"":"e"} aktiv · ${attention.length} mit Hinweis`:(attention.length?`${attention.length} Auftrag${attention.length===1?"":"e"} benötigt deine Aufmerksamkeit`:"Alles erledigt – keine offenen Aufträge.");
  $("workerBadge").textContent=workerState.status==="online"?"Worker online":"Worker offline";
  $("workerBadge").classList.toggle("offline",workerState.status!=="online");
  const shown=importJobs.filter(j=>["running","queued","review","failed"].includes(j.status)).slice(0,30);
  $("queueList").innerHTML=shown.map(job=>{
    const m=jobStatusMeta(job),review=job.status==="review",failed=job.status==="failed",running=job.status==="running";
    const pending=(job.suggestions||[]).filter(x=>x.status==="pending").length;
    const staleFor=secondsSince(job.updated_at),cancelFor=secondsSince(job.cancel_requested_at);
    const canForce=running&&(staleFor>=forceReleaseAfterSeconds||(job.cancel_requested&&cancelFor>=forceReleaseCancelGraceSeconds));
    let actions="";
    if(review)actions=`<div class="queue-actions"><button class="button queue-action" type="button" data-review-game="${esc(job.game_id)}">${pending?`${pending} Vorschläge prüfen`:"Prüfen"}</button></div>`;
    else if(failed)actions=`<div class="queue-actions"><button class="button queue-action" type="button" data-retry-job="${esc(job.id)}">↻ Erneut</button></div>`;
    else if(running){
      const cancelButton=job.cancel_requested?`<span class="queue-cancel-note">Abbruch angefordert …</span>`:`<button class="button queue-action" type="button" data-cancel-running-job="${esc(job.id)}">Abbrechen</button>`;
      const forceButton=canForce?`<button class="button queue-action danger" type="button" data-force-release-job="${esc(job.id)}">Hängenden Auftrag freigeben</button>`:"";
      actions=`<div class="queue-actions">${cancelButton}${forceButton}</div>`;
    }
    return `<div class="queue-row ${review?"review-row":""}"><div class="queue-status-dot ${m.kind}" aria-hidden="true"></div><div class="queue-copy"><strong>${esc(job.game_title||job.query)}</strong><small>${esc(job.progress||m.label)}${job.game_storage_location?` · 📍 ${esc(job.game_storage_location)}`:""}${job.error?` · ${esc(job.error)}`:""}</small></div><span class="queue-state ${m.kind}">${esc(m.label)}</span>${actions}</div>`;
  }).join("") || `<div class="queue-empty">${esc(workerState.message||"Worker bereit.")}</div>`;
  $("queueList").querySelectorAll("[data-retry-job]").forEach(b=>b.addEventListener("click",async()=>{b.disabled=true;try{await provider.retryImportJob(b.dataset.retryJob);await refreshQueue(true);}catch(err){showMessage("Erneuter Versuch fehlgeschlagen",err.message);}finally{b.disabled=false;}}));
  $("queueList").querySelectorAll("[data-cancel-running-job]").forEach(b=>b.addEventListener("click",async()=>{
    if(!confirm("Laufenden Hintergrundauftrag abbrechen? Das Spiel selbst bleibt in deiner Sammlung."))return;
    b.disabled=true;try{await provider.requestCancelImportJob(b.dataset.cancelRunningJob);await refreshQueue(true);}catch(err){showMessage("Abbrechen fehlgeschlagen",err.message);}finally{b.disabled=false;}
  }));
  $("queueList").querySelectorAll("[data-force-release-job]").forEach(b=>b.addEventListener("click",async()=>{
    if(!confirm("Diesen hängenden Auftrag wirklich freigeben? Das Spiel bleibt erhalten; temporäre KI-Vorschläge dieses Auftrags werden verworfen."))return;
    b.disabled=true;try{await provider.forceReleaseImportJob(b.dataset.forceReleaseJob);await refreshQueue(true);}catch(err){showMessage("Freigeben fehlgeschlagen",err.message);}finally{b.disabled=false;}
  }));
  $("queueList").querySelectorAll("[data-review-game]").forEach(b=>b.addEventListener("click",()=>openGameDetail(b.dataset.reviewGame)));
}
function openQueueCleanup(){
  const dlg=$("queueCleanupDialog");
  if(!dlg)return;
  dlg.showModal();
}
async function cleanupQueue(mode){
  const dlg=$("queueCleanupDialog");
  if(mode==="including_review"&&!confirm("Offene KI-Vorschläge wirklich verwerfen und aus der Warteschlange entfernen?"))return;
  if(mode==="all_non_running"&&!confirm("Wirklich alle nicht laufenden Aufträge löschen? Wartende Recherchen werden dadurch abgebrochen und offene KI-Vorschläge verworfen."))return;
  const button=dlg?.querySelector(`[data-cleanup-mode="${mode}"]`);
  setBusy(button,true,"Räume auf …");
  try{
    const result=await provider.cleanupImportQueue(mode);
    if(dlg?.open)dlg.close();
    await refreshQueue(true);
    const protectedText=result.running_protected?` ${result.running_protected} laufender Auftrag blieb geschützt.`:"";
    showMessage("Warteschlange aufgeräumt",`${result.deleted||0} Eintrag${result.deleted===1?"":"e"} entfernt.${protectedText}`);
  }catch(err){showMessage("Aufräumen fehlgeschlagen",err.message);}
  finally{setBusy(button,false);}
}

async function refreshQueue(forceGames=false){
  if(!researchAvailable()){importJobs=[];renderQueue();return;}
  try{
    const result=await provider.importQueue();
    importJobs=Array.isArray(result.jobs)?result.jobs:[];workerState=result.worker||{status:"offline",message:""};
    forceReleaseAfterSeconds=Number(result.force_release_after_seconds)||600;
    forceReleaseCancelGraceSeconds=Number(result.force_release_cancel_grace_seconds)||15;
    const fingerprint=importJobs.map(j=>`${j.id}:${j.status}:${j.updated_at}`).join("|");
    const changed=fingerprint!==queueFingerprint;queueFingerprint=fingerprint;
    renderQueue();renderGames();
    if(forceGames||changed&&importJobs.some(j=>["done","review"].includes(j.status)))await loadGames();
  }catch(err){workerState={status:"offline",message:err.message};renderQueue();}
}
function startQueuePolling(){
  if(queueTimer){clearInterval(queueTimer);queueTimer=null;}
  if(researchAvailable()){refreshQueue();queueTimer=setInterval(()=>refreshQueue(),8000);}
}
async function loadGames(){
  showBanner("");
  try{games=await provider.list();renderGames();}
  catch(err){games=[];renderGames();showBanner(err.message,"error");}
}
function imageAttachment(game){
  const images=(game.attachments||[]).filter(a=>a.kind==="image");
  return images.find(a=>a.id===game.cover_attachment_id)||images[0]||null;
}
function coverHtml(game,classes="game-cover",attachment=null){
  const selected=attachment||imageAttachment(game);
  const initial=(game.title||"B").trim().slice(0,1).toLocaleUpperCase("de");
  if(selected)return `<div class="${classes} game-cover-placeholder" data-attachment-id="${esc(selected.id)}" data-game-id="${esc(game.id)}" aria-label="Lade Bild"><span>${esc(initial)}</span></div>`;
  const url=safeHttpsUrl(game.cover_url);
  if(url)return `<img class="${classes}" src="${esc(url)}" alt="Cover von ${esc(game.title)}" loading="lazy" referrerpolicy="no-referrer">`;
  return `<div class="${classes} game-cover-placeholder" aria-hidden="true"><span>${esc(initial)}</span></div>`;
}
function releaseCovers(scope){
  const r=coverResources[scope];if(r.observer){r.observer.disconnect();r.observer=null;}
  for(const url of r.urls)URL.revokeObjectURL(url);r.urls=[];
}
function hydrateCovers(scope){
  const root=scope==="list"?$("gameList"):$("detailBody");
  const resource=coverResources[scope];
  const hydrate=async node=>{
    if(node.dataset.loading)return;node.dataset.loading="1";
    const gameId=node.dataset.gameId,attId=node.dataset.attachmentId,providerAtStart=provider;
    try{
      const blob=await providerAtStart.getAttachmentBlob(gameId,attId);
      if(provider!==providerAtStart||!node.isConnected||!root.contains(node))return;
      const url=URL.createObjectURL(blob),img=document.createElement("img");
      resource.urls.push(url);img.className=node.className.replace("game-cover-placeholder","");img.alt="Gespeichertes Bild";img.loading="lazy";
      img.onload=()=>{if(node.isConnected&&root.contains(node))node.replaceWith(img);};
      img.onerror=()=>{if(node.isConnected)node.title="Keine Bildvorschau in diesem Browser – die Datei kann trotzdem geöffnet werden.";};
      img.src=url;
    }catch{node.removeAttribute("data-loading");node.title="Bild konnte nicht geladen werden";}
  };
  const nodes=[...root.querySelectorAll("[data-attachment-id]")];
  if("IntersectionObserver" in window){
    resource.observer=new IntersectionObserver(entries=>{
      for(const entry of entries)if(entry.isIntersecting){resource.observer?.unobserve(entry.target);hydrate(entry.target);}
    },{rootMargin:"240px"});
    for(const node of nodes)resource.observer.observe(node);
  }else for(const node of nodes)hydrate(node);
}
function renderGames(){
  releaseCovers("list");
  const q=$("searchInput").value.trim().toLocaleLowerCase("de");
  const filtered=games.filter(g=>(!q||[g.title,g.description,g.publisher,g.designer,g.ean,g.award,g.storage_location,g.notes,...(g.tags||[])].join(" ").toLocaleLowerCase("de").includes(q))&&tagFilterMatches(g));
  const narrowed=!!q||selectedTagFilters.size>0;
  $("collectionCount").textContent=narrowed?`${filtered.length} von ${games.length} Spielen`:`${games.length} ${games.length===1?"Spiel":"Spiele"}`;
  $("emptyState").classList.toggle("hidden",games.length!==0);
  const list=$("gameList");list.innerHTML="";list.classList.toggle("shelf-view",collectionView==="shelf");
  for(const g of filtered){
    const card=document.createElement("article"),meta=[];
    if(g.min_players||g.max_players)meta.push({text:`${g.min_players||"?"}–${g.max_players||g.min_players||"?"} Spieler`,kind:"core"});
    if(g.play_time_min)meta.push({text:`${g.play_time_min} Min.`,kind:"core"});
    if(g.min_age!==null&&g.min_age!==undefined&&g.min_age!=="")meta.push({text:`ab ${g.min_age}`,kind:"core"});
    if(g.storage_location)meta.push({text:`📍 ${g.storage_location}`,kind:"location"});
    if(g.publisher)meta.push({text:g.publisher,kind:""});
    if(g.year)meta.push({text:String(g.year),kind:""});
    if(g.award)meta.push({text:g.award,kind:"award"});
    for(const tag of (g.tags||[]).slice(0,2))meta.push({text:tag,kind:""});
    if(collectionView==="shelf"){
      card.className="game-card shelf-card";
      const subline=[g.storage_location?`📍 ${g.storage_location}`:"",g.publisher,g.year].filter(Boolean).join(" · ")||(g.designer?`von ${g.designer}`:"Meine Sammlung");
      card.innerHTML=`<button class="shelf-hit" type="button"><div class="shelf-cover-wrap">${coverHtml(g,"game-cover shelf-cover")}${g.award?`<span class="shelf-award">★ ${esc(g.award)}</span>`:""}</div><div class="shelf-copy"><h3>${esc(g.title)}</h3><p class="shelf-subline">${esc(subline)}</p><div class="shelf-mini-meta">${meta.filter(x=>x.kind==="core").slice(0,3).map(x=>`<span class="shelf-mini-chip">${esc(x.text)}</span>`).join("")}</div></div></button>`;
    }else{
      card.className="game-card";
      card.innerHTML=`<button class="card-hit with-cover" type="button">${coverHtml(g)}<div class="card-copy"><div class="game-title-row"><h3>${esc(g.title)}</h3><span aria-hidden="true">›</span></div>${g.description?`<p class="game-description">${esc(g.description)}</p>`:""}<div class="game-meta">${meta.map(x=>`<span class="chip ${x.kind}">${esc(x.text)}</span>`).join("")}</div></div></button>`;
    }
    card.querySelector("button").addEventListener("click",()=>openGameDetail(g.id));list.append(card);
  }
  if(games.length&&filtered.length===0)list.innerHTML='<div class="empty-state"><strong>Nichts gefunden</strong><p>Versuche einen anderen Suchbegriff.</p></div>';
  updateViewButtons();renderTagFilters();hydrateCovers("list");
}

function clearGameForm(){
  pendingFiles=[];$("gameAttachmentInput").value="";$("pendingAttachmentList").innerHTML="";$("existingAttachmentList").innerHTML="";$("attachmentFormStatus").textContent="";
  for(const id of ["gameId","titleInput","sourceUrlInput","descriptionInput","minPlayersInput","maxPlayersInput","playTimeInput","minAgeInput","publisherInput","storageLocationInput","yearInput","designerInput","eanInput","awardInput","coverUrlInput","tagsInput","rulesUrlInput","rulesTextInput","notesInput"])$(id).value="";
  renderCoverPreview();renderTagPicker();
}
function renderCoverPreview(){
  const url=safeHttpsUrl($("coverUrlInput").value);
  const box=$("coverPreview");
  if(!url){box.classList.add("hidden");box.innerHTML="";return;}
  box.innerHTML=`<img src="${esc(url)}" alt="Cover-Vorschau" referrerpolicy="no-referrer"><span class="hint">Cover wird extern per HTTPS geladen und nicht in Backups eingebettet.</span>`;
  box.classList.remove("hidden");
}
function openGame(game=null){
  clearGameForm();$("deleteGameButton").classList.toggle("hidden",!game);$("gameDialogTitle").textContent=game?"Spiel bearbeiten":"Spiel erfassen";
  if(game){
    $("gameId").value=game.id;$("titleInput").value=game.title||"";$("sourceUrlInput").value=game.source_url||"";$("descriptionInput").value=game.description||"";
    $("minPlayersInput").value=game.min_players??"";$("maxPlayersInput").value=game.max_players??"";$("playTimeInput").value=game.play_time_min??"";$("minAgeInput").value=game.min_age??"";
    $("publisherInput").value=game.publisher||"";$("storageLocationInput").value=game.storage_location||"";$("yearInput").value=game.year??"";$("designerInput").value=game.designer||"";$("eanInput").value=game.ean||"";$("awardInput").value=game.award||"";$("coverUrlInput").value=game.cover_url||"";
    $("tagsInput").value=(game.tags||[]).join(", ");$("rulesUrlInput").value=game.rules_url||"";$("rulesTextInput").value=game.rules_text||"";$("notesInput").value=game.notes||"";
    renderCoverPreview();
  }
  renderTagPicker();renderEditAttachments(game);
  const researchRow=$("newGameResearchRow"),researchToggle=$("newGameAutoEnrich");
  const showResearch=!game&&currentMode==="server";
  if(researchRow&&researchToggle){researchRow.classList.toggle("hidden",!showResearch);
  if(showResearch){researchToggle.disabled=!researchAvailable();researchToggle.checked=researchAvailable();}}
  $("gameDialog").showModal();setTimeout(()=>$("titleInput").focus(),50);
}
function sizeText(bytes){return bytes>=1024*1024?`${(bytes/1024/1024).toFixed(1)} MB`:`${Math.max(1,Math.ceil(bytes/1024))} KB`;}
function renderEditAttachments(game=null){
  const current=game?.attachments||[];
  $("pendingAttachmentList").innerHTML=pendingFiles.map((file,i)=>`<div class="attachment-row"><div class="attachment-row-copy"><strong>${esc(file.name)}</strong><small>Wird beim Speichern hinzugefügt · ${sizeText(file.size)}</small></div><button type="button" class="button" data-remove-pending="${i}">Entfernen</button></div>`).join("");
  $("pendingAttachmentList").querySelectorAll("[data-remove-pending]").forEach(b=>b.addEventListener("click",()=>{pendingFiles.splice(Number(b.dataset.removePending),1);renderEditAttachments(game);}));
  $("existingAttachmentList").innerHTML=current.map(a=>`<div class="attachment-row"><div class="attachment-row-copy"><strong>${a.kind==="rules"?"📄":"🖼️"} ${esc(a.filename)}</strong><small>Gespeichert · ${sizeText(a.size)}</small></div><button type="button" class="button danger" data-delete-existing="${esc(a.id)}">Löschen</button></div>`).join("");
  $("existingAttachmentList").querySelectorAll("[data-delete-existing]").forEach(b=>b.addEventListener("click",async()=>{
    if(!confirm("Diesen Anhang endgültig löschen?"))return;
    try{await provider.removeAttachment(game.id,b.dataset.deleteExisting);await loadGames();renderEditAttachments(games.find(g=>g.id===game.id));}
    catch(err){$("attachmentFormStatus").textContent=err.message;}
  }));
}
function addPendingFiles(fileList){
  const files=[...fileList];const game=games.find(g=>g.id===$("gameId").value);
  const available=15-(game?.attachments?.length||0)-pendingFiles.length;
  if(files.length>available){$("attachmentFormStatus").textContent="Maximal 15 Anhänge pro Spiel möglich.";return;}
  for(const file of files){
    if(file.size<1||file.size>10*1024*1024){$("attachmentFormStatus").textContent=`${file.name}: maximal 10 MB pro Datei.`;continue;}
    pendingFiles.push(file);
  }
  renderEditAttachments(game);
}
function detailChip(text,kind=""){return `<span class="chip ${kind}">${esc(text)}</span>`;}
function openGameDetail(gameId){
  const game=games.find(g=>g.id===gameId);if(!game)return;
  activeDetailGameId=gameId;releaseCovers("detail");$("detailAttachmentStatus").textContent="";
  const chips=[];
  if(game.min_players||game.max_players)chips.push(detailChip(`${game.min_players||"?"}–${game.max_players||game.min_players||"?"} Spieler`,"core"));
  if(game.play_time_min)chips.push(detailChip(`${game.play_time_min} Min.`,"core"));
  if(game.min_age!==null&&game.min_age!==undefined&&game.min_age!=="")chips.push(detailChip(`ab ${game.min_age}`,"core"));
  if(game.award)chips.push(detailChip(game.award,"award"));
  const facts=[["Lagerort",game.storage_location],["Verlag",game.publisher],["Jahr",game.year],["Autor / Designer",game.designer],["EAN / GTIN",game.ean]].filter(([,v])=>v!==null&&v!==undefined&&v!=="");
  const images=(game.attachments||[]).filter(a=>a.kind==="image"),pdfs=(game.attachments||[]).filter(a=>a.kind==="rules"),selected=imageAttachment(game);
  const imageGallery=images.length?`<div class="attachment-gallery">${images.map(a=>`<div class="attachment-tile ${selected?.id===a.id?"cover-selected":""}">${coverHtml(game,"tile-image",a)}<strong>${esc(a.filename)}</strong><div class="attachment-actions"><button class="button" type="button" data-open-attachment="${esc(a.id)}">Ansehen</button><button class="button" type="button" data-cover-attachment="${esc(a.id)}" ${selected?.id===a.id?"disabled":""}>${selected?.id===a.id?"Cover ✓":"Als Cover"}</button><button class="button danger" type="button" data-delete-attachment="${esc(a.id)}">×</button></div></div>`).join("")}</div>`:"";
  const pdfList=pdfs.length?`<div class="attachment-pdf-list">${pdfs.map(a=>`<div class="attachment-pdf"><span aria-hidden="true">📄</span><div class="attachment-row-copy"><strong>${esc(a.filename)}</strong><small>${sizeText(a.size)} · PDF</small></div><div class="attachment-actions"><button class="button" type="button" data-open-attachment="${esc(a.id)}">Öffnen</button><button class="button" type="button" data-download-attachment="${esc(a.id)}">Laden</button><button class="button danger" type="button" data-delete-attachment="${esc(a.id)}">×</button></div></div>`).join("")}</div>`:"";
  const links=[["Produkt- oder Quellseite",game.source_url],["Online-Anleitung",game.rules_url]].filter(([,url])=>safeHttpsUrl(url));
  const reviewJob=latestJobForGame(game.id);
  const pendingSuggestions=(reviewJob?.suggestions||[]).filter(x=>x.status==="pending");
  const needsReview=reviewJob?.status==="review"&&pendingSuggestions.length>0;
  const sourceItems=(reviewJob?.sources||[]).map(url=>{try{const u=new URL(url);return `<li><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(u.hostname.replace(/^www\./,""))}</a></li>`;}catch{return "";}}).join("");
  const research=reviewJob?.research||{};
  const identity=research.identity||null;
  const selectedResearch=(research.selected||[]).map(item=>{
    const label=item.title||item.url||"Quelle";const score=Number(item.score);const scoreText=Number.isFinite(score)?` · ${score} Punkte`:"";
    return `<li><strong>${esc(label)}</strong><small>${esc(item.trust||"")}${esc(scoreText)}</small>${safeHttpsUrl(item.url)?`<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">Öffnen ↗</a>`:""}</li>`;
  }).join("");
  const ignoredResearch=(research.ignored||[]).map(item=>{const score=Number(item.score);const why=(item.reasons||[]).join(" · ");return `<li><span>${esc(item.title||item.url||"Treffer")}</span><small>${Number.isFinite(score)?`${score} Punkte · `:""}${esc(why)}</small></li>`;}).join("");
  const researchPanel=(identity||selectedResearch||ignoredResearch)?`<div class="research-report"><div class="research-report-head"><strong>Quellenauswahl v8.7</strong><span>${esc(String(research.candidate_count||0))} Treffer geprüft</span></div>${identity?`<div class="identity-card"><span>Identifiziert über BoardGameGeek</span><strong>${esc(identity.title||identity.matched_name||"Brettspiel")}</strong><small>Übereinstimmung ${esc(String(identity.score||"?"))}% · BGG #${esc(String(identity.bgg_id||""))}</small></div>`:""}${selectedResearch?`<div class="research-list"><strong>Für Ollama ausgewählt</strong><ul>${selectedResearch}</ul></div>`:""}${ignoredResearch?`<details class="research-ignored"><summary>Verworfene Suchtreffer</summary><ul>${ignoredResearch}</ul></details>`:""}${research.bgg_error?`<p class="hint">BGG-Hinweis: ${esc(research.bgg_error)}</p>`:""}</div>`:"";
  const fmtSuggestion=(field,value)=>{if(value===null||value===undefined||value===""||(Array.isArray(value)&&!value.length))return "—";return valueText(field,value);};
  const suggestionRows=pendingSuggestions.map(item=>{
    const field=item.field,label=FIELD_LABELS[field]||field,current=game[field],proposed=item.value;
    const coverPreview=field==="cover_url"&&safeHttpsUrl(proposed)?`<img class="suggestion-cover" src="${esc(safeHttpsUrl(proposed))}" alt="KI-Covervorschlag" referrerpolicy="no-referrer">`:"";
    return `<div class="suggestion-row"><div class="suggestion-field"><strong>${esc(label)}</strong></div><div class="suggestion-values"><div><small>Aktuell</small><span>${esc(fmtSuggestion(field,current))}</span></div><div class="suggestion-proposed"><small>KI-Vorschlag</small>${coverPreview}<span>${esc(fmtSuggestion(field,proposed))}</span></div></div><div class="suggestion-actions"><button type="button" class="button primary" data-apply-suggestion="${esc(field)}">Übernehmen</button><button type="button" class="button subtle" data-reject-suggestion="${esc(field)}">Verwerfen</button></div></div>`;
  }).join("");
  const warningPanel=needsReview?`<section class="detail-panel review-panel"><div class="suggestion-head"><div><h4>KI-Vorschläge prüfen</h4><p class="hint">Noch nichts davon hat deine freigegebenen Spieldaten überschrieben. Übernimm nur, was passt.</p></div><span class="proposal-count">${pendingSuggestions.length}</span></div>${researchPanel}${suggestionRows}${reviewJob.warnings?.length?`<div class="warning-box"><strong>Hinweise der Recherche</strong><ul>${reviewJob.warnings.map(w=>`<li>${esc(w)}</li>`).join("")}</ul></div>`:""}${sourceItems?`<details class="review-sources"><summary>Verwendete Recherchequellen</summary><ul>${sourceItems}</ul></details>`:""}<div class="suggestion-footer"><button type="button" class="button subtle" data-reject-all-suggestions>Alle verwerfen</button></div></section>`:"";
  $("detailTitle").textContent=game.title||"Spiel";
  const tagPanel=(game.tags||[]).length?`<section class="detail-panel"><h4>Tags</h4><div class="detail-tag-groups">${detailTagGroups(game.tags)}</div></section>`:"";
  $("detailBody").innerHTML=`<div class="detail-hero">${coverHtml(game,"detail-cover")}<div class="detail-copy"><h3>${esc(game.title)}</h3><p class="detail-description">${esc(game.description||"Noch keine Beschreibung hinterlegt.")}</p><div class="detail-meta">${chips.join("")}</div></div></div><div class="detail-panels">${warningPanel}<section class="detail-panel"><h4>Auf einen Blick</h4><div class="detail-grid">${facts.length?facts.map(([name,value])=>`<div class="detail-item"><span>${esc(name)}</span><strong>${esc(value)}</strong></div>`).join(""):`<p class="hint">Noch keine weiteren Angaben.</p>`}</div></section>${tagPanel}<section class="detail-panel"><h4>Eigene Anhänge (${images.length+pdfs.length})</h4>${imageGallery}${pdfList}${images.length+pdfs.length===0?`<p class="hint">Noch keine Bilder oder PDF-Anleitungen hochgeladen.</p>`:""}</section>${links.length?`<section class="detail-panel"><h4>Externe Links</h4>${links.map(([name,url])=>`<a class="detail-link" href="${esc(safeHttpsUrl(url))}" target="_blank" rel="noopener noreferrer">${esc(name)} ↗</a>`).join("")}</section>`:""}${game.rules_text?`<section class="detail-panel"><h4>Kurzregeln</h4><p class="detail-notes">${esc(game.rules_text)}</p></section>`:""}${game.notes?`<section class="detail-panel"><h4>Notizen</h4><p class="detail-notes">${esc(game.notes)}</p></section>`:""}</div>`;
  $("detailEditButton").onclick=()=>{$("gameDetailDialog").close();releaseCovers("detail");openGame(game);};
  $("detailApproveButton").classList.toggle("hidden",!needsReview);
  $("detailApproveButton").onclick=needsReview?async()=>{const b=$("detailApproveButton");setBusy(b,true,"Übernehme …");try{await provider.applyImportSuggestions(reviewJob.id,null);await loadGames();await refreshQueue();openGameDetail(game.id);showMessage("Vorschläge übernommen","Alle noch offenen KI-Vorschläge wurden in die freigegebenen Spieldaten übernommen.");}catch(err){$("detailAttachmentStatus").textContent=err.message;}finally{setBusy(b,false);}}:null;
  if(needsReview){
    $("detailBody").querySelectorAll("[data-apply-suggestion]").forEach(b=>b.addEventListener("click",async()=>{setBusy(b,true,"Übernehme …");try{await provider.applyImportSuggestions(reviewJob.id,[b.dataset.applySuggestion]);await loadGames();await refreshQueue();openGameDetail(game.id);}catch(err){$("detailAttachmentStatus").textContent=err.message;}finally{setBusy(b,false);}}));
    $("detailBody").querySelectorAll("[data-reject-suggestion]").forEach(b=>b.addEventListener("click",async()=>{setBusy(b,true,"Verwerfe …");try{await provider.rejectImportSuggestions(reviewJob.id,[b.dataset.rejectSuggestion]);await refreshQueue();openGameDetail(game.id);}catch(err){$("detailAttachmentStatus").textContent=err.message;}finally{setBusy(b,false);}}));
    $("detailBody").querySelectorAll("[data-reject-all-suggestions]").forEach(b=>b.addEventListener("click",async()=>{if(!confirm("Alle offenen KI-Vorschläge für dieses Spiel verwerfen?"))return;setBusy(b,true,"Verwerfe …");try{await provider.rejectImportSuggestions(reviewJob.id,null);await refreshQueue();openGameDetail(game.id);}catch(err){$("detailAttachmentStatus").textContent=err.message;}finally{setBusy(b,false);}}));
  }
  const canReEnrich=currentMode==="server"&&autoEnrichEnabled&&!needsReview&&!(["queued","running"].includes(reviewJob?.status));
  $("detailReEnrichButton").classList.toggle("hidden",!canReEnrich);
  $("detailReEnrichButton").onclick=canReEnrich?async()=>{const b=$("detailReEnrichButton");setBusy(b,true,"Reihe ein …");try{await provider.enqueueEnrichment(game.id,game.ean||game.title,false);await refreshQueue();$("gameDetailDialog").close();showView("import");}catch(err){$("detailAttachmentStatus").textContent=err.message;}finally{setBusy(b,false);}}:null;
  const find=id=>(game.attachments||[]).find(a=>a.id===id);
  $("detailBody").querySelectorAll("[data-open-attachment]").forEach(b=>b.addEventListener("click",()=>openStoredAttachment(game,find(b.dataset.openAttachment))));
  $("detailBody").querySelectorAll("[data-download-attachment]").forEach(b=>b.addEventListener("click",()=>downloadStoredAttachment(game,find(b.dataset.downloadAttachment))));
  $("detailBody").querySelectorAll("[data-cover-attachment]").forEach(b=>b.addEventListener("click",async()=>{
    try{await provider.update(game.id,{...game,cover_attachment_id:b.dataset.coverAttachment});await loadGames();openGameDetail(game.id);}
    catch(err){$("detailAttachmentStatus").textContent=err.message;}
  }));
  $("detailBody").querySelectorAll("[data-delete-attachment]").forEach(b=>b.addEventListener("click",async()=>{
    if(!confirm("Diesen Anhang endgültig löschen?"))return;
    try{await provider.removeAttachment(game.id,b.dataset.deleteAttachment);await loadGames();openGameDetail(game.id);}
    catch(err){$("detailAttachmentStatus").textContent=err.message;}
  }));
  hydrateCovers("detail");
  if(!$("gameDetailDialog").open)$("gameDetailDialog").showModal();
}
async function downloadStoredAttachment(game,att){
  if(!att)return;
  try{const blob=await provider.getAttachmentBlob(game.id,att.id),url=URL.createObjectURL(blob);
    const a=document.createElement("a");a.href=url;a.download=att.filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
  }catch(err){$("detailAttachmentStatus").textContent=err.message;}
}
async function openStoredAttachment(game,att){
  if(!att)return;
  const tab=window.open("about:blank","_blank");if(tab)tab.opener=null;
  try{const blob=await provider.getAttachmentBlob(game.id,att.id),url=URL.createObjectURL(blob);
    if(tab){tab.location.href=url;setTimeout(()=>URL.revokeObjectURL(url),300000);}
    else{const a=document.createElement("a");a.href=url;a.download=att.filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);}
  }catch(err){tab?.close();$("detailAttachmentStatus").textContent=err.message;}
}
async function addDetailFiles(files){
  if(!files.length||!activeDetailGameId)return;
  const gameId=activeDetailGameId;$("detailAttachmentStatus").textContent="Dateien werden gespeichert …";
  try{
    for(const file of files)await provider.addAttachment(gameId,file);
    await loadGames();openGameDetail(gameId);$("detailAttachmentStatus").textContent=`${files.length} Datei(en) gespeichert.`;
  }catch(err){await loadGames();openGameDetail(gameId);$("detailAttachmentStatus").textContent=`Nicht alle Dateien gespeichert: ${err.message}`;}
  $("detailAttachmentInput").value="";
}

function formGame(){return {
  title:$("titleInput").value.trim(),source_url:$("sourceUrlInput").value.trim(),description:$("descriptionInput").value.trim(),
  min_players:inputNumber("minPlayersInput"),max_players:inputNumber("maxPlayersInput"),play_time_min:inputNumber("playTimeInput"),min_age:inputNumber("minAgeInput"),
  publisher:$("publisherInput").value.trim(),storage_location:$("storageLocationInput").value.trim(),year:inputNumber("yearInput"),designer:$("designerInput").value.trim(),ean:$("eanInput").value.replace(/\s+/g,"").trim(),award:$("awardInput").value.trim(),cover_url:$("coverUrlInput").value.trim(),
  tags:$("tagsInput").value.split(",").map(x=>x.trim()).filter(Boolean),rules_url:$("rulesUrlInput").value.trim(),rules_text:$("rulesTextInput").value.trim(),notes:$("notesInput").value.trim()
};}
function applyProposal(d){
  for(const [key,,id] of FIELD_MAP){
    const value=d[key];
    if(value===null||value===undefined||value===""||(Array.isArray(value)&&value.length===0))continue;
    $(id).value=Array.isArray(value)?value.join(", "):value;
  }
  renderCoverPreview();renderTagPicker();
}

async function saveGame(event){
  event.preventDefault();const data=formGame();if(!data.title){showMessage("Titel fehlt","Bitte gib einen Titel ein.");return;}
  const submit=$("gameForm").querySelector('button[type="submit"]');setBusy(submit,true,"Speichere …");
  try{
    const id=$("gameId").value;const researchToggle=$("newGameAutoEnrich");const saved=id?await provider.update(id,data):await provider.create(data,{autoEnrich:!!researchToggle?.checked});
    $("gameId").value=saved.id;
    for(let i=0;i<pendingFiles.length;){
      try{await provider.addAttachment(saved.id,pendingFiles[i]);pendingFiles.splice(i,1);}
      catch(err){await loadGames();renderEditAttachments(games.find(g=>g.id===saved.id));$("attachmentFormStatus").textContent=`Spiel gespeichert, aber Anhang fehlgeschlagen: ${err.message}`;return;}
    }
    $("gameDialog").close();await loadGames();
  }catch(err){$("attachmentFormStatus").textContent=`Speichern fehlgeschlagen: ${err.message}`;}finally{setBusy(submit,false);}
}
async function removeGame(){const id=$("gameId").value;if(!id)return;if(!confirm("Dieses Brettspiel wirklich löschen?"))return;try{await provider.remove(id);$("gameDialog").close();await loadGames();}catch(err){showMessage("Löschen fehlgeschlagen",err.message);}}

function proposalDialog(data,warnings=[],options={}){
  return new Promise(resolve=>{
    const rows=[];
    for(const [key,label] of FIELD_MAP){
      const value=data[key];if(value===null||value===undefined||value===""||(Array.isArray(value)&&value.length===0))continue;
      const shown=valueText(key,value);
      rows.push(`<div class="preview-row"><span>${esc(label)}</span><strong>${nl2br(shown)}</strong></div>`);
    }
    const warningHtml=warnings.length?`<div class="warning-box"><strong>Bitte prüfen</strong><ul>${warnings.map(x=>`<li>${esc(x)}</li>`).join("")}</ul></div>`:"";
    const cover=safeHttpsUrl(data.cover_url);
    const coverHtml=cover?`<img class="preview-cover" src="${esc(cover)}" alt="Gefundenes Cover" referrerpolicy="no-referrer">`:"";
    $("metadataPreviewTitle").textContent=options.title||"Gefundene Daten prüfen";
    $("metadataPreviewBody").innerHTML=`${options.intro?`<p>${esc(options.intro)}</p>`:""}${coverHtml}<div class="preview-grid">${rows.join("")||"<p>Keine übernehmbaren Daten gefunden.</p>"}</div>${warningHtml}`;
    $("applyMetadataPreviewButton").textContent=options.applyLabel||"Vorschläge übernehmen";
    const dlg=$("metadataPreviewDialog");
    const finish=value=>{cleanup();dlg.close();resolve(value);};
    const apply=()=>finish(true),cancel=()=>finish(false);
    function cleanup(){$("applyMetadataPreviewButton").removeEventListener("click",apply);$("cancelMetadataPreviewButton").removeEventListener("click",cancel);$("closeMetadataPreviewButton").removeEventListener("click",cancel);dlg.removeEventListener("cancel",cancel);}
    $("applyMetadataPreviewButton").addEventListener("click",apply);$("cancelMetadataPreviewButton").addEventListener("click",cancel);$("closeMetadataPreviewButton").addEventListener("click",cancel);dlg.addEventListener("cancel",cancel);dlg.showModal();
  });
}

async function processMagicImport(payload){
  if(!payload)return;
  let data=payload.fallback||{}, warnings=[];
  let intro="Die vorbereiteten Produktdaten wurden aus dem Import-Link gelesen. Es wird noch nichts gespeichert.";
  if(currentMode==="server"&&aiEnabled){
    try{
      const result=await provider.aiFromText(payload.text,payload.source_url);
      data=result.game||data;warnings=Array.isArray(result.warnings)?result.warnings:[];
      const providerName=result.ai_provider==="ollama"?"lokalem Ollama":result.ai_provider==="openai"?"OpenAI":"KI";
      intro=`Der vorbereitete Datensatz wurde serverseitig mit ${providerName} ausgewertet. Galaxus selbst musste dafür nicht abgerufen werden. Es wird noch nichts gespeichert.`;
    }catch(err){
      if(!payload.fallback){showMessage("Import fehlgeschlagen",err.message);return;}
      warnings=[`Ollama-Auswertung nicht möglich: ${err.message}`];
      intro="Ollama konnte den vorbereiteten Datensatz nicht auswerten. Deshalb werden die mitgelieferten Fallback-Daten angezeigt.";
    }
  }else if(currentMode!=="server"){
    warnings=["Im lokalen Modus wird Ollama nicht angesprochen. Die vorbereiteten Fallback-Daten werden direkt übernommen."];
  }else if(!aiEnabled){
    warnings=["Die serverseitige KI-Auswertung ist deaktiviert. Die vorbereiteten Fallback-Daten werden direkt angezeigt."];
  }
  if(payload.source_url&&!data.source_url)data.source_url=payload.source_url;
  const apply=await proposalDialog(data,warnings,{title:"Import-Link erkannt",intro,applyLabel:"Spiel übernehmen"});
  if(apply){openGame();applyProposal(data);}
}

async function submitQuickCapture(event){
  event.preventDefault();const text=$("quickCaptureInput").value.trim();if(!text)return;
  if(currentMode!=="server"){showMessage("Nur im Server-Modus","Die Schnellerfassung steht im Server-Modus zur Verfügung.");return;}
  const enrich=!!$("quickCaptureUseAi")?.checked;
  if(enrich&&!researchAvailable()){showMessage("KI-Recherche nicht aktiv","Deaktiviere „Mit KI recherchieren“ oder aktiviere die Hintergrund-Recherche im Server-Setup.");return;}
  const b=$("submitQuickCaptureButton");setBusy(b,true,enrich?"Reihe ein …":"Erfasse …");
  try{
    const result=await provider.quickCapture(text,$("quickCaptureLocation").value.trim(),enrich);$("quickCaptureInput").value="";await loadGames();if(enrich)await refreshQueue();
    showMessage(enrich?"Erfasst & Recherche gestartet":"Spiele erfasst",enrich?`${result.count||0} Spiel${result.count===1?"":"e"} sind sofort in der Sammlung. KI-Ergebnisse erscheinen später als prüfbare Vorschläge.`:`${result.count||0} Spiel${result.count===1?"":"e"} sind in der Sammlung. Es wurde keine KI-Recherche gestartet.`);
  }catch(err){showMessage("Schnellerfassung fehlgeschlagen",err.message);}finally{setBusy(b,false);updateResearchControls();}
}

async function aiImageImport(files){
  files=[...files||[]];
  $("aiImageInput").value="";
  if(!files.length)return;
  if(currentMode!=="server"){showMessage("Nur im Server-Modus","Der Screenshot-Import läuft ausschließlich über das Docker-Backend und dein lokales Ollama.");return;}
  if(!aiEnabled||aiProvider!=="ollama"){showMessage("Ollama nicht aktiv","Für den Screenshot-Import muss AI_PROVIDER=ollama und AI_IMPORT_ENABLED=true gesetzt sein.");return;}
  if(files.length>4){showMessage("Zu viele Bilder","Bitte maximal 4 Screenshots gleichzeitig auswählen.");return;}
  const allowed=new Set(["image/jpeg","image/png","image/webp"]);
  for(const file of files){
    if(!allowed.has(file.type)){showMessage("Bildformat nicht unterstützt",`${file.name}: Für die KI-Auswertung bitte JPG, PNG oder WebP verwenden. HEIC kann weiterhin als normaler Anhang gespeichert werden.`);return;}
    if(file.size<1||file.size>10*1024*1024){showMessage("Bild zu groß",`${file.name}: maximal 10 MB pro Bild.`);return;}
  }
  const btn=$("aiImageButton");setBusy(btn,true,"Lese Bilder …");
  try{
    const result=await provider.aiFromImages(files,$("sourceUrlInput").value.trim());
    const d=result.game||{},warnings=Array.isArray(result.warnings)?result.warnings:[];
    const apply=await proposalDialog(d,warnings,{title:"Screenshot erkannt",intro:`${files.length} Bild(er) wurden lokal mit ${aiVisionModel||"dem Ollama-Vision-Modell"} ausgewertet. Es wird noch nichts gespeichert.`,applyLabel:"Vorschläge übernehmen"});
    if(apply)applyProposal(d);
  }catch(err){showMessage("Screenshot konnte nicht ausgewertet werden",err.message);}finally{setBusy(btn,false);}
}

async function aiImport(){
  const url=$("sourceUrlInput").value.trim();if(!url){showMessage("Link fehlt","Bitte zuerst einen HTTPS-Link zur Spielseite eintragen.");return;}
  if(currentMode!=="server"){showMessage("Nur im Server-Modus","Die Link-Auswertung läuft bewusst serverseitig, damit kein KI-API-Schlüssel im Browser gespeichert werden muss.");return;}
  const btn=$("aiImportButton");setBusy(btn,true,"Analysiere Link …");
  try{
    const result=await provider.aiFromUrl(url);const d=result.game||{};
    const warnings=Array.isArray(result.warnings)?result.warnings:[];
    const providerName=result.ai_provider==="ollama"?"lokalem Ollama":result.ai_provider==="openai"?"OpenAI":"KI";
    const intro=result.web_search_used?"Der direkte Abruf war nicht möglich; die konkrete Produktseite wurde über den aktivierten serverseitigen Websuche-Fallback ausgewertet. Es wird noch nichts gespeichert.":result.ai_used?`Strukturierte Seitendaten wurden serverseitig ausgewertet und mit ${providerName} bereinigt. Es wird noch nichts gespeichert.`:"Die Seite wurde serverseitig ohne KI ausgewertet. Es wird noch nichts gespeichert.";
    const apply=await proposalDialog(d,warnings,{intro});
    if(apply)applyProposal(d);
  }catch(err){showMessage("Link konnte nicht ausgewertet werden",err.message);}finally{setBusy(btn,false);}
}

async function rulesSearch(){
  if(currentMode!=="server"){showMessage("Nur im Server-Modus","Die Suche nach offiziellen Anleitungen läuft serverseitig.");return;}
  if(!rulesSearchEnabled){showMessage("Anleitungssuche deaktiviert","Die serverseitige Link-Auswertung ist deaktiviert.");return;}
  const game=formGame();if(!game.title){showMessage("Titel fehlt","Bitte zuerst den Spieltitel eintragen oder Daten aus dem Produkt-Link übernehmen.");return;}
  const btn=$("rulesSearchButton");setBusy(btn,true,"Suche Anleitung …");
  try{
    const result=await provider.searchRules(game);
    if(!result.rules_url){showMessage("Keine offizielle Anleitung gefunden",result.note||"Es wurde keine ausreichend sichere offizielle Quelle gefunden.");return;}
    const proposal={rules_url:result.rules_url};
    const notes=[result.note, result.source_name?`Quelle: ${result.source_name}`:"", result.web_search_used?"Die URL wurde per serverseitiger Websuche gefunden; bitte vor dem Speichern kurz öffnen und prüfen.":"Die URL wurde direkt auf der angegebenen Quellseite gefunden."].filter(Boolean);
    const apply=await proposalDialog(proposal,notes,{title:"Offizielle Anleitung gefunden",intro:"Die Anleitung wird nur als Link übernommen; fremde Regeltexte werden nicht kopiert.",applyLabel:"Anleitungs-Link übernehmen"});
    if(apply)applyProposal(proposal);
  }catch(err){showMessage("Anleitungs-Suche fehlgeschlagen",err.message);}finally{setBusy(btn,false);}
}

function downloadJson(data,name){const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});const file=new File([blob],name,{type:"application/json"});if(navigator.share&&navigator.canShare?.({files:[file]})){return navigator.share({files:[file],title:"Brettspielregal Backup"}).catch(()=>fallbackDownload(blob,name));}fallbackDownload(blob,name);}
function fallbackDownload(blob,name){const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=name;document.body.append(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},1000);}
async function exportCurrent(){try{const backup=await provider.exportData();await downloadJson(backup,`brettspielregal-${currentMode}-${new Date().toISOString().slice(0,10)}.json`);}catch(err){showMessage("Export fehlgeschlagen",err.message);}}
function strategyDialog(preview,context){
  return new Promise(resolve=>{
    $("strategyBody").innerHTML=`<p>${esc(context)}</p><p><strong>${preview.total}</strong> Spiele und <strong>${preview.attachments||0}</strong> Anhänge im Import<br>${preview.new} neu · ${preview.conflicts} Konflikte · ${preview.same} unverändert</p><p class="hint">„Ersetzen“ löscht alle aktuellen Spiele und Anhänge vor dem Import. „Zusammenführen“ behält andere Ziel-Datensätze; gleiche IDs aus dem Import werden übernommen.</p>`;
    const dlg=$("strategyDialog");
    const finish=v=>{cleanup();dlg.close();resolve(v);};
    const merge=()=>finish("merge"),replace=()=>finish("replace"),close=()=>finish(null);
    function cleanup(){$("mergeStrategyButton").removeEventListener("click",merge);$("replaceStrategyButton").removeEventListener("click",replace);$("closeStrategyButton").removeEventListener("click",close);dlg.removeEventListener("cancel",close);}
    $("mergeStrategyButton").addEventListener("click",merge);$("replaceStrategyButton").addEventListener("click",replace);$("closeStrategyButton").addEventListener("click",close);dlg.addEventListener("cancel",close);dlg.showModal();
  });
}
async function importFile(file){
  try{const backup=validateBackup(JSON.parse(await file.text()));const preview=await provider.previewImport(backup);const strategy=await strategyDialog(preview,`Backup v${backup.version} in den aktuell aktiven Speicher importieren?`);if(!strategy)return;await provider.importData(backup,strategy);await loadGames();showMessage("Import abgeschlossen",`${backup.data.games.length} Spiele und ${(backup.data.attachments||[]).length} Anhänge wurden verarbeitet.`);}catch(err){showMessage("Import fehlgeschlagen",err.message);}finally{$("importInput").value="";}
}
async function localToServer(){
  try{const local=new LocalProvider();const backup=await local.exportData();if(backup.data.games.length===0){showMessage("Keine lokalen Daten","Im lokalen Speicher sind keine Brettspiele vorhanden.");return;}const server=await makeServerProvider();const preview=await server.previewImport(backup);const strategy=await strategyDialog(preview,"Lokale Daten auf den Server übertragen? Der lokale Bestand bleibt dabei unverändert.");if(!strategy)return;await server.importData(backup,strategy);showMessage("Übertragung abgeschlossen",`${backup.data.games.length} Spiele und ${(backup.data.attachments||[]).length} Anhänge wurden an den Server übertragen.`);if(currentMode==="server")await loadGames();}catch(err){showMessage("Übertragung fehlgeschlagen",err.message);}
}
async function serverToLocal(){
  try{const server=await makeServerProvider();const backup=await server.exportData();const local=new LocalProvider();const preview=await local.previewImport(backup);const strategy=await strategyDialog(preview,"Serverdaten lokal übernehmen? Vor einem Ersetzen empfiehlt sich ein Export des aktuellen lokalen Bestands.");if(!strategy)return;if(strategy==="replace"&&confirm("Vor dem Ersetzen jetzt ein lokales Sicherheitsbackup exportieren?")){const old=await local.exportData();await downloadJson(old,`brettspielregal-lokal-vor-restore-${new Date().toISOString().slice(0,10)}.json`);}await local.importData(backup,strategy);showMessage("Lokale Übernahme abgeschlossen",`${backup.data.games.length} Spiele und ${(backup.data.attachments||[]).length} Anhänge wurden lokal übernommen.`);if(currentMode==="local")await loadGames();}catch(err){showMessage("Übernahme fehlgeschlagen",err.message);}
}

function setDiagnostic(id,label,kind="neutral"){const el=$(id);if(!el)return;el.textContent=label;el.className=`diagnostic-state ${kind}`;}
function resetDiagnostics(message="Nicht geprüft"){for(const id of ["diagBackend","diagApi","diagWorker","diagOllama","diagSearxng","diagCors"])setDiagnostic(id,message,"neutral");const hint=$("diagnosticHint");if(hint)hint.textContent="";}
function diagnosticAiLabel(ai={}){
  if(ai.status==="disabled")return ["deaktiviert","warn"];
  if(ai.status==="error")return ["Fehler","error"];
  if(ai.status==="model_missing")return [`Modell fehlt${ai.model?` · ${ai.model}`:""}`,"warn"];
  if(ai.provider==="ollama"&&ai.vision_model&&ai.vision_model_available===false)return [`Text OK · Vision fehlt`,"warn"];
  if(["ok","configured"].includes(ai.status))return [`OK${ai.model?` · ${ai.model}`:""}`,"ok"];
  return [ai.status||"unbekannt","warn"];
}
async function runSystemDiagnostics({showDialog=false}={}){
  const b=$("testConnectionButton");setBusy(b,true,"Prüfe …");
  const origin=window.location.origin;const originEl=$("diagnosticOrigin");if(originEl)originEl.textContent=`Frontend: ${origin}`;
  resetDiagnostics("Prüfe …");
  try{
    const srv=await makeServerProvider();
    const result=await srv.systemStatus();
    setDiagnostic("diagBackend","erreichbar","ok");
    setDiagnostic("diagApi",result.api?.status==="ok"?`OK · v${result.version||config.version}`:"Fehler",result.api?.status==="ok"?"ok":"error");
    const worker=result.worker||{};setDiagnostic("diagWorker",worker.status==="online"?"online":"offline",worker.status==="online"?"ok":"warn");
    const [aiLabel,aiKind]=diagnosticAiLabel(result.ai||{});setDiagnostic("diagOllama",aiLabel,aiKind);
    const search=result.search||{};setDiagnostic("diagSearxng",search.status==="ok"?"erreichbar":search.status==="disabled"?"deaktiviert":"Fehler",search.status==="ok"?"ok":search.status==="disabled"?"warn":"error");
    const cors=result.cors||{};
    if(cors.status==="not_required")setDiagnostic("diagCors","nicht nötig","ok");
    else if(cors.allowed)setDiagnostic("diagCors","erlaubt","ok");
    else setDiagnostic("diagCors","blockiert","error");
    const hints=[];
    if(worker.status!=="online")hints.push("Der Worker meldet keinen aktuellen Heartbeat.");
    if(result.ai?.error)hints.push(result.ai.error);
    if(search.error)hints.push(search.error);
    if(cors.invalid_entries?.length)hints.push(`Ungültige CORS-Einträge: ${cors.invalid_entries.join(", ")}`);
    if(cors.status==="not_required")hints.push("Frontend und API verwenden dieselbe Origin; CORS ist hier nicht erforderlich.");
    else if(cors.allowed)hints.push(`${origin} ist vom Backend als externe Frontend-Origin erlaubt.`);
    $("diagnosticHint").textContent=hints.join(" ");
    diagnosticsChecked=true;
    if(showDialog)showMessage("Systemstatus",`Backend und API sind erreichbar. Worker: ${worker.status==="online"?"online":"offline"}.`);
    return result;
  }catch(err){
    setDiagnostic("diagBackend","nicht erreichbar","error");setDiagnostic("diagApi","nicht erreichbar","error");setDiagnostic("diagWorker","–","neutral");setDiagnostic("diagOllama","–","neutral");setDiagnostic("diagSearxng","–","neutral");setDiagnostic("diagCors","prüfen","warn");
    $("diagnosticHint").textContent=`${err.message} Falls du GitHub Pages verwendest, muss ${origin} exakt in PWA_ALLOWED_ORIGINS stehen.`;
    if(showDialog)showMessage("Verbindung fehlgeschlagen",err.message);
    return null;
  }finally{setBusy(b,false);}
}

async function loadSetup(){
  serverConfig=await loadServerConnection();$("backendUrl").value=serverConfig.url||config.defaultApiUrl||"";$("cfClientId").value=serverConfig.clientId||"";$("cfClientSecret").value="";$("cfClientSecret").placeholder=serverConfig.clientSecret?"Gespeichert – zum Ersetzen neu eingeben":"Neu setzen oder leer lassen";
  if($("diagnosticOrigin"))$("diagnosticOrigin").textContent=`Frontend: ${window.location.origin}`;
  $("versionLabel").textContent=config.version;$("buildTargetLabel").textContent=isDocker()?"Docker Fullstack Build":"GitHub Pages PWA Build";
  $("serverConfigForm").classList.toggle("hidden",isDocker());
  $("researchSettingsDetails").classList.toggle("hidden",currentMode!=="server");
  if(currentMode==="server"){
    try{
      const r=await provider.researchSettings();
      $("primarySourcesInput").value=(r.primary_domains||[]).join("\n");
      $("referenceSourcesInput").value=(r.reference_domains||[]).join("\n");
      $("lowTrustSourcesInput").value=(r.low_trust_domains||[]).join("\n");
      $("researchSystemPromptInput").value=r.system_prompt||"";
      $("researchPromptInput").value=r.research_prompt||"";
      $("researchSettingsStatus").textContent="";
    }catch(err){$("researchSettingsStatus").textContent=err.message;}
    if(!diagnosticsChecked)runSystemDiagnostics().catch(()=>{});
  }else if(!isDocker()){resetDiagnostics("Server-Modus nötig");}
}
async function saveResearchSettings(event){
  event.preventDefault();const submit=$("researchSettingsForm").querySelector('button[type="submit"]');setBusy(submit,true,"Speichere …");
  try{
    const data=await provider.saveResearchSettings({
      primary_domains:$("primarySourcesInput").value.split(/\n+/).map(x=>x.trim()).filter(Boolean),
      reference_domains:$("referenceSourcesInput").value.split(/\n+/).map(x=>x.trim()).filter(Boolean),
      low_trust_domains:$("lowTrustSourcesInput").value.split(/\n+/).map(x=>x.trim()).filter(Boolean),
      system_prompt:$("researchSystemPromptInput").value,
      research_prompt:$("researchPromptInput").value,
    });
    $("primarySourcesInput").value=(data.primary_domains||[]).join("\n");$("referenceSourcesInput").value=(data.reference_domains||[]).join("\n");$("lowTrustSourcesInput").value=(data.low_trust_domains||[]).join("\n");
    $("researchSettingsStatus").textContent="Gespeichert. Neue Worker-Aufträge verwenden diese Einstellungen.";
  }catch(err){$("researchSettingsStatus").textContent=err.message;}finally{setBusy(submit,false);}
}
async function resetResearchSettings(){
  if(!confirm("Primärquellen und Prompts auf die v8.5-Standardwerte zurücksetzen?"))return;
  const b=$("resetResearchSettingsButton");setBusy(b,true,"Setze zurück …");
  try{await provider.resetResearchSettings();await loadSetup();$("researchSettingsStatus").textContent="Standardwerte wiederhergestellt.";}catch(err){$("researchSettingsStatus").textContent=err.message;}finally{setBusy(b,false);}
}
async function cleanupExistingTags(){
  if(currentMode!=="server")return;
  if(!confirm("Bestehende Tags auf die kontrollierte Tag-Liste normalisieren? Unbekannte freie Tags werden entfernt."))return;
  const b=$("cleanupTagsButton");setBusy(b,true,"Bereinige …");
  try{
    const result=await provider.cleanupTags();
    $("cleanupTagsStatus").textContent=`${result.changed_games||0} Spiele geändert · ${result.removed_tags||0} alte Tags entfernt.`;
    await loadGames();
  }catch(err){$("cleanupTagsStatus").textContent=err.message;}finally{setBusy(b,false);}
}

async function saveConnection(event){event.preventDefault();const url=normalizeUrl($("backendUrl").value);if(url&&!/^https:\/\//i.test(url)){showMessage("Ungültige Backend-URL","Im externen Pages-Frontend ist nur eine öffentliche HTTPS-Backend-URL vorgesehen.");return;}await saveServerConnection({url,clientId:$("cfClientId").value.trim(),clientSecret:$("cfClientSecret").value});diagnosticsChecked=false;if(currentMode==="server"){try{provider=await makeServerProvider();}catch{}}showMessage("Gespeichert","Die Server-Konfiguration wurde nur auf diesem Gerät gespeichert.");await loadSetup();if(currentMode==="server"){try{await refreshConfig();await loadGames();}catch{}}}
async function clearSecrets(){if(!confirm("Gespeicherte Cloudflare-Zugangsdaten auf diesem Gerät löschen?"))return;await wipeServerSecrets();await loadSetup();showMessage("Zugangsdaten gelöscht","Client ID und Client Secret wurden aus IndexedDB entfernt.");}
async function testConnection(){await runSystemDiagnostics({showDialog:true});}

async function testAi(){
  if(currentMode!=="server"){showMessage("Nur im Server-Modus","Im lokalen Pages-Modus wird bewusst keine KI angesprochen.");return;}
  const b=$("testAiButton");setBusy(b,true,"Teste KI …");
  try{
    const result=await provider.aiStatus();
    if(result.provider==="ollama"){
      const missing=[];
      if(!result.model_available)missing.push(`Textmodell ${result.model||aiModel}`);
      if(!result.vision_model_available)missing.push(`Bildmodell ${result.vision_model||aiVisionModel}`);
      if(missing.length)showMessage("Ollama erreichbar",`Ollama antwortet, aber folgende Modelle fehlen: ${missing.join(", ")}. Lade sie auf dem Ollama-Host mit „ollama pull …“.`);
      else showMessage("KI-Verbindung funktioniert",`Text: ${result.model||aiModel}
Bild: ${result.vision_model||aiVisionModel}
Beide Modelle sind vom Docker-Backend erreichbar.`);
    }else showMessage("KI-Verbindung funktioniert",`${result.provider||aiProvider}${result.model?` · ${result.model}`:""} ist vom Docker-Backend erreichbar.`);
  }catch(err){showMessage("KI-Verbindung fehlgeschlagen",err.message);}finally{setBusy(b,false);}
}

async function switchMode(mode){
  if(isDocker()||!config.allowLocalMode)return;if(mode===currentMode)return;setModeValue(mode);
  try{await selectProvider();await refreshConfig();await loadGames();startQueuePolling();showMessage("Betriebsmodus gewechselt",`Aktiv ist jetzt: ${modeLabel()}. Es wurden keine Daten zwischen Lokal und Server übertragen.`);}catch(err){showMessage("Server-Modus noch nicht bereit",err.message);showView("setup");}
  await loadSetup();
}
function showView(view){document.querySelectorAll(".view").forEach(v=>v.classList.toggle("active",v.id===`view${view[0].toUpperCase()+view.slice(1)}`));document.querySelectorAll(".nav-button").forEach(b=>b.classList.toggle("active",b.dataset.view===view));$("mainContent").focus();}

function bindEvents(){
  $("addGameButton").addEventListener("click",()=>openGame());$("emptyAddButton").addEventListener("click",()=>openGame());$("quickCaptureForm").addEventListener("submit",submitQuickCapture);$("quickCaptureUseAi")?.addEventListener("change",updateResearchControls);$("searchInput").addEventListener("input",renderGames);
  $("cleanupQueueButton")?.addEventListener("click",openQueueCleanup);$("closeQueueCleanupButton")?.addEventListener("click",()=>$("queueCleanupDialog")?.close());document.querySelectorAll("[data-cleanup-mode]").forEach(b=>b.addEventListener("click",()=>cleanupQueue(b.dataset.cleanupMode)));
  $("viewListButton").addEventListener("click",()=>setCollectionView("list"));$("viewShelfButton").addEventListener("click",()=>setCollectionView("shelf"));
  $("tagFilterButton").addEventListener("click",()=>{const panel=$("tagFilterPanel"),open=panel.classList.contains("hidden");panel.classList.toggle("hidden",!open);$("tagFilterButton").setAttribute("aria-expanded",String(open));if(open)renderTagFilters();});
  $("clearTagFiltersButton").addEventListener("click",()=>{selectedTagFilters.clear();localStorage.removeItem("brettspielregal-tag-filters");renderGames();});
  $("closeDetailDialog").addEventListener("click",()=>$("gameDetailDialog").close());
  $("gameDetailDialog").addEventListener("close",()=>releaseCovers("detail"));
  $("gameAttachmentInput").addEventListener("change",e=>{addPendingFiles(e.target.files||[]);e.target.value="";});
  $("detailAttachmentInput").addEventListener("change",e=>addDetailFiles([...e.target.files||[]]));
  $("closeGameDialog").addEventListener("click",()=>$("gameDialog").close());$("cancelGameButton").addEventListener("click",()=>$("gameDialog").close());$("gameForm").addEventListener("submit",saveGame);$("deleteGameButton").addEventListener("click",removeGame);$("aiImportButton").addEventListener("click",aiImport);$("aiImageButton").addEventListener("click",()=>$("aiImageInput").click());$("aiImageInput").addEventListener("change",e=>aiImageImport(e.target.files));$("rulesSearchButton").addEventListener("click",rulesSearch);$("coverUrlInput").addEventListener("input",renderCoverPreview);
  document.querySelectorAll(".nav-button").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.view)));document.querySelectorAll("[data-mode]").forEach(b=>b.addEventListener("click",()=>switchMode(b.dataset.mode)));
  $("serverConfigForm").addEventListener("submit",saveConnection);$("clearSecretsButton").addEventListener("click",clearSecrets);$("testConnectionButton").addEventListener("click",testConnection);$("testAiButton").addEventListener("click",testAi);$("researchSettingsForm").addEventListener("submit",saveResearchSettings);$("resetResearchSettingsButton").addEventListener("click",resetResearchSettings);$("cleanupTagsButton").addEventListener("click",cleanupExistingTags);$("exportButton").addEventListener("click",exportCurrent);$("importInput").addEventListener("change",e=>{if(e.target.files?.[0])importFile(e.target.files[0]);});$("localToServerButton").addEventListener("click",localToServer);$("serverToLocalButton").addEventListener("click",serverToLocal);
  const closeMsg=()=>$("messageDialog").close();$("closeMessageButton").addEventListener("click",closeMsg);$("messageOkButton").addEventListener("click",closeMsg);
  document.querySelectorAll("[data-first-mode]").forEach(b=>b.addEventListener("click",async()=>{$("firstRunDialog").close();setModeValue(b.dataset.firstMode);try{await selectProvider();await refreshConfig();await loadGames();startQueuePolling();}catch(err){showView("setup");showMessage("Server einrichten",err.message);}await loadSetup();if(pendingMagicImport){const p=pendingMagicImport;pendingMagicImport=null;await processMagicImport(p);}}));
  window.addEventListener("online",()=>currentMode==="server"&&loadGames());window.addEventListener("offline",()=>currentMode==="server"&&showBanner("Offline: Im Server-Modus sind Schreibaktionen erst wieder nach erfolgreicher Verbindung möglich."));
}

async function init(){
  bindEvents();updateViewButtons();renderTagPicker();$("versionLabel").textContent=config.version;
  pendingMagicImport=readMagicImport();
  if("serviceWorker" in navigator){navigator.serviceWorker.register("./service-worker.js").catch(()=>{});}
  if(!isDocker()&&config.allowLocalMode&&!selectedMode()){
    currentMode="local";provider=new LocalProvider();$("modeBadge").textContent="Lokal";await loadSetup();$("firstRunDialog").showModal();return;
  }
  try{await selectProvider();await refreshConfig();await loadGames();startQueuePolling();}catch(err){currentMode="server";$("modeBadge").textContent="Server";showBanner(err.message,"error");showView("setup");}
  await loadSetup();
  if(pendingMagicImport){const p=pendingMagicImport;pendingMagicImport=null;await processMagicImport(p);}
}
init();
