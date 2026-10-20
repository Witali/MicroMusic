import { Renderer } from './lib/renderer.js';
let renderer, entry, port;

function publish(samples, milliseconds) {
  const scope = new Float32Array(512);
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i];
  for (let i = 0; i < scope.length; i++) scope[i] = samples[Math.floor(i * samples.length / scope.length)];
  self.postMessage({type:'state',state:renderer.core.state(),scope,
    averagePWM:128 + 128 * sum / samples.length,
    headroom:samples.length * 1000 / renderer.sampleRate / Math.max(milliseconds, 0.01)}, [scope.buffer]);
}
function fail(error) {
  port?.postMessage({type:'error'});
  self.postMessage({type:'error',message:error.message});
}
self.onmessage = ({data}) => {
  try {
    if (data.type === 'init') {
      entry = data.entry; renderer = new Renderer(entry, data.sampleRate);
      self.postMessage({type:'ready',state:renderer.core.state()});
    } else if (data.type === 'audio-port') {
      renderer = new Renderer(entry, data.sampleRate);
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
    }
  } catch (error) { fail(error); }
};
