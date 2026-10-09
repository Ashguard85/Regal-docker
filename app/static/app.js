import {LocalProvider,ServerProvider,loadServerConnection,saveServerConnection,wipeServerSecrets,validateBackup} from "./providers.js";

const $=id=>document.getElementById(id);
const config=window.APP_CONFIG||{buildTarget:"shared",version:"4.0.0",defaultApiUrl:"",allowLocalMode:true};
let provider=null, currentMode="local", games=[], serverConfig=null, aiEnabled=false, rulesSearchEnabled=false, aiProvider="none", aiModel="", rulesSearchProvider="none", collectionView=localStorage.getItem("brettspielregal-collection-view")||"list", activeDetailGameId="";

const FIELD_MAP=[
  ["title","Titel","titleInput"],["description","Beschreibung","descriptionInput"],["min_players","Spieler min.","minPlayersInput"],
  ["max_players","Spieler max.","maxPlayersInput"],["play_time_min","Spieldauer","playTimeInput"],["min_age","Mindestalter","minAgeInput"],
  ["publisher","Verlag","publisherInput"],["year","Jahr","yearInput"],["designer","Autor / Designer","designerInput"],
  ["ean","EAN / GTIN","eanInput"],["award","Auszeichnung","awardInput"],["cover_url","Cover","coverUrlInput"],
  ["tags","Tags","tagsInput"],["rules_url","Anleitungs-Link","rulesUrlInput"],["rules_text","Kurzregeln","rulesTextInput"],
  ["source_url","Quelle","sourceUrlInput"]
];

