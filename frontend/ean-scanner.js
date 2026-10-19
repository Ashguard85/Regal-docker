/* Brettspielregal v9.1.3 – lokaler EAN/UPC-Scanner für Safari und andere Browser.
 * EAN-13 / EAN-8 sind reine Strichmuster. Hier werden ausschließlich lokale
 * Kamerapixel gelesen: keine externen Skripte, Dienste oder Foto-Uploads.
 * Die Prüfziffer ist bei jeder Erkennung zwingend gültig.
 */
const L = ["0001101","0011001","0010011","0111101","0100011","0110001","0101111","0111011","0110111","0001011"];
const G = ["0100111","0110011","0011011","0100001","0011101","0111001","0000101","0010001","0001001","0010111"];
const FIRST_PARITY = ["LLLLLL","LLGLGG","LLGGLG","LLGGGL","LGLLGG","LGGLLG","LGGGLL","LGLGLG","LGLGGL","LGGLGL"];
const R = L.map(s=>[...s].map(c=>c==="0"?"1":"0").join(""));
const patternWidths = bits => {
  const out=[];let start=0;
  for(let i=1;i<=bits.length;i++)if(i===bits.length||bits[i]!==bits[start]){out.push(i-start);start=i;}
  return out;
};
const LP=L.map(patternWidths), GP=G.map(patternWidths), RP=R.map(patternWidths);
const mean = items => items.reduce((a,b)=>a+b,0)/items.length;

export function validEan(value){
  if(!/^\d{8}$|^\d{12}$|^\d{13}$|^\d{14}$/.test(String(value||"")))return false;
  const s=String(value),body=s.slice(0,-1);
  let total=0;
  for(let i=body.length-1,k=0;i>=0;i--,k++)total+=Number(body[i])*(k%2===0?3:1);
  return (10-total%10)%10===Number(s[s.length-1]);
}
function sampleRuns(samples, threshold){
  const runs=[];let prev=samples[0]<threshold,w=1,start=0;
  for(let i=1;i<samples.length;i++){
    const dark=samples[i]<threshold;
    if(dark===prev){w++;continue;}
    runs.push({black:prev,width:w,start});prev=dark;start=i;w=1;
  }
  runs.push({black:prev,width:w,start});
  return runs;
}
function matchDigit(runs, i, patterns){
  const values=[runs[i]?.width,runs[i+1]?.width,runs[i+2]?.width,runs[i+3]?.width];
  if(values.some(x=>!x||x<1))return null;
  const module=mean(values)/1.75; // four run lengths add up to seven modules
  let best=null;
  for(let d=0;d<10;d++){
    const p=patterns[d];let err=0;
    for(let j=0;j<4;j++)err+=Math.pow(values[j]/module-p[j],2);
    if(!best||err<best.error)best={digit:String(d),error:err};
  }
  return best;
}
function guardError(runs, offset, width, module){
  let error=0;
  for(let j=0;j<width;j++){
    const r=runs[offset+j];
    if(!r)return 999;
    error+=Math.pow(r.width/module-1,2);
  }
  return error;
}
function decodeGroup(runs,start,count){
  const center=start+3+count*4,right=center+5,end=right+count*4;
  if(!runs[end+2])return null;
  const guard=runs.slice(start,start+3).map(r=>r.width);
  const module=mean(guard);
  if(module<1.85)return null;
  // The start, middle and end guards each consist of narrow single modules.
  const guards=guardError(runs,start,3,module)+guardError(runs,center,5,module)+guardError(runs,end,3,module);
  if(guards>2.0)return null;
  const widths=runs.slice(start,end+3).reduce((t,r)=>t+r.width,0);
  const modules=count===6?95:67;
  if(Math.abs(widths/module-modules)>modules*.065)return null;
  if(start>0&&runs[start-1].width<module*4)return null;
  if(runs[end+3]&&runs[end+3].width<module*4)return null;
  let rightDigits="",error=guards;
  for(let d=0;d<count;d++){
    const m=matchDigit(runs,right+d*4,RP);
    if(!m||m.error>1.15)return null;
    rightDigits+=m.digit;error+=m.error;
  }
  const parities=count===6?FIRST_PARITY:["LLLL"];
  let best=null;
  for(let first=0;first<parities.length;first++){
    let leftDigits="",cost=error,valid=true;
    for(let d=0;d<count;d++){
      const m=matchDigit(runs,start+3+d*4,parities[first][d]==="G"?GP:LP);
      if(!m||m.error>1.15){valid=false;break;}
      leftDigits+=m.digit;cost+=m.error;
    }
    if(!valid)continue;
    const value=count===6?String(first)+leftDigits+rightDigits:leftDigits+rightDigits;
    if(!validEan(value))continue;
    if(cost>6.0)continue;
    if(!best||cost<best.error)best={value,error:cost};
  }
  return best;
}
function decodeSamples(samples){
  if(samples.length<95)return null;
  // Smooth only slightly: a barcode may have modules as small as 2 pixels.
  const smooth=new Uint8Array(samples.length);
  for(let i=0;i<samples.length;i++){
    const a=samples[Math.max(0,i-1)],b=samples[i],c=samples[Math.min(samples.length-1,i+1)];
    smooth[i]=(a+2*b+c)/4;
  }
  let min=255,max=0;
  for(const v of smooth){min=Math.min(min,v);max=Math.max(max,v);}
  if(max-min<45)return null;
  const thresholds=[.38,.5,.62].map(r=>min+(max-min)*r);
  let best=null;
  for(const t of thresholds){
    const runs=sampleRuns(smooth,t);
    for(let i=0;i<runs.length-42;i++){
      if(!runs[i].black)continue;
      // Avoid scanning arbitrary object textures: narrow equal-width start guard.
      const trip=runs.slice(i,i+3).map(r=>r.width);
      const module=mean(trip);
      if(!trip[2]||module<1.1||trip.some(w=>Math.abs(w/module-1)>.44))continue;
      for(const count of [6,4]){
        const found=decodeGroup(runs,i,count);
        if(found&&(!best||found.error<best.error))best=found;
      }
    }
    if(best&&best.error<2.5)break;
  }
  return best;
}
/** Process image data from a canvas. Includes portrait/sideways package scanning. */
export function decodeEanImageData(image){
  if(!image||!image.data||!image.width||!image.height)return null;
  const {data,width,height}=image;
  const lines=[.5,.45,.55,.4,.6,.35,.65,.3,.7,.25,.75,.2,.8];
  let best=null;
  for(const vertical of [false,true]){
    const length=vertical?height:width;
    if(length<95)continue;
    for(const fraction of lines){
      const fixed=Math.floor((vertical?width:height)*fraction);
      const values=new Uint8Array(length);
      for(let i=0;i<length;i++){
        const pos=((vertical?i*width+fixed:fixed*width+i)*4);
        values[i]=Math.round(data[pos]*.299+data[pos+1]*.587+data[pos+2]*.114);
      }
      for(const reversed of [false,true]){
        const found=decodeSamples(reversed?values.slice().reverse():values);
        if(found&&(!best||found.error<best.error))best=found;
        if(best&&best.error<2.5)return best.value;
      }
    }
  }
  return best?.value||null;
}
