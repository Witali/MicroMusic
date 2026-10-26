// Measure software reconstruction of a constant PWM; no hardware claim.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { AudioBus } from '../../Emulator/core8080.mjs';
import { StreamingAudio } from '../../Emulator/stream-audio.mjs';

export function carrierAlias(cutoff,poles,{rate=192000,deviceRate=48000}={}) {
  const hz=3500000,period=82;
  const end=Math.floor(hz*1.5/period)*period,bus=new AudioBus(hz,rate,'inte',2);
  for(let t=0;t<end;t+=period){bus.edge(1,t);bus.edge(0,t+32);}
  const stream=new StreamingAudio(deviceRate,{rate,cutoff,poles,normalize:false,volume:.65});
  stream.push(bus.finish(end));stream.finished=true;
  const output=new Float32Array(deviceRate*1.5);stream.render(output);
  const frequency=deviceRate-hz/period;let real=0,imaginary=0,weight=0;
  for(let i=0;i<deviceRate;i++){
    const window=.5-.5*Math.cos(2*Math.PI*i/(deviceRate-1)),angle=2*Math.PI*frequency*i/deviceRate;
    const sample=output[deviceRate/4+i];
    real+=sample*window*Math.cos(angle);imaginary-=sample*window*Math.sin(angle);weight+=window;
  }
  return {source_rate_hz:rate,device_rate_hz:deviceRate,cutoff_hz:cutoff,rc_poles:poles,alias_hz:frequency,alias_dbfs:Number((20*Math.log10(2*Math.hypot(real,imaginary)/weight)).toFixed(6))};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const report={cpu_hz:3500000,period_t:82,constant_pcm_level:7,high_width_t:32,
    volume:.65,normalize:false,
    measurement:'1s Hann amplitude at Fs_device-carrier after 0.25s settling; AudioBus and band-limited StreamingAudio, no hardware',
    baseline_linear_96_to_48:{cutoff_hz:10000,rc_poles:1,alias_hz:48000-3500000/82,alias_dbfs:-15.097138,revision:'28885cc5'},
    results:[carrierAlias(10000,1,{rate:96000}),...[44100,48000].flatMap(deviceRate=>[carrierAlias(10000,1,{deviceRate}),carrierAlias(4500,4,{deviceRate})])],hardware_measured:false};
  const target=new URL('PREVIEW.json',import.meta.url);
  if(process.argv.includes('--check'))assert.deepEqual(report,JSON.parse(readFileSync(target)));
  else writeFileSync(target,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report.results));
}
