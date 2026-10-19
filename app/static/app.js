import {LocalProvider,ServerProvider,OfflineProvider,createOfflineSnapshot,readOfflineSnapshot,clearOfflineSnapshot,loadServerConnection,saveServerConnection,wipeServerSecrets,validateBackup} from "./providers.js";
import {decodeEanImageData,validEan} from "./ean-scanner.js";

const $=id=>document.getElementById(id);
const config=window.APP_CONFIG||{buildTarget:"shared",version:"9.1.3",defaultApiUrl:"",allowLocalMode:true};
let provider=null, currentMode="local", games=[], serverConfig=null, aiEnabled=false, rulesSearchEnabled=false, aiProvider="none", aiModel="", aiVisionModel="", rulesSearchProvider="none", autoEnrichEnabled=false, autoSearchProvider="none";
let importJobs=[], workerState={status:"offline",message:""}, queueTimer=null, queueFingerprint="", forceReleaseAfterSeconds=600, forceReleaseCancelGraceSeconds=15, diagnosticsChecked=false;
let collectionView=localStorage.getItem("brettspielregal-collection-view")==="shelf"?"shelf":"list", activeDetailGameId="", pendingFiles=[], pendingMagicImport=null;
const coverResources={list:{urls:[],observer:null,cleanup:null},detail:{urls:[],observer:null,cleanup:null}};
const DEFAULT_TAG_CATALOG={
  "Spielart":["Familienspiel","Kinderspiel","Kennerspiel","Expertenspiel","Partyspiel","Solospiel","Zweipersonenspiel","Kooperativ","Kompetitiv"],
  "Mechanik":["Deckbau","Kartenauswahl","Arbeitereinsatz","Plättchenlegen","Sets sammeln","Risikoabwägung","Handkartenmanagement","Gebietskontrolle","Kombinationsaufbau","Würfeln & Eintragen","Deduktion","Versteigerung","Stichspiel","Geschicklichkeit","Gedächtnis","Rätsel","Kampagne","Routenbau","Mehrheiten","Würfelspiel","Kartenspiel"],
  "Thema":["Fantasy","Science-Fiction","Abenteuer","Natur & Tiere","Historisch","Krimi","Wirtschaft","Weltraum","Eisenbahn","Städtebau","Landwirtschaft","Piraten","Horror"],
  "Eigenschaften":["Schnell gelernt","Kurze Partie","Lange Partie","Strategisch","Taktisch","Glückslastig","Hohe Interaktion","Wenig Interaktion","Asymmetrisch","Hoher Wiederspielwert","Reisetauglich"]
};
let tagCatalog=DEFAULT_TAG_CATALOG;
let selectedTagFilters=new Set((()=>{try{const v=JSON.parse(localStorage.getItem("brettspielregal-tag-filters")||"[]");return Array.isArray(v)?v:[];}catch{return [];}})());

