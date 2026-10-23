import {AVRCore as PeripheralRuntime} from './avr-wasm.js';
import {runtimeABI,transpileAVR} from './avr-transpiler.js';

// CPU instructions are generated WASM. Only timers, I/O and interrupt entry
// use the existing C/WASM peripheral runtime, sharing its linear memory.
export class AVRCore extends PeripheralRuntime {
  constructor(binary,eeprom,options={}) {
    super(binary,eeprom,{fastIdle:false,fastBlocks:false});
    const generated=transpileAVR(binary,runtimeABI(this._exports),options);
    this.transpilation=generated.manifest;
    this.transpiledBytes=generated.bytes;
    this._translated=new WebAssembly.Instance(new WebAssembly.Module(generated.bytes),{avr:{
      memory:this._exports.memory,clock:this._exports.avr_clock,
      interrupt:this._exports.avr_interrupt,writeIO:this._exports.avr_write_io,
    }}).exports;
    this._bridges=Object.fromEntries(Object.entries(this._translated).map(([name,fn])=>[name,{...this._exports,translated:fn}]));
  }
  _execute(name,...args) {
    // Reuse ABI state/diagnostic synchronization without entering the C CPU.
    const native=this._exports;
    try {this._exports=this._bridges[name];return this._call('translated',...args);}
    finally {this._exports=native;}
  }
  step(){this._execute('step');}
  run(instructions){
    if(!Number.isInteger(instructions)||instructions<0||instructions>0x7fffffff)throw new Error('Invalid instruction count');
    return this._execute('run',instructions);
  }
  runBlock(deadline=Infinity){return!!this._execute('block',deadline,0x7fffffff);}
  skipIdle(){return false;}
  nextDuty(){return this._execute('nextDuty');}
  // The inherited C renderer executes its own CPU. Use renderer-transpiled.js
  // for audio so every instruction goes through this module instead.
  render(){throw new Error('Use the transpiled renderer for generated AVR audio');}
  decode(){throw new Error('Transpiled Flash is immutable; construct a new AVRCore');}
  decodeIdle(){throw new Error('Transpiled Flash is immutable; construct a new AVRCore');}
}
