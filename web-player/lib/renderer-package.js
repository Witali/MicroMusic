import {Renderer as AudioRenderer} from './renderer-js.js';
import {ATtiny13A} from './attiny13a-runtime.js';

// This path imports no default WASM loader: both binaries come from the package.
export async function createPackageRenderer(entry,sampleRate,controls){
  const core=await ATtiny13A.fromPackage(entry.devicePackage);
  return new Renderer({...entry,pwmHz:entry.pwmHz??1},sampleRate,controls,core);
}
class Renderer extends AudioRenderer {
  render(count){
    if(!Number.isInteger(count)||count<1||count>16384)throw Error('Invalid audio block size');
    return this.processRaw(this.core.capturePhysical(count,this.sampleRate,this.channels),count);
  }
}
