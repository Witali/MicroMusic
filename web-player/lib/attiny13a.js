import {ATtiny13A as DeviceRuntime} from './attiny13a-runtime.js';
const url=new URL('../wasm/attiny13a.wasm?v=20261101-low-power-clock',import.meta.url);
const bytes=globalThis.process?.versions?.node
  ? await (await import('node:fs/promises')).readFile(url)
  : await (async()=>{const r=await fetch(url);if(!r.ok)throw Error('ATtiny13A WASM HTTP '+r.status);return r.arrayBuffer();})();
export const runtimeModule=await WebAssembly.compile(bytes);
export const getRuntimeBytes=()=>new Uint8Array(new Uint8Array(bytes));
export class ATtiny13A extends DeviceRuntime {
  constructor(binary,eeprom,options={}){
    super(binary,eeprom,{...options,runtimeModule:options.runtimeModule??runtimeModule});
  }
}
