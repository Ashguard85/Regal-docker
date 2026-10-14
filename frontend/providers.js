import {getAllGames,getGame,putGame,deleteGame,getAllAttachments,getAttachment,putAttachment,deleteAttachment,importGamesAndAttachments,getSetting,setSetting,getSecret,setSecret,clearSecrets} from "./db.js";

export const BACKUP_FORMAT="brettspielregal-backup";
export const BACKUP_VERSION=4;
export const SUPPORTED_BACKUP_VERSIONS=new Set([1,2,3,4]);

function nowIso(){return new Date().toISOString();}
function id(){return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;}
function cleanGame(raw={}){
  const num=v=>v===""||v===null||v===undefined?null:Number(v);
  const tags=Array.isArray(raw.tags)?raw.tags:typeof raw.tags==="string"?raw.tags.split(",").map(x=>x.trim()).filter(Boolean):[];
  return {
    id: String(raw.id||id()), title:String(raw.title||"").trim(), description:String(raw.description||"").trim(),
    source_url:String(raw.source_url||"").trim(), rules_url:String(raw.rules_url||"").trim(), rules_text:String(raw.rules_text||"").trim(),
    min_players:num(raw.min_players), max_players:num(raw.max_players), play_time_min:num(raw.play_time_min), min_age:num(raw.min_age),
    publisher:String(raw.publisher||"").trim(), year:num(raw.year), designer:String(raw.designer||"").trim(), ean:String(raw.ean||"").trim(), cover_url:String(raw.cover_url||"").trim(), cover_attachment_id:String(raw.cover_attachment_id||"").trim(), award:String(raw.award||"").trim(), storage_location:String(raw.storage_location||"").trim(), tags:[...new Set(tags)], notes:String(raw.notes||"").trim(),
    created_at:raw.created_at||nowIso(), updated_at:raw.updated_at||nowIso()
  };
}
function validateBackup(backup){
  if(!backup||backup.format!==BACKUP_FORMAT||!SUPPORTED_BACKUP_VERSIONS.has(backup.version)||!backup.data||!Array.isArray(backup.data.games))throw new Error("Ungültiges oder nicht unterstütztes Backup-Format.");
  return backup;
}
function backupFromGames(games,meta={},attachments=[]){return {format:BACKUP_FORMAT,version:BACKUP_VERSION,exported_at:nowIso(),meta,data:{games:games.map(cleanGame),attachments,settings:{}}};}
function comparable(g){const x={...cleanGame(g)};delete x.updated_at;return JSON.stringify(x);}
function previewAgainst(current,incoming){const map=new Map(current.map(g=>[g.id,g]));let fresh=0,conflicts=0,same=0;for(const g of incoming){const old=map.get(g.id);if(!old)fresh++;else if(comparable(old)===comparable(g))same++;else conflicts++;}return {total:incoming.length,new:fresh,conflicts,same};}

