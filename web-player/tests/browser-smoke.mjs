import {createRenderer} from '../lib/engines.js';
const results=document.getElementById('results');results.textContent='';
const log=text=>results.textContent+=text+'\n';
const assert=(ok,message)=>{if(!ok)throw new Error(message);};
const difference=(a,b)=>{assert(a.length===b.length,'Sample count');let max=0;for(let i=0;i<a.length;i++)max=Math.max(max,Math.abs(a[i]-b[i]));return max;};
function message(target,type){
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{target.removeEventListener('message',receive);reject(new Error(type+' timed out'));},10000);
    function receive({data}){
      if(data.type!==type&&data.type!=='error')return;
      clearTimeout(timer);target.removeEventListener('message',receive);
      if(data.type==='error')reject(new Error(data.message));else resolve(data);
    }
    target.addEventListener('message',receive);
  });
}
let worker,ports;
try{
  const catalog=await(await fetch('../firmware.json')).json(),entry=catalog.entries[0];
  for(const engine of [undefined,'js','transpiled']){
    // Post immediately: imports must not drop init or overtake queued controls.
    const name=engine??'wasm';
    worker=new Worker('../worker.js',{type:'module'});
    const ready=message(worker,'ready');worker.postMessage({type:'init',entry,engine,sampleRate:48000,controls:{cutoff:9000,volume:.65}});
    assert((await ready).engine===name,'Selected Worker engine differs');
    log('PASS: immediate Worker init / '+name);
    ports=new MessageChannel();ports.port1.start();
    worker.postMessage({type:'audio-port',port:ports.port2,sampleRate:48000,controls:{cutoff:9000,volume:.65}},[ports.port2]);
    const reference=await createRenderer(entry,48000,{cutoff:9000,volume:.65},engine);
    for(let n=0;n<3;n++){
      const state=message(worker,'state'),samples=message(ports.port1,'samples');
      ports.port1.postMessage({type:'need',frames:4096});
      const [actualState,actualSamples]=await Promise.all([state,samples]),expected=reference.render(4096);
      assert(difference(actualSamples.samples,expected)===0,'Worker PCM differs');
      assert(JSON.stringify(actualState.state)===JSON.stringify(reference.core.state()),'Worker CPU/IRQ counters differ');
      assert(Math.abs(actualState.averagePWM-reference.core.averagePWM)<1e-12,'Raw PWM average differs');
    }
    log('PASS: Worker/MessageChannel PCM, PWM, CPU cycles and IRQs / '+name);
    worker.terminate();ports.port1.close();
  }
  for(const engine of ['js','wasm','transpiled'])for(const rate of [44100,48000,96000])for(const cutoff of [4000,6000,9000,12000]){
    const renderer=await createRenderer(entry,rate,{cutoff,volume:.65},engine),actual=renderer.render(16384);
    const context=new OfflineAudioContext(1,actual.length,rate),source=context.createBufferSource();
    source.buffer=context.createBuffer(1,actual.length,rate);source.buffer.copyToChannel(renderer.core.rawSamples,0);
    const hp=context.createBiquadFilter(),lp=context.createBiquadFilter(),gain=context.createGain();
    hp.type='highpass';hp.frequency.value=35;hp.Q.value=20*Math.log10(.5);
    lp.type='lowpass';lp.frequency.value=Math.min(cutoff,rate*.45);lp.Q.value=20*Math.log10(.5);gain.gain.value=.65;
    source.connect(hp);hp.connect(lp);lp.connect(gain);gain.connect(context.destination);source.start();
    const expected=(await context.startRendering()).getChannelData(0),error=difference(actual,expected);
    // The browser graph is not bit-exact to f64 DSP. Bound its maximum absolute
    // difference at 5e-5 full scale (-86 dB), including all filter stages.
    assert(error<5e-5,'Web Audio filter error '+error);
    log('PASS: '+engine+' filters vs Web Audio '+rate+' Hz / '+cutoff+' Hz; max error '+error.toExponential(2));
  }
  log('ALL BROWSER CHECKS PASSED');
}catch(error){results.className='fail';log('FAIL: '+error.message);console.error(error);}
finally{worker?.terminate();ports?.port1.close();}