let scannerStream=null,scanTimeout=null,scanInProgress=false,scannerSession=0;
const offlineReadOnly=()=>provider?.kind==="offline";
function updateOfflineUi(){
  document.body.classList.toggle("offline-read-only",offlineReadOnly());
  if(offlineReadOnly()){
    $("modeBadge").textContent="Offline · nur lesen";
    $("quickCaptureInput").disabled=true;$("submitQuickCaptureButton").disabled=true;
    showBanner("Offline-Regal: gespeicherte Momentaufnahme, nur Lesen. Unter Setup kannst du die Verbindung wiederherstellen.");
  }
}
async function updateOfflineStatus(){
  const snapshot=await readOfflineSnapshot();
  $("offlineSnapshotStatus").textContent=snapshot.meta?`${snapshot.meta.games} Spiele, ${snapshot.meta.covers} Cover · Stand ${new Date(snapshot.meta.saved_at).toLocaleString("de-CH")}`:"Noch keine Offline-Momentaufnahme auf diesem Gerät.";
  $("saveOfflineSnapshotButton").disabled=currentMode!=="server"||offlineReadOnly();
}
async function saveOfflineShelf(){
  if(currentMode!=="server"||offlineReadOnly()){showMessage("Server nötig","Offline-Momentaufnahmen können nur im verbundenen Server-Modus erstellt werden.");return;}
  const b=$("saveOfflineSnapshotButton");setBusy(b,true,"Speichere …");
  try{
    const meta=await createOfflineSnapshot(provider,(n,total)=>{$("offlineSnapshotStatus").textContent=`Lade Cover und Spiele: ${n}/${total}`;});
    await updateOfflineStatus();showMessage("Offline-Regal gespeichert",`${meta.games} Spiele und ${meta.covers} eigene Cover sind auf diesem Gerät schreibgeschützt verfügbar. Änderungen werden nicht offline gespeichert.`);
  }catch(err){showMessage("Offline-Sicherung fehlgeschlagen",err.message);}finally{setBusy(b,false);}
}
async function useOfflineSnapshot(reason){
  try{
    const snapshot=await readOfflineSnapshot();
    if(!snapshot.meta||!snapshot.games.length)return false;
    provider=new OfflineProvider(snapshot);currentMode="offline";games=await provider.list();
    if(queueTimer){clearInterval(queueTimer);queueTimer=null;}
    importJobs=[];renderQueue();renderLocations();renderGames();updateOfflineUi();
    showBanner(`Keine Verbindung (${reason}). Offline-Regal vom ${new Date(snapshot.meta.saved_at).toLocaleString("de-CH")} ist schreibgeschützt geöffnet.`);
    return true;
  }catch{return false;}
}
async function reconnectServer(){
  try{
    const server=await makeServerProvider();await server.health();
    provider=server;currentMode="server";updateOfflineUi();await refreshConfig();await loadGames();startQueuePolling();await updateOfflineStatus();
    showMessage("Wieder verbunden","Die Server-Sammlung ist wieder aktiv. Offline-Änderungen gab es keine.");
  }catch(err){showMessage("Noch keine Verbindung",err.message);}
}
async function deleteOfflineShelf(){
  if(!confirm("Offline-Momentaufnahme dieses Geräts löschen? Die Server-Sammlung bleibt unverändert."))return;
  await clearOfflineSnapshot();await updateOfflineStatus();
  if(offlineReadOnly()){games=[];renderGames();showBanner("Offline-Daten gelöscht. Bitte mit dem Server verbinden.","error");}
}
function stopScanner(){
  scannerSession++;
  scanInProgress=false;if(scanTimeout){clearTimeout(scanTimeout);scanTimeout=null;}
  for(const track of scannerStream?.getTracks?.()||[])track.stop();scannerStream=null;
  const video=$("barcodeVideo");if(video){video.pause();video.srcObject=null;}
}
function acceptScannedCode(code){
  const clean=String(code||"").replace(/\D/g,"");
  if(![8,12,13,14].includes(clean.length)){ $("barcodeStatus").textContent="EAN muss 8, 12, 13 oder 14 Ziffern haben.";return;}
  // Prüfziffer schützt davor, dass Bildrauschen als Barcode übernommen wird.
  if(!validEan(clean)){$("barcodeStatus").textContent="Die Prüfziffer der EAN stimmt nicht. Bitte Ziffern prüfen.";return;}
  stopScanner();$("barcodeDialog").close();$("quickAddText").value=clean;$("quickAddText").focus();
}
async function openBarcodeScanner(){
  stopScanner();
  const session=scannerSession;
  $("barcodeManual").value="";$("barcodeStatus").textContent="Prüfe Kamerazugriff …";
  $("barcodeDialog").showModal();
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){
    $("barcodeStatus").textContent="Kamera benötigt HTTPS und einen unterstützten Browser. Bitte EAN manuell eingeben.";return;
  }
  try{
    const stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:"environment"},width:{ideal:1280},height:{ideal:720}}});
    if(session!==scannerSession||!$("barcodeDialog").open){stream.getTracks().forEach(t=>t.stop());return;}
    scannerStream=stream;
    const video=$("barcodeVideo");video.srcObject=stream;await video.play();
    if(session!==scannerSession||!$("barcodeDialog").open){stopScanner();return;}
    scanInProgress=true;
    const canvas=document.createElement("canvas"),ctx=canvas.getContext("2d",{willReadFrequently:true});
    if(!ctx)throw new Error("Kamerabilder können nicht verarbeitet werden.");
    let nativeDetector=null;
    // Safari/iOS bietet BarcodeDetector teils an, erkennt aber keine Codes.
    // Dort niemals darauf warten: ausschließlich den lokalen Decoder nutzen.
    // Auf anderen Browsern bleibt der native Decoder eine optionale Ergänzung.
    const isIOS=/iPad|iPhone|iPod/i.test(navigator.userAgent)
      ||(navigator.platform==="MacIntel"&&navigator.maxTouchPoints>1);
    if(!isIOS&&"BarcodeDetector" in window){
      try{
        const supported=typeof BarcodeDetector.getSupportedFormats==="function"
          ?await BarcodeDetector.getSupportedFormats():["ean_13","ean_8","upc_a"];
        const formats=["ean_13","ean_8","upc_a","itf"].filter(f=>supported.includes(f));
        if(formats.length)nativeDetector=new BarcodeDetector({formats});
      }catch{/* Kein Problem: der lokale Decoder ist unabhängig davon. */}
    }
    $("barcodeStatus").textContent="EAN-Balken waagrecht und gut beleuchtet in die Mitte halten. Erkennung läuft direkt auf dem iPhone …";
    let lastValue="",repeats=0,frame=0;
    const scan=async()=>{
      if(session!==scannerSession||!scanInProgress||!$("barcodeDialog").open)return;
      try{
        if(video.readyState>=2&&video.videoWidth&&video.videoHeight){
          const scale=Math.min(1,1280/video.videoWidth);
          const w=Math.max(1,Math.round(video.videoWidth*scale));
          const h=Math.max(1,Math.round(video.videoHeight*scale));
          if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
          ctx.drawImage(video,0,0,w,h);
          const local=decodeEanImageData(ctx.getImageData(0,0,w,h));
          if(local&&validEan(local)){
            repeats=local===lastValue?repeats+1:1;lastValue=local;
            if(repeats>=2){acceptScannedCode(local);return;}
          }else{repeats=0;lastValue="";}
          // Weniger native Aufrufe: Safari kann bei detect(video) hängen.
          if(nativeDetector&&++frame%5===0){
            const hits=await nativeDetector.detect(video);
            if(session!==scannerSession)return;
            const match=hits.find(x=>validEan(String(x.rawValue||"")));
            if(match){acceptScannedCode(match.rawValue);return;}
          }
        }
      }catch{/* Einzelne Kameraframes können während Start/Fokus ungültig sein. */}
      if(session===scannerSession&&scanInProgress)scanTimeout=setTimeout(scan,280);
    };
    scan();
  }catch(err){
    if(session!==scannerSession)return;
    stopScanner();$("barcodeStatus").textContent=`Kamera/Erkennung nicht verfügbar: ${err.message}. Bitte EAN manuell eingeben.`;
  }
}
async function downloadFullZip(){
  if(currentMode!=="server")return showMessage("Nur Server","Das vollständige ZIP enthält die Docker-Daten. Im lokalen Pages-Modus bitte den JSON-Export verwenden.");
  const b=$("downloadFullZipButton");setBusy(b,true,"ZIP wird erstellt …");
  try{const blob=await provider.downloadFullZip();fallbackDownload(blob,`brettspielregal-full-${new Date().toISOString().slice(0,10)}.zip`);$("fullBackupStatus").textContent="ZIP erstellt. Kopie ausserhalb des Servers aufbewahren.";}
  catch(err){showMessage("ZIP-Backup fehlgeschlagen",err.message);}finally{setBusy(b,false);}
}
async function stageFullRestore(){
  if(currentMode!=="server")return showMessage("Nur Server","Ein vollständiger Restore ist nur im Docker-Servermodus verfügbar.");
  const file=$("fullZipRestoreFile").files?.[0];if(!file)return showMessage("ZIP fehlt","Bitte ein vollständiges Backup-ZIP auswählen.");
  if(!confirm("ZIP wird geprüft und für den nächsten vollständigen Stack-Neustart vorgemerkt. App UND Worker müssen anschließend gemeinsam neu gestartet werden. Fortfahren?"))return;
  const phrase=prompt('Zur Sicherheit RESTORE eingeben (damit wird die bestehende Sammlung beim nächsten gemeinsamen Stack-Neustart ersetzt):');
  if(phrase!=="RESTORE")return;
  const b=$("stageFullRestoreButton");setBusy(b,true,"Prüfe ZIP …");
  try{const token=$("fullRestoreToken").value;const out=await provider.restoreFullZip(file,token);$("fullRestoreToken").value="";$("fullBackupStatus").textContent=`Restore vorgemerkt: ${out.games} Spiele, ${out.attachments} Anhänge. Jetzt den GESAMTEN Portainer-Stack (App und Worker) stoppen und neu starten. Vor dem Ersetzen wird ein Backup erstellt.`;showMessage("Restore vorbereitet","Archiv und Prüfsummen sind gültig. Jetzt den gesamten Portainer-Stack mit App und Worker gemeinsam neu starten. Bis dahin wurden keine Live-Daten überschrieben.");}
  catch(err){showMessage("Restore-Prüfung fehlgeschlagen",err.message);}finally{setBusy(b,false);$("fullZipRestoreFile").value="";$("fullRestoreToken").value="";}
}
const APPROVAL_LABELS={min_players:"Spieler min.",max_players:"Spieler max.",play_time_min:"Spieldauer",min_age:"Alter",year:"Jahr",designer:"Designer",publisher:"Verlag",ean:"EAN",bgg_id:"BGG-ID"};
async function loadApprovalSettings(){
  const container=$("aiApprovalFields"),info=$("aiApprovalStatus");
  if(currentMode!=="server"){container.innerHTML="";info.textContent="Nur im Server-Modus verfügbar.";return;}
  try{
    const prefs=await provider.getApprovalSettings();$("aiApprovalEnabled").checked=!!prefs.enabled;
    container.innerHTML=(prefs.allowed_fields||[]).map(field=>`<label><input type="checkbox" data-approval-field="${esc(field)}" ${prefs.fields.includes(field)?"checked":""}> ${esc(APPROVAL_LABELS[field]||field)}</label>`).join("");
    info.textContent="Freigaben gelten nur für neue abgeschlossene Recherchen. Standard: aus.";
  }catch(err){info.textContent=err.message;}
}
async function saveApprovalSettings(){
  if(currentMode!=="server")return;
  const fields=[...document.querySelectorAll("[data-approval-field]:checked")].map(e=>e.dataset.approvalField);
  const btn=$("saveAiApprovalButton");setBusy(btn,true,"Speichere …");
  try{const prefs=await provider.saveApprovalSettings($("aiApprovalEnabled").checked,fields);$("aiApprovalStatus").textContent=prefs.enabled?`Aktiv für ${prefs.fields.length} erlaubte Felder; Widersprüche bleiben offen.`:"Automatische Freigabe ist ausgeschaltet.";}
  catch(err){$("aiApprovalStatus").textContent=err.message;}finally{setBusy(btn,false);}
}
const FILTER_IDS=["filterPlayers","filterDuration","filterAge","filterLocation","filterMissing"];
let advancedFilters={};
try{advancedFilters=JSON.parse(localStorage.getItem("brettspielregal-advanced-filters")||"{}");}catch{advancedFilters={};}
const getLocations=()=>[...new Set(games.map(g=>(g.storage_location||"").trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"de"));
function renderLocations(){
  const locations=getLocations();
  $("knownLocations").innerHTML=locations.map(x=>`<option value="${esc(x)}"></option>`).join("");
  const oldFilter=$("filterLocation").value||advancedFilters.filterLocation||"";
  $("filterLocation").innerHTML='<option value="">Alle Lagerorte</option>'+locations.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join("");
  $("filterLocation").value=locations.includes(oldFilter)?oldFilter:"";
  const ren=$("locationRenameFrom"),selected=ren.value;
  ren.innerHTML='<option value="">Lagerort auswählen …</option>'+locations.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join("");
  if(locations.includes(selected))ren.value=selected;
  $("locationManagerList").innerHTML=locations.length?locations.map(x=>`<div class="location-row"><span>📍 ${esc(x)}</span><small>${games.filter(g=>g.storage_location===x).length} Spiele</small></div>`).join(""):'<p class="hint">Noch keine Lagerorte vorhanden.</p>';
}
function advancedMatch(g){
  const players=Number($("filterPlayers").value),duration=Number($("filterDuration").value),age=Number($("filterAge").value),loc=$("filterLocation").value,missing=$("filterMissing").value;
  if(players&&!(g.min_players!=null&&g.max_players!=null&&g.min_players<=players&&g.max_players>=players))return false;
  if(duration&&!(g.play_time_min!=null&&g.play_time_min<=duration))return false;
  if(age&&!(g.min_age!=null&&g.min_age<=age))return false;
  if(loc&&g.storage_location!==loc)return false;
  if(missing==="cover"&&(imageAttachment(g)||g.cover_url))return false;
  if(missing==="rules"&&(g.attachments||[]).some(a=>a.kind==="rules"))return false;
  if(missing==="bgg"&&g.bgg_id)return false;
  return true;
}
function applyAdvancedFilters(){
  const n=FILTER_IDS.filter(id=>$(id).value).length;
  $("activeAdvancedFilters").textContent=n?`(${n} aktiv)`:"";
  advancedFilters=Object.fromEntries(FILTER_IDS.map(id=>[id,$(id).value]));
  localStorage.setItem("brettspielregal-advanced-filters",JSON.stringify(advancedFilters));
  renderGames();
}
async function renameLocation(){
  const oldName=$("locationRenameFrom").value,newName=$("locationRenameTo").value.trim();
  if(!oldName||!newName||oldName===newName){showMessage("Lagerort","Bitte einen bisherigen und neuen Lagerort eingeben.");return;}
  if(!confirm(`Lagerort „${oldName}“ bei allen zugehörigen Spielen durch „${newName}“ ersetzen?`))return;
  const btn=$("renameLocationButton");setBusy(btn,true,"Ändere …");
  try{const out=await provider.renameLocation(oldName,newName);await loadGames();$("locationRenameTo").value="";showMessage("Lagerort geändert",`${out.changed||0} Spiele aktualisiert.`);}catch(err){showMessage("Fehler",err.message);}finally{setBusy(btn,false);}
}
function openQuickAdd(){
  if(offlineReadOnly()){showMessage("Offline-Regal","Die gespeicherte Ansicht ist schreibgeschützt.");return;}
  $("quickAddAi").disabled=!researchAvailable();$("quickAddAi").checked=researchAvailable();
  $("quickAddLocation").value=localStorage.getItem("brettspielregal-last-location")||"";
  $("quickAddText").value="";$("quickAddDialog").showModal();
  setTimeout(()=>$('quickAddText').focus(),50);
}
async function submitQuickAdd(event){
  event.preventDefault();const text=$("quickAddText").value.trim(),loc=$("quickAddLocation").value.trim(),enrich=researchAvailable()&&$("quickAddAi").checked;
  if(!text)return;
  const b=$("quickAddForm").querySelector('[type="submit"]');setBusy(b,true,"Speichere …");
  try{
    let saved;
    if(currentMode==="server"){
      const result=await provider.quickCapture(text,loc,enrich);
      saved=result?.items?.[0]?.game;
    }else{
      const digits=text.replace(/\D/g,"");const isEan=/^[\d\s-]+$/.test(text)&&[8,12,13,14].includes(digits.length);
      const title=isEan?`EAN ${digits}`:text;
      saved=await provider.create({title,ean:isEan?digits:"",storage_location:loc},{autoEnrich:false});
    }
    localStorage.setItem("brettspielregal-last-location",loc);
    $("quickAddDialog").close();await loadGames();if(enrich)await refreshQueue();
    showMessage("Spiel erfasst",`${saved?.title||text} wurde zur Sammlung hinzugefügt.${enrich?" Die Recherche läuft im Hintergrund.":""}`);
  }catch(err){showMessage("Erfassung fehlgeschlagen",err.message);}finally{setBusy(b,false);}
}
async function archiveAsset(kind){
  const game=games.find(g=>g.id===$("gameId").value);
  if(!game||!$("gameDialog").open)return;
  const url=kind==="cover"?game.cover_url:game.rules_url;
  if(!safeHttpsUrl(url)){showMessage("Archivieren","Es ist kein gültiger HTTPS-Link gespeichert.");return;}
  if(!confirm(`${kind==="cover"?"Cover":"PDF-Anleitung"} von der externen Quelle in den ${currentMode==="server"?"Docker-Speicher":"lokalen Gerätespeicher"} übernehmen?`))return;
  const b=$(kind==="cover"?"archiveCoverButton":"archiveRulesButton");setBusy(b,true,"Lade herunter …");
  try{await provider.archiveAsset(game.id,kind,url);await loadGames();renderEditAttachments(games.find(g=>g.id===game.id));$("editActionStatus").textContent="Datei wurde lokal archiviert; Original-Link bleibt erhalten.";}
  catch(err){$("editActionStatus").textContent=err.message;}
  finally{setBusy(b,false);}
}

const FIELD_MAP=[
  ["title","Titel","titleInput"],["description","Beschreibung","descriptionInput"],["min_players","Spieler min.","minPlayersInput"],
  ["max_players","Spieler max.","maxPlayersInput"],["play_time_min","Spieldauer","playTimeInput"],["min_age","Mindestalter","minAgeInput"],
  ["publisher","Verlag","publisherInput"],["storage_location","Lagerort","storageLocationInput"],["year","Jahr","yearInput"],["designer","Autor / Designer","designerInput"],
  ["ean","EAN / GTIN","eanInput"],["bgg_id","BGG-ID","bggIdInput"],["award","Auszeichnung","awardInput"],["cover_url","Cover","coverUrlInput"],
  ["tags","Tags","tagsInput"],["rules_url","Anleitungs-Link","rulesUrlInput"],["rules_text","Kurzregeln","rulesTextInput"],
  ["source_url","Quelle","sourceUrlInput"]
];
const FIELD_LABELS=Object.fromEntries(FIELD_MAP.map(([key,label])=>[key,label]));

function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));}
function nl2br(s){return esc(s).replace(/\n/g,"<br>");}
function modeLabel(){return currentMode==="offline"?"Offline · nur lesen":currentMode==="server"?"Server":"Lokal";}
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
  $("queueList").querySelectorAll("[data-review-game]").forEach(b=>b.addEventListener("click",()=>{const game=games.find(g=>g.id===b.dataset.reviewGame);if(game)openGame(game);}));
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
    renderQueue();
    // Die Queue hat in der Sammlungsansicht keine Status-Badges mehr. Ein
    // komplettes Karten-Rendern bei jedem 8-Sekunden-Poll würde Blob-Cover
    // unnötig verwerfen und neu laden. Nur bei echten Spieldatenänderungen neu laden.
    if(forceGames||changed&&importJobs.some(j=>["done","review"].includes(j.status)))await loadGames();
  }catch(err){workerState={status:"offline",message:err.message};renderQueue();}
}
function startQueuePolling(){
  if(queueTimer){clearInterval(queueTimer);queueTimer=null;}
  if(researchAvailable()){refreshQueue();queueTimer=setInterval(()=>refreshQueue(),8000);}
}
async function loadGames(){
  showBanner("");
  try{games=await provider.list();renderLocations();renderGames();updateOfflineUi();}
  catch(err){
    if(currentMode==="server"&&(/nicht erreichbar|Zeitüberschreitung|network|offline|fetch/i.test(err.message)||!navigator.onLine)&&await useOfflineSnapshot(err.message))return;
    games=[];renderGames();showBanner(err.message,"error");
  }
}
function imageAttachment(game){
  const images=(game.attachments||[]).filter(a=>a.kind==="image");
  return images.find(a=>a.id===game.cover_attachment_id)||images[0]||null;
}
function coverHtml(game,classes="game-cover",attachment=null){
  const selected=attachment||imageAttachment(game);
  const initial=(game.title||"B").trim().slice(0,1).toLocaleUpperCase("de");
  if(selected){
    const nativeUrl=provider?.attachmentImageUrl?.(game.id,selected.id,classes.includes("game-cover"))||"";
    if(nativeUrl)return `<img class="${classes}" src="${esc(nativeUrl)}" alt="Cover von ${esc(game.title)}" decoding="async" referrerpolicy="no-referrer" data-native-cover data-cover-game="${esc(game.id)}" data-cover-id="${esc(selected.id)}" data-cover-initial="${esc(initial)}">`;
    return `<div class="${classes} game-cover-placeholder" data-attachment-id="${esc(selected.id)}" data-game-id="${esc(game.id)}" aria-label="Lade Bild"><span>${esc(initial)}</span></div>`;
  }
  const url=safeHttpsUrl(game.cover_url);
  if(url)return `<img class="${classes}" src="${esc(url)}" alt="Cover von ${esc(game.title)}" loading="lazy" referrerpolicy="no-referrer">`;
  return `<div class="${classes} game-cover-placeholder" aria-hidden="true"><span>${esc(initial)}</span></div>`;
}
function installNativeCoverFallback(root){
  root.querySelectorAll("img[data-native-cover]").forEach(img=>{
    img.addEventListener("error",()=>{
      if(!img.isConnected)return;
      if(!img.dataset.fullTried&&img.dataset.coverGame&&provider?.attachmentImageUrl){
        img.dataset.fullTried="1";
        const original=provider.attachmentImageUrl(img.dataset.coverGame,img.dataset.coverId,false);
        if(original&&original!==img.src){img.src=original;return;}
      }
      const ph=document.createElement("div");
      ph.className=`${img.className} game-cover-placeholder cover-load-error`.trim();
      ph.title="Eigenes Cover konnte nicht geladen werden.";
      ph.innerHTML=`<span>${esc(img.dataset.coverInitial||"!")}</span>`;
      img.replaceWith(ph);
    },{once:true});
  });
}
function releaseCovers(scope){
  const r=coverResources[scope];
  if(r.observer){r.observer.disconnect();r.observer=null;}
  if(r.cleanup){try{r.cleanup();}catch{}r.cleanup=null;}
  for(const url of r.urls)URL.revokeObjectURL(url);r.urls=[];
}
function hydrateCovers(scope){
  const root=scope==="list"?$("gameList"):$("detailBody");
  const resource=coverResources[scope];
  const fail=(node,message)=>{
    if(!node.isConnected||!root.contains(node))return;
    node.removeAttribute("data-loading");
    node.classList.add("cover-load-error");
    node.title=message;
    node.innerHTML=`<span aria-hidden="true">!</span><small>${esc(message)}</small>`;
  };
  const hydrate=async node=>{
    if(node.dataset.loading)return;node.dataset.loading="1";
    const gameId=node.dataset.gameId,attId=node.dataset.attachmentId,providerAtStart=provider;
    try{
      const blob=await providerAtStart.getAttachmentBlob(gameId,attId);
      if(provider!==providerAtStart||!node.isConnected||!root.contains(node))return;
      if(blob.type&&!blob.type.toLowerCase().startsWith("image/"))throw new Error("Der gespeicherte Anhang ist kein Bild.");
      const url=URL.createObjectURL(blob),img=document.createElement("img");
      resource.urls.push(url);
      img.className=node.className.replace("game-cover-placeholder","").replace("cover-load-error","").trim();
      img.alt="Gespeichertes Bild";
      img.loading=scope==="detail"?"eager":"lazy";
      img.decoding="async";
      img.onload=()=>{if(node.isConnected&&root.contains(node))node.replaceWith(img);};
      img.onerror=()=>{
        const mime=(blob.type||"").toLowerCase();
        const message=(mime.includes("heic")||mime.includes("heif"))
          ?"Bild gespeichert – HEIC/HEIF-Vorschau wird von diesem Browser nicht unterstützt."
          :"Bild gespeichert, aber die Vorschau konnte nicht dargestellt werden.";
        fail(node,message);
      };
      img.src=url;
    }catch(err){fail(node,err?.message||"Bild konnte nicht geladen werden.");}
  };
  const nodes=[...root.querySelectorAll("[data-attachment-id]")];
  // In der Detailansicht sind die Bilder zentraler Inhalt und werden sofort
  // geladen. Lazy Loading per IntersectionObserver bleibt nur für die Sammlung.
  if(scope==="detail"){
    for(const node of nodes)hydrate(node);
    return;
  }
  const isNearViewport=node=>{
    if(!node.isConnected||!root.contains(node))return false;
    const rect=node.getBoundingClientRect();
    const h=window.innerHeight||document.documentElement.clientHeight||0;
    return rect.bottom>=-320&&rect.top<=h+320;
  };
  if("IntersectionObserver" in window){
    resource.observer=new IntersectionObserver(entries=>{
      for(const entry of entries)if(entry.isIntersecting){resource.observer?.unobserve(entry.target);hydrate(entry.target);}
    },{rootMargin:"320px"});
    for(const node of nodes)resource.observer.observe(node);

    // Safari/iOS kann IntersectionObserver nach PWA-Tabwechseln oder bei zuvor
    // versteckten Ansichten verzögert auslösen. Sichtbare Cover deshalb sofort
    // prüfen und bei Scroll/Resize nochmals anstoßen. So bleibt die Sammlung
    // lazy, aber sichtbare eigene Cover erscheinen zuverlässig.
    let raf=0;
    const hydrateVisible=()=>{
      raf=0;
      for(const node of nodes){
        if(node.dataset.loading)continue;
        if(isNearViewport(node)){resource.observer?.unobserve(node);hydrate(node);}
      }
    };
    const schedule=()=>{if(!raf)raf=requestAnimationFrame(hydrateVisible);};
    window.addEventListener("scroll",schedule,{passive:true,capture:true});
    window.addEventListener("resize",schedule,{passive:true});
    const timer=setTimeout(schedule,180);
    resource.cleanup=()=>{
      clearTimeout(timer);
      if(raf)cancelAnimationFrame(raf);
      window.removeEventListener("scroll",schedule,true);
      window.removeEventListener("resize",schedule);
    };
    schedule();
  }else for(const node of nodes)hydrate(node);
}
function renderGames(){
  releaseCovers("list");
  const q=$("searchInput").value.trim().toLocaleLowerCase("de");
  const filtered=games.filter(g=>advancedMatch(g)&&(!q||[g.title,g.description,g.publisher,g.designer,g.ean,g.award,g.storage_location,g.notes,...(g.tags||[])].join(" ").toLocaleLowerCase("de").includes(q))&&tagFilterMatches(g));
  const narrowed=!!q||selectedTagFilters.size>0||FILTER_IDS.some(id=>$(id).value);
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
  updateViewButtons();renderTagFilters();installNativeCoverFallback(list);hydrateCovers("list");
}