export const MAX_ATTACHMENT_SIZE=10*1024*1024;
export const MAX_ATTACHMENTS_PER_GAME=15;
function mimeFromHeader(bytes){
  if(bytes[0]===255&&bytes[1]===216&&bytes[2]===255)return "image/jpeg";
  if([137,80,78,71,13,10,26,10].every((n,i)=>bytes[i]===n))return "image/png";
  const header=String.fromCharCode(...bytes.slice(0,12));
  if(header.startsWith("GIF87a")||header.startsWith("GIF89a"))return "image/gif";
  if(header.startsWith("RIFF")&&header.slice(8,12)==="WEBP")return "image/webp";
  if(header.slice(4,8)==="ftyp"){
    const brand=header.slice(8,12);
    if(["heic","heix","hevc","hevx","heim","heis"].includes(brand))return "image/heic";
    if(["mif1","msf1","heif"].includes(brand))return "image/heif";
  }
  if(header.startsWith("%PDF-"))return "application/pdf";
  return "";
}
async function validateFile(file){
  if(!file||file.size<1||file.size>MAX_ATTACHMENT_SIZE)throw new Error("Datei muss zwischen 1 Byte und 10 MB groß sein.");
  const mime=mimeFromHeader(new Uint8Array(await file.slice(0,32).arrayBuffer()));
  if(!mime)throw new Error("Erlaubt sind JPG, PNG, GIF, WebP, HEIC/HEIF und PDF.");
  return mime;
}
function safeFilename(name,mime=""){
  let clean=String(name||"Anhang").replace(/\\/g,"/").split("/").pop().replace(/[\x00-\x1f\x7f]/g,"").replace(/^\.+|\.+$/g,"").slice(0,180)||"Anhang";
  const extensions={"image/jpeg":[".jpg",".jpeg"],"image/png":[".png"],"image/gif":[".gif"],"image/webp":[".webp"],"image/heic":[".heic"],"image/heif":[".heif"],"application/pdf":[".pdf"]}[mime];
  if(extensions&&!extensions.some(ext=>clean.toLowerCase().endsWith(ext)))clean=clean.slice(0,175)+extensions[0];
  return clean;
}
function metadata(row){const {blob,content_base64,...rest}=row;return rest;}
async function blobToBase64(blob){
  const bytes=new Uint8Array(await blob.arrayBuffer());let str="";
  for(let i=0;i<bytes.length;i+=32768)str+=String.fromCharCode(...bytes.subarray(i,i+32768));
  return btoa(str);
}
async function decodeAttachments(backup){
  if(![3,4].includes(backup.version))return [];
  const rows=backup.data.attachments??[];
  if(!Array.isArray(rows)||rows.length>1000)throw new Error("Ungültige Anhänge im Backup.");
  const games=new Set(backup.data.games.map(g=>g.id));
  const ids=new Set(),counts=new Map(),result=[];
  for(const row of rows){
    if(!row||typeof row!=="object"||!games.has(row.game_id)||typeof row.content_base64!=="string"||!(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(row.id||"")))throw new Error("Ungültiger Anhang im Backup.");
    if(ids.has(row.id))throw new Error("Doppelte Anhang-ID im Backup.");ids.add(row.id);
    const count=(counts.get(row.game_id)||0)+1;counts.set(row.game_id,count);
    if(count>MAX_ATTACHMENTS_PER_GAME)throw new Error("Mehr als 15 Anhänge für ein Spiel.");
    if(row.content_base64.length>Math.ceil(MAX_ATTACHMENT_SIZE/3)*4+16)throw new Error("Anhang im Backup ist zu groß.");
    let decoded;try{decoded=atob(row.content_base64);}catch{throw new Error("Ungültiger Dateiinhalt im Backup.");}
    const bytes=Uint8Array.from(decoded,c=>c.charCodeAt(0));
    const mime=mimeFromHeader(bytes.subarray(0,32));
    if(!mime||bytes.length<1||bytes.length>MAX_ATTACHMENT_SIZE||row.mime_type&&row.mime_type!==mime)throw new Error("Dateityp oder Dateigröße im Backup ungültig.");
    result.push({id:row.id,game_id:row.game_id,filename:safeFilename(row.filename,mime),mime_type:mime,kind:mime==="application/pdf"?"rules":"image",size:bytes.length,created_at:row.created_at||nowIso(),blob:new Blob([bytes],{type:mime})});
  }
  return result;
}

export class LocalProvider{
  constructor(){this.kind="local";}
  async list(){
    const games=(await getAllGames()).map(cleanGame).sort((a,b)=>a.title.localeCompare(b.title,"de"));
    const grouped=new Map();
    for(const a of await getAllAttachments()){
      if(!grouped.has(a.game_id))grouped.set(a.game_id,[]);
      grouped.get(a.game_id).push(metadata(a));
    }
    for(const game of games)game.attachments=(grouped.get(game.id)||[]).sort((a,b)=>a.created_at.localeCompare(b.created_at));
    return games;
  }
  async get(id){const g=(await this.list()).find(g=>g.id===id);if(!g)throw new Error("Spiel wurde nicht gefunden.");return g;}
  async create(data,_options={}){const g=cleanGame(data);g.created_at=g.updated_at=nowIso();await putGame(g);return g;}
  async update(id,data){const old=await getGame(id);if(!old)throw new Error("Spiel wurde nicht gefunden.");const g=cleanGame({...old,...data,id,created_at:old.created_at,updated_at:nowIso()});await putGame(g);return g;}
  async remove(id){await deleteGame(id);}
  async listAttachments(gameId){return (await getAllAttachments()).filter(a=>a.game_id===gameId).map(metadata);}
  async addAttachment(gameId,file){
    if(!(await getGame(gameId)))throw new Error("Spiel wurde nicht gefunden.");
    if((await this.listAttachments(gameId)).length>=MAX_ATTACHMENTS_PER_GAME)throw new Error("Maximal 15 Anhänge pro Spiel.");
    const mime=await validateFile(file);
    const row={id:id(),game_id:gameId,filename:safeFilename(file.name,mime),mime_type:mime,kind:mime==="application/pdf"?"rules":"image",size:file.size,created_at:nowIso(),blob:new Blob([file],{type:mime})};
    await putAttachment(row);return metadata(row);
  }
  async getAttachmentBlob(gameId,attachmentId){const row=await getAttachment(attachmentId);if(!row||row.game_id!==gameId)throw new Error("Anhang wurde nicht gefunden.");return row.blob;}
  async removeAttachment(gameId,attachmentId){return deleteAttachment(gameId,attachmentId);}
  async exportData(){
    const rows=[];
    for(const a of await getAllAttachments())rows.push({...metadata(a),content_base64:await blobToBase64(a.blob)});
    return backupFromGames(await this.list(),{source:"local"},rows);
  }
  async previewImport(backup){validateBackup(backup);const files=await decodeAttachments(backup);return {...previewAgainst(await this.list(),backup.data.games.map(cleanGame)),attachments:files.length};}
  async importData(backup,strategy="merge"){
    validateBackup(backup);if(!["merge","replace"].includes(strategy))throw new Error("Unbekannte Importstrategie.");
    const games=backup.data.games.map(cleanGame),attachments=await decodeAttachments(backup);
    await importGamesAndAttachments(games,attachments,strategy);
    return {imported:games.length,attachments:attachments.length,strategy};
  }
  async config(){return {title:"Brettspielregal",version:window.APP_CONFIG?.version||"8.7.2",ai_import_enabled:false,rules_search_enabled:false,auto_enrich_enabled:false,auto_search_provider:"none",ai_provider:"none",ai_model:"",ai_vision_model:"",rules_search_provider:"none"};}
  async aiFromText(){throw new Error("Vorbereitete KI-Imports sind nur im Server-Modus verfügbar.");}
}

