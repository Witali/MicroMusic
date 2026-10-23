// Match each selected phrase to its frozen HQ4 through the UI's actual RC chain.
import {readFileSync} from 'node:fs';
import {Renderer} from '../web-player/lib/renderer-js.js';
const stdin=process.argv.includes('--stdin');
const catalog=JSON.parse(readFileSync(stdin?0:new URL('../web-player/hq4-firmware.json',import.meta.url),'utf8'));
const references=catalog.referenceEntries??(stdin?[]:JSON.parse(readFileSync(
  new URL('../ATtiny13A/Sound/research/hq4-catalog-archive.json',import.meta.url),'utf8')).entries);
const clips=JSON.parse(readFileSync(new URL('../ATtiny13A/Sound/audio-references.json',import.meta.url),'utf8')).clips;
const entries=new Map([...references,...catalog.entries].map(entry=>[entry.id,entry]));
const sampleRate=48000,cutoff=9000,rms={},framesById={};
const variants=catalog.entries.filter(entry=>['hq4-t','tiny-period'].includes(entry.codec));
function measure(entry){
  if(rms[entry.id]!==undefined)return rms[entry.id];
  const clip=clips.find(clip=>clip.id===entry.audioReferenceId);
  if(!clip)throw new Error('Missing canonical phrase for '+entry.id);
  const frames=Math.round(clip.samples/clip.sample_rate*sampleRate);
  const renderer=new Renderer(entry,sampleRate,{cutoff,volume:1});
  let power=0;
  for(let offset=0;offset<frames;offset+=4096)
    for(const value of renderer.render(Math.min(4096,frames-offset)))power+=value*value;
  framesById[entry.id]=frames;
  return rms[entry.id]=Math.sqrt(power/frames);
}
const monitorGains={};
for(const entry of variants){
  const baseline=entries.get('hq4-'+entry.audioReferenceId);
  if(!baseline)throw new Error('Missing frozen HQ4 for '+entry.id);
  const gain=Number((measure(baseline)/measure(entry)).toFixed(10));
  if(!Number.isFinite(gain)||gain<=0||gain>1)throw new Error('Invalid listening gain: '+entry.id);
  monitorGains[entry.id]=gain;
  if(!stdin&&Math.abs(entry.monitorGain-gain)>1e-9)throw new Error('Stale listening gain: '+entry.id);
}
console.log(JSON.stringify({sampleRate,cutoff,framesById,rms,monitorGains}));
