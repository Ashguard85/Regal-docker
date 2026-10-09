const DB_NAME = "brettspielregal-local";
const DB_VERSION = 2;

function reqToPromise(req){return new Promise((resolve,reject)=>{req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});}
function txDone(tx){return new Promise((resolve,reject)=>{tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error("IndexedDB transaction aborted"));});}

export async function openDb(){
  return new Promise((resolve,reject)=>{
    const req=indexedDB.open(DB_NAME,DB_VERSION);
    req.onupgradeneeded=()=>{
      const db=req.result;
      let games;
      if(!db.objectStoreNames.contains("games")){
        games=db.createObjectStore("games",{keyPath:"id"});
        games.createIndex("updated_at","updated_at");
        games.createIndex("title","title");
      }else{
        games=req.transaction.objectStore("games");
      }
      if(!games.indexNames.contains("ean"))games.createIndex("ean","ean",{unique:false});
      if(!db.objectStoreNames.contains("settings"))db.createObjectStore("settings",{keyPath:"key"});
      if(!db.objectStoreNames.contains("secrets"))db.createObjectStore("secrets",{keyPath:"key"});
    };
    req.onsuccess=()=>resolve(req.result);
    req.onerror=()=>reject(req.error);
  });
}

async function withStore(name,mode,fn){const db=await openDb();const tx=db.transaction(name,mode);const result=await fn(tx.objectStore(name));await txDone(tx);db.close();return result;}
export async function getAllGames(){return withStore("games","readonly",s=>reqToPromise(s.getAll()));}
export async function getGame(id){return withStore("games","readonly",s=>reqToPromise(s.get(id)));}
export async function putGame(game){return withStore("games","readwrite",s=>reqToPromise(s.put(game)));}
export async function deleteGame(id){return withStore("games","readwrite",s=>reqToPromise(s.delete(id)));}
export async function clearGames(){return withStore("games","readwrite",s=>reqToPromise(s.clear()));}
export async function replaceGames(games){const db=await openDb();const tx=db.transaction("games","readwrite");const s=tx.objectStore("games");s.clear();for(const game of games)s.put(game);await txDone(tx);db.close();}
export async function mergeGames(games){const db=await openDb();const tx=db.transaction("games","readwrite");const s=tx.objectStore("games");for(const game of games)s.put(game);await txDone(tx);db.close();}
export async function getSetting(key, fallback=null){const row=await withStore("settings","readonly",s=>reqToPromise(s.get(key)));return row?row.value:fallback;}
export async function setSetting(key,value){return withStore("settings","readwrite",s=>reqToPromise(s.put({key,value})));}
export async function deleteSetting(key){return withStore("settings","readwrite",s=>reqToPromise(s.delete(key)));}
export async function getSecret(key){const row=await withStore("secrets","readonly",s=>reqToPromise(s.get(key)));return row?row.value:null;}
export async function setSecret(key,value){return withStore("secrets","readwrite",s=>reqToPromise(s.put({key,value})));}
export async function deleteSecret(key){return withStore("secrets","readwrite",s=>reqToPromise(s.delete(key)));}
export async function clearSecrets(){const db=await openDb();const tx=db.transaction("secrets","readwrite");tx.objectStore("secrets").clear();await txDone(tx);db.close();}
