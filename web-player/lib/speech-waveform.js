import {Renderer} from './renderer-js.js';

// Use the existing player DSP/resampler so full-phrase input/output views match
// the same firmware duties and controls. The supplied core reads saved duties.
export function speechSignals(raw,rate,{native=false,cutoff=9000,volume=.65}={}){
  if(native)return {sampleRate:rate,input:raw,output:Float32Array.from(raw,value=>value*volume)};
  let index=0;const core={nextDuty:()=>index<raw.length?Math.round(raw[index++]*128+128):128};
  const renderer=new Renderer({pwmHz:rate},48000,{cutoff,volume},core);
  const count=Math.ceil(raw.length*48000/rate),input=new Float32Array(count),output=new Float32Array(count);
  for(let offset=0;offset<count;){
    const length=Math.min(4096,count-offset);output.set(renderer.render(length),offset);
    input.set(core.rawSamples,offset);offset+=length;
  }
  return {sampleRate:48000,input,output};
}

export function speechWindow(signal,rate,seconds,milliseconds=85){
  const count=Math.max(2,Math.round(milliseconds*rate/1000));
  const end=Math.max(count,Math.min(signal.length,Math.round(seconds*rate)));
  return signal.subarray(Math.max(0,end-count),Math.min(signal.length,end));
}
