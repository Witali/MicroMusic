import {CPU} from '../vendor/avr8js/0.21.1/browser/cpu/cpu.js';
import {avrInstruction} from '../vendor/avr8js/0.21.1/browser/cpu/instruction.js';
import {AVRTimer,timer0Config,timer1Config,timer2Config} from '../vendor/avr8js/0.21.1/browser/peripherals/timer.js';
import {AVRIOPort,PinState,portBConfig,portCConfig,portDConfig} from '../vendor/avr8js/0.21.1/browser/peripherals/gpio.js';
import {AVREEPROM,EEPROMMemoryBackend} from '../vendor/avr8js/0.21.1/browser/peripherals/eeprom.js';
import {ATMEGA328P_PROFILE,resolveATmega328PProfile} from './atmega328p-profile.js';
export {ATMEGA328P_PROFILE,resolveATmega328PProfile} from './atmega328p-profile.js';

// Geometry: Microchip ATmega328P, 32 KiB Flash / 2 KiB SRAM / 1 KiB EEPROM.
// Register addresses and timer vectors come from the pinned AVR8js configs,
// also used by Codecs/Speex/AVR/tests/verify_player.mjs (not a Tiny88 map).
const OUTPUTS=Object.freeze({
  OC2B:Object.freeze({port:'D',pin:timer2Config.compPinB,ocr:timer2Config.OCRB,label:'PD3 / Arduino D3'}),
  OC1A:Object.freeze({port:'B',pin:timer1Config.compPinA,ocr:timer1Config.OCRA,label:'PB1 / Arduino D9'}),
});

// Same bounded correction as the existing Speex AVR8js player oracle:
// honor the instruction after SEI/RETI and charge four IRQ-entry cycles.
export function tickATmega328P(cpu,previouslyEnabled){
  const defer=!previouslyEnabled&&cpu.interruptsEnabled;
  if(defer)cpu.data[95]&=127;
  const pc=cpu.pc;
  cpu.tick();
  if(defer)cpu.data[95]|=128;
  if(cpu.pc!==pc){cpu.cycles+=2;return true;}
  return false;
}

