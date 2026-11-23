import{prepareAudio,createInputResampler}from'../../lpx/audio-source.js';
self.onmessage=async({data})=>{
 let source;
 try{
  const name='pcm-'+crypto.randomUUID()+'.tmp';let stats;
  const binary=await(await fetch(new URL('../../lpx/input-resampler.wasm',import.meta.url))).arrayBuffer();
  const fir=await createInputResampler(binary);fir.init(data.referenceRate,8000,data.channels.length);
  const prepared=[];for(let at=0;at<data.channels[0].length;at+=fir.capacity){const n=Math.min(fir.capacity,data.channels[0].length-at);for(let c=0;c<data.channels.length;c++)fir.input.set(data.channels[c].subarray(at,at+n),c*fir.capacity);prepared.push(fir.push(n).slice());}prepared.push(fir.push(0,true).slice());
  const reference=Int16Array.from(prepared.flatMap(p=>Array.from(p)));
  await navigator.locks.request('lpx-input-'+name,async()=>{
   try{
    source=await prepareAudio(data.file,8000,name,()=>{},async url=>(await fetch(url)).arrayBuffer());
    let error=0,energy=0,peak=0;const high=[[0,0],[0,0]];
    for(let at=0;at<source.samples;at+=20480){const pcm=await source.read(at,Math.min(20480,source.samples-at));for(let i=0;i<pcm.length;i++){
      const wanted=(reference[at+i]||0)/32768,actual=pcm[i]/32768;error+=(wanted-actual)**2;energy+=wanted**2;peak=Math.max(peak,Math.abs(wanted-actual));
      const phase=2*Math.PI*2900*(at+i)/8000;for(const[p,value]of[[0,wanted],[1,actual]]){high[p][0]+=value*Math.cos(phase);high[p][1]+=value*Math.sin(phase);}}}
    const relativeRms=Math.sqrt(error/(energy||1));stats={kind:source.kind,samples:source.samples,referenceSamples:reference.length,relativeRms,peakError:peak,amplitude2900:high.map(z=>2*Math.hypot(...z)/source.samples),maxRead:source.maxCompressedRead,resamplerMemory:source.modelMemoryBytes,pass:source.samples===reference.length&&relativeRms<.02};
   }finally{await source?.dispose();source=null;}
  });self.postMessage(stats);
 }catch(error){self.postMessage({error:error.message});}
};