function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));}
function nl2br(s){return esc(s).replace(/\n/g,"<br>");}
function modeLabel(){return currentMode==="server"?"Server":"Lokal";}
function isDocker(){return config.buildTarget==="docker";}
function selectedMode(){return isDocker()?"server":(localStorage.getItem("brettspielregal-mode")||"");}
function setCollectionView(view){collectionView=view==="shelf"?"shelf":"list";localStorage.setItem("brettspielregal-collection-view",collectionView);updateCollectionViewButtons();renderGames();}
function updateCollectionViewButtons(){const listBtn=$("viewListButton"), shelfBtn=$("viewShelfButton"); if(!listBtn||!shelfBtn)return; const listActive=collectionView!=="shelf"; listBtn.classList.toggle("active",listActive); shelfBtn.classList.toggle("active",!listActive); listBtn.setAttribute("aria-selected", String(listActive)); shelfBtn.setAttribute("aria-selected", String(!listActive));}
function setModeValue(mode){if(!isDocker())localStorage.setItem("brettspielregal-mode",mode);currentMode=mode;}
function setBusy(button,busy,label="Bitte warten …"){if(!button)return;if(busy){button.dataset.oldText=button.textContent;button.textContent=label;button.disabled=true;}else{button.textContent=button.dataset.oldText||button.textContent;button.disabled=false;}}
function showBanner(message,type="info"){const el=$("statusBanner");if(!message){el.className="status-banner hidden";el.textContent="";return;}el.className=`status-banner${type==="error"?" error":""}`;el.textContent=message;}
function showMessage(title,message){$("messageTitle").textContent=title;$("messageBody").innerHTML=`<p>${nl2br(message)}</p>`;$("messageDialog").showModal();}
function normalizeUrl(url){return (url||"").trim().replace(/\/$/,"");}
function inputNumber(id){const v=$(id).value;return v===""?null:Number(v);}
function safeHttpsUrl(value){try{const u=new URL(String(value||""));return u.protocol==="https:"?u.href:"";}catch{return "";}}
function valueText(key,value){if(Array.isArray(value))return value.join(", ");if(value===null||value===undefined)return "";if(key==="play_time_min"&&value)return `${value} Min.`;if(key==="min_age"&&value!=="")return `ab ${value}`;return String(value);}

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
    rulesSearchProvider=c.rules_search_provider||"none";
  }catch{aiEnabled=false;rulesSearchEnabled=false;aiProvider="none";aiModel="";rulesSearchProvider="none";}
  $("aiImportRow").classList.toggle("hidden",currentMode!=="server"||!aiEnabled);
  $("rulesSearchButton").disabled=!rulesSearchEnabled;
  $("rulesSearchButton").title=rulesSearchProvider==="openai"?"Offizielle Anleitung mit serverseitiger Websuche verifizieren":"Anleitungs-Link auf der Quellseite suchen; externe Websuche ist deaktiviert";
  $("aiProviderLabel").textContent=currentMode==="server"?(aiEnabled?aiProvider:"deaktiviert"):"keine KI im lokalen Modus";
  $("aiModelLabel").textContent=currentMode==="server"&&aiEnabled&&aiModel?`Modell: ${aiModel}`:"";
  $("aiSearchLabel").textContent=currentMode==="server"&&aiEnabled?`Externe Anleitungs-Websuche: ${rulesSearchProvider==="openai"?"OpenAI":"aus"}`:"";
  $("testAiButton").disabled=currentMode!=="server"||!aiEnabled;
}
async function loadGames(){
  showBanner("");
  try{games=await provider.list();renderGames();}
  catch(err){games=[];renderGames();showBanner(err.message,"error");}
}
function renderGames(){
  const q=$("searchInput").value.trim().toLocaleLowerCase("de");
  const filtered=games.filter(g=>!q||[g.title,g.description,g.publisher,g.designer,g.ean,g.award,g.notes,...(g.tags||[])].join(" ").toLocaleLowerCase("de").includes(q));
  $("collectionCount").textContent=q&&filtered.length!==games.length?`${filtered.length} von ${games.length} ${games.length===1?"Spiel":"Spielen"}`:`${games.length} ${games.length===1?"Spiel":"Spiele"}`;
  $("emptyState").classList.toggle("hidden",games.length!==0);
  const list=$("gameList");list.innerHTML="";list.classList.toggle("shelf-view",collectionView==="shelf");
  for(const g of filtered){
    const card=document.createElement("article");
    const meta=[];
    if(g.min_players||g.max_players)meta.push({text:`${g.min_players||"?"}–${g.max_players||g.min_players||"?"} Spieler`,kind:"core"});
    if(g.play_time_min)meta.push({text:`${g.play_time_min} Min.`,kind:"core"});
    if(g.min_age!==null&&g.min_age!==undefined&&g.min_age!=="")meta.push({text:`ab ${g.min_age}`,kind:"core"});
    if(g.publisher)meta.push({text:g.publisher,kind:""});
    if(g.year)meta.push({text:String(g.year),kind:""});
    if(g.award)meta.push({text:g.award,kind:"award"});
    for(const tag of (g.tags||[]).slice(0,2))meta.push({text:tag,kind:""});
    const cover=safeHttpsUrl(g.cover_url);
    const initial=(g.title||"B").trim().slice(0,1).toLocaleUpperCase("de");
    const listVisual=cover?`<img class="game-cover" src="${esc(cover)}" alt="Cover von ${esc(g.title)}" loading="lazy" referrerpolicy="no-referrer">`:`<div class="game-cover game-cover-placeholder" aria-hidden="true"><span>${esc(initial)}</span></div>`;
    const shelfVisual=cover?`<img class="game-cover shelf-cover" src="${esc(cover)}" alt="Cover von ${esc(g.title)}" loading="lazy" referrerpolicy="no-referrer">`:`<div class="game-cover shelf-cover game-cover-placeholder" aria-hidden="true"><span>${esc(initial)}</span></div>`;
    if(collectionView==="shelf"){
      card.className="game-card shelf-card";
      const subline=[g.publisher,g.year].filter(Boolean).join(" · ") || (g.designer?`von ${g.designer}`:"Ohne weitere Angaben");
      const mini=[meta[0]?.text, meta[1]?.text, meta[2]?.text].filter(Boolean).slice(0,3);
      card.innerHTML=`<button class="shelf-hit" type="button"><div class="shelf-cover-wrap">${shelfVisual}${g.award?`<span class="shelf-award">★ ${esc(g.award)}</span>`:""}</div><div class="shelf-copy"><h3>${esc(g.title)}</h3><p class="shelf-subline">${esc(subline)}</p>${mini.length?`<div class="shelf-mini-meta">${mini.map(x=>`<span class="shelf-mini-chip">${esc(x)}</span>`).join("")}</div>`:""}</div></button>`;
    }else{
      card.className="game-card";
      card.innerHTML=`<button class="card-hit with-cover" type="button">${listVisual}<div class="card-copy"><div class="game-title-row"><h3>${esc(g.title)}</h3><span aria-hidden="true">›</span></div>${g.description?`<p class="game-description">${esc(g.description)}</p>`:""}<div class="game-meta">${meta.map(x=>`<span class="chip ${x.kind}">${esc(x.text)}</span>`).join("")}</div></div></button>`;
    }
    card.querySelector("button").addEventListener("click",()=>openGameDetail(g));list.append(card);
  }
  if(games.length&&filtered.length===0)list.innerHTML='<div class="empty-state"><strong>Nichts gefunden</strong><p>Versuche einen anderen Suchbegriff.</p></div>';
  updateCollectionViewButtons();
}

