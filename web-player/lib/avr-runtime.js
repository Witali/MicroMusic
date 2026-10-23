// Shared state/ABI wrapper. Runtime modules are supplied by the caller.
const decoder = new TextDecoder();
function cstring(memory,address) {
  const view=new Uint8Array(memory.buffer); let end=address;
  while(view[end])end++;
  return decoder.decode(view.subarray(address,end));
}
const booleans=new Set(['timer','inIRQ','fastIdle','fastBlocks']);
const optional=new Set(['eempeUntil','clkprUntil']);
const statePrototypes=new WeakMap();
function bindStateFields(core,names){
  const parent=Object.getPrototypeOf(core),key=names.join('\0');
  if(!statePrototypes.has(parent))statePrototypes.set(parent,new Map());
  const layouts=statePrototypes.get(parent);
  if(!layouts.has(key)){
    const prototype=Object.create(parent),index={};
    names.forEach((name,i)=>{
      index[name]=i;
      Object.defineProperty(prototype,name,{
        get(){const v=this._state[i];return booleans.has(name)?!!v:optional.has(name)&&Number.isNaN(v)?undefined:v;},
        set(v){this._state[i]=v===undefined?NaN:Number(v);},
      });
    });
    layouts.set(key,{prototype,index:Object.freeze(index)});
  }
  const layout=layouts.get(key);core._fieldIndex=layout.index;
  Object.setPrototypeOf(core,layout.prototype);
}