export class ServerProvider{
  constructor(baseUrl,creds={}){this.kind="server";this.baseUrl=(baseUrl||"").replace(/\/$/,"");this.creds=creds;}
  url(path){return `${this.baseUrl}${path}`;}
  headers(extra={}){const h={Accept:"application/json",...extra};if(this.creds.clientId)h["CF-Access-Client-Id"]=this.creds.clientId;if(this.creds.clientSecret)h["CF-Access-Client-Secret"]=this.creds.clientSecret;return h;}
  async request(path,options={}){
    const {timeoutMs=12000,...fetchOptions}=options;const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),timeoutMs);
    try{
      const res=await fetch(this.url(path),{...fetchOptions,headers:this.headers(fetchOptions.headers||{}),signal:controller.signal,credentials:this.baseUrl?"omit":"same-origin"});
      const text=await res.text();let body=null;if(text){try{body=JSON.parse(text);}catch{body=null;}}
      if(!res.ok){if(res.status===401||res.status===403)throw new Error("Authentifizierung oder Berechtigung fehlgeschlagen.");if(res.status===404)throw new Error("Die angeforderte Serverfunktion ist nicht verfügbar.");throw new Error(body?.error||`Serverfehler (${res.status}).`);}
      if(text&&!body)throw new Error("Der Server hat eine ungültige Antwort geliefert.");return body;
    }catch(err){if(err.name==="AbortError")throw new Error("Zeitüberschreitung beim Serverzugriff.");if(err instanceof TypeError)throw new Error("Server nicht erreichbar oder Anfrage durch CORS/Cloudflare blockiert.");throw err;}finally{clearTimeout(timer);}
  }
  async blobRequest(path){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),60000);
    try{
      const res=await fetch(this.url(path),{headers:this.headers(),signal:controller.signal,credentials:this.baseUrl?"omit":"same-origin",cache:"no-store"});
      if(!res.ok){let data={};try{data=await res.json();}catch{}throw new Error(data.error||`Datei konnte nicht geladen werden (${res.status}).`);}
      return await res.blob();
    }finally{clearTimeout(timer);}
  }
  listAttachments(gameId){return this.request(`/api/games/${encodeURIComponent(gameId)}/attachments`);}
  async addAttachment(gameId,file){
    await validateFile(file);
    const form=new FormData();form.append("file",file,file.name);
    return this.request(`/api/games/${encodeURIComponent(gameId)}/attachments`,{method:"POST",body:form,timeoutMs:120000});
  }
  getAttachmentBlob(gameId,attachmentId){return this.blobRequest(`/api/games/${encodeURIComponent(gameId)}/attachments/${encodeURIComponent(attachmentId)}`);}
  removeAttachment(gameId,attachmentId){return this.request(`/api/games/${encodeURIComponent(gameId)}/attachments/${encodeURIComponent(attachmentId)}`,{method:"DELETE"});}
  list(){return this.request("/api/games");}
  get(id){return this.request(`/api/games/${encodeURIComponent(id)}`);}
  create(data,options={}){return this.request("/api/games",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...data,_auto_enrich:options.autoEnrich!==false})});}
  update(id,data){return this.request(`/api/games/${encodeURIComponent(id)}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});}
  remove(id){return this.request(`/api/games/${encodeURIComponent(id)}`,{method:"DELETE"});}
  exportData(){return this.request("/api/export",{timeoutMs:120000});}
  previewImport(backup){return this.request("/api/import/preview",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({backup}),timeoutMs:120000});}
  importData(backup,strategy="merge"){return this.request("/api/import",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({backup,strategy}),timeoutMs:180000});}
  config(){return this.request("/api/config");}
  health(){return this.request("/health");}
  systemStatus(){return this.request("/api/system/status",{timeoutMs:20000});}
  aiStatus(){return this.request("/api/ai/status",{timeoutMs:15000});}
  researchSettings(){return this.request("/api/research-settings",{timeoutMs:20000});}
  saveResearchSettings(data){return this.request("/api/research-settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(data),timeoutMs:30000});}
  resetResearchSettings(){return this.request("/api/research-settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"reset"}),timeoutMs:20000});}
  cleanupTags(){return this.request("/api/tags/cleanup",{method:"POST",timeoutMs:60000});}
  aiFromUrl(url){return this.request("/api/ai/from-url",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url}),timeoutMs:620000});}
  aiFromText(text,sourceUrl=""){return this.request("/api/ai/from-text",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text,source_url:sourceUrl}),timeoutMs:620000});}
  aiFromImages(files,sourceUrl=""){
    const form=new FormData();
    for(const file of files)form.append("images",file,file.name||"screenshot.png");
    if(sourceUrl)form.append("source_url",sourceUrl);
    return this.request("/api/ai/from-image",{method:"POST",body:form,timeoutMs:620000});
  }
  searchRules(game){return this.request("/api/ai/rules-search",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({game}),timeoutMs:90000});}
  importQueue(){return this.request("/api/import-queue",{timeoutMs:20000});}
  cleanupImportQueue(mode="history"){return this.request("/api/import-queue/cleanup",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mode}),timeoutMs:30000});}
  quickCapture(text,storageLocation="",enrich=true){return this.request("/api/import-queue/quick",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text,storage_location:storageLocation,enrich:enrich!==false}),timeoutMs:60000});}
  enqueueEnrichment(gameId,query="",replaceActive=false){return this.request(`/api/import-queue/games/${encodeURIComponent(gameId)}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query,replace_active:replaceActive}),timeoutMs:20000});}
  approveImportJob(jobId){return this.request(`/api/import-queue/${encodeURIComponent(jobId)}/approve`,{method:"POST",timeoutMs:20000});}
  applyImportSuggestions(jobId,fields=null){return this.request(`/api/import-queue/${encodeURIComponent(jobId)}/suggestions/apply`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(fields===null?{}:{fields}),timeoutMs:30000});}
  rejectImportSuggestions(jobId,fields=null){return this.request(`/api/import-queue/${encodeURIComponent(jobId)}/suggestions/reject`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(fields===null?{}:{fields}),timeoutMs:30000});}
  retryImportJob(jobId){return this.request(`/api/import-queue/${encodeURIComponent(jobId)}/retry`,{method:"POST",timeoutMs:20000});}
  requestCancelImportJob(jobId){return this.request(`/api/import-queue/${encodeURIComponent(jobId)}/cancel`,{method:"POST",timeoutMs:20000});}
  forceReleaseImportJob(jobId){return this.request(`/api/import-queue/${encodeURIComponent(jobId)}/force-release`,{method:"POST",timeoutMs:20000});}
  cancelImportJob(jobId){return this.request(`/api/import-queue/${encodeURIComponent(jobId)}`,{method:"DELETE",timeoutMs:20000});}
}

export async function loadServerConnection(){return {url:await getSetting("serverUrl",""),clientId:await getSecret("cfClientId"),clientSecret:await getSecret("cfClientSecret")};}
export async function saveServerConnection({url,clientId,clientSecret}){await setSetting("serverUrl",url||"");if(clientId!==undefined)await setSecret("cfClientId",clientId||"");if(clientSecret!==undefined&&clientSecret!=="")await setSecret("cfClientSecret",clientSecret);}
export async function wipeServerSecrets(){await clearSecrets();}
export {cleanGame,validateBackup,backupFromGames,previewAgainst};
