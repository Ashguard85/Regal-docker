// v10: deterministic collection helpers, no AI/network required.
export const GAME_TYPES={base:"Grundspiel",expansion:"Erweiterung",standalone_expansion:"Eigenständige Erweiterung",promo:"Promo",accessory:"Zubehör"};
const norm=s=>String(s||"").normalize("NFKD").toLowerCase().replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g," ").trim();
const digits=s=>String(s||"").replace(/\D/g,"");
export function duplicateCandidates(candidate,games,excludeId=""){
  return games.filter(g=>g.id!==excludeId).map(g=>{
    let score=0,reason="";
    const cean=digits(candidate.ean),gean=digits(g.ean);
    if(cean.length>=8&&cean===gean){score=100;reason="Gleiche EAN – vermutlich dieselbe Ausgabe";}
    else if(candidate.bgg_id&&g.bgg_id&&Number(candidate.bgg_id)===Number(g.bgg_id)){
      score=90;
      const variant=norm(candidate.edition_language)!==norm(g.edition_language)||
        (candidate.edition_name&&g.edition_name&&norm(candidate.edition_name)!==norm(g.edition_name))||
        (candidate.edition_year&&g.edition_year&&Number(candidate.edition_year)!==Number(g.edition_year));
      reason=variant?"Gleiche BGG-ID, aber unterschiedliche Ausgabe möglich":"Gleiche BGG-ID";
      if(variant)score=72;
    }else if(norm(candidate.title)&&norm(candidate.title)===norm(g.title)){
      score=60;reason="Gleicher Titel – Ausgabe oder Erweiterung prüfen";
      if(candidate.game_type&&g.game_type&&candidate.game_type!==g.game_type)score=40;
    }
    return {game:g,score,reason};
  }).filter(x=>x.score>=40).sort((a,b)=>b.score-a.score).slice(0,6);
}
export function playableGames(games,{players=0,maxMinutes=0,maxAge=0,tag="",includeExpansions=false}={}){
  return games.filter(g=>{
    if(!includeExpansions&&["expansion","promo","accessory"].includes(g.game_type))return false;
    if(players&&!(g.min_players!=null&&g.max_players!=null&&Number(g.min_players)<=players&&Number(g.max_players)>=players))return false;
    if(maxMinutes&&!(g.play_time_min!=null&&Number(g.play_time_min)<=maxMinutes))return false;
    if(maxAge&&!(g.min_age!=null&&Number(g.min_age)<=maxAge))return false;
    if(tag&&!(g.tags||[]).includes(tag))return false;
    return true;
  });
}
