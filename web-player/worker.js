import { createRenderer, DEFAULT_ENGINE } from './lib/engines.js';
let renderer, entry, port, engine = DEFAULT_ENGINE, controls = {cutoff:4000,volume:1};
let messages = Promise.resolve();

function publish(samples, milliseconds) {
  const scope = new Float32Array(512);
  const raw = renderer.core.rawSamples;
  for (let i = 0; i < scope.length; i++) scope[i] = raw[Math.floor(i * raw.length / scope.length)];
  self.postMessage({type:'state',state:renderer.core.state(),scope,
    averagePWM:renderer.core.averagePWM,
    headroom:samples.length * 1000 / renderer.sampleRate / Math.max(milliseconds, 0.01)}, [scope.buffer]);
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
