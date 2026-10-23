import {AVRCore as TranslatedCore} from './avr-transpiled-runtime.js';
import {resetInputProfileFields,normalizeResetInputProfile} from './devices/attiny13a-reset-profile.js';
import {AT13_FUSE_MASK as FUSE} from './attiny13a-registers.js';
const configuration={oscillatorHz:1,watchdogHz:2,vccMicrovolts:3,bandgapMicrovolts:4,
  fuseLow:5,fuseHigh:6,lock:7,adcFirstSample:8,comparatorPropagationHalf:9,
  bandgapStartupHalf:10,comparatorInitial:11,wakeStartupHalf:12,spmCommandCycles:13,flashMaximum:14,bodRecoveryNs:15,factoryOsccal96:16,fuseStartupProfile:17,
  nvmClockProfile:18,nvmCalibrationReferenceHz:19};
const powerFields=['porAssertMicrovolts','porReleaseMicrovolts','bod00Microvolts','bod01Microvolts','bod10Microvolts',
  'bodHysteresisMicrovolts','bodFilterNs','bodRecoveryNs','flashProgrammingMinMicrovolts'];
const timestamp=value=>{
  if(typeof value!=='bigint'||value<0n||value>BigInt(Number.MAX_SAFE_INTEGER))throw Error('Timestamp must be an exact nonnegative bigint below 2^53');
  return value;
};
const timestampPs=value=>{
  if(typeof value!=='bigint'||value<0n||value>0xffffffffffffffffn)throw Error('Picosecond timestamp must be a nonnegative uint64 bigint');
  return value;
};
export class ATtiny13A extends TranslatedCore {
  static async fromPackage(input,{fastIdle=true}={}){
    const {decodePackage,assertPackageRuntimeABI}=await import('./attiny13a-package.js');
    const decoded=await decodePackage(input);
    const core=new this(decoded.flash,decoded.eeprom,{...decoded.options,fastIdle,_packageVersion:decoded.version,
      runtimeModule:await WebAssembly.compile(decoded.runtime),
      precompiled:{bytes:decoded.translated,manifest:decoded.manifest},
      optimizeFlags:decoded.manifest.optimizeFlags,maxBlockInstructions:decoded.manifest.maxBlockInstructions,
      validateRuntimeABI:abi=>assertPackageRuntimeABI(decoded,abi),
    });
    core.packageIntegrity={...decoded.integrity};return core;
  }
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
    super(binary,eeprom,{...options,fastIdle:false,runtimeModule:options.runtimeModule,configureRuntime:exports=>{
      if(options.resumable!==undefined&&typeof options.resumable!=='boolean')throw Error('resumable must be a boolean');
      if(options.resumable){
        if(!options.osccalHz)throw Error('Resumable execution requires a physical OSCCAL table');
        if(!exports.avr_device_phase_enable?.(1))throw Error('Runtime has no resumable CPU mode');
      }
      for(const [name,key] of Object.entries(configuration))if(options[name]!==undefined){
        const value=options[name];if(!Number.isInteger(value)||value<0||value>0xffffffff)throw Error('Invalid device configuration: '+name);
        const accepted=exports.avr_device_configure(key,value);
        const historicalDefault=options._packageVersion===1&&((key===15&&value===60000)||([16,17].includes(key)&&value===0));
        if(!accepted&&!historicalDefault)throw Error('Invalid device configuration: '+name);
      }
      if(options.osccalHz!=null){
        const table=options.osccalHz;
        if(!Array.isArray(table)||table.length!==128||!table.some(Boolean))throw Error('osccalHz must contain128 CAL frequencies (zero means unspecified)');
        for(let cal=0;cal<128;cal++)if(!Number.isInteger(table[cal])||table[cal]<0||table[cal]>1000000000||
          !exports.avr_device_configure_osccal_hz?.(cal,table[cal]))throw Error('Invalid OSCCAL frequency at CAL '+cal);
      }
      if(options.powerResetProfile!=null){
        const profile=options.powerResetProfile;
        if(typeof profile!=='object'||Array.isArray(profile)||Object.keys(profile).sort().join()!==[...powerFields].sort().join())throw Error('Invalid powerResetProfile fields');
        for(const [index,name] of powerFields.entries()){
          const value=profile[name];
          if(!Number.isInteger(value)||value<0||value>0xffffffff||!exports.avr_device_configure_power?.(index+1,value))throw Error('Invalid powerResetProfile: '+name);
        }
        if(!exports.avr_device_configure_power(0,1))throw Error('Power reset profile unavailable');
      }
      if(options.resetInputProfile!=null){
        const profile=normalizeResetInputProfile(options.resetInputProfile);
        if(!options.osccalHz)throw Error('resetInputProfile requires a physical OSCCAL table');
        if(!((options.fuseHigh??255)&FUSE.HIGH_DWEN))throw Error('resetInputProfile requires DWEN unprogrammed');
        for(const [index,name] of resetInputProfileFields.entries())
          if(!exports.avr_device_configure_reset_input?.(index+1,profile[name]))throw Error('RESET input profile unavailable: '+name);
        if(!exports.avr_device_configure_reset_input(0,1))throw Error('RESET input profile unavailable');
      }
    }});
    this._exports.avr_device_bind_generation();
    this._generation=this._exports.avr_device_generation();
    this._physicalRate=0;
    this._ps=!!this._exports.avr_device_physical_mode?.();
    this.fastIdle=options.fastIdle??true;
  }
  _refreshFlash(){
    const generation=this._exports.avr_device_generation();
    if(generation===this._generation)return false;
    // An in-flight instruction owns its latched code and operands. Replacing
    // its continuation before retirement would replay or discard its effects.
    if(this._translationOptions.resumable&&this._exports.avr_device_phase_active())return false;
    const debug=this.debugEnabled;this._compile();this.debugEnabled=debug;
    this._exports.avr_device_bind_generation();this._generation=generation;return true;
  }
  runUntil(at){
    this._clockDomain(false);
    const target=Number(timestamp(at));let instructions=0;
    if(at<this._exports.avr_device_time64())throw Error('Cannot run backwards');
    do{instructions+=this._execute('runUntil',target);}while(this._refreshFlash()&&this._exports.avr_device_time()<target);
    return instructions;
  }
  _clockDomain(ps){if(this._ps!==ps)throw Error(ps?'Use runUntil/injectPins/setAnalog/drainPins with the fixed oscillator profile':'Use runUntilPs/injectPinsPs/setAnalogPs/drainPinsPs with the physical clock profile');}
  runUntilPs(at){
    this._clockDomain(true);timestampPs(at);let instructions=0;
    let now=BigInt.asUintN(64,this._exports.avr_device_time_ps());
    if(at<now)throw Error('Cannot run backwards');
    // Bound both the f64 time offset and the generated i32 instruction count.
    // A one-second slice has at most1e9 instructions at the configuration limit.
    while(now<at){
      const origin=BigInt.asUintN(64,this._exports.avr_device_rebase_time());
      const end=at-origin>1000000000000n?origin+1000000000000n:at;
      const target=Number(end-origin);let refreshed;
      do{
        instructions+=this._execute('runUntil',target);refreshed=this._refreshFlash();
        now=BigInt.asUintN(64,this._exports.avr_device_time_ps());
      }while(refreshed&&now<end);
      if(now<end)throw Error('Device stopped before the physical deadline');
    }
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
    this._clockDomain(false);this._injectPins('avr_device_inject_pins',timestamp(at),mask,levels);
  }
  injectPinsPs({at,mask,levels}){
    this._clockDomain(true);this._injectPins('avr_device_inject_pins_ps',timestampPs(at),mask,levels);
  }
  _injectPins(name,at,mask,levels){
    if(at===0xffffffffffffffffn)throw Error('Invalid pin input timestamp');
    if(![mask,levels].every(v=>Number.isInteger(v)&&v>=0&&v<64))throw Error('Pin masks must contain PB0..PB5 only');
    if(!this._call(name,at,mask,levels))throw Error('Invalid or full timestamped input queue');
  }
  setAnalog({at,pin,microvolts}){
    this._clockDomain(false);this._setAnalog('avr_device_inject_analog',timestamp(at),pin,microvolts);
  }
  setAnalogPs({at,pin,microvolts}){
    this._clockDomain(true);this._setAnalog('avr_device_inject_analog_ps',timestampPs(at),pin,microvolts);
  }
  _setAnalog(name,at,pin,microvolts){
    if(at===0xffffffffffffffffn)throw Error('Invalid analog input timestamp');
    if(!Number.isInteger(pin)||pin<0||pin>5||!Number.isInteger(microvolts)||microvolts<0||microvolts>0x7fffffff)throw Error('Invalid analog input');
    if(!this._call(name,at,pin,microvolts))throw Error('Invalid or full timestamped input queue');
  }
  setVccPs({at,microvolts}){
    this._clockDomain(true);timestampPs(at);
    if(!this._exports.avr_device_power_enabled?.())throw Error('VCC inputs require an explicit powerResetProfile');
    if(at===0xffffffffffffffffn||!Number.isInteger(microvolts)||microvolts<0||microvolts>0x7fffffff)throw Error('Invalid supply input');
    if(!this._call('avr_device_inject_vcc_ps',at,microvolts))throw Error('Invalid or full timestamped input queue');
  }
  drainPins(){
    this._clockDomain(false);return this._drainPins('','baseHalf');
  }
  drainPinsPs(){
    this._clockDomain(true);return this._drainPins('_ps','timePs');
  }
  _drainPins(suffix,timeKey){
    const result=[],exports=this._exports;
    for(let count;(count=exports['avr_device_pin_count'+suffix]());){
      const pointer=exports['avr_device_pin_buffer'+suffix](),view=new DataView(exports.memory.buffer,pointer,count*16);
      for(let n=0;n<count;n++){const at=n*16;result.push({[timeKey]:view.getBigUint64(at,true),levels:view.getUint8(at+8),driven:view.getUint8(at+9),pullups:view.getUint8(at+10),floating:view.getUint8(at+11),contention:view.getUint8(at+12)});}
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
      if(this._ps)this._exports.avr_device_rebase_time();
      this._exports.avr_device_audio_begin();
      try{done=this._execute('capturePhysical',n);}finally{this._exports.avr_device_audio_end();}
      result.set(this._raw.subarray(0,done*channels),offset*channels);offset+=done;
      const refreshed=this._refreshFlash();
      if(!done&&!refreshed)throw Error('Device stopped before the next audio frame');
    }
    return result;
  }
  state(){
    const exports=this._exports,view=new DataView(exports.memory.buffer,this._ps?exports.avr_device_pins_ps():exports.avr_device_pins(),16);
    const time=this._ps?{timePs:BigInt.asUintN(64,exports.avr_device_time_ps()),startupDeadlinePs:BigInt.asUintN(64,exports.avr_device_startup_deadline_ps()),oscillatorHz:exports.avr_device_oscillator_hz()}:
      {baseHalf:exports.avr_device_time64(),startupDeadline:BigInt.asUintN(64,exports.avr_device_startup_deadline?.()??exports.avr_device_time64())};
    const power=exports.avr_device_power_enabled?.()?{powerResetEnabled:true,vccMicrovolts:exports.avr_device_vcc_microvolts()}:{};
    const resetInput=exports.avr_device_reset_input_enabled?.()?{resetInputEnabled:true,
      resetInputAsserted:!!exports.avr_device_reset_input_asserted(),
      resetInputDeadlinePs:BigInt.asUintN(64,exports.avr_device_reset_input_deadline_ps())}:{};
    const p=this._phaseABI,phase=p?new DataView(exports.memory.buffer,p.pointer,p.bytes):null;
    const continuation=phase?{cpuPhase:{active:phase.getUint32(p.active-p.pointer,true),
      execPc:phase.getUint32(p.execPc-p.pointer,true),stage:phase.getUint32(p.stage-p.pointer,true),
      remainingHalves:phase.getBigUint64(p.remaining-p.pointer,true),retired:phase.getBigUint64(p.retired-p.pointer,true)}}:{};
    return {...super.state(),...time,...power,...resetInput,...continuation,clockDivisor:exports.avr_device_divisor(),
      halted:!!exports.avr_device_halted(),sleeping:!!exports.avr_device_sleep_phase(),resetHeld:!!exports.avr_device_reset_held(),
      starting:!!exports.avr_device_starting?.(),
      bodDisabled:!!exports.avr_device_bod_disabled?.(),bodRecovering:!!exports.avr_device_bod_recovering?.(),
      resetCount:exports.avr_device_reset_count(),deviceFault:exports.avr_device_fault(),pendingIRQs:exports.avr_device_pending(),
      pins:{levels:view.getUint8(8),driven:view.getUint8(9),pullups:view.getUint8(10),floating:view.getUint8(11),contention:view.getUint8(12)}};
  }
}
