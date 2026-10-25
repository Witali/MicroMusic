import {AVRCore as PeripheralRuntime} from './avr-runtime.js';
import {runtimeABI,transpileAVR} from './avr-transpiler.js';
import {deviceProfile,DEFAULT_DEVICE} from './devices/profiles.js';
const littleEndian=new Uint8Array(Uint16Array.of(1).buffer)[0]===1;
const runtimeCaches=new WeakMap(),legacyCache=new Map();
const abiKey=abi=>JSON.stringify([abi.data,abi.rom,abi.idle,abi.frames,abi.pwm,
  abi.memoryPages,!!abi.device,Object.entries(abi.state).sort(([a],[b])=>a.localeCompare(b)),
  abi.phase?Object.entries(abi.phase).sort(([a],[b])=>a.localeCompare(b)):null]);
function compileTranslation(binary,abi,options) {
  const runtime=options.runtimeModule;
  let cache=legacyCache;
  if(runtime){if(!runtimeCaches.has(runtime))runtimeCaches.set(runtime,new Map());cache=runtimeCaches.get(runtime);}
  const profile=deviceProfile(options.device??DEFAULT_DEVICE);
  const padded=new Uint8Array(profile.flashBytes).fill(255);padded.set(binary);
  // Exact image keys avoid hash collisions. Configuration does not enter the
  // lowering: live clocks/fuses are supplied by this runtime instance's bus.
  const key=JSON.stringify([profile.name,abiKey(abi),!!options.resumable,options.optimizeFlags??true,options.maxBlockInstructions??32,options.optimizePhaseLocals??false,Array.from(padded)]);
  if(options.cacheTranslation!==false&&cache.has(key)) {
    const cached=cache.get(key);cache.delete(key);cache.set(key,cached);
    return {...cached,cacheHit:true};
  }
  const generated=transpileAVR(binary,abi,options);
  const compiled={...generated,module:new WebAssembly.Module(generated.bytes),cacheHit:false};
  if(options.cacheTranslation!==false) {
    cache.set(key,compiled);
    // Bounded per runtime identity; instances and mutable device memory are
    // never cached. Changed Flash naturally selects a different image key.
    while(cache.size>8||[...cache.values()].reduce((n,v)=>n+v.bytes.length,0)>16*1024*1024)
      cache.delete(cache.keys().next().value);
  }
  return compiled;
}

