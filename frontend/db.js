const DB_NAME = "brettspielregal-local";
const DB_VERSION = 4;

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
      if(!db.objectStoreNames.contains("offline_games"))db.createObjectStore("offline_games",{keyPath:"id"});
      if(!db.objectStoreNames.contains("offline_covers"))db.createObjectStore("offline_covers",{keyPath:"id"});
      if(!db.objectStoreNames.contains("attachments")){
        const files=db.createObjectStore("attachments",{keyPath:"id"});
        files.createIndex("game_id","game_id",{unique:false});
      }
    };
    req.onsuccess=()=>resolve(req.result);
    req.onerror=()=>reject(req.error);
  });
}

async function withStore(name,mode,fn){const db=await openDb();const tx=db.transaction(name,mode);const result=await fn(tx.objectStore(name));await txDone(tx);db.close();return result;}
export async function getAllGames(){return withStore("games","readonly",s=>reqToPromise(s.getAll()));}
export async function getGame(id){return withStore("games","readonly",s=>reqToPromise(s.get(id)));}
export async function putGame(game){return withStore("games","readwrite",s=>reqToPromise(s.put(game)));}
export async function deleteGame(id){
  const db=await openDb(),tx=db.transaction(["games","attachments"],"readwrite");
  tx.objectStore("games").delete(id);
  const files=tx.objectStore("attachments").index("game_id");
  files.openCursor(IDBKeyRange.only(id)).onsuccess=e=>{const cursor=e.target.result;if(cursor){cursor.delete();cursor.continue();}};
  await txDone(tx);db.close();
}
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

export async function getAllAttachments(){return withStore("attachments","readonly",s=>reqToPromise(s.getAll()));}
export async function getAttachment(id){return withStore("attachments","readonly",s=>reqToPromise(s.get(id)));}
export async function putAttachment(row){return withStore("attachments","readwrite",s=>reqToPromise(s.put(row)));}
export async function deleteAttachment(gameId,attachmentId){
  const db=await openDb(),tx=db.transaction(["games","attachments"],"readwrite");
  const files=tx.objectStore("attachments"),gameStore=tx.objectStore("games");
  const record=await reqToPromise(files.get(attachmentId));
  if(record?.game_id===gameId){
    files.delete(attachmentId);
    const game=await reqToPromise(gameStore.get(gameId));
    if(game?.cover_attachment_id===attachmentId){game.cover_attachment_id="";gameStore.put(game);}
  }
  await txDone(tx);db.close();return !!record&&record.game_id===gameId;
}
export async function importGamesAndAttachments(games,attachments,strategy){
  const db=await openDb(),tx=db.transaction(["games","attachments"],"readwrite");
  const gs=tx.objectStore("games"),files=tx.objectStore("attachments");
  if(strategy==="replace"){gs.clear();files.clear();}
  for(const game of games)gs.put(game);
  for(const file of attachments)files.put(file);
  await txDone(tx);db.close();
}

// A separate explicitly user-created read-only server snapshot. No credentials
// are saved here. LocalProvider games/attachments remain entirely independent.
export async function readOfflineSnapshot(){
  const db=await openDb(),tx=db.transaction(["offline_games","offline_covers","settings"],"readonly");
  const done=txDone(tx);
  const gamesReq=tx.objectStore("offline_games").getAll();
  const coversReq=tx.objectStore("offline_covers").getAll();
  const metaReq=tx.objectStore("settings").get("offline_snapshot_meta");
  const [games,covers,meta]=await Promise.all([reqToPromise(gamesReq),reqToPromise(coversReq),reqToPromise(metaReq)]);
  await done;db.close();return {games,covers,meta:meta?.value||null};
}
export async function saveOfflineSnapshot(games,covers){
  const db=await openDb(),tx=db.transaction(["offline_games","offline_covers","settings"],"readwrite");
  const gs=tx.objectStore("offline_games"),cs=tx.objectStore("offline_covers");gs.clear();cs.clear();
  for(const g of games)gs.put(g);
  for(const c of covers)cs.put(c);
  const meta={saved_at:new Date().toISOString(),games:games.length,covers:covers.length};
  tx.objectStore("settings").put({key:"offline_snapshot_meta",value:meta});
  await txDone(tx);db.close();return meta;
}
export async function clearOfflineSnapshot(){
  const db=await openDb(),tx=db.transaction(["offline_games","offline_covers","settings"],"readwrite");
  tx.objectStore("offline_games").clear();tx.objectStore("offline_covers").clear();tx.objectStore("settings").delete("offline_snapshot_meta");
  await txDone(tx);db.close();
}
