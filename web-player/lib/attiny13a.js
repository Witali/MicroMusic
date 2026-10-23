import {AVRCore as TranslatedCore} from './avr-transpiled.js';
const url=new URL('../wasm/attiny13a.wasm?v=20261023-device',import.meta.url);
const bytes=globalThis.process?.versions?.node
  ? await (await import('node:fs/promises')).readFile(url)
  : await (async()=>{const r=await fetch(url);if(!r.ok)throw Error('ATtiny13A WASM HTTP '+r.status);return r.arrayBuffer();})();
const runtimeModule=await WebAssembly.compile(bytes);
const configuration={oscillatorHz:1,watchdogHz:2,vccMicrovolts:3,bandgapMicrovolts:4,
  fuseLow:5,fuseHigh:6,lock:7,adcFirstSample:8,comparatorPropagationHalf:9,
  bandgapStartupHalf:10,comparatorInitial:11,wakeStartupHalf:12,spmCommandCycles:13,flashMaximum:14,bodRecoveryNs:15};
const timestamp=value=>{
  if(typeof value!=='bigint'||value<0n||value>BigInt(Number.MAX_SAFE_INTEGER))throw Error('Timestamp must be an exact nonnegative bigint below 2^53');
  return value;
};
export class ATtiny13A extends TranslatedCore {
  _call(name,...args){
    try{return super._call(name,...args);}
    catch(error){
      if(this.error===26){this.error=0;return 0;}
      const code=this._exports.avr_device_fault();
      if(code)throw Error(`ATtiny13A peripheral fault ${code}, detail ${this._exports.avr_device_fault_detail()}`);
      throw error;
    }
  }
  constructor(binary,eeprom,options={}){
    super(binary,eeprom,{...options,fastIdle:false,runtimeModule,configureRuntime:exports=>{
      for(const [name,key] of Object.entries(configuration))if(options[name]!==undefined){
        const value=options[name];if(!Number.isInteger(value)||value<0||value>0xffffffff||!exports.avr_device_configure(key,value))throw Error('Invalid device configuration: '+name);
      }
    }});
    this._exports.avr_device_bind_generation();
    this._generation=this._exports.avr_device_generation();
    this._physicalRate=0;
    this.fastIdle=options.fastIdle??true;
  }
  _refreshFlash(){
    const generation=this._exports.avr_device_generation();
    if(generation===this._generation)return false;
    const debug=this.debugEnabled;this._compile();this.debugEnabled=debug;
    this._exports.avr_device_bind_generation();this._generation=generation;return true;
  }
  runUntil(at){
    const target=Number(timestamp(at));let instructions=0;
    if(at<this._exports.avr_device_time64())throw Error('Cannot run backwards');
    do{instructions+=this._execute('runUntil',target);}while(this._refreshFlash()&&this._exports.avr_device_time()<target);
    return instructions;
  }
  readIO(address){this._address(address);return this._call('avr_read_io',address);}
  writeIO(address,value,mask=255){
    this._address(address);
    if(![value,mask].every(v=>Number.isInteger(v)&&v>=0&&v<256))throw Error('I/O value and mask must be bytes');
    const stalls=this._call('avr_write_io_masked',address,value,mask);if(stalls)this.clock(stalls);return stalls;
  }
  _address(value){if(!Number.isInteger(value)||value<0||value>63)throw Error('I/O address must be 0..63');}
  injectPins({at,mask,levels}){
    if(![mask,levels].every(v=>Number.isInteger(v)&&v>=0&&v<64))throw Error('Pin masks must contain PB0..PB5 only');
    if(!this._call('avr_device_inject_pins',timestamp(at),mask,levels))throw Error('Invalid or full timestamped input queue');
  }
  setAnalog({at,pin,microvolts}){
    if(!Number.isInteger(pin)||pin<0||pin>5||!Number.isInteger(microvolts)||microvolts<0||microvolts>0x7fffffff)throw Error('Invalid analog input');
    if(!this._call('avr_device_inject_analog',timestamp(at),pin,microvolts))throw Error('Invalid or full timestamped input queue');
  }
  drainPins(){
    const result=[],exports=this._exports;
    for(let count;(count=exports.avr_device_pin_count());){
      const pointer=exports.avr_device_pin_buffer(),view=new DataView(exports.memory.buffer,pointer,count*16);
      for(let n=0;n<count;n++){const at=n*16;result.push({baseHalf:view.getBigUint64(at,true),levels:view.getUint8(at+8),driven:view.getUint8(at+9),pullups:view.getUint8(at+10),floating:view.getUint8(at+11),contention:view.getUint8(at+12)});}
      exports.avr_device_pin_consume(count);
    }
    return result;
  }
  capturePhysical(count,sampleRate,channels=1){
    if(!Number.isInteger(count)||count<0||count>1048576||!Number.isInteger(sampleRate)||sampleRate<8000||sampleRate>192000||![1,2].includes(channels))throw Error('Invalid physical capture');
    if(this._physicalRate&&this._physicalRate!==sampleRate)throw Error('Reset capture before changing sample rate');
    if(!this._physicalRate){this._call('avr_device_audio_config',sampleRate,channels);this._physicalRate=sampleRate;this._physicalChannels=channels;}
    if(channels!==this._physicalChannels)throw Error('Reset capture before changing channel count');
    const result=new Float32Array(count*channels);let offset=0;
    while(offset<count){
      const n=Math.min(4096/channels,count-offset);let done;
      this._exports.avr_device_audio_begin();
      try{done=this._execute('capturePhysical',n);}finally{this._exports.avr_device_audio_end();}
      result.set(this._raw.subarray(0,done*channels),offset*channels);offset+=done;
      const refreshed=this._refreshFlash();
      if(!done&&!refreshed)throw Error('Device stopped before the next audio frame');
    }
    return result;
  }
  state(){
    const exports=this._exports,view=new DataView(exports.memory.buffer,exports.avr_device_pins(),16);
    return {...super.state(),baseHalf:exports.avr_device_time64(),clockDivisor:exports.avr_device_divisor(),
      halted:!!exports.avr_device_halted(),sleeping:!!exports.avr_device_sleep_phase(),resetHeld:!!exports.avr_device_reset_held(),
      bodDisabled:!!exports.avr_device_bod_disabled(),bodRecovering:!!exports.avr_device_bod_recovering(),
      resetCount:exports.avr_device_reset_count(),deviceFault:exports.avr_device_fault(),pendingIRQs:exports.avr_device_pending(),
      pins:{levels:view.getUint8(8),driven:view.getUint8(9),pullups:view.getUint8(10),floating:view.getUint8(11),contention:view.getUint8(12)}};
  }
}