function clearGameForm(){
  for(const id of ["gameId","titleInput","sourceUrlInput","descriptionInput","minPlayersInput","maxPlayersInput","playTimeInput","minAgeInput","publisherInput","yearInput","designerInput","eanInput","awardInput","coverUrlInput","tagsInput","rulesUrlInput","rulesTextInput","notesInput"])$(id).value="";
  renderCoverPreview();
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
    $("publisherInput").value=game.publisher||"";$("yearInput").value=game.year??"";$("designerInput").value=game.designer||"";$("eanInput").value=game.ean||"";$("awardInput").value=game.award||"";$("coverUrlInput").value=game.cover_url||"";
    $("tagsInput").value=(game.tags||[]).join(", ");$("rulesUrlInput").value=game.rules_url||"";$("rulesTextInput").value=game.rules_text||"";$("notesInput").value=game.notes||"";
    renderCoverPreview();
  }
  $("gameDialog").showModal();setTimeout(()=>$("titleInput").focus(),50);
}

function detailChip(text,kind=""){return `<span class="chip ${kind}">${esc(text)}</span>`;}
function openLink(url){if(!url)return;window.open(url,"_blank","noopener,noreferrer");}
function openGameDetail(gameOrId){
  const game=typeof gameOrId==="string"?games.find(g=>g.id===gameOrId):gameOrId;
  if(!game)return;
  activeDetailGameId=game.id||"";
  const cover=safeHttpsUrl(game.cover_url);
  const initial=(game.title||"B").trim().slice(0,1).toLocaleUpperCase("de");
  const visual=cover?`<img class="detail-cover" src="${esc(cover)}" alt="Cover von ${esc(game.title)}" loading="lazy" referrerpolicy="no-referrer">`:`<div class="detail-cover game-cover-placeholder" aria-hidden="true"><span>${esc(initial)}</span></div>`;
  const chips=[];
  if(game.min_players||game.max_players)chips.push(detailChip(`${game.min_players||"?"}–${game.max_players||game.min_players||"?"} Spieler`,`core`));
  if(game.play_time_min)chips.push(detailChip(`${game.play_time_min} Min.`,`core`));
  if(game.min_age!==null&&game.min_age!==undefined&&game.min_age!=="")chips.push(detailChip(`ab ${game.min_age}`,`core`));
  if(game.award)chips.push(detailChip(game.award,`award`));
  for(const tag of (game.tags||[]))chips.push(detailChip(tag));
  const facts=[
    ["Verlag", game.publisher], ["Jahr", game.year], ["Autor / Designer", game.designer], ["EAN / GTIN", game.ean]
  ].filter(([,v])=>v!==null&&v!==undefined&&v!=="");
  $("detailTitle").textContent=game.title||"Spiel";
  $("detailBody").innerHTML=`<div class="detail-hero">${visual}<div class="detail-copy"><h3>${esc(game.title||"Unbenanntes Spiel")}</h3>${game.description?`<p class="detail-description">${esc(game.description)}</p>`:`<p class="detail-description">Noch keine Beschreibung hinterlegt.</p>`}${chips.length?`<div class="detail-meta">${chips.join("")}</div>`:""}</div></div><div class="detail-panels"><section class="detail-panel"><h4>Auf einen Blick</h4><div class="detail-grid">${facts.length?facts.map(([label,value])=>`<div class="detail-item"><span>${esc(label)}</span><strong>${esc(String(value))}</strong></div>`).join(""):`<div class="detail-item"><p>Noch keine weiteren Daten hinterlegt.</p></div>`}</div></section>${(game.source_url||game.rules_url)?`<section class="detail-panel"><h4>Links</h4><div class="detail-links">${game.source_url?`<a class="detail-link" href="${esc(game.source_url)}" target="_blank" rel="noopener noreferrer">Produkt- oder Quellseite<small>${esc(game.source_url)}</small></a>`:""}${game.rules_url?`<a class="detail-link" href="${esc(game.rules_url)}" target="_blank" rel="noopener noreferrer">Anleitung öffnen<small>${esc(game.rules_url)}</small></a>`:""}</div></section>`:""}${game.rules_text?`<section class="detail-panel"><h4>Kurzregeln / Anleitung</h4><p class="detail-notes">${esc(game.rules_text)}</p></section>`:""}${game.notes?`<section class="detail-panel"><h4>Notizen</h4><p class="detail-notes">${esc(game.notes)}</p></section>`:""}</div>`;
  $("detailOpenSourceButton").classList.toggle("hidden",!game.source_url);
  $("detailOpenRulesButton").classList.toggle("hidden",!game.rules_url);
  $("detailOpenSourceButton").onclick=()=>openLink(game.source_url);
  $("detailOpenRulesButton").onclick=()=>openLink(game.rules_url);
  $("detailEditButton").onclick=()=>{$("gameDetailDialog").close();openGame(game);};
  $("gameDetailDialog").showModal();
}
function formGame(){return {
  title:$("titleInput").value.trim(),source_url:$("sourceUrlInput").value.trim(),description:$("descriptionInput").value.trim(),
  min_players:inputNumber("minPlayersInput"),max_players:inputNumber("maxPlayersInput"),play_time_min:inputNumber("playTimeInput"),min_age:inputNumber("minAgeInput"),
  publisher:$("publisherInput").value.trim(),year:inputNumber("yearInput"),designer:$("designerInput").value.trim(),ean:$("eanInput").value.replace(/\s+/g,"").trim(),award:$("awardInput").value.trim(),cover_url:$("coverUrlInput").value.trim(),
  tags:$("tagsInput").value.split(",").map(x=>x.trim()).filter(Boolean),rules_url:$("rulesUrlInput").value.trim(),rules_text:$("rulesTextInput").value.trim(),notes:$("notesInput").value.trim()
};}
function applyProposal(d){
  for(const [key,,id] of FIELD_MAP){
    const value=d[key];
    if(value===null||value===undefined||value===""||(Array.isArray(value)&&value.length===0))continue;
    $(id).value=Array.isArray(value)?value.join(", "):value;
  }
  renderCoverPreview();
}