export class ATmega328P{
  constructor(flash,eeprom=null,{target='atmega328p',cpuHz=16000000,pwmOutput='OC2B'}={}){
    this.profile=resolveATmega328PProfile(target,{cpuHz});
    if(!(flash instanceof Uint8Array)||!flash.length||flash.length>this.profile.flashBytes)throw Error('Invalid ATmega328P Flash image');
    if(eeprom!==null&&(!(eeprom instanceof Uint8Array)||eeprom.length>this.profile.eepromBytes))throw Error('Invalid ATmega328P EEPROM image');
    if(!Object.hasOwn(OUTPUTS,pwmOutput))throw Error('Unsupported ATmega328P PWM output');
    this.output=OUTPUTS[pwmOutput];this.pwmOutput=pwmOutput;
    const program=new Uint16Array(this.profile.flashBytes/2).fill(65535);
    new Uint8Array(program.buffer).set(flash);
    this.cpu=new CPU(program,this.profile.sramBytes);
    this.ports={B:new AVRIOPort(this.cpu,portBConfig),C:new AVRIOPort(this.cpu,portCConfig),D:new AVRIOPort(this.cpu,portDConfig)};
    this.timers=[new AVRTimer(this.cpu,timer0Config),new AVRTimer(this.cpu,timer1Config),new AVRTimer(this.cpu,timer2Config)];
    this.eeprom=new EEPROMMemoryBackend(this.profile.eepromBytes);
    if(eeprom)this.eeprom.memory.set(eeprom);
    this.eepromPeripheral=new AVREEPROM(this.cpu,this.eeprom);
    this.irqCount=0;this.maxIRQ=0;this.irqStart=null;this.timerLost=0;
    this.instructions=0;this.pinEdges=0;this.pwmWrites=0;this.minimumSP=this.cpu.SP;
    this.timeline=[];this.timelineIndex=0;this.sampleCycle=0;this.sampleFrame=0;
    this.observedPin=0;this.observedRegister=0;this.pinLevel=0;
    this.ports[this.output.port].addListener(()=>{
      const level=Number(this.ports[this.output.port].pinState(this.output.pin)===PinState.High);
      if(level!==this.pinLevel){this.pinLevel=level;this.pinEdges++;this.timeline.push([this.cpu.cycles,level,null]);}
    });
    const oldWrite=this.cpu.writeHooks[this.output.ocr];
    this.cpu.writeHooks[this.output.ocr]=(value,old,address,mask)=>{
      const handled=oldWrite?.(value,old,address,mask)??false;
      if(!handled)this.cpu.data[address]=value;
      this.pwmWrites++;this.timeline.push([this.cpu.cycles,null,value]);
      this.onPwmWrite?.(value,this.cpu.cycles);
      return true;
    };
    const setFlag=this.cpu.setInterruptFlag.bind(this.cpu);
    this.cpu.setInterruptFlag=interrupt=>{
      if(this.cpu.pendingInterrupts[interrupt.address]&&(this.cpu.data[interrupt.enableRegister]&interrupt.enableMask))this.timerLost++;
      setFlag(interrupt);
    };
  }
  get cyc(){return this.cpu.cycles;}
  get data(){return this.cpu.data;}
  get r(){return this.cpu.data.subarray(0,32);}
  step(){
    const opcode=this.cpu.progMem[this.cpu.pc],enabled=this.cpu.interruptsEnabled;
    if(opcode===undefined)throw Error('ATmega328P PC outside Flash');
    avrInstruction(this.cpu);this.instructions++;
    if(opcode===0x9518&&this.irqStart!==null){this.maxIRQ=Math.max(this.maxIRQ,this.cpu.cycles-this.irqStart);this.irqStart=null;}
    if(tickATmega328P(this.cpu,enabled)){this.irqCount++;this.irqStart=this.cpu.cycles-4;}
    this.minimumSP=Math.min(this.minimumSP,this.cpu.SP);
    if(this.cpu.SP<this.profile.sramStart||this.cpu.SP>this.profile.ramEnd)throw Error('ATmega328P stack outside SRAM');
  }
  integrateUntil(end){
    let cursor=this.sampleCycle,pinArea=0,registerArea=0;
    while(this.timelineIndex<this.timeline.length&&this.timeline[this.timelineIndex][0]<=end){
      const [at,pin,ocr]=this.timeline[this.timelineIndex++],span=Math.max(0,at-cursor);
      pinArea+=span*this.observedPin;registerArea+=span*this.observedRegister;cursor=Math.max(cursor,at);
      if(pin!==null)this.observedPin=pin;if(ocr!==null)this.observedRegister=ocr;
    }
    pinArea+=(end-cursor)*this.observedPin;registerArea+=(end-cursor)*this.observedRegister;
    const duration=end-this.sampleCycle;this.sampleCycle=end;
    return [2*pinArea/duration-1,(registerArea/duration-128)/128];
  }
  captureAudio(count,sampleRate){
    const physical=new Float32Array(count),registers=new Float32Array(count);
    for(let i=0;i<count;i++){
      const end=(++this.sampleFrame)*this.profile.cpuHz/sampleRate;
      while(this.cpu.cycles<end)this.step();
      const [pin,ocr]=this.integrateUntil(end);physical[i]=pin;registers[i]=ocr;
    }
    this.timeline=this.timeline.slice(this.timelineIndex);this.timelineIndex=0;
    return {physical,registers};
  }
  state(){
    return {pc:this.cpu.pc*2,cycles:this.cpu.cycles,irqs:this.irqCount,maxISR:this.maxIRQ,
      lost:this.timerLost,timerLost:this.timerLost,workLost:0,duty:this.cpu.data[this.output.ocr],
      registers:Array.from(this.r),idleCycles:0,device:this.profile.id,engine:'avr8js',
      pwmOutput:this.pwmOutput,pinEdges:this.pinEdges,pwmWrites:this.pwmWrites,minimumSP:this.minimumSP};
  }
}
