import {decodeEanImageData,validEan} from '../frontend/ean-scanner.js';
import assert from 'node:assert/strict';
const L=['0001101','0011001','0010011','0111101','0100011','0110001','0101111','0111011','0110111','0001011'];
const G=['0100111','0110011','0011011','0100001','0011101','0111001','0000101','0010001','0001001','0010111'];
const P=['LLLLLL','LLGLGG','LLGGLG','LLGGGL','LGLLGG','LGGLLG','LGGGLL','LGLGLG','LGLGGL','LGGLGL'];
const R=L.map(p=>[...p].map(c=>c==='0'?'1':'0').join(''));
function bitsFor(value){
  let bits='101';
  if(value.length===13){
    const par=P[Number(value[0])];for(let i=1;i<=6;i++)bits+=(par[i-1]==='G'?G:L)[Number(value[i])];
    bits+='01010';for(let i=7;i<=12;i++)bits+=R[Number(value[i])];
  }else{
    for(let i=0;i<4;i++)bits+=L[Number(value[i])];
    bits+='01010';for(let i=4;i<8;i++)bits+=R[Number(value[i])];
  }
  return bits+'101';
}
function image(value,module=3,rotation=0){
  const bits=('0'.repeat(16)+bitsFor(value)+'0'.repeat(16));
  const w=bits.length*module,h=100;
  const pix=new Uint8ClampedArray(w*h*4);
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
    const k=(y*w+x)*4,dark=bits[Math.floor(x/module)]==='1',v=dark?12:235;
    pix[k]=pix[k+1]=pix[k+2]=v;pix[k+3]=255;
  }
  if(!rotation)return {data:pix,width:w,height:h};
  const rotated=new Uint8ClampedArray(pix.length);
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
    const src=(y*w+x)*4,dest=(x*h+(h-1-y))*4;
    for(let c=0;c<4;c++)rotated[dest+c]=pix[src+c];
  }
  return {data:rotated,width:h,height:w};
}
for(const value of ['4002051698973','0123456789012','96385074']){
  if(!validEan(value)){console.log('wrong sample',value);continue;}
  for(const module of [2,3,4,6])for(const rotate of [0,1]){
    const out=decodeEanImageData(image(value,module,rotate));
    assert.equal(out,value,`EAN ${value}, module=${module}, rotation=${rotate} got ${out}`);
  }
}

// Barcode at the centre of a realistic, wider camera frame: surrounding
// background cannot prevent finding start, centre and end patterns.
function padded(original,extra=160){
  const {data,width,height}=original;
  const width2=width+extra*2,out=new Uint8ClampedArray(width2*height*4);
  for(let y=0;y<height;y++)for(let x=0;x<width2;x++){
    const d=(y*width2+x)*4,inside=x>=extra&&x<extra+width;
    const src=(y*width+(x-extra))*4;
    const v=inside?data[src]:215;
    out[d]=out[d+1]=out[d+2]=v;out[d+3]=255;
  }
  return {data:out,width:width2,height};
}
for(const value of ['4002051698973','96385074']){
  assert.equal(decodeEanImageData(padded(image(value,3))),value);
  const img=padded(image(value,4));
  // Uneven indoor lighting: gradual variation behind the code.
  for(let y=0;y<img.height;y++)for(let x=0;x<img.width;x++){
    const index=(y*img.width+x)*4;
    const gray=img.data[index];
    const modified=Math.max(0,Math.min(255,Math.round(gray*.77+x/img.width*30)));
    img.data[index]=img.data[index+1]=img.data[index+2]=modified;
  }
  assert.equal(decodeEanImageData(img),value);
}

// v9.1.4: skewed / perspective-like barcode stripes and independent scanline confidence.
// On a handheld iPhone the box is rarely held precisely parallel to the sensor.
function skewed(original, shift=60){
  const {data,width,height}=original;
  const outer=70, w=width+2*outer;
  const out=new Uint8ClampedArray(w*height*4);
  for(let y=0;y<height;y++)for(let x=0;x<w;x++){
    // Barcode tilts across the image: its actual baseline rises from left to right.
    const dy=Math.round(shift*(x/w-.5));
    const yy=Math.max(0,Math.min(height-1,y-dy));
    const xx=x-outer;
    const v=(xx<0||xx>=width)?230:data[(yy*width+xx)*4];
    const dst=(y*w+x)*4;
    out[dst]=out[dst+1]=out[dst+2]=v;out[dst+3]=255;
  }
  return {data:out,width:w,height};
}
for(const value of ['4002051698973','96385074']){
  const orig=image(value,4);
  for(const shift of [16,30,45]){
    assert.equal(decodeEanImageData(skewed(orig,shift)),value,`skew ${shift} for ${value}`);
  }
}
// High-frequency noisy video frames must NOT be accepted as barcodes, even
// when some accidental 8-digit strings pass the checksum.
const noisyWidth=1280,noisyHeight=720,noisy=new Uint8ClampedArray(noisyWidth*noisyHeight*4);
let seed=1234;
for(let i=0;i<noisy.length;i+=4){
  seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;
  const v=((seed>>>0)%140)+65;
  noisy[i]=noisy[i+1]=noisy[i+2]=v;noisy[i+3]=255;
}
assert.equal(decodeEanImageData({data:noisy,width:noisyWidth,height:noisyHeight}),null);

assert.equal(validEan('4002051698973'),true);
assert.equal(validEan('4002051698974'),false);
console.log('EAN local decoder tests passed');
