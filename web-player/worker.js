import { createRenderer, DEFAULT_ENGINE } from './lib/engines.js?v=20261025-um88';
let renderer, entry, port, engine = DEFAULT_ENGINE, controls = {cutoff:4000,volume:1};
let messages = Promise.resolve();

function publish(samples, milliseconds) {
  const raw = renderer.core.rawSamples;
  const channels=renderer.channels||1,frames=raw.length/channels,scopes=[],averages=[];
  for(let ch=0;ch<channels;ch++){
    const scope=new Float32Array(512);let sum=0;
    for(let i=0;i<frames;i++)sum+=raw[i*channels+ch];
    for(let i=0;i<scope.length;i++)scope[i]=raw[Math.floor(i*frames/scope.length)*channels+ch];
    scopes.push(scope);averages.push(128+128*sum/frames);
  }
  self.postMessage({type:'state',state:renderer.core.state(),scope:scopes[0],scopes,averages,
    averagePWM:renderer.core.averagePWM,
    headroom:frames * 1000 / renderer.sampleRate / Math.max(milliseconds, 0.01)}, scopes.map(scope=>scope.buffer));
}
function fail(error) {
  port?.postMessage({type:'error'});
  self.postMessage({type:'error',message:error.message});
}
self.onmessage = ({data}) => {
  // Preserve init/audio-port/controls order while the chosen engine imports.
  messages = messages.then(async () => {
    if (data.type === 'init') {
      entry = data.entry; engine = data.engine ?? DEFAULT_ENGINE; controls = data.controls ?? controls;
      renderer = await createRenderer(entry, data.sampleRate, controls, engine);
      self.postMessage({type:'ready',engine,state:renderer.core.state()});
    } else if (data.type === 'audio-port') {
      controls = data.controls ?? controls;
      port?.close();
      renderer = await createRenderer(entry, data.sampleRate, controls, engine);
      port = data.port;
      port.onmessage = ({data}) => {
        try {
          if (data.type !== 'need') return;
          const started = performance.now(), samples = renderer.render(data.frames);
          publish(samples, performance.now() - started);
          port.postMessage({type:'samples',samples}, [samples.buffer]);
        } catch (error) { fail(error); }
      };
      port.start();
    } else if (data.type === 'controls') {
      controls = {...controls,...data.controls}; renderer?.setAudioControls(controls);
    }
  }).catch(fail);
};
