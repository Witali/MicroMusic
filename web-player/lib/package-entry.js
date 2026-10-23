import {decodePackage} from './attiny13a-package.js';
const hex=n=>n.toString(16).padStart(2,'0').toUpperCase();
function intelHex(bytes){
  const lines=[];
  for(let at=0;at<bytes.length;at+=16){
    const data=[Math.min(16,bytes.length-at),at>>8,at&255,0,...bytes.subarray(at,at+16)];
    lines.push(':'+data.map(hex).join('')+hex(-data.reduce((a,b)=>a+b,0)&255));
  }
  return lines.join('\n')+'\n:00000001FF\n';
}
export async function packageEntry(input,{name='Пакет ATtiny13A',channels=2}={}){
  if(![1,2].includes(channels))throw Error('Unsupported audio channel count');
  const decoded=await decodePackage(input),pkg=typeof input==='string'?JSON.parse(input):structuredClone(input);
  return {id:'package-'+decoded.integrity.sha256.slice(0,16),order:'PKG',title:name,
    kind:'package',description:'Пакет ATtiny13A · '+(channels===2?'PB0 / PB1':'PB1'),
    devicePackage:pkg,deviceConfiguration:decoded.configuration,audioChannels:channels,
    flashHex:intelHex(decoded.flash),eepromHex:intelHex(decoded.eeprom),
    flashBytes:1024,eepromBytes:64,flashSha256:pkg.assets.flash.sha256};
}
