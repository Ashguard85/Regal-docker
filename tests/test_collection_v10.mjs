import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../frontend/collection-v10.js', import.meta.url),'utf8');
const mod=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const games=[
  {id:'1',title:'Scythe',bgg_id:169786,ean:'4001111111111',game_type:'base',edition_language:'Deutsch',min_players:1,max_players:5,play_time_min:115,min_age:14,tags:['Strategisch']},
  {id:'2',title:'Scythe: Erweiterung',game_type:'expansion',base_game_id:'1',min_players:1,max_players:5,play_time_min:115,min_age:14,tags:['Strategisch']},
  {id:'3',title:'Patchwork',game_type:'base',min_players:2,max_players:2,play_time_min:30,min_age:8,tags:['Zweipersonenspiel']},
];
assert.equal(mod.duplicateCandidates({title:'Scythe',ean:'4001111111111'},games)[0].score,100);
assert.match(mod.duplicateCandidates({title:'Scythe',bgg_id:169786,edition_language:'Englisch'},games)[0].reason,/Ausgabe/);
assert.equal(mod.duplicateCandidates({title:'Scythe: Erweiterung',game_type:'expansion'},games)[0].game.id,'2');
assert.deepEqual(mod.playableGames(games,{players:2,maxMinutes:60}).map(x=>x.id),['3']);
assert.deepEqual(mod.playableGames(games,{players:2,maxMinutes:120}).map(x=>x.id),['1','3']);
assert.deepEqual(mod.playableGames(games,{players:2,maxMinutes:120,tag:'Zweipersonenspiel'}).map(x=>x.id),['3']);
assert.equal(mod.playableGames(games,{players:6}).length,0);
console.log('v10 pure JS collection tests OK');