// CPU instructions are generated WASM. Only timers, I/O and interrupt entry
// use the existing C/WASM peripheral runtime, sharing its linear memory.
export class AVRCore extends PeripheralRuntime {
  constructor(binary,eeprom,options={}) {
    if(options.optimizePhaseLocals!==undefined&&(typeof options.optimizePhaseLocals!=='boolean'||options.optimizePhaseLocals&&!options.resumable))
      throw Error('Phase-local optimization requires resumable execution');
    const profile=deviceProfile(options.device??DEFAULT_DEVICE);
    super(binary,eeprom,{fastIdle:options.fastIdle??true,fastBlocks:false,runtimeModule:options.runtimeModule,configureRuntime:options.configureRuntime});
    this._translationOptions={...options,device:profile.name};
    this._compile(binary);
  }
  _compile(binary=this.rom) {
    const options=this._translationOptions;
    const abi=runtimeABI(this._exports,{resumable:!!options.resumable});let generated;
    if(!this._translated)options.validateRuntimeABI?.(abi);
    if(!this._translated&&options.precompiled) {
      generated=options.precompiled;
      if(generated.manifest.device!==options.device)throw Error('Packaged translation device profile mismatch');
      if((generated.manifest.executionMode==='resumable-v1')!==!!options.resumable)throw Error('Packaged translation execution mode mismatch');
      if(abiKey(generated.manifest.abi)!==abiKey(abi))throw Error('Packaged translation runtime ABI mismatch');
      generated={...generated,module:new WebAssembly.Module(generated.bytes),cacheHit:false};
    } else generated=compileTranslation(binary,abi,options);
    // Public diagnostics must not mutate a module cached for another device.
    this.transpilation=structuredClone(generated.manifest);
    this._phaseABI=generated.manifest.abi.phase?{...generated.manifest.abi.phase}:null;
    this.transpiledBytes=new Uint8Array(generated.bytes);
    this.translationCacheHit=generated.cacheHit;this._translatedModule=generated.module;
    this._translated=new WebAssembly.Instance(generated.module,{avr:{
      memory:this._exports.memory,clock:this._exports.avr_clock,
      interrupt:this._exports.avr_interrupt,writeIO:this._exports.avr_write_io,idle:this._exports.avr_idle,
      readIO:this._exports.avr_read_io,writeMasked:this._exports.avr_write_io_masked,
      ready:this._exports.avr_device_ready,time:this._exports.avr_device_time,wait:this._exports.avr_device_wait,
      control:this._exports.avr_device_control,lpm:this._exports.avr_device_lpm,
      audioDeadline:this._exports.avr_device_audio_deadline,audioSample:this._exports.avr_device_audio_sample,
      pending:this._exports.avr_device_pending,
      cpuDeadline:this._exports.avr_device_cpu_deadline,
      idleUntil:this._exports.avr_device_idle,
      phaseClock:this._exports.avr_device_phase_clock,
      phaseDeadline:this._exports.avr_device_phase_deadline,
      phaseRetire:this._exports.avr_device_phase_retire,
    }}).exports;
    this._bridges=Object.fromEntries(Object.entries(this._translated).filter(([,fn])=>typeof fn==='function').map(([name,fn])=>[name,{...this._exports,translated:fn}]));
    const pwm=generated.manifest.abi.pwm;
    this._pwm8=new Uint8Array(this._exports.memory.buffer,pwm,8192);
    this._pwm16=new Uint16Array(this._exports.memory.buffer,pwm,4096);
  }
  _execute(name,...args) {
    // Reuse ABI state/diagnostic synchronization without entering the C CPU.
    const native=this._exports;
    try {
      this._exports=this._bridges[name];const result=this._call('translated',...args);
      if(this.controlRequest)throw new Error(['','SLEEP requires a sleep/wake peripheral model','SPM requires a Flash-controller peripheral model','WDR requires a watchdog peripheral model','CPU stopped at BREAK'][this.controlRequest]);
      if(name==='capturePWM'&&this._translated.captureFault.value)throw new Error('Stereo frame requires one OC0A write before OC0B');
      return result;
    }
    finally {this._exports=native;}
  }
  step(){
    if(this._translationOptions.resumable)this._exports.avr_device_phase_deadline(Infinity);
    this._execute('step');
  }
  get controlRequest(){return this._translated.controlRequest.value;}
  get watchdogResetCycle(){return this._translated.watchdogResetCycle.value;}
  get debugEnabled(){return!!this._translated.debugEnabled.value;}
  set debugEnabled(value){this._translated.debugEnabled.value=Number(!!value);}
  acknowledgeControl(cycles=0){
    if(!this.controlRequest)throw new Error('No pending MCU operation');
    if(!Number.isInteger(cycles)||cycles<0||cycles>0x7fffffff||(this.controlRequest===2&&cycles===0))throw new Error('Provide the actual MCU operation cycle count');
    if(cycles){this.clock(cycles);this.interrupt();}
    this._translated.controlRequest.value=0;
  }
  run(instructions){
    if(!Number.isInteger(instructions)||instructions<0||instructions>0x7fffffff)throw new Error('Invalid instruction count');
    return this._execute('run',instructions);
  }
  runBlock(deadline=Infinity){return !this._translationOptions.resumable&&!!this._execute('block',deadline,0x7fffffff);}
  skipIdle(){return !this._translationOptions.resumable&&this.fastIdle&&!!this._call('avr_idle');}
  nextDuty(){
    if(this._translationOptions.resumable)throw Error('Resumable execution requires capturePhysical for audio');
    return this._execute('nextDuty');
  }
  capturePWM(count,channels=1){
    if(this._translationOptions.resumable)throw Error('Resumable execution requires capturePhysical for audio');
    if(!Number.isInteger(count)||count<0||count>1048576||![1,2].includes(channels))throw new Error('Invalid PWM capture size or channels');
    const output=channels===2?new Uint16Array(count):new Uint8Array(count);
    for(let offset=0;offset<count;offset+=4096){
      const n=Math.min(4096,count-offset);this._execute('capturePWM',n,channels);
      if(channels===1)output.set(this._pwm8.subarray(0,n),offset);
      else if(littleEndian)output.set(this._pwm16.subarray(0,n),offset);
      else for(let i=0;i<n;i++)output[offset+i]=this._pwm8[2*i]|(this._pwm8[2*i+1]<<8);
    }
    return output;
  }
  // The inherited C renderer executes its own CPU. Use renderer-transpiled.js
  // for audio so every instruction goes through this module instead.
  render(){throw new Error('Use the transpiled renderer for generated AVR audio');}
  decode(){throw new Error('Transpiled Flash is immutable; construct a new AVRCore');}
  decodeIdle(){throw new Error('Transpiled Flash is immutable; construct a new AVRCore');}
}
