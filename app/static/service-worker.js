const CACHE_NAME="brettspielregal-pwa-v5";
const APP_SHELL=["./","./index.html","./app.css","./config.js","./app.js","./db.js","./providers.js","./manifest.webmanifest","./offline.html","./icons/icon-192.png","./icons/icon-512.png","./icons/apple-touch-icon.png"];
self.addEventListener("install",event=>{event.waitUntil(caches.open(CACHE_NAME).then(cache=>cache.addAll(APP_SHELL)).then(()=>self.skipWaiting()));});
self.addEventListener("activate",event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE_NAME).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener("fetch",event=>{
  if(event.request.method!=="GET")return;
  const url=new URL(event.request.url);
  if(url.pathname.includes("/api/")||url.pathname.endsWith("/health"))return;
  if(event.request.mode==="navigate"){
    event.respondWith(fetch(event.request).then(r=>{const c=r.clone();caches.open(CACHE_NAME).then(cache=>cache.put("./index.html",c));return r;}).catch(()=>caches.match("./index.html").then(r=>r||caches.match("./offline.html"))));return;
  }
  if(url.origin===self.location.origin)event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request).then(r=>{if(r.ok){const c=r.clone();caches.open(CACHE_NAME).then(cache=>cache.put(event.request,c));}return r;})));
});
