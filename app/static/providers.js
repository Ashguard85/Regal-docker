import {getAllGames,getGame,putGame,deleteGame,replaceGames,mergeGames,getSetting,setSetting,getSecret,setSecret,clearSecrets} from "./db.js";

export const BACKUP_FORMAT="brettspielregal-backup";
export const BACKUP_VERSION=2;
export const SUPPORTED_BACKUP_VERSIONS=new Set([1,2]);

function nowIso(){return new Date().toISOString();}
function id(){return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;}
function cleanGame(raw={}){
  const num=v=>v===""||v===null||v===undefined?null:Number(v);
  const tags=Array.isArray(raw.tags)?raw.tags:typeof raw.tags==="string"?raw.tags.split(",").map(x=>x.trim()).filter(Boolean):[];
  return {
    id: String(raw.id||id()), title:String(raw.title||"").trim(), description:String(raw.description||"").trim(),
    source_url:String(raw.source_url||"").trim(), rules_url:String(raw.rules_url||"").trim(), rules_text:String(raw.rules_text||"").trim(),
    min_players:num(raw.min_players), max_players:num(raw.max_players), play_time_min:num(raw.play_time_min), min_age:num(raw.min_age),
    publisher:String(raw.publisher||"").trim(), year:num(raw.year), designer:String(raw.designer||"").trim(), ean:String(raw.ean||"").trim(), cover_url:String(raw.cover_url||"").trim(), award:String(raw.award||"").trim(), tags:[...new Set(tags)], notes:String(raw.notes||"").trim(),
    created_at:raw.created_at||nowIso(), updated_at:raw.updated_at||nowIso()
  };
}
function validateBackup(backup){
  if(!backup||backup.format!==BACKUP_FORMAT||!SUPPORTED_BACKUP_VERSIONS.has(backup.version)||!backup.data||!Array.isArray(backup.data.games))throw new Error("Ungültiges oder nicht unterstütztes Backup-Format.");
  return backup;
}
function backupFromGames(games,meta={}){return {format:BACKUP_FORMAT,version:BACKUP_VERSION,exported_at:nowIso(),meta,data:{games:games.map(cleanGame),settings:{}}};}
function comparable(g){const x={...cleanGame(g)};delete x.updated_at;return JSON.stringify(x);}
function previewAgainst(current,incoming){const map=new Map(current.map(g=>[g.id,g]));let fresh=0,conflicts=0,same=0;for(const g of incoming){const old=map.get(g.id);if(!old)fresh++;else if(comparable(old)===comparable(g))same++;else conflicts++;}return {total:incoming.length,new:fresh,conflicts,same};}

export class LocalProvider{
  constructor(){this.kind="local";}
  async list(){return (await getAllGames()).map(cleanGame).sort((a,b)=>a.title.localeCompare(b.title,"de"));}
  async get(id){const g=await getGame(id);if(!g)throw new Error("Spiel wurde nicht gefunden.");return cleanGame(g);}
  async create(data){const g=cleanGame(data);g.created_at=g.updated_at=nowIso();await putGame(g);return g;}
  async update(id,data){const old=await getGame(id);if(!old)throw new Error("Spiel wurde nicht gefunden.");const g=cleanGame({...old,...data,id,created_at:old.created_at,updated_at:nowIso()});await putGame(g);return g;}
  async remove(id){await deleteGame(id);}
  async exportData(){return backupFromGames(await this.list(),{source:"local"});}
  async previewImport(backup){validateBackup(backup);return previewAgainst(await this.list(),backup.data.games.map(cleanGame));}
  async importData(backup,strategy="merge"){validateBackup(backup);const games=backup.data.games.map(cleanGame);if(strategy==="replace")await replaceGames(games);else await mergeGames(games);return {imported:games.length,strategy};}
  async config(){return {title:"Brettspielregal",version:window.APP_CONFIG?.version||"4.0.0",ai_import_enabled:false,rules_search_enabled:false,ai_provider:"none",ai_model:"",rules_search_provider:"none"};}
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
  list(){return this.request("/api/games");}
  get(id){return this.request(`/api/games/${encodeURIComponent(id)}`);}
  create(data){return this.request("/api/games",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});}
  update(id,data){return this.request(`/api/games/${encodeURIComponent(id)}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});}
  remove(id){return this.request(`/api/games/${encodeURIComponent(id)}`,{method:"DELETE"});}
  exportData(){return this.request("/api/export");}
  previewImport(backup){return this.request("/api/import/preview",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({backup})});}
  importData(backup,strategy="merge"){return this.request("/api/import",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({backup,strategy})});}
  config(){return this.request("/api/config");}
  health(){return this.request("/health");}
  aiStatus(){return this.request("/api/ai/status",{timeoutMs:15000});}
  aiFromUrl(url){return this.request("/api/ai/from-url",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url}),timeoutMs:180000});}
  searchRules(game){return this.request("/api/ai/rules-search",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({game}),timeoutMs:90000});}
}

export async function loadServerConnection(){return {url:await getSetting("serverUrl",""),clientId:await getSecret("cfClientId"),clientSecret:await getSecret("cfClientSecret")};}
export async function saveServerConnection({url,clientId,clientSecret}){await setSetting("serverUrl",url||"");if(clientId!==undefined)await setSecret("cfClientId",clientId||"");if(clientSecret!==undefined&&clientSecret!=="")await setSecret("cfClientSecret",clientSecret);}
export async function wipeServerSecrets(){await clearSecrets();}
export {cleanGame,validateBackup,backupFromGames,previewAgainst};
