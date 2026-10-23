import {runtimeModule} from './avr-wasm.js';
import {AVRCore as TranslatedRuntime} from './avr-transpiled-runtime.js';
export class AVRCore extends TranslatedRuntime {
  constructor(binary,eeprom,options={}){
    super(binary,eeprom,{...options,runtimeModule:options.runtimeModule??runtimeModule});
  }
}
