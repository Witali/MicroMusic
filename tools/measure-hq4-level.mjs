// Match the first phrase's RMS after the same resampling and RC chain as the UI.
import {readFileSync} from 'node:fs';
import {Renderer} from '../web-player/lib/renderer-js.js';
const stdin=process.argv.includes('--stdin');
const catalog=JSON.parse(readFileSync(stdin?0:new URL('../web-player/hq4-firmware.json',import.meta.url),'utf8'));
const sampleRate=48000,cutoff=9000,frames=Math.round(9216/7500*sampleRate),rms={};
for(const id of ['hq4-chego','hq4-chego-timbre']){
  const entry=catalog.entries.find(e=>e.id===id);
  if(!entry)throw new Error('Missing '+id);
  const renderer=new Renderer(entry,sampleRate,{cutoff,volume:1});
  let power=0;
  for(let offset=0;offset<frames;offset+=4096)
    for(const value of renderer.render(Math.min(4096,frames-offset)))power+=value*value;
  rms[id]=Math.sqrt(power/frames);
}
const monitorGain=Number((rms['hq4-chego']/rms['hq4-chego-timbre']).toFixed(10));
if(!stdin&&Math.abs(catalog.entries.find(e=>e.id==='hq4-chego-timbre').monitorGain-monitorGain)>1e-9)
  throw new Error('Stale listening gain');
console.log(JSON.stringify({sampleRate,cutoff,frames,rms,monitorGain}));