async function saveGame(event){
  event.preventDefault();const data=formGame();if(!data.title){showMessage("Titel fehlt","Bitte gib einen Titel ein.");return;}
  const submit=$("gameForm").querySelector('button[type="submit"]');setBusy(submit,true,"Speichere …");
  try{const id=$("gameId").value;if(id)await provider.update(id,data);else await provider.create(data);$("gameDialog").close();await loadGames();}
  catch(err){showMessage("Speichern fehlgeschlagen",err.message);}finally{setBusy(submit,false);}
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
    $("strategyBody").innerHTML=`<p>${esc(context)}</p><p><strong>${preview.total}</strong> Datensätze im Import<br>${preview.new} neu · ${preview.conflicts} Konflikte · ${preview.same} unverändert</p><p class="hint">„Ersetzen“ löscht den aktuellen Zielbestand vor dem Import. „Zusammenführen“ behält andere Ziel-Datensätze; gleiche IDs aus dem Import werden übernommen.</p>`;
    const dlg=$("strategyDialog");
    const finish=v=>{cleanup();dlg.close();resolve(v);};
    const merge=()=>finish("merge"),replace=()=>finish("replace"),close=()=>finish(null);
    function cleanup(){$("mergeStrategyButton").removeEventListener("click",merge);$("replaceStrategyButton").removeEventListener("click",replace);$("closeStrategyButton").removeEventListener("click",close);dlg.removeEventListener("cancel",close);}
    $("mergeStrategyButton").addEventListener("click",merge);$("replaceStrategyButton").addEventListener("click",replace);$("closeStrategyButton").addEventListener("click",close);dlg.addEventListener("cancel",close);dlg.showModal();
  });
}
async function importFile(file){
  try{const backup=validateBackup(JSON.parse(await file.text()));const preview=await provider.previewImport(backup);const strategy=await strategyDialog(preview,`Backup v${backup.version} in den aktuell aktiven Speicher importieren?`);if(!strategy)return;await provider.importData(backup,strategy);await loadGames();showMessage("Import abgeschlossen",`${backup.data.games.length} Datensätze wurden verarbeitet.`);}catch(err){showMessage("Import fehlgeschlagen",err.message);}finally{$("importInput").value="";}
}
async function localToServer(){
  try{const local=new LocalProvider();const backup=await local.exportData();if(backup.data.games.length===0){showMessage("Keine lokalen Daten","Im lokalen Speicher sind keine Brettspiele vorhanden.");return;}const server=await makeServerProvider();const preview=await server.previewImport(backup);const strategy=await strategyDialog(preview,"Lokale Daten auf den Server übertragen? Der lokale Bestand bleibt dabei unverändert.");if(!strategy)return;await server.importData(backup,strategy);showMessage("Übertragung abgeschlossen",`${backup.data.games.length} lokale Datensätze wurden an den Server übertragen.`);if(currentMode==="server")await loadGames();}catch(err){showMessage("Übertragung fehlgeschlagen",err.message);}
}
async function serverToLocal(){
  try{const server=await makeServerProvider();const backup=await server.exportData();const local=new LocalProvider();const preview=await local.previewImport(backup);const strategy=await strategyDialog(preview,"Serverdaten lokal übernehmen? Vor einem Ersetzen empfiehlt sich ein Export des aktuellen lokalen Bestands.");if(!strategy)return;if(strategy==="replace"&&confirm("Vor dem Ersetzen jetzt ein lokales Sicherheitsbackup exportieren?")){const old=await local.exportData();await downloadJson(old,`brettspielregal-lokal-vor-restore-${new Date().toISOString().slice(0,10)}.json`);}await local.importData(backup,strategy);showMessage("Lokale Übernahme abgeschlossen",`${backup.data.games.length} Server-Datensätze wurden lokal übernommen.`);if(currentMode==="local")await loadGames();}catch(err){showMessage("Übernahme fehlgeschlagen",err.message);}
}

