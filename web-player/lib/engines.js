export const DEFAULT_ENGINE = 'wasm';
import {DEFAULT_EMULATION_CONFIGURATION,emulationConfiguration,executionOptions,nominalVerificationDeviceOptions} from './emulation-configurations.js';
export {DEFAULT_EMULATION_CONFIGURATION,EMULATION_CONFIGURATIONS} from './emulation-configurations.js';

// Load only the selected engine: JS playback also works without WebAssembly.
export async function createRenderer(entry, sampleRate, controls, engine, configuration=DEFAULT_EMULATION_CONFIGURATION) {
  emulationConfiguration(configuration);
  const verification=configuration==='verification',tiny88=entry.device?.toLowerCase()==='attiny88';
  engine??=verification&&!tiny88?'transpiled':DEFAULT_ENGINE;
  if (!['js','wasm','transpiled','device'].includes(engine)) throw new Error('Unknown AVR engine: ' + engine);
  if(verification&&!tiny88&&!['device','transpiled'].includes(engine))throw Error('ATtiny13A verification requires AVR → WASM / the device engine');
  if(tiny88&&engine==='device')throw Error('The physical device engine supports only ATtiny13A');
  if(entry.devicePackage){
    if(!['device','transpiled'].includes(engine))throw Error('An ATtiny13A package requires the device engine or AVR → WASM');
    const {createPackageRenderer}=await import('./renderer-package.js?v=20261026-emulation-config');
    const renderer=await createPackageRenderer(entry,sampleRate,controls,{verification});
    renderer.engine=engine;renderer.configuration=configuration;renderer.emulationModel='packaged-device';return renderer;
  }
  const physical=engine==='device'||verification&&!tiny88;
  const rendererModule = await (physical ? import('./renderer-device.js?v=20261026-persistent-cache') : engine === 'js' ? import('./renderer-js.js?v=20261026-emulation-config') : engine === 'transpiled' ? import('./renderer-transpiled.js?v=20261026-emulation-config') : import('./renderer.js?v=20261026-emulation-config'));
  const {Renderer}=rendererModule;
  const options=verification&&!tiny88?nominalVerificationDeviceOptions(entry.cpuHz):executionOptions(configuration);
  const renderer = physical?await rendererModule.createDeviceRenderer(entry,sampleRate,controls,options):engine==='js'||engine==='transpiled'
    ? new Renderer(entry,sampleRate,controls,undefined,options) : new Renderer(entry,sampleRate,controls,options);
  renderer.engine = engine;
  renderer.configuration=configuration;
  renderer.emulationModel=physical?'physical-device':verification?'core-timer-reference':'music';
  return renderer;
}
