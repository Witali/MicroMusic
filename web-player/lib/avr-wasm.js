// Profile-aware C/WASM loader; generated and physical paths share the bridge.
import {AVRCore as RuntimeCore} from './avr-runtime.js';
const url = new URL('../wasm/avr.wasm?v=20261025-um88', import.meta.url);
const bytes = globalThis.process?.versions?.node
  ? await (await import('node:fs/promises')).readFile(url)
  : await (async () => { const r=await fetch(url); if(!r.ok)throw new Error('AVR WASM HTTP '+r.status); return r.arrayBuffer(); })();
const module = await WebAssembly.compile(bytes);
export const runtimeModule=module;

export class AVRCore extends RuntimeCore {
  constructor(binary,eeprom,options={}){super(binary,eeprom,{...options,runtimeModule:module});}
}
