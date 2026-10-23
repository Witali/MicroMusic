import {AVRCore as RuntimeCore} from './avr-runtime.js';
// C/WASM owns execution. Each CPU has one fixed 64-KiB memory, no host imports.
const url = new URL('../wasm/avr.wasm?v=20261023-ocr0a', import.meta.url);
const bytes = globalThis.process?.versions?.node
  ? await (await import('node:fs/promises')).readFile(url)
  : await (async () => { const r=await fetch(url); if(!r.ok)throw new Error('AVR WASM HTTP '+r.status); return r.arrayBuffer(); })();
export const runtimeModule = await WebAssembly.compile(bytes);
export class AVRCore extends RuntimeCore {
  constructor(binary,eeprom,options={}){
    super(binary,eeprom,{...options,runtimeModule:options.runtimeModule??runtimeModule});
  }
}