function clearGameForm(){
  pendingFiles=[];$("gameAttachmentInput").value="";$("pendingAttachmentList").innerHTML="";$("existingAttachmentList").innerHTML="";$("attachmentFormStatus").textContent="";
  for(const id of ["gameId","bggIdInput","titleInput","sourceUrlInput","descriptionInput","minPlayersInput","maxPlayersInput","playTimeInput","minAgeInput","publisherInput","storageLocationInput","yearInput","designerInput","eanInput","awardInput","coverUrlInput","tagsInput","rulesUrlInput","rulesTextInput","notesInput"])$(id).value="";
  renderCoverPreview();renderTagPicker();
}
function renderCoverPreview(){
  const url=safeHttpsUrl($("coverUrlInput").value);
  const box=$("coverPreview");
  if(!url){box.classList.add("hidden");box.innerHTML="";return;}
  box.innerHTML=`<img src="${esc(url)}" alt="Cover-Vorschau" referrerpolicy="no-referrer"><span class="hint">Cover wird extern per HTTPS geladen und nicht in Backups eingebettet.</span>`;
  box.classList.remove("hidden");
}
function resetGameDialogToTop(){
  // <form class="dialog-card"> ist der eigentliche Scroll-Container, nicht
  // die dahinterliegende Sammlungsseite. Insbesondere Safari merkt sich sonst
  // die alte Position eines zuvor geöffneten Bearbeitungsdialogs.
  const dialog=$("gameDialog"), form=$("gameForm");
  if(!dialog.open)return;
  form.scrollTop=0;
  dialog.scrollTop=0;
}
function openGame(game=null){
  if(offlineReadOnly()){showMessage("Offline-Regal","Bearbeiten ist erst nach Wiederverbindung möglich.");return;}
  clearGameForm();$("deleteGameButton").classList.toggle("hidden",!game);$("gameDialogTitle").textContent=game?"Spiel bearbeiten":"Spiel erfassen";
  if(game){
    $("gameId").value=game.id;$("titleInput").value=game.title||"";$("sourceUrlInput").value=game.source_url||"";$("descriptionInput").value=game.description||"";
    $("minPlayersInput").value=game.min_players??"";$("maxPlayersInput").value=game.max_players??"";$("playTimeInput").value=game.play_time_min??"";$("minAgeInput").value=game.min_age??"";
    $("publisherInput").value=game.publisher||"";$("storageLocationInput").value=game.storage_location||"";$("yearInput").value=game.year??"";$("designerInput").value=game.designer||"";$("eanInput").value=game.ean||"";$("bggIdInput").value=game.bgg_id??"";$("awardInput").value=game.award||"";$("coverUrlInput").value=game.cover_url||"";
    $("tagsInput").value=(game.tags||[]).join(", ");$("rulesUrlInput").value=game.rules_url||"";$("rulesTextInput").value=game.rules_text||"";$("notesInput").value=game.notes||"";
    renderCoverPreview();
  }
  renderTagPicker();renderEditAttachments(game);
  $("editAdvancedTools").classList.toggle("hidden",!game);
  $("editAdvancedTools").open=!!game&&latestJobForGame(game.id)?.status==="review";
  $("editActionStatus").textContent="";
  $("archiveCoverButton").classList.toggle("hidden",!game||!safeHttpsUrl(game.cover_url));
  $("archiveRulesButton").classList.toggle("hidden",!game||!safeHttpsUrl(game.rules_url));
  renderEditReview(game);
  const researchRow=$("newGameResearchRow"),researchToggle=$("newGameAutoEnrich");
  const showResearch=!game&&currentMode==="server";
  if(researchRow&&researchToggle){researchRow.classList.toggle("hidden",!showResearch);
  if(showResearch){researchToggle.disabled=!researchAvailable();researchToggle.checked=researchAvailable();}}
  const dialog=$("gameDialog");
  dialog.showModal();
  if(game){
    // Beim Bearbeiten NICHT den Titel fokussieren: Unter einem aufgeklappten
    // KI-Bereich läge er weit unten; iOS/Safari scrollt dann automatisch dorthin.
    // Stattdessen den Dialogtitel ohne Scrollen fokussieren und die Formular-
    // Scrollposition nach dem Öffnen (auch im nächsten Frame) zurücksetzen.
    try{$("gameDialogTitle").focus({preventScroll:true});}catch{}
    resetGameDialogToTop();
    requestAnimationFrame(()=>resetGameDialogToTop());
  }else{
    resetGameDialogToTop();
    setTimeout(()=>$("titleInput").focus(),50);
  }
}
function sizeText(bytes){return bytes>=1024*1024?`${(bytes/1024/1024).toFixed(1)} MB`:`${Math.max(1,Math.ceil(bytes/1024))} KB`;}
function renderEditAttachments(game=null){
  const current=game?.attachments||[];
  $("pendingAttachmentList").innerHTML=pendingFiles.map((file,i)=>`<div class="attachment-row"><div class="attachment-row-copy"><strong>${esc(file.name)}</strong><small>Wird beim Speichern hinzugefügt · ${sizeText(file.size)}</small></div><button type="button" class="button" data-remove-pending="${i}">Entfernen</button></div>`).join("");
  $("pendingAttachmentList").querySelectorAll("[data-remove-pending]").forEach(b=>b.addEventListener("click",()=>{pendingFiles.splice(Number(b.dataset.removePending),1);renderEditAttachments(game);}));
  $("existingAttachmentList").innerHTML=current.map(a=>`<div class="attachment-row"><div class="attachment-row-copy"><strong>${a.kind==="rules"?"📄":"🖼️"} ${esc(a.filename)}</strong><small>Gespeichert · ${sizeText(a.size)}${a.kind==="image"&&game?.cover_attachment_id===a.id?" · Cover ✓":""}</small></div><div class="edit-attachment-actions"><button type="button" class="button" data-open-existing="${esc(a.id)}">${a.kind==="rules"?"Öffnen":"Ansehen"}</button>${a.kind==="rules"?`<button type="button" class="button" data-download-existing="${esc(a.id)}">Herunterladen</button>`:""}${a.kind==="image"?`<button type="button" class="button" data-cover-existing="${esc(a.id)}" ${game?.cover_attachment_id===a.id?"disabled":""}>${game?.cover_attachment_id===a.id?"Cover ✓":"Als Cover"}</button>`:""}<button type="button" class="button danger" data-delete-existing="${esc(a.id)}">Löschen</button></div></div>`).join("");
  const find=id=>current.find(a=>a.id===id);
  $("existingAttachmentList").querySelectorAll("[data-open-existing]").forEach(b=>b.addEventListener("click",()=>openStoredAttachment(game,find(b.dataset.openExisting))));
  $("existingAttachmentList").querySelectorAll("[data-download-existing]").forEach(b=>b.addEventListener("click",()=>downloadStoredAttachment(game,find(b.dataset.downloadExisting))));
  $("existingAttachmentList").querySelectorAll("[data-cover-existing]").forEach(b=>b.addEventListener("click",async()=>{
    try{const saved=games.find(g=>g.id===game.id);await provider.update(game.id,{...saved,cover_attachment_id:b.dataset.coverExisting});await loadGames();renderEditAttachments(games.find(g=>g.id===game.id));$("attachmentFormStatus").textContent="Cover wurde geändert.";}
    catch(err){$("attachmentFormStatus").textContent=err.message;}
  }));
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
function suggestionEvidenceMarkup(item){
  const ev=item?.evidence||{};
  const level=ev.level||"derived";
  const labels={primary:"🔵 Primärquelle",strong:"🟢 Gut belegt",single:"⚪ Eine Quelle",derived:"🟡 KI-abgeleitet",conflict:"🟠 Widerspruch"};
  const badge=`<span class="evidence-badge evidence-${esc(level)}">${esc(labels[level]||ev.label||"Hinweis")}</span>`;
  const summary=ev.summary?`<span class="evidence-summary">${esc(ev.summary)}</span>`:"";
  const supports=(ev.sources||[]).filter(x=>x&&x.name);
  const conflicts=(ev.conflicts||[]).filter(x=>x&&x.name);
  if(!supports.length&&!conflicts.length)return `<div class="suggestion-evidence-line">${badge}${summary}</div>`;
  const rows=[];
  if(supports.length)rows.push(`<div class="evidence-group"><strong>Belege</strong><ul>${supports.map(src=>`<li><span>${esc(src.name)}${src.source_label?` · ${esc(src.source_label)}`:""}</span>${src.value!==null&&src.value!==undefined&&src.value!==""?`<small>${esc(String(src.value))}</small>`:""}${safeHttpsUrl(src.url)?`<a href="${esc(src.url)}" target="_blank" rel="noopener noreferrer">Öffnen ↗</a>`:""}</li>`).join("")}</ul></div>`);
  if(conflicts.length)rows.push(`<div class="evidence-group evidence-conflicts"><strong>Abweichende Angaben</strong><ul>${conflicts.map(src=>`<li><span>${esc(src.name)}</span><small>${esc(String(src.value??"—"))}</small>${safeHttpsUrl(src.url)?`<a href="${esc(src.url)}" target="_blank" rel="noopener noreferrer">Öffnen ↗</a>`:""}</li>`).join("")}</ul></div>`);
  return `<div class="suggestion-evidence-line">${badge}${summary}<details class="suggestion-evidence-details"><summary>Belege ansehen</summary>${rows.join("")}</details></div>`;
}
function renderEditReview(game){
  const box=$("editReviewPanel");
  if(!game||currentMode!=="server"||offlineReadOnly()){box.innerHTML="";$("detailReEnrichButton").classList.add("hidden");$("detailApproveButton").classList.add("hidden");return;}
  const reviewJob=latestJobForGame(game.id);
  const pendingSuggestions=(reviewJob?.suggestions||[]).filter(x=>x.status==="pending");
  const needsReview=reviewJob?.status==="review"&&pendingSuggestions.length>0;
  const sourceItems=(reviewJob?.sources||[]).map(url=>{try{const u=new URL(url);return `<li><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(u.hostname.replace(/^www\./,""))}</a></li>`;}catch{return "";}}).join("");
  const research=reviewJob?.research||{};
  const identity=research.identity||null;
  const selectedResearch=(research.selected||[]).map(item=>{
    const label=item.title||item.url||"Quelle";const score=Number(item.post_fetch_score??item.score);const scoreText=Number.isFinite(score)?` · ${score} Punkte`:"";const sourceLabel=item.source_label||({primary:"Primärquelle",reference:"Referenzquelle",low:"niedrige Priorität"}[item.trust]||"Webquelle");
    const why=(item.post_fetch_reasons||[]).slice(0,3).join(" · ");
    return `<li><strong>${esc(label)}</strong><small>${esc(sourceLabel)}${esc(scoreText)}${why?` · ${esc(why)}`:""}</small>${safeHttpsUrl(item.url)?`<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">Öffnen ↗</a>`:""}</li>`;
  }).join("");
  const ignoredResearch=(research.ignored||[]).map(item=>{const score=Number(item.post_fetch_score??item.score);const sourceLabel=item.source_label?`${item.source_label} · `:"";const why=(item.post_fetch_reasons?.length?item.post_fetch_reasons:item.reasons||[]).join(" · ");return `<li><span>${esc(item.title||item.url||"Treffer")}</span><small>${esc(sourceLabel)}${Number.isFinite(score)?`${score} Punkte · `:""}${esc(why)}</small></li>`;}).join("");
  const researchPanel=(identity||selectedResearch||ignoredResearch)?`<div class="research-report"><div class="research-report-head"><strong>Quellenauswahl v8.8</strong><span>${esc(String(research.candidate_count||0))} Treffer geprüft</span></div>${identity?`<div class="identity-card"><span>Identifiziert über BoardGameGeek</span><strong>${esc(identity.title||identity.matched_name||"Brettspiel")}</strong><small>Übereinstimmung ${esc(String(identity.score||"?"))}% · BGG #${esc(String(identity.bgg_id||""))}</small></div>`:""}${selectedResearch?`<div class="research-list"><strong>Für Ollama ausgewählt</strong><ul>${selectedResearch}</ul></div>`:""}${ignoredResearch?`<details class="research-ignored"><summary>Verworfene Suchtreffer</summary><ul>${ignoredResearch}</ul></details>`:""}${research.bgg_error?`<p class="hint">BGG-Hinweis: ${esc(research.bgg_error)}</p>`:""}</div>`:"";
  const fmtSuggestion=(field,value)=>{if(value===null||value===undefined||value===""||(Array.isArray(value)&&!value.length))return "—";return valueText(field,value);};
  const safeSuggestionCount=pendingSuggestions.filter(item=>item?.evidence?.safe_to_apply===true).length;
  const suggestionRows=pendingSuggestions.map(item=>{
    const field=item.field,label=FIELD_LABELS[field]||field,current=game[field],proposed=item.value;
    const coverPreview=field==="cover_url"&&safeHttpsUrl(proposed)?`<img class="suggestion-cover" src="${esc(safeHttpsUrl(proposed))}" alt="KI-Covervorschlag" referrerpolicy="no-referrer">`:"";
    return `<div class="suggestion-row"><div class="suggestion-field"><strong>${esc(label)}</strong>${suggestionEvidenceMarkup(item)}</div><div class="suggestion-values"><div><small>Aktuell</small><span>${esc(fmtSuggestion(field,current))}</span></div><div class="suggestion-proposed"><small>KI-Vorschlag</small>${coverPreview}<span>${esc(fmtSuggestion(field,proposed))}</span></div></div><div class="suggestion-actions"><button type="button" class="button primary" data-apply-suggestion="${esc(field)}">Übernehmen</button><button type="button" class="button subtle" data-reject-suggestion="${esc(field)}">Verwerfen</button></div></div>`;
  }).join("");
  const safeAction=safeSuggestionCount?`<button type="button" class="button approve" data-apply-safe-suggestions>✓ Alle gut belegten übernehmen (${safeSuggestionCount})</button>`:"";
  const warningPanel=needsReview?`<section class="detail-panel review-panel"><div class="suggestion-head"><div><h4>KI-Vorschläge prüfen</h4><p class="hint">Noch nichts davon hat deine freigegebenen Spieldaten überschrieben. Übernimm nur, was passt.</p><div class="evidence-legend"><span>🔵 Primärquelle</span><span>🟢 Gut belegt</span><span>⚪ Eine Quelle</span><span>🟡 KI-abgeleitet</span><span>🟠 Widerspruch</span></div></div><span class="proposal-count">${pendingSuggestions.length}</span></div>${safeAction?`<div class="safe-apply-bar"><div><strong>Schnellfreigabe</strong><small>Übernimmt nur vom Backend als gut belegt markierte Felder. Widersprüche und KI-abgeleitete Texte bleiben offen.</small></div>${safeAction}</div>`:""}${researchPanel}${suggestionRows}${reviewJob.warnings?.length?`<div class="warning-box"><strong>Hinweise der Recherche</strong><ul>${reviewJob.warnings.map(w=>`<li>${esc(w)}</li>`).join("")}</ul></div>`:""}${sourceItems?`<details class="review-sources"><summary>Verwendete Recherchequellen</summary><ul>${sourceItems}</ul></details>`:""}<div class="suggestion-footer"><button type="button" class="button subtle" data-reject-all-suggestions>Alle verwerfen</button></div></section>`:"";

  box.innerHTML=warningPanel;
  $("detailApproveButton").classList.toggle("hidden",!needsReview);
  const refresh=async(applied=[])=>{
    await refreshQueue();await loadGames();
    const updated=games.find(g=>g.id===game.id);
    for(const field of applied){
      const found=FIELD_MAP.find(item=>item[0]===field);
      if(found&&updated){const val=updated[field];$(found[2]).value=Array.isArray(val)?val.join(", "):(val??"");}
    }
    renderCoverPreview();
    if(updated){$("archiveCoverButton").classList.toggle("hidden",!safeHttpsUrl(updated.cover_url));$("archiveRulesButton").classList.toggle("hidden",!safeHttpsUrl(updated.rules_url));}
    renderEditReview(updated);
  };
  const reportError=err=>{$("editActionStatus").textContent=err?.message||String(err);};
  $("detailApproveButton").onclick=needsReview?async()=>{
    if(!confirm("Alle offenen KI-Vorschläge übernehmen? Nicht gespeicherte Änderungen in den betroffenen Feldern werden ersetzt."))return;
    const b=$("detailApproveButton");setBusy(b,true,"Übernehme …");
    try{const result=await provider.applyImportSuggestions(reviewJob.id,null);await refresh(result?.applied||[]);$("editActionStatus").textContent="KI-Vorschläge übernommen.";}catch(err){reportError(err);}finally{setBusy(b,false);}
  }:null;
  if(needsReview){
    const safeButton=box.querySelector("[data-apply-safe-suggestions]");
    if(safeButton)safeButton.addEventListener("click",async()=>{setBusy(safeButton,true,"Übernehme …");try{const result=await provider.applySafeImportSuggestions(reviewJob.id);await refresh(result?.applied||[]);$("editActionStatus").textContent=`${result.applied?.length||0} gut belegte Felder übernommen.`;}catch(err){reportError(err);}finally{setBusy(safeButton,false);}});
    box.querySelectorAll("[data-apply-suggestion]").forEach(b=>b.addEventListener("click",async()=>{setBusy(b,true,"Übernehme …");try{const result=await provider.applyImportSuggestions(reviewJob.id,[b.dataset.applySuggestion]);await refresh(result?.applied||[]);}catch(err){reportError(err);}finally{setBusy(b,false);}}));
    box.querySelectorAll("[data-reject-suggestion]").forEach(b=>b.addEventListener("click",async()=>{setBusy(b,true,"Verwerfe …");try{await provider.rejectImportSuggestions(reviewJob.id,[b.dataset.rejectSuggestion]);await refresh();}catch(err){reportError(err);}finally{setBusy(b,false);}}));
    box.querySelectorAll("[data-reject-all-suggestions]").forEach(b=>b.addEventListener("click",async()=>{if(!confirm("Alle offenen KI-Vorschläge für dieses Spiel verwerfen?"))return;setBusy(b,true,"Verwerfe …");try{await provider.rejectImportSuggestions(reviewJob.id,null);await refresh();}catch(err){reportError(err);}finally{setBusy(b,false);}}));
  }
  const canReEnrich=autoEnrichEnabled&&!needsReview&&!["queued","running"].includes(reviewJob?.status);
  $("detailReEnrichButton").classList.toggle("hidden",!canReEnrich);
  $("detailReEnrichButton").onclick=canReEnrich?async()=>{
    if(!confirm("Recherche neu starten? Nicht gespeicherte Änderungen im Bearbeitungsformular gehen verloren."))return;
    const b=$("detailReEnrichButton");setBusy(b,true,"Reihe ein …");
    try{await provider.enqueueEnrichment(game.id,game.ean||game.title,false);await refreshQueue();$("gameDialog").close();showView("import");}
    catch(err){reportError(err);}finally{setBusy(b,false);}
  }:null;
}

function openGameDetail(gameId){
  if(offlineReadOnly())$("detailAttachmentStatus").textContent="Offline-Momentaufnahme · schreibgeschützt";
  const game=games.find(g=>g.id===gameId);if(!game)return;
  activeDetailGameId=gameId;releaseCovers("detail");$("detailAttachmentStatus").textContent="";
  const chips=[];
  if(game.min_players||game.max_players)chips.push(detailChip(`${game.min_players||"?"}–${game.max_players||game.min_players||"?"} Spieler`,"core"));
  if(game.play_time_min)chips.push(detailChip(`${game.play_time_min} Min.`,"core"));
  if(game.min_age!==null&&game.min_age!==undefined&&game.min_age!=="")chips.push(detailChip(`ab ${game.min_age}`,"core"));
  if(game.award)chips.push(detailChip(game.award,"award"));
  const facts=[["Lagerort",game.storage_location],["Verlag",game.publisher],["Jahr",game.year],["Autor / Designer",game.designer],["EAN / GTIN",game.ean],["BGG-ID",game.bgg_id]].filter(([,v])=>v!==null&&v!==undefined&&v!=="");
  const images=(game.attachments||[]).filter(a=>a.kind==="image"),pdfs=(game.attachments||[]).filter(a=>a.kind==="rules"),selected=imageAttachment(game);
  const imageGallery=images.length?`<div class="attachment-gallery">${images.map(a=>`<div class="attachment-tile ${selected?.id===a.id?"cover-selected":""}">${coverHtml(game,"tile-image",a)}<strong>${esc(a.filename)}</strong><div class="attachment-actions"><button class="button" type="button" data-open-attachment="${esc(a.id)}">Ansehen</button></div></div>`).join("")}</div>`:"";
  const pdfList=pdfs.length?`<div class="attachment-pdf-list">${pdfs.map(a=>`<div class="attachment-pdf"><span aria-hidden="true">📄</span><div class="attachment-row-copy"><strong>${esc(a.filename)}</strong><small>${sizeText(a.size)} · PDF</small></div><div class="attachment-actions"><button class="button" type="button" data-open-attachment="${esc(a.id)}">Öffnen</button></div></div>`).join("")}</div>`:"";
  const links=[["Produkt- oder Quellseite",game.source_url],["Online-Anleitung",game.rules_url]].filter(([,url])=>safeHttpsUrl(url));
  const reviewJob=latestJobForGame(game.id);
  const needsReview=reviewJob?.status==="review"&&(reviewJob?.suggestions||[]).some(x=>x.status==="pending");
  $("detailTitle").textContent=game.title||"Spiel";
  const tagPanel=(game.tags||[]).length?`<section class="detail-panel"><h4>Tags</h4><div class="detail-tag-groups">${detailTagGroups(game.tags)}</div></section>`:"";
  $("detailBody").innerHTML=`<div class="detail-hero">${coverHtml(game,"detail-cover")}<div class="detail-copy"><h3>${esc(game.title)}</h3><p class="detail-description">${esc(game.description||"Noch keine Beschreibung hinterlegt.")}</p><div class="detail-meta">${chips.join("")}</div></div></div><div class="detail-panels">${needsReview&&!offlineReadOnly()?`<p class="review-readonly-hint">KI-Vorschläge warten auf Prüfung. Öffne <strong>Bearbeiten</strong>, um sie zu prüfen.</p>`:""}<section class="detail-panel"><h4>Auf einen Blick</h4><div class="detail-grid">${facts.length?facts.map(([name,value])=>`<div class="detail-item"><span>${esc(name)}</span><strong>${esc(value)}</strong></div>`).join(""):`<p class="hint">Noch keine weiteren Angaben.</p>`}</div></section>${tagPanel}<section class="detail-panel"><h4>Eigene Anhänge (${images.length+pdfs.length})</h4>${imageGallery}${pdfList}${images.length+pdfs.length===0?`<p class="hint">Noch keine Bilder oder PDF-Anleitungen hochgeladen.</p>`:""}</section>${links.length?`<section class="detail-panel"><h4>Externe Links</h4>${links.map(([name,url])=>`<a class="detail-link" href="${esc(safeHttpsUrl(url))}" target="_blank" rel="noopener noreferrer">${esc(name)} ↗</a>`).join("")}</section>`:""}${game.rules_text?`<section class="detail-panel"><h4>Kurzregeln</h4><p class="detail-notes">${esc(game.rules_text)}</p></section>`:""}${game.notes?`<section class="detail-panel"><h4>Notizen</h4><p class="detail-notes">${esc(game.notes)}</p></section>`:""}</div>`;
  installNativeCoverFallback($("detailBody"));
  $("detailEditButton").onclick=()=>{$("gameDetailDialog").close();releaseCovers("detail");openGame(game);};
  const find=id=>(game.attachments||[]).find(a=>a.id===id);
  $("detailBody").querySelectorAll("[data-open-attachment]").forEach(b=>b.addEventListener("click",()=>openStoredAttachment(game,find(b.dataset.openAttachment))));
  const detailDialog=$("gameDetailDialog");
  if(!detailDialog.open)detailDialog.showModal();
  // Erst nach dem Öffnen laden. Safari/iOS erkennt Bilder in einem geschlossenen
  // <dialog> sonst nicht zuverlässig als sichtbar.
  requestAnimationFrame(()=>hydrateCovers("detail"));
}
async function downloadStoredAttachment(game,att){
  if(!att)return;
  try{const blob=await provider.getAttachmentBlob(game.id,att.id),url=URL.createObjectURL(blob);
    const a=document.createElement("a");a.href=url;a.download=att.filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
  }catch(err){($("gameDialog").open?$("attachmentFormStatus"):$("detailAttachmentStatus")).textContent=err.message;}
}
async function openStoredAttachment(game,att){
  if(!att)return;
  const tab=window.open("about:blank","_blank");if(tab)tab.opener=null;
  try{const blob=await provider.getAttachmentBlob(game.id,att.id),url=URL.createObjectURL(blob);
    if(tab){tab.location.href=url;setTimeout(()=>URL.revokeObjectURL(url),300000);}
    else{const a=document.createElement("a");a.href=url;a.download=att.filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);}
  }catch(err){tab?.close();($("gameDialog").open?$("attachmentFormStatus"):$("detailAttachmentStatus")).textContent=err.message;}
}
function formGame(){return {
  title:$("titleInput").value.trim(),source_url:$("sourceUrlInput").value.trim(),description:$("descriptionInput").value.trim(),
  min_players:inputNumber("minPlayersInput"),max_players:inputNumber("maxPlayersInput"),play_time_min:inputNumber("playTimeInput"),min_age:inputNumber("minAgeInput"),
  publisher:$("publisherInput").value.trim(),storage_location:$("storageLocationInput").value.trim(),year:inputNumber("yearInput"),designer:$("designerInput").value.trim(),ean:$("eanInput").value.replace(/\s+/g,"").trim(),bgg_id:inputNumber("bggIdInput"),award:$("awardInput").value.trim(),cover_url:$("coverUrlInput").value.trim(),
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
function fallbackDownload(blob,name){const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=name;document.body.append(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},60000);}
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
function resetDiagnostics(message="Nicht geprüft"){for(const id of ["diagBackend","diagApi","diagWorker","diagOllama","diagSearxng","diagCors","diagBgg","diagSqlite","diagFiles","diagDisk","diagBackup"])setDiagnostic(id,message,"neutral");const hint=$("diagnosticHint");if(hint)hint.textContent="";}
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
    const storage=result.storage||{};
    setDiagnostic("diagBgg",result.bgg?.status==="configured"?"Token hinterlegt":"ohne Token",result.bgg?.status==="configured"?"ok":"warn");
    setDiagnostic("diagSqlite",storage.database==="ok"?`OK · Schema ${storage.schema_version}`:"Fehler",storage.database==="ok"?"ok":"error");
    setDiagnostic("diagFiles",storage.status==="ok"?`${storage.attachments} Dateien · ${storage.games} Spiele`:"Fehler",storage.status==="ok"?"ok":"error");
    setDiagnostic("diagDisk",Number.isFinite(storage.free_bytes)?`${(storage.free_bytes/1024**3).toFixed(1)} GB frei`:"–",Number.isFinite(storage.free_bytes)?"ok":"warn");
    setDiagnostic("diagBackup",storage.last_full_backup?new Date(storage.last_full_backup*1000).toLocaleDateString("de-CH"):"noch keines",storage.last_full_backup?"ok":"warn");
    const hints=[];
    if(storage.restore_pending)hints.push("Vollständiger ZIP-Restore ist für den nächsten gemeinsamen Stack-Neustart vorgemerkt.");
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
  updateOfflineStatus().catch(()=>{});loadApprovalSettings().catch(()=>{});
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
function showView(view){
  localStorage.setItem("brettspielregal-last-view",view);
  document.querySelectorAll(".view").forEach(v=>v.classList.toggle("active",v.id===`view${view[0].toUpperCase()+view.slice(1)}`));
  document.querySelectorAll(".nav-button").forEach(b=>b.classList.toggle("active",b.dataset.view===view));
  if(view==="collection")requestAnimationFrame(()=>renderGames());
  $("mainContent").focus();
}

function bindEvents(){
  $("openScannerButton").addEventListener("click",openBarcodeScanner);
  $("closeBarcode").addEventListener("click",()=>$("barcodeDialog").close());
  $("barcodeDialog").addEventListener("close",stopScanner);
  $("barcodeUseManual").addEventListener("click",()=>acceptScannedCode($("barcodeManual").value));
  document.addEventListener("visibilitychange",()=>{if(document.hidden&&$("barcodeDialog").open)$("barcodeDialog").close();});
  $("saveOfflineSnapshotButton").addEventListener("click",saveOfflineShelf);
  $("reconnectServerButton").addEventListener("click",reconnectServer);
  $("deleteOfflineSnapshotButton").addEventListener("click",deleteOfflineShelf);
  $("downloadFullZipButton").addEventListener("click",downloadFullZip);
  $("stageFullRestoreButton").addEventListener("click",stageFullRestore);
  $("saveAiApprovalButton").addEventListener("click",saveApprovalSettings);
  $("quickAddFab").addEventListener("click",openQuickAdd);
  $("closeQuickAdd").addEventListener("click",()=>$("quickAddDialog").close());
  $("quickAddForm").addEventListener("submit",submitQuickAdd);
  $("quickAddLink").addEventListener("click",()=>{$("quickAddDialog").close();openGame();$("sourceUrlInput").focus();});
  $("quickAddPhoto").addEventListener("click",()=>{$("quickAddDialog").close();openGame();$("gameAttachmentInput").click();});
  $("archiveCoverButton").addEventListener("click",()=>archiveAsset("cover"));
  $("archiveRulesButton").addEventListener("click",()=>archiveAsset("rules"));
  $("renameLocationButton").addEventListener("click",renameLocation);
  for(const id of FILTER_IDS){$(id).addEventListener("change",applyAdvancedFilters);}
  $("resetAdvancedFilters").addEventListener("click",()=>{for(const id of FILTER_IDS)$(id).value="";applyAdvancedFilters();});

  $("addGameButton").addEventListener("click",()=>openGame());$("emptyAddButton").addEventListener("click",()=>openGame());$("quickCaptureForm").addEventListener("submit",submitQuickCapture);$("quickCaptureUseAi")?.addEventListener("change",updateResearchControls);$("searchInput").addEventListener("input",renderGames);
  $("cleanupQueueButton")?.addEventListener("click",openQueueCleanup);$("closeQueueCleanupButton")?.addEventListener("click",()=>$("queueCleanupDialog")?.close());document.querySelectorAll("[data-cleanup-mode]").forEach(b=>b.addEventListener("click",()=>cleanupQueue(b.dataset.cleanupMode)));
  $("viewListButton").addEventListener("click",()=>setCollectionView("list"));$("viewShelfButton").addEventListener("click",()=>setCollectionView("shelf"));
  $("tagFilterButton").addEventListener("click",()=>{const panel=$("tagFilterPanel"),open=panel.classList.contains("hidden");panel.classList.toggle("hidden",!open);$("tagFilterButton").setAttribute("aria-expanded",String(open));if(open)renderTagFilters();});
  $("clearTagFiltersButton").addEventListener("click",()=>{selectedTagFilters.clear();localStorage.removeItem("brettspielregal-tag-filters");renderGames();});
  $("closeDetailDialog").addEventListener("click",()=>$("gameDetailDialog").close());
  $("gameDetailDialog").addEventListener("close",()=>releaseCovers("detail"));
  $("gameAttachmentInput").addEventListener("change",e=>{addPendingFiles(e.target.files||[]);e.target.value="";});
  $("closeGameDialog").addEventListener("click",()=>$("gameDialog").close());$("cancelGameButton").addEventListener("click",()=>$("gameDialog").close());$("gameForm").addEventListener("submit",saveGame);$("deleteGameButton").addEventListener("click",removeGame);$("aiImportButton").addEventListener("click",aiImport);$("aiImageButton").addEventListener("click",()=>$("aiImageInput").click());$("aiImageInput").addEventListener("change",e=>aiImageImport(e.target.files));$("rulesSearchButton").addEventListener("click",rulesSearch);$("coverUrlInput").addEventListener("input",renderCoverPreview);
  document.querySelectorAll(".nav-button").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.view)));document.querySelectorAll("[data-mode]").forEach(b=>b.addEventListener("click",()=>switchMode(b.dataset.mode)));
  $("serverConfigForm").addEventListener("submit",saveConnection);$("clearSecretsButton").addEventListener("click",clearSecrets);$("testConnectionButton").addEventListener("click",testConnection);$("testAiButton").addEventListener("click",testAi);$("researchSettingsForm").addEventListener("submit",saveResearchSettings);$("resetResearchSettingsButton").addEventListener("click",resetResearchSettings);$("cleanupTagsButton").addEventListener("click",cleanupExistingTags);$("exportButton").addEventListener("click",exportCurrent);$("importInput").addEventListener("change",e=>{if(e.target.files?.[0])importFile(e.target.files[0]);});$("localToServerButton").addEventListener("click",localToServer);$("serverToLocalButton").addEventListener("click",serverToLocal);
  const closeMsg=()=>$("messageDialog").close();$("closeMessageButton").addEventListener("click",closeMsg);$("messageOkButton").addEventListener("click",closeMsg);
  document.querySelectorAll("[data-first-mode]").forEach(b=>b.addEventListener("click",async()=>{$("firstRunDialog").close();setModeValue(b.dataset.firstMode);try{await selectProvider();await refreshConfig();await loadGames();startQueuePolling();}catch(err){showView("setup");showMessage("Server einrichten",err.message);}await loadSetup();if(pendingMagicImport){const p=pendingMagicImport;pendingMagicImport=null;await processMagicImport(p);}}));
  window.addEventListener("online",()=>{if(currentMode==="server")loadGames();else if(offlineReadOnly())showBanner("Verbindung möglicherweise wieder verfügbar. Unter Setup auf ‚Wieder verbinden‘ tippen.");});window.addEventListener("offline",()=>currentMode==="server"&&showBanner("Offline: Im Server-Modus sind Schreibaktionen erst wieder nach erfolgreicher Verbindung möglich."));
}

async function init(){
  bindEvents();for(const id of FILTER_IDS){if(id!=="filterLocation")$(id).value=advancedFilters[id]||"";}updateViewButtons();renderTagPicker();$("versionLabel").textContent=config.version;
  pendingMagicImport=readMagicImport();
  if("serviceWorker" in navigator){navigator.serviceWorker.register("./service-worker.js").catch(()=>{});}
  if(!isDocker()&&config.allowLocalMode&&!selectedMode()){
    currentMode="local";provider=new LocalProvider();$("modeBadge").textContent="Lokal";await loadSetup();$("firstRunDialog").showModal();return;
  }
  try{await selectProvider();await refreshConfig();await loadGames();startQueuePolling();}catch(err){
    if(!(await useOfflineSnapshot(err.message))){currentMode="server";$("modeBadge").textContent="Server";showBanner(err.message,"error");showView("setup");}
  }
  await loadSetup();
  const view=localStorage.getItem("brettspielregal-last-view");if(["collection","import","setup"].includes(view))showView(view);
  if(pendingMagicImport){const p=pendingMagicImport;pendingMagicImport=null;await processMagicImport(p);}
}
init();
