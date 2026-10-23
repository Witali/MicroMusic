// Match the first phrase's RMS after the same resampling and RC chain as the UI.
import {readFileSync} from 'node:fs';
import {Renderer} from '../web-player/lib/renderer-js.js';
const stdin=process.argv.includes('--stdin');
const catalog=JSON.parse(readFileSync(stdin?0:new URL('../web-player/hq4-firmware.json',import.meta.url),'utf8'));
const sampleRate=48000,cutoff=9000,frames=Math.round(9216/7500*sampleRate),rms={};
const variants=catalog.entries.filter(e=>e.codec==='hq4-t').map(e=>e.id);
for(const id of ['hq4-chego',...variants]){
  const entry=catalog.entries.find(e=>e.id===id);
  if(!entry)throw new Error('Missing '+id);
  const renderer=new Renderer(entry,sampleRate,{cutoff,volume:1});
  let power=0;
  for(let offset=0;offset<frames;offset+=4096)
    for(const value of renderer.render(Math.min(4096,frames-offset)))power+=value*value;
  rms[id]=Math.sqrt(power/frames);
}
const monitorGains=Object.fromEntries(variants.map(id=>[id,Number((rms['hq4-chego']/rms[id]).toFixed(10))]));
for(const [id,gain] of Object.entries(monitorGains))
  if(!stdin&&Math.abs(catalog.entries.find(e=>e.id===id).monitorGain-gain)>1e-9)
    throw new Error('Stale listening gain: '+id);
console.log(JSON.stringify({sampleRate,cutoff,frames,rms,monitorGains}));