export class AVRCore {
  constructor(binary,eeprom,{fastIdle=true,fastBlocks=fastIdle,runtimeModule,configureRuntime}={}) {
    if(!binary.length||binary.length>1024)throw new Error('Flash must contain 1–1024 bytes');
    if(eeprom&&eeprom.length!==64)throw new Error('EEPROM must contain 64 bytes');
    this._exports=new WebAssembly.Instance(runtimeModule).exports;
    const layout=Array.from({length:15},(_,i)=>this._exports.avr_layout(i));
    configureRuntime?.(this._exports);
    // Share field accessors per class/layout; allocating closures on every
    // device makes state-heavy debuggers and instruction hooks megamorphic.
    bindStateFields(this,Array.from({length:layout[1]},(_,i)=>cstring(this._exports.memory,this._exports.avr_field_name(i))));
    const buffer=this._exports.memory.buffer;
    this._state=new Float64Array(buffer,layout[0],layout[1]);
    this.rom=new Uint8Array(buffer,layout[2],1024);this.eeprom=new Uint8Array(buffer,layout[3],64);
    this.data=new Uint8Array(buffer,layout[4],160);
    this.r=this.data.subarray(0,32);this.io=this.data.subarray(32,96);
    this.sram=this.data.subarray(96);this.ram=this.sram;
    this.op=new Uint8Array(buffer,layout[5],512);this.d=new Uint8Array(buffer,layout[6],512);
    this.s=new Uint8Array(buffer,layout[7],512);this.k=new Int16Array(buffer,layout[8],512);
    this.batch=new Uint8Array(buffer,layout[9],512);this.idle=new Uint8Array(buffer,layout[10],512);
    this._frameMemory=new Float64Array(buffer,layout[11],32);
    this._pcm=new Float32Array(buffer,layout[12],4096);this._raw=new Float32Array(buffer,layout[13],4096);
    this._frames=[];this._framesDirty=false;
    this.irqFrames=new Proxy(this._frames,{
      set:(target,key,value)=>{this._framesDirty=true;return Reflect.set(target,key,value);},
      deleteProperty:(target,key)=>{this._framesDirty=true;return Reflect.deleteProperty(target,key);},
    });
    this.rom.fill(255);this.rom.set(binary);this.eeprom.fill(255);if(eeprom)this.eeprom.set(eeprom);
    this._call('avr_reset',Number(fastIdle),Number(fastBlocks));
  }
  _call(name,...args) {
    if(this._framesDirty){
      if(this._frames.length>32)throw new Error('Too many nested IRQ frames');
      this._frameMemory.set(this._frames);this._state[this._fieldIndex.frameCount]=this._frames.length;this._framesDirty=false;
    }
    const result=this._exports[name](...args);
    this._frames.length=this._state[this._fieldIndex.frameCount];
    for(let i=0;i<this._frames.length;i++)this._frames[i]=this._frameMemory[i];
    if(this._state[this._fieldIndex.error]){
      let message=cstring(this._exports.memory,this._exports.avr_error_message());
      if(this._state[this._fieldIndex.error]===2)message+=' at 0x'+(this._state[this._fieldIndex.errorPC]*2).toString(16);
      if(this._state[this._fieldIndex.error]===6)message='Timer0 WGM mode '+((this.io[0x2f]&3)|((this.io[0x33]&8)>>1))+' is not implemented';
      throw new Error(message);
    }
    return result;
  }
  get sreg(){return this.io[0x3f];} set sreg(v){this.io[0x3f]=v;}
  get c(){return this.sreg&1;} set c(v){this.sreg=(this.sreg&~1)|(v&1);}
  get z(){return(this.sreg>>1)&1;} set z(v){this.sreg=(this.sreg&~2)|((v&1)<<1);}
  get i(){return this.sreg>>7;} set i(v){this.sreg=(this.sreg&127)|((v&1)<<7);}
  get t(){return(this.sreg>>6)&1;} set t(v){this.sreg=(this.sreg&~64)|((v&1)<<6);}
  get sp(){return this.io[0x3d];} set sp(v){this.io[0x3d]=v;}
  get pending(){return!!(this.io[0x38]&2);} set pending(v){this.io[0x38]=(this.io[0x38]&~2)|(v?2:0);}
  decode(p){this._call('avr_decode',p);}
  decodeIdle(p){this._call('avr_decode_idle',p);}
  arithmetic(x,y,carry=0,subtract=false){return this._call('avr_arithmetic',x,y,carry,Number(subtract));}
  nzvs(v,overflow=0){this._call('avr_nzvs',v,overflow);}
  push(v){this._call('avr_push',v);} pop(){return this._call('avr_pop');}
  pushPC(v){this._call('avr_push_pc',v);} popPC(){return this._call('avr_pop_pc');}
  timerMode(){return this._call('avr_timer_mode');} updateTimer(){this._call('avr_update_timer');}
  writeIO(a,v){return this._call('avr_write_io',a,v);}
  clock(n){this._call('avr_clock',n);} interrupt(){this._call('avr_interrupt');}
  step(){this._call('avr_step');} skipIdle(){return!!this._call('avr_idle');}
  runBlock(deadline=Infinity){return!!this._call('avr_block',deadline);}
  nextDuty(){
    if(this.step===AVRCore.prototype.step)return this._call('avr_next');
    // Preserve instruction hooks used by musical and timing audits.
    const before=this.writes,deadline=this.cyc+9600000;
    while(this.writes===before){
      if(!(this.fastIdle&&this.idle[this.pc]&&this.skipIdle()))this.step();
      if(this.cyc>deadline)throw new Error('Firmware produced no PWM for one emulated second');
    }
    return this.duty;
  }
  nextStereoDuty(){
    const before=this.leftWrites;this.nextDuty();
    if(this.leftWrites!==before+1)throw new Error('Stereo frame requires one OC0A write before OC0B');
    return this.dutyLeft|(this.duty<<8);
  }
  configureAudio(sampleRate,pwmHz,{cutoff=4000,volume=1,filtered=true,channels=1}={}){
    if(![1,2].includes(channels))throw new Error('Unsupported audio channel count');
    this._call('avr_audio_init',sampleRate,pwmHz,cutoff,volume,Number(filtered));
    this._call('avr_audio_channels',channels);this.audioChannels=channels;
  }
  setAudioControls({cutoff=4000,volume=1}){this._call('avr_audio_controls',cutoff,volume);}
  render(count){
    if(!Number.isInteger(count)||count<1||count>16384)throw new Error('Invalid audio block size');
    const channels=this.audioChannels||1,block=4096/channels;
    const output=new Float32Array(count*channels),raw=new Float32Array(count*channels);let sum=0;
    for(let offset=0;offset<count;offset+=block){
      const n=Math.min(block,count-offset);this._call('avr_render',n);
      output.set(this._pcm.subarray(0,n*channels),offset*channels);raw.set(this._raw.subarray(0,n*channels),offset*channels);
      sum+=(this._exports.avr_average()-128)/128*n;
    }
    this.rawSamples=raw;this.averagePWM=128+128*sum/count;return output;
  }
  filterSamples(input){
    const output=new Float32Array(input.length);
    for(let offset=0;offset<input.length;offset+=4096){
      const n=Math.min(4096,input.length-offset);this._raw.set(input.subarray(offset,offset+n));
      this._call('avr_filter',n);output.set(this._pcm.subarray(0,n),offset);
    }
    return output;
  }
  state(){return{pc:this.pc*2,cycles:this.cyc,irqs:this.irqCount,maxISR:this.maxIRQ,
    lost:this.lost+this.workLost,timerLost:this.lost,workLost:this.workLost,duty:this.duty,
    registers:Array.from(this.r),idleCycles:this.idleCycles};}
}