async function loadSetup(){
  serverConfig=await loadServerConnection();$("backendUrl").value=serverConfig.url||config.defaultApiUrl||"";$("cfClientId").value=serverConfig.clientId||"";$("cfClientSecret").value="";$("cfClientSecret").placeholder=serverConfig.clientSecret?"Gespeichert – zum Ersetzen neu eingeben":"Neu setzen oder leer lassen";
  $("versionLabel").textContent=config.version;$("buildTargetLabel").textContent=isDocker()?"Docker Fullstack Build":"GitHub Pages PWA Build";
  $("serverConfigForm").classList.toggle("hidden",isDocker());
}
async function saveConnection(event){event.preventDefault();const url=normalizeUrl($("backendUrl").value);if(url&&!/^https:\/\//i.test(url)){showMessage("Ungültige Backend-URL","Im externen Pages-Frontend ist nur eine öffentliche HTTPS-Backend-URL vorgesehen.");return;}await saveServerConnection({url,clientId:$("cfClientId").value.trim(),clientSecret:$("cfClientSecret").value});showMessage("Gespeichert","Die Server-Konfiguration wurde nur auf diesem Gerät gespeichert.");await loadSetup();if(currentMode==="server"){try{provider=await makeServerProvider();await refreshConfig();await loadGames();}catch{}}}
async function clearSecrets(){if(!confirm("Gespeicherte Cloudflare-Zugangsdaten auf diesem Gerät löschen?"))return;await wipeServerSecrets();await loadSetup();showMessage("Zugangsdaten gelöscht","Client ID und Client Secret wurden aus IndexedDB entfernt.");}
async function testConnection(){const b=$("testConnectionButton");setBusy(b,true,"Teste …");try{const srv=await makeServerProvider();const h=await srv.health();showMessage("Verbindung funktioniert",h.status==="ok"?"Backend ist erreichbar und meldet Status ok.":"Backend ist erreichbar.");}catch(err){showMessage("Verbindung fehlgeschlagen",err.message);}finally{setBusy(b,false);}}

async function testAi(){
  if(currentMode!=="server"){showMessage("Nur im Server-Modus","Im lokalen Pages-Modus wird bewusst keine KI angesprochen.");return;}
  const b=$("testAiButton");setBusy(b,true,"Teste KI …");
  try{
    const result=await provider.aiStatus();
    if(result.provider==="ollama"&&result.status==="model_missing")showMessage("Ollama erreichbar",`Ollama antwortet, aber das konfigurierte Modell ${result.model||""} wurde nicht gefunden. Lade das Modell auf dem Ollama-Host oder passe OLLAMA_MODEL an.`);
    else showMessage("KI-Verbindung funktioniert",`${result.provider||aiProvider}${result.model?` · ${result.model}`:""} ist vom Docker-Backend erreichbar.`);
  }catch(err){showMessage("KI-Verbindung fehlgeschlagen",err.message);}finally{setBusy(b,false);}
}

async function switchMode(mode){
  if(isDocker()||!config.allowLocalMode)return;if(mode===currentMode)return;setModeValue(mode);
  try{await selectProvider();await refreshConfig();await loadGames();showMessage("Betriebsmodus gewechselt",`Aktiv ist jetzt: ${modeLabel()}. Es wurden keine Daten zwischen Lokal und Server übertragen.`);}catch(err){showMessage("Server-Modus noch nicht bereit",err.message);showView("setup");}
  await loadSetup();
}
function showView(view){document.querySelectorAll(".view").forEach(v=>v.classList.toggle("active",v.id===`view${view[0].toUpperCase()+view.slice(1)}`));document.querySelectorAll(".nav-button").forEach(b=>b.classList.toggle("active",b.dataset.view===view));$("mainContent").focus();}

function bindEvents(){
  $("addGameButton").addEventListener("click",()=>openGame());$("emptyAddButton").addEventListener("click",()=>openGame());$("searchInput").addEventListener("input",renderGames);$("viewListButton").addEventListener("click",()=>setCollectionView("list"));$("viewShelfButton").addEventListener("click",()=>setCollectionView("shelf"));
  $("closeGameDialog").addEventListener("click",()=>$("gameDialog").close());$("cancelGameButton").addEventListener("click",()=>$("gameDialog").close());$("gameForm").addEventListener("submit",saveGame);$("deleteGameButton").addEventListener("click",removeGame);$("aiImportButton").addEventListener("click",aiImport);$("rulesSearchButton").addEventListener("click",rulesSearch);$("coverUrlInput").addEventListener("input",renderCoverPreview);
  document.querySelectorAll(".nav-button").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.view)));document.querySelectorAll("[data-mode]").forEach(b=>b.addEventListener("click",()=>switchMode(b.dataset.mode)));
  $("serverConfigForm").addEventListener("submit",saveConnection);$("clearSecretsButton").addEventListener("click",clearSecrets);$("testConnectionButton").addEventListener("click",testConnection);$("testAiButton").addEventListener("click",testAi);$("exportButton").addEventListener("click",exportCurrent);$("importInput").addEventListener("change",e=>{if(e.target.files?.[0])importFile(e.target.files[0]);});$("localToServerButton").addEventListener("click",localToServer);$("serverToLocalButton").addEventListener("click",serverToLocal);
  const closeMsg=()=>$("messageDialog").close();$("closeMessageButton").addEventListener("click",closeMsg);$("messageOkButton").addEventListener("click",closeMsg);$("closeDetailDialog").addEventListener("click",()=>$("gameDetailDialog").close());
  document.querySelectorAll("[data-first-mode]").forEach(b=>b.addEventListener("click",async()=>{$("firstRunDialog").close();setModeValue(b.dataset.firstMode);try{await selectProvider();await refreshConfig();await loadGames();}catch(err){showView("setup");showMessage("Server einrichten",err.message);}await loadSetup();}));
  window.addEventListener("online",()=>currentMode==="server"&&loadGames());window.addEventListener("offline",()=>currentMode==="server"&&showBanner("Offline: Im Server-Modus sind Schreibaktionen erst wieder nach erfolgreicher Verbindung möglich."));
}

async function init(){
  bindEvents();updateCollectionViewButtons();$("versionLabel").textContent=config.version;
  if("serviceWorker" in navigator){navigator.serviceWorker.register("./service-worker.js").catch(()=>{});}
  if(!isDocker()&&config.allowLocalMode&&!selectedMode()){
    currentMode="local";provider=new LocalProvider();$("modeBadge").textContent="Lokal";await loadSetup();$("firstRunDialog").showModal();return;
  }
  try{await selectProvider();await refreshConfig();await loadGames();}catch(err){currentMode="server";$("modeBadge").textContent="Server";showBanner(err.message,"error");showView("setup");}
  await loadSetup();
}
init();
