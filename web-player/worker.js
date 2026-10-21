// Register the message handler before the asynchronous WASM import finishes.
// Otherwise the initial init message can arrive while the module graph awaits
// fetch/compilation and be discarded by the Worker's event loop.
const rendererModule = import('./lib/renderer.js');
let renderer, entry, port, controls = {cutoff:4000,volume:1};

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
self.onmessage = async ({data}) => {
  try {
    const { Renderer } = await rendererModule;
    if (data.type === 'init') {
      entry = data.entry; controls = data.controls ?? controls;
      renderer = new Renderer(entry, data.sampleRate, controls);
      self.postMessage({type:'ready',state:renderer.core.state()});
    } else if (data.type === 'audio-port') {
      controls = data.controls ?? controls;
      renderer = new Renderer(entry, data.sampleRate, controls);
      port?.close(); port = data.port;
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
  } catch (error) { fail(error); }
};
