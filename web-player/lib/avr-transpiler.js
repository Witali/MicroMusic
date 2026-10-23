// ATtiny13A binary -> WebAssembly MVP. No C compiler or WAT assembler required.
// Encodings: WebAssembly Core, binary/{modules,instructions,values}.html.
// AVR semantics: Microchip DS40002198A and ATtiny13A DS40002307A.
import {AT13_DATA,AT13_MEMORY} from './attiny13a-registers.js';
const uleb = value => {
  const out = []; do { const byte = value & 127; value >>>= 7; out.push(byte | (value ? 128 : 0)); } while (value);
  return out;
};
const sleb = value => {
  const out = []; let more;
  do { const byte = value & 127; value >>= 7; more = !((value === 0 && !(byte & 64)) || (value === -1 && (byte & 64))); out.push(byte | (more ? 128 : 0)); } while (more);
  return out;
};
const bytes = (...parts) => parts.flat(Infinity);
const vector = entries => bytes(uleb(entries.length), entries);
const string = text => { const data = Array.from(new TextEncoder().encode(text)); return bytes(uleb(data.length), data); };
const section = (id, data) => bytes(id, uleb(data.length), data);
const constant = n => bytes(0x41, sleb(n));
const get = n => [0x20, n], set = (n, value) => bytes(value, 0x21, n);
const binary = (op, a, b) => bytes(a, b, op);
const add = (a,b) => binary(0x6a,a,b), sub = (a,b) => binary(0x6b,a,b);
const and = (a,b) => binary(0x71,a,b), or = (a,b) => binary(0x72,a,b), xor = (a,b) => binary(0x73,a,b);
const shl = (a,n) => binary(0x74,a,constant(n)), shr = (a,n) => binary(0x76,a,constant(n));
const eq = (a,b) => binary(0x46,a,b), lt = (a,b) => binary(0x48,a,b), ge = (a,b) => binary(0x4e,a,b);
const eqz = a => bytes(a,0x45);
const load8 = address => bytes(address,0x2d,0,0);
const load8Signed = address => bytes(address,0x2c,0,0);
const store8 = (address,value) => bytes(address,value,0x3a,0,0);
const load64 = address => bytes(address,0x2b,3,0);
const store64 = (address,value) => bytes(address,value,0x39,3,0);
const float = n => { const data = new Uint8Array(8); new DataView(data.buffer).setFloat64(0,n,true); return bytes(0x44,Array.from(data)); };
const asFloat = value => bytes(value,0xb7);
const asInt = value => bytes(value,0xaa);
const call = (index,...args) => bytes(args,0x10,uleb(index));
const condition = (test,yes,no=[]) => bytes(test,0x04,0x40,yes,no.length ? bytes(0x05,no) : [],0x0b);
const conditionValue = (test,yes,no) => bytes(test,0x04,0x7f,yes,0x05,no,0x0b);
const sign = (v,bit) => v & bit ? v - 2*bit : v;
const width = w => (w&0xfe0f)===0x9000 || (w&0xfe0f)===0x9200 || (w&0xfe0e)===0x940c || (w&0xfe0e)===0x940e ? 2 : 1;

// Decode independently of the interpreter. Aliases (CLR, TST, LSL, ROL, SER,
// SBR, CBR and individual BRxx/flag names) share their real machine encoding.
export function decodeAVR(word, second = 0xffff) {
  let name='unsupported', d=(word>>4)&31, s=(word&15)|((word>>5)&16), k=0;
  if(word===0)name='NOP';
  else if(word===0x9508)name='RET';
  else if(word===0x9518)name='RETI';
  else if(word===0x94f8)name='CLI';
  else if(word===0x9478)name='SEI';
  else if(word===0x9409)name='IJMP';
  else if(word===0x9509)name='ICALL';
  else if(word===0x9588)name='SLEEP';
  else if(word===0x95a8)name='WDR';
  else if(word===0x9598)name='BREAK';
  else if(word===0x95e8)name='SPM';
  else if(word===0x95c8){name='LPM';d=0;}
  else if((word&0xfe08)===0xfa00 || (word&0xfe08)===0xf800){name=word&0x200?'BST':'BLD';s=word&7;}
  else if((word&0xff00)===0x9600 || (word&0xff00)===0x9700){name=word&0x100?'SBIW':'ADIW';d=24+2*((word>>4)&3);k=(word&15)|((word>>2)&48);}
  else if((word&0xfc00)===0x0800)name='SBC';
  else if((word&0xfc00)===0x0400)name='CPC';
  else if((word&0xfc00)===0x1000)name='CPSE';
  else if((word&0xff0f)===0x9408){name='FLAG';d=(word>>4)&7;k=Number(!(word&128));}
  else if((word&0xf000)===0xd000){name='RCALL';k=sign(word&4095,2048);}
  else if((word&0xf000)===0xc000){name='RJMP';k=sign(word&4095,2048);}
  else if((word&0xf800)===0xf000){name='BRANCH';d=word&7;s=Number(!(word&0x400));k=sign((word>>3)&127,64);}
  else if((word&0xfc08)===0xfc00){name='SKIP';s=word&7;k=Number(!!(word&0x200));}
  else if((word&0xf000)===0xe000){name='LDI';d=16+((word>>4)&15);k=(word&15)|((word>>4)&240);}
  else if([0x3000,0x4000,0x5000,0x6000,0x7000].includes(word&0xf000)){
    name=({0x3000:'CPI',0x4000:'SBCI',0x5000:'SUBI',0x6000:'ORI',0x7000:'ANDI'})[word&0xf000];d=16+((word>>4)&15);k=(word&15)|((word>>4)&240);
  } else if((word&0xff00)===0x0100){name='MOVW';d=2*((word>>4)&15);s=2*(word&15);}
  else if(({0x0c00:'ADD',0x1c00:'ADC',0x1800:'SUB',0x2000:'AND',0x2400:'EOR',0x2800:'OR',0x2c00:'MOV',0x1400:'CP'})[word&0xfc00])
    name=({0x0c00:'ADD',0x1c00:'ADC',0x1800:'SUB',0x2000:'AND',0x2400:'EOR',0x2800:'OR',0x2c00:'MOV',0x1400:'CP'})[word&0xfc00];
  else if(({0x9401:'NEG',0x9403:'INC',0x940a:'DEC',0x9400:'COM',0x9406:'LSR',0x9405:'ASR',0x9407:'ROR',0x9402:'SWAP'})[word&0xfe0f])
    name=({0x9401:'NEG',0x9403:'INC',0x940a:'DEC',0x9400:'COM',0x9406:'LSR',0x9405:'ASR',0x9407:'ROR',0x9402:'SWAP'})[word&0xfe0f];
  else if((word&0xfe0f)===0x9000 || (word&0xfe0f)===0x9200){name=word&0x200?'STS':'LDS';k=second;}
  else if((word&0xf800)===0xb000 || (word&0xf800)===0xb800){name=word&0x800?'OUT':'IN';k=((word>>5)&48)|(word&15);}
  else if((word&0xfc00)===0x9800){name=['CBI','SBIC','SBI','SBIS'][(word>>8)&3];d=(word>>3)&31;k=word&7;}
  else if((word&0xfe0f)===0x920f)name='PUSH';
  else if((word&0xfe0f)===0x900f)name='POP';
  else if([0x900c,0x900d,0x900e,0x9009,0x900a,0x9001,0x9002,0x920c,0x920d,0x920e,0x9209,0x920a,0x9201,0x9202].includes(word&0xfe0f)){
    const low=word&15;name=word&0x200?'ST':'LD';s=low>=12?26:low>=9?28:30;k=[1,9,13].includes(low)?1:[2,10,14].includes(low)?-1:2;
  } else if((word&0xd200)===0x8000 || (word&0xd200)===0x8200){
    name=word&0x200?'ST':'LD';s=word&8?28:30;k=2+((word&7)|((word>>7)&0x18)|((word>>8)&0x20));
  } else if((word&0xfe0f)===0x9004 || (word&0xfe0f)===0x9005){name='LPM';k=word&1;}
  return {name,d,s,k,words:width(word)};
}

// The runtime ABI is discovered, never hard-coded to a particular C build.
export function runtimeABI(exports) {
  const data=new Uint8Array(exports.memory.buffer), decoder=new TextDecoder();
  const state={};
  for(let i=0;i<exports.avr_layout(1);i++){
    const start=exports.avr_field_name(i);let end=start;while(data[end])end++;
    state[decoder.decode(data.subarray(start,end))]=exports.avr_layout(0)+8*i;
  }
  return {state,data:exports.avr_layout(4),rom:exports.avr_layout(2),idle:exports.avr_layout(10),frames:exports.avr_layout(11),pwm:exports.avr_layout(13),memoryPages:exports.memory.buffer.byteLength/65536,device:typeof exports.avr_device_time==='function'};
}

const writes={ADD:63,ADC:63,SUB:63,CP:63,CPI:63,SUBI:63,NEG:63,SBC:63,SBCI:63,CPC:63,ADIW:31,SBIW:31,BST:64,AND:30,ANDI:30,OR:30,ORI:30,EOR:30,INC:30,DEC:30,COM:31,LSR:31,ASR:31,ROR:31};
const reads={ADC:1,ROR:1,SBC:3,SBCI:3,CPC:3,BLD:64};
const pure=new Set(['NOP','LDI','MOV','MOVW','SWAP','BLD',...Object.keys(writes)]);
const guardedMemory=new Set(['LD','ST','LPM']);
const batchable=i=>pure.has(i.name)||guardedMemory.has(i.name);
const instructionCycles=i=>i.name==='LPM'?3:['ADIW','SBIW','LD','ST'].includes(i.name)?2:1;
const popcount=n=>{let count=0;for(;n;n&=n-1)count++;return count;};

export function transpileAVR(image, abi, {optimizeFlags=true, maxBlockInstructions=32}={}) {
  const full=!!abi.device,canBatch=i=>batchable(i)&&(!full||i.name!=='LPM');
  if(!(image instanceof Uint8Array)||!image.length||image.length>1024)throw new Error('ATtiny13A Flash must contain 1–1024 bytes');
  if(!Number.isInteger(maxBlockInstructions)||maxBlockInstructions<2||maxBlockInstructions>64)throw new Error('Block size must be 2–64 instructions');
  for(const field of ['pc','cyc','error','errorPC','irqDelay','overflowAt','writes','frameCount'])
    if(!Number.isInteger(abi?.state?.[field]))throw new Error('Invalid AVR runtime ABI: '+field);
  const flash=new Uint8Array(1024).fill(255);flash.set(image);
  const word=p=>flash[(p&511)*2]|(flash[(p&511)*2+1]<<8);
  const decoded=Array.from({length:512},(_,p)=>({...decodeAVR(word(p),word(p+1)),pc:p,word:word(p)}));
  const S=name=>constant(abi.state[name]), stateF=name=>load64(S(name)), state=name=>asInt(stateF(name));
  const putF=(name,value)=>store64(S(name),value), put=(name,value)=>putF(name,asFloat(value));
  const reg=n=>load8(constant(abi.data+n)), writeReg=(n,value)=>store8(constant(abi.data+n),value);
  const dataAt=address=>add(constant(abi.data),address);
  const flagsAddress=constant(abi.data+AT13_DATA.SREG), flags=()=>get(5);
  const fail=(code,result=false)=>bytes(put('error',constant(code)),result?constant(0):[],0x0f);
  const guard=()=>condition(state('error'),[0x0f]);
  // Runtime imports are WASM functions, not JS callbacks. None execute opcodes.
  const imports=[['clock',0],['interrupt',1],['writeIO',2],['idle',5]];
  const CLOCK=0, IRQ=1, IO=2, IDLE=3;
  if(full)imports.push(['readIO',4],['writeMasked',7],['ready',5],['time',8],['wait',9],['control',7],['lpm',4],['audioDeadline',8],['audioSample',4],['pending',5],['cpuDeadline',10],['idleUntil',9]);
  const READ=4,MASKED=5,READY=6,TIME=7,WAIT=8,CONTROL=9,LPM=10,AUDIO_DEADLINE=11,AUDIO_SAMPLE=12,PENDING=13;
  const firstFunction=imports.length;
  const clock=value=>bytes(call(CLOCK,asFloat(value)),guard());
  const clockHalf=cycles=>bytes(call(CLOCK,float(cycles)),guard());
  const finish=()=>bytes(guard(),put('pc',and(state('pc'),constant(511))),clock(get(7)),call(IRQ));

  // Locals: x,y,carry,total,value,flags,address,cycles,temp (i32); f64 temporaries.
  const X=get(0),Y=get(1),C=get(2),T=get(3),V=get(4),Z=get(6);
  function updateFlags(mask, formula) {
    if(!mask)return [];
    let value=and(flags(),constant(255^mask));
    for(let bit=0;bit<8;bit++)if(mask&(1<<bit))value=or(value,shl(formula(bit),bit));
    return set(5,value);
  }
  function alu(i,mask) {
    const {name,d,s,k}=i;let code=[];
    if(['CP','CPI','CPC'].includes(name)&&!mask)return code;
    if(name==='NOP')return code;
    if(name==='LDI')return writeReg(d,constant(k));
    if(name==='MOV')return writeReg(d,reg(s));
    if(name==='MOVW')return bytes(writeReg(d,reg(s)),writeReg(d+1,reg(s+1)));
    if(name==='SWAP')return writeReg(d,or(shl(and(reg(d),constant(15)),4),shr(reg(d),4)));
    if(name==='BST')return updateFlags(mask,()=>and(shr(reg(d),s),constant(1)));
    if(name==='BLD')return writeReg(d,or(and(reg(d),constant(255^(1<<s))),shl(and(shr(flags(),6),constant(1)),s)));
    if(name==='ADIW'||name==='SBIW'){
      const subtract=name==='SBIW';
      code.push(...set(0,or(reg(d),shl(reg(d+1),8))),...set(3,subtract?sub(X,constant(k)):add(X,constant(k))),...set(4,and(T,constant(65535))));
      const n=shr(V,15),old=shr(X,15),overflow=subtract?and(old,xor(n,constant(1))):and(xor(old,constant(1)),n);
      code.push(...updateFlags(mask,bit=>[subtract?lt(T,constant(0)):binary(0x4b,T,constant(65535)),eqz(V),n,overflow,xor(n,overflow)][bit]),...writeReg(d,V),...writeReg(d+1,shr(V,8)));
      return code;
    }
    code.push(...set(0,name==='ASR'?load8Signed(constant(abi.data+d)):reg(d)));
    if(['ADD','ADC','SUB','CP','CPI','SUBI','NEG','SBC','SBCI','CPC'].includes(name)){
      const subtract=['SUB','CP','CPI','SUBI','NEG','SBC','SBCI','CPC'].includes(name),chained=['SBC','SBCI','CPC'].includes(name);
      code.push(...set(1,['CPI','SUBI','SBCI'].includes(name)?constant(k):name==='NEG'?X:reg(s)));
      if(name==='NEG')code.push(...set(0,constant(0)));
      code.push(...set(2,name==='ADC'||chained?and(flags(),constant(1)):constant(0)),
        ...set(3,subtract?sub(sub(X,Y),C):add(add(X,Y),C)),...set(4,and(T,constant(255))));
      const n=shr(V,7), overflow=shr(and(and(subtract?xor(X,Y):xor(xor(X,Y),constant(255)),xor(X,V)),constant(128)),7);
      code.push(...updateFlags(mask,bit=>[
        subtract?lt(T,constant(0)):binary(0x4b,T,constant(255)), chained?and(eqz(V),and(shr(flags(),1),constant(1))):eqz(V), n, overflow, xor(n,overflow),
        subtract?lt(and(X,constant(15)),add(and(Y,constant(15)),C)):binary(0x4b,add(add(and(X,constant(15)),and(Y,constant(15))),C),constant(15)),
      ][bit]));
      if(!['CP','CPI','CPC'].includes(name))code.push(...writeReg(d,V));
    }else{
      let value,overflow=constant(0),carry=and(X,constant(1));
      if(['AND','ANDI','OR','ORI','EOR'].includes(name)){
        const rhs=['ANDI','ORI'].includes(name)?constant(k):reg(s);
        value=name==='EOR'?xor(X,rhs):['AND','ANDI'].includes(name)?and(X,rhs):or(X,rhs);
      }else if(name==='INC'){value=and(add(X,constant(1)),constant(255));overflow=eq(V,constant(128));}
      else if(name==='DEC'){value=and(sub(X,constant(1)),constant(255));overflow=eq(V,constant(127));}
      else if(name==='COM'){value=xor(X,constant(255));carry=constant(1);}
      else if(name==='LSR'){value=shr(X,1);overflow=carry;}
      else if(name==='ASR'){value=and(binary(0x75,X,constant(1)),constant(255));overflow=xor(shr(V,7),carry);}
      else if(name==='ROR'){value=or(shr(X,1),shl(and(flags(),constant(1)),7));overflow=xor(shr(V,7),carry);}
      else throw new Error('Missing ALU lowering: '+name);
      code.push(...set(4,value),...writeReg(d,V),...updateFlags(mask,bit=>[carry,eqz(V),shr(V,7),overflow,xor(shr(V,7),overflow)][bit]));
    }
    return code;
  }
  function push(value) {
    return bytes(set(6,reg(AT13_DATA.SPL)),condition(or(lt(Z,constant(AT13_MEMORY.RAMSTART)),binary(0x4b,Z,constant(AT13_MEMORY.RAMEND))),fail(3)),
      store8(dataAt(Z),value),writeReg(AT13_DATA.SPL,sub(Z,constant(1))),
      condition(lt(reg(AT13_DATA.SPL),state('minSP')),put('minSP',reg(AT13_DATA.SPL))));
  }
  function pop(local) {
    return bytes(set(6,reg(AT13_DATA.SPL)),condition(or(lt(Z,constant(AT13_MEMORY.RAMSTART-1)),ge(Z,constant(AT13_MEMORY.RAMEND))),fail(4)),
      set(6,add(Z,constant(1))),writeReg(AT13_DATA.SPL,Z),set(local,load8(dataAt(Z))));
  }
  function effects(i) {
    const {name,d,s,k,pc:p}=i,next=(p+1)&511;
    if(pure.has(name))return bytes(full?clock(constant(instructionCycles(i))):[],alu(i,writes[name]||0),set(7,constant(full?0:instructionCycles(i))));
    if(['SLEEP','WDR','BREAK','SPM'].includes(name)){
      if(full&&name!=='BREAK')return bytes(name==='SPM'?[]:clock(constant(1)),set(7,call(CONTROL,constant({SLEEP:1,SPM:2,WDR:3}[name]),or(reg(30),shl(reg(31),8)),or(reg(0),shl(reg(1),8)))),guard());
      // Device requests are exported globals, not calls from WASM into JS.
      // SPM cannot invent a fixed latency; its controller completes it later.
      if(name==='SPM')return bytes(constant(2),0x24,0,store8(flagsAddress,flags()),0x0f);
      if(name==='SLEEP')return condition(and(reg(85),constant(32)),bytes(constant(1),0x24,0));
      if(name==='BREAK')return condition([0x23,2],bytes(constant(4),0x24,0));
      return bytes(binary(0xa0,stateF('cyc'),float(1)),0x24,1,condition(and(reg(65),constant(0x48)),bytes(constant(3),0x24,0)));
    }
    if(name==='RJMP')return bytes(put('pc',constant((next+k)&511)),set(7,constant(2)));
    if(name==='BRANCH')return condition(eq(and(shr(flags(),d),constant(1)),constant(s)),bytes(put('pc',constant((next+k)&511)),set(7,constant(2))));
    if(name==='SKIP'){
      const skip=width(word(next));return condition(eq(and(shr(reg(d),s),constant(1)),constant(k)),bytes(put('pc',constant((next+skip)&511)),set(7,constant(1+skip))));
    }
    if(name==='CPSE'){
      const skip=width(word(next));return condition(eq(reg(d),reg(s)),bytes(put('pc',constant((next+skip)&511)),set(7,constant(1+skip))));
    }
    if(name==='SBIC'||name==='SBIS'){
      const skip=width(word(next));return bytes(full?bytes(clockHalf(.5),set(0,call(READ,constant(d))),clockHalf(.5)):clock(constant(1)),set(7,constant(0)),condition(eq(and(shr(full?X:reg(32+d),k),constant(1)),constant(name==='SBIS'?1:0)),bytes(put('pc',constant((next+skip)&511)),set(7,constant(skip)))));
    }
    if(name==='CLI')return set(5,and(flags(),constant(127)));
    if(name==='SEI')return bytes(set(5,or(flags(),constant(128))),put('irqDelay',constant(1)));
    if(name==='FLAG')return bytes(d===6&&k?condition(and(binary(0x47,and(flags(),constant(64)),constant(0)),binary(0x47,state('inIRQ'),constant(0))),putF('workLost',binary(0xa0,stateF('workLost'),float(1)))):[],set(5,or(and(flags(),constant(255^(1<<d))),constant(k<<d))));
    // The manuals specify cycle totals and stack ordering, not every internal
    // stack phase. The full-device digital profile uses accesses at C2/C3;
    // every access follows a reset-aware clock barrier (see AVR_TO_WASM.md).
    const stackClock=n=>full?clock(constant(n)):[];
    if(name==='PUSH')return bytes(set(0,reg(d)),stackClock(2),push(X),set(7,constant(full?0:2)));
    if(name==='POP')return bytes(stackClock(2),pop(0),writeReg(d,X),set(7,constant(full?0:2)));
    if(name==='RCALL')return bytes(stackClock(2),push(constant(next&255)),stackClock(1),push(constant(next>>8)),put('pc',constant((next+k)&511)),set(7,constant(full?0:3)));
    if(name==='IJMP'||name==='ICALL')return bytes(set(0,and(or(reg(30),shl(reg(31),8)),constant(511))),
      name==='ICALL'?bytes(stackClock(2),push(constant(next&255)),stackClock(1),push(constant(next>>8))):[],
      put('pc',X),set(7,constant(name==='ICALL'?(full?0:3):2)));
    if(name==='RET'||name==='RETI'){
      let code=bytes(stackClock(2),pop(0),stackClock(1),pop(1),stackClock(1),put('pc',and(or(shl(X,8),Y),constant(511))),set(7,constant(full?0:4)));
      if(name==='RETI')code.push(...set(5,or(flags(),constant(128))),put('irqDelay',constant(1)),
        condition(state('frameCount'),bytes(put('frameCount',sub(state('frameCount'),constant(1))),
          set(9,load64(add(constant(abi.frames),shl(state('frameCount'),3)))),
          // Full-device RETI has already charged its four cycles.
          putF('maxIRQ',binary(0xa5,stateF('maxIRQ'),binary(0xa1,binary(0xa0,stateF('cyc'),float(full?0:4)),get(9)))))),
        put('inIRQ',binary(0x4b,state('frameCount'),constant(0))),
        condition(state('inIRQ'),putF('irqStart',load64(add(constant(abi.frames),shl(sub(state('frameCount'),constant(1)),3)))),putF('irqStart',float(0))));
      return code;
    }
    if(name==='IN')return bytes(full?bytes(clockHalf(.5),set(0,call(READ,constant(k))),clockHalf(.5),writeReg(d,X)):bytes(clock(constant(1)),writeReg(d,reg(32+k))),set(7,constant(0)));
    if(name==='OUT'||name==='SBI'||name==='CBI')return bytes(clock(constant(name==='OUT'?1:2)),set(7,full?call(MASKED,constant(name==='OUT'?k:d),name==='OUT'?reg(d):constant(name==='SBI'?1<<k:0),constant(name==='OUT'?255:1<<k)):call(IO,constant(name==='OUT'?k:d),name==='SBI'?or(reg(32+d),constant(1<<k)):name==='CBI'?and(reg(32+d),constant(255^(1<<k))):reg(d))),guard(),set(5,load8(flagsAddress)));
    if(name==='LDS'||name==='STS'){
      if(k>AT13_MEMORY.RAMEND)return fail(16);
      if(full&&name==='LDS')return bytes(put('pc',constant((p+2)&511)),clockHalf(1.5),set(0,k>=32&&k<AT13_MEMORY.RAMSTART?call(READ,constant(k-32)):reg(k)),clockHalf(.5),writeReg(d,X),set(7,constant(0)));
      return bytes(set(0,reg(d)),put('pc',constant((p+2)&511)),clock(constant(2)),set(7,constant(0)),
        name==='LDS'?writeReg(d,full&&k>=32&&k<AT13_MEMORY.RAMSTART?call(READ,constant(k-32)):reg(k)):k>=32&&k<AT13_MEMORY.RAMSTART?bytes(set(7,call(IO,constant(k-32),X)),guard(),set(5,load8(flagsAddress))):writeReg(k,X));
    }
    if(name==='LD'||name==='ST'){
      if(k<2&&(d===s||d===s+1))return fail(name==='LD'?19:17);
      // DS40002198A 5.66-68/5.114-116: for <=256-byte data spaces only
      // the low pointer byte participates; XH/YH/ZH remain general registers.
      const code=bytes(set(6,and(add(reg(s),constant(k<0?-1:k>=2?k-2:0)),constant(255))),condition(ge(Z,constant(AT13_MEMORY.RAMEND+1)),fail(name==='LD'?20:18)),
        !full&&k<0?writeReg(s,Z):[],set(0,reg(d)),
        full&&name==='LD'?bytes(clockHalf(1.5),set(0,conditionValue(and(ge(Z,constant(32)),lt(Z,constant(AT13_MEMORY.RAMSTART))),call(READ,sub(Z,constant(32))),load8(dataAt(Z)))),clockHalf(.5)):clock(constant(2)),
        set(7,constant(0)),full&&k<0?writeReg(s,Z):[]);
      if(name==='LD')code.push(...writeReg(d,full?X:load8(dataAt(Z))));
      else code.push(...condition(and(ge(Z,constant(32)),lt(Z,constant(AT13_MEMORY.RAMSTART))),bytes(set(7,call(IO,sub(Z,constant(32)),X)),guard()),store8(dataAt(Z),X)));
      if(k===1)code.push(...writeReg(s,and(add(Z,constant(1)),constant(255))));
      // Indirect stores can alias SREG, just like OUT or STS.
      if(name==='ST')code.push(...set(5,load8(flagsAddress)));
      return code;
    }
    if(name==='LPM'){
      if(k&&d>=30)return fail(21);
      // The special fuse/lock LPM command is recognized when LPM starts,
      // within RFLB's three-cycle window; its own three cycles follow.
      return bytes(set(6,or(reg(30),shl(reg(31),8))),condition(ge(Z,constant(1024)),fail(22)),
        full?bytes(set(0,call(LPM,Z)),clock(constant(3)),writeReg(d,X)):writeReg(d,load8(add(constant(abi.rom),Z))),
        k?bytes(set(6,add(Z,constant(1))),writeReg(30,Z),writeReg(31,shr(Z,8))):[],set(7,constant(full?0:3)));
    }
    return fail(2);
  }
  const instructionBodies=decoded.map(i=>bytes(set(5,load8(flagsAddress)),set(7,constant(1)),put('errorPC',constant(i.pc)),put('pc',constant((i.pc+1)&511)),effects(i),store8(flagsAddress,flags()),finish()));

  // SRAM/Flash accesses use guards before observable I/O, alias faults or
  // invalid addresses. Every guard exit observes a complete, exact SREG.
  const leaders=new Set([0,3]);
  for(const i of decoded){
    if(!canBatch(i))leaders.add((i.pc+i.words)&511);
    if(['RJMP','RCALL','BRANCH'].includes(i.name))leaders.add((i.pc+1+i.k)&511);
    if(['SKIP','CPSE','SBIC','SBIS'].includes(i.name))leaders.add((i.pc+1+width(word(i.pc+1)))&511);
  }
  const blocks=[];
  for(let p=0;p<512;){
    if(!canBatch(decoded[p])){p++;continue;}
    const sequence=[decoded[p++]];
    while(p<512&&canBatch(decoded[p])&&!leaders.has(p)&&sequence.length<maxBlockInstructions)sequence.push(decoded[p++]);
    if(sequence.length<2)continue;
    let live=255,removed=0,computed=0;
    const masks=new Array(sequence.length);
    for(let n=sequence.length-1;n>=0;n--){
      const i=sequence[n],written=writes[i.name]||0,needed=optimizeFlags?written&live:written;
      if(guardedMemory.has(i.name))live=255;
      masks[n]=needed;removed+=popcount(written&~needed);computed+=popcount(needed);
      let read=reads[i.name]||0;
      if(['SBC','SBCI','CPC'].includes(i.name))read=1|(needed&2);
      if(i.name==='CPC'&&!needed)read=0;
      live=(live&~written)|read;
    }
    blocks.push({start:sequence[0].pc,end:p&511,instructions:sequence.length,cycles:sequence.reduce((n,i)=>n+instructionCycles(i),0),masks,removed,computed,sequence});
  }
  const blockBodies=[];
  // Function local remapping is performed while emitting block ALU below.
  // Separate emitters make the local types and their indices explicit.
  function remapLocals(code, shift) {
    const out=[];
    for(let p=0;p<code.length;){
      const op=code[p++];out.push(op);
      if(op===0x20||op===0x21||op===0x22){out.push(code[p++]+shift);}
      else if(op===0x41){let byte;do{byte=code[p++];out.push(byte);}while(byte&128);}
      else if(op===0x44){out.push(...code.slice(p,p+8));p+=8;}
      else if(op===0x10){let byte;do{byte=code[p++];out.push(byte);}while(byte&128);}
      else if(op===0x2c||op===0x2d||op===0x3a||op===0x2b||op===0x39){out.push(code[p++],code[p++]);}
      else if(op===0x04)out.push(code[p++]);
      else if(op===0x05||op===0x0b||op===0x0f||(op>=0x45&&op<=0xc4)){}
      else throw new Error('Unexpected opcode in remapped ALU: '+op.toString(16));
    }
    return out;
  }
  // Rebuild block functions with remapped i32 locals (arguments precede them).
  blocks.forEach((block,index)=>{
    const elapsed=binary(0xa0,stateF('cyc'),float(block.cycles));
    // No IRQ can occur inside an accepted block. Timer state advances by the
    // exact number of original CPU cycles, including the prescaler phase.
    const blocked=or(or(state('irqDelay'),full?call(PENDING):and(reg(88),constant(2))),or(lt(get(1),constant(block.instructions)),
      or(binary(0x66,elapsed,stateF('overflowAt')),binary(0x64,elapsed,get(0)))));
    const code=bytes(condition(blocked,bytes(constant(0),0x0f)),set(7,load8(flagsAddress)));
    let elapsedCycles=0;
    block.sequence.forEach((i,n)=>{
      let effects;
      if(guardedMemory.has(i.name)){
        const bailout=n?bytes(store8(flagsAddress,flags()),put('pc',constant(i.pc)),put('errorPC',constant(block.sequence[n-1].pc)),call(CLOCK,float(elapsedCycles)),constant(n),0x0f):bytes(constant(0),0x0f);
        const {name,d,s,k}=i;
        if(name==='LPM'){
          effects=bytes(set(6,or(reg(30),shl(reg(31),8))),condition(k&&d>=30?constant(1):ge(Z,constant(1024)),bailout),
            writeReg(d,load8(add(constant(abi.rom),Z))),k?bytes(set(6,add(Z,constant(1))),writeReg(30,Z),writeReg(31,shr(Z,8))):[]);
        }else{
          const alias=k<2&&(d===s||d===s+1);
          effects=bytes(set(6,and(add(reg(s),constant(k<0?-1:k>=2?k-2:0)),constant(255))),
            condition(alias?constant(1):or(lt(Z,constant(AT13_MEMORY.RAMSTART)),ge(Z,constant(AT13_MEMORY.RAMEND+1))),bailout),
            k<0?writeReg(s,Z):[],name==='LD'?writeReg(d,load8(dataAt(Z))):store8(dataAt(Z),reg(d)),
            k===1?writeReg(s,and(add(Z,constant(1)),constant(255))):[]);
        }
      }else effects=alu(i,block.masks[n]);
      code.push(...remapLocals(effects,2));elapsedCycles+=instructionCycles(i);
    });
    code.push(...store8(flagsAddress,get(7)),put('pc',constant(block.end)),put('errorPC',constant((block.end-1)&511)),
      call(CLOCK,float(block.cycles)),constant(block.instructions));
    blockBodies[index]=code;
  });

  const STEP=firstFunction+512+blocks.length+1, BLOCK=STEP+1, RUN=STEP+2, NEXT=STEP+3, CAPTURE=STEP+4, UNTIL=STEP+5, PHYSICAL=STEP+6;
  const emptyBlock=bytes(constant(0));
  const step=bytes(condition([0x23,0],[0x0f]),full?condition(eqz(call(READY)),[0x0f]):[],put('error',constant(0)),condition(or(lt(state('pc'),constant(0)),ge(state('pc'),constant(512))),fail(1)),state('pc'),0x11,1,0,full?condition(eq(state('error'),constant(26)),put('error',constant(0))):[]);
  const block=bytes(condition([0x23,0],bytes(constant(0),0x0f)),full?condition(eqz(call(READY)),bytes(constant(0),0x0f)):[],put('error',constant(0)),condition(or(lt(state('pc'),constant(0)),ge(state('pc'),constant(512))),fail(1,true)),
    get(0),get(1),add(state('pc'),constant(512)),0x11,3,0);
  const run=bytes(set(1,constant(0)),0x02,0x40,0x03,0x40,
    condition(ge(get(1),get(0)),[0x0c,2]),
    condition([0x23,0],[0x0c,2]),
    full?condition(eqz(call(READY)),[0x0c,2]):[],
    set(2,call(BLOCK,float(Infinity),sub(get(0),get(1)))),
    condition(state('error'),[0x0c,2]),condition(eqz(get(2)),bytes(call(STEP),set(2,constant(1)))),
    set(1,add(get(1),get(2))),condition(state('error'),[0x0c,2]),0x0c,0,0x0b,0x0b,get(1));
  const next=bytes(put('error',constant(0)),condition(or(lt(state('pc'),constant(0)),ge(state('pc'),constant(512))),fail(1,true)),
    set(0,stateF('writes')),set(1,binary(0xa0,stateF('cyc'),float(9600000))),
    0x02,0x40,0x03,0x40,
    condition(binary(0x62,stateF('writes'),get(0)),[0x0c,2]),
    condition([0x23,0],bytes(constant(0),0x0f)),
    // Reuse only the audited WASM wait-loop accelerator, never its opcode
    // executor. This legacy peripheral profile has one Timer0 IRQ source.
    condition(eqz(conditionValue(and(state('fastIdle'),eqz(eqz(load8(add(constant(abi.idle),state('pc')))))),call(IDLE),constant(0))),condition(eqz(call(BLOCK,get(1),constant(2147483647))),call(STEP))),
    condition(state('error'),bytes(constant(0),0x0f)),
    condition(binary(0x64,stateF('cyc'),get(1)),fail(23,true)),0x0c,0,0x0b,0x0b,state('duty'));
  const until=full?bytes(set(1,constant(0)),0x02,0x40,0x03,0x40,
    condition(binary(0x66,call(TIME),get(0)),[0x0c,2]),
    condition(or(state('error'),[0x23,0]),[0x0c,2]),
    condition(eqz(call(READY)),bytes(condition(eqz(call(WAIT,get(0))),[0x0c,3]),0x0c,1)),
    condition(or(lt(state('pc'),constant(0)),ge(state('pc'),constant(512))),fail(1,true)),
    condition(conditionValue(and(state('fastIdle'),eqz(eqz(load8(add(constant(abi.idle),state('pc')))))),call(15,call(14,get(0))),constant(0)),[0x0c,1]),
    set(2,call(BLOCK,call(14,get(0)),constant(2147483647))),
    condition(state('error'),[0x0c,2]),
    condition(eqz(get(2)),bytes(call(STEP),set(2,constant(1)))),set(1,add(get(1),get(2))),
    0x0c,0,0x0b,0x0b,get(1)):[];
  const physical=full?bytes(set(1,constant(0)),0x02,0x40,0x03,0x40,
    condition(ge(get(1),get(0)),[0x0c,2]),
    call(UNTIL,call(AUDIO_DEADLINE)),0x1a,
    condition(or(state('error'),[0x23,0]),[0x0c,2]),
    condition(eqz(call(AUDIO_SAMPLE,get(1))),[0x0c,2]),
    set(1,add(get(1),constant(1))),0x0c,0,0x0b,0x0b,get(1)):[];
  // Collect OCR0A/OCR0B duty frames into a dedicated byte region of WASM
  // memory. This reuses the unused native raw-audio scratch buffer; generated
  // execution never invokes the native renderer or writes its DSP state.
  const capture=bytes(constant(0),0x24,3,put('error',constant(0)),
    condition(or(or(lt(get(0),constant(1)),binary(0x4b,get(0),constant(4096))),and(binary(0x47,get(1),constant(1)),binary(0x47,get(1),constant(2)))),fail(24,true)),
    set(2,constant(0)),0x02,0x40,0x03,0x40,
    condition(ge(get(2),get(0)),[0x0c,2]),
    set(5,stateF('leftWrites')),set(3,call(NEXT)),
    condition(or(state('error'),[0x23,0]),bytes(get(2),0x0f)),
    set(4,add(constant(abi.pwm),binary(0x6c,get(2),get(1)))),
    condition(eq(get(1),constant(2)),bytes(
      condition(binary(0x62,stateF('leftWrites'),binary(0xa0,get(5),float(1))),bytes(constant(1),0x24,3,get(2),0x0f)),
      store8(get(4),state('dutyLeft')),store8(add(get(4),constant(1)),get(3))),store8(get(4),get(3))),
    set(2,add(get(2),constant(1))),0x0c,0,0x0b,0x0b,get(2));
  const types=[
    [0x60,1,0x7c,0], // clock(f64)
    [0x60,0,0], // instruction()
    [0x60,2,0x7f,0x7f,1,0x7f], // writeIO(i32,i32)->i32
    [0x60,2,0x7c,0x7f,1,0x7f], // block(f64 deadline,i32 limit)->i32
    [0x60,1,0x7f,1,0x7f], // run(i32)->i32
    [0x60,0,1,0x7f], // nextDuty()->i32
    [0x60,0,0], // reserved
    [0x60,3,0x7f,0x7f,0x7f,1,0x7f], // maskedIO/control(i32,i32,i32)->i32
    [0x60,0,1,0x7c], // time()->f64
    [0x60,1,0x7c,1,0x7f], // wait/runUntil(f64)->i32
    [0x60,1,0x7c,1,0x7c], // base-time deadline -> CPU-cycle deadline
  ];
  const importSection=vector([
    bytes(string('avr'),string('memory'),2,1,...uleb(abi.memoryPages||1),...uleb(abi.memoryPages||1)),
    ...imports.map(([name,type])=>bytes(string('avr'),string(name),0,uleb(type))),
  ]);
  const functionTypes=[...Array(512).fill(1),...Array(blocks.length+1).fill(3),1,3,4,5,2,...(full?[9,4]:[])];
  const table=Array.from({length:512},(_,p)=>firstFunction+p);
  const blockIndex=new Map(blocks.map((b,n)=>[b.start,firstFunction+512+n]));
  for(let p=0;p<512;p++)table.push(blockIndex.get(p)??firstFunction+512+blocks.length);
  const body=(code,locals)=>{const content=bytes(vector(locals),code,0x0b);return bytes(uleb(content.length),content);};
  const codes=[...instructionBodies.map(code=>body(code,[[9,0x7f],[1,0x7c]])),
    ...blockBodies.map(code=>body(code,[[9,0x7f]])),body(emptyBlock,[]),body(step,[]),body(block,[]),body(run,[[2,0x7f]]),body(next,[[2,0x7c]]),body(capture,[[3,0x7f],[1,0x7c]]),...(full?[body(until,[[2,0x7f]]),body(physical,[[1,0x7f]])]:[])];
  const exports=vector([...['controlRequest','watchdogResetCycle','debugEnabled','captureFault'].map((name,index)=>bytes(string(name),3,index)),
    ...[['step',STEP],['block',BLOCK],['run',RUN],['nextDuty',NEXT],['capturePWM',CAPTURE],...(full?[['runUntil',UNTIL],['capturePhysical',PHYSICAL]]:[])].map(([name,index])=>bytes(string(name),0,uleb(index)))]);
  const mapping=decoded.map(({pc,word,name,d,s,k,words})=>({pc,byteAddress:pc*2,word,name,d,s,k,words}));
  const stats={decodableWords:decoded.filter(i=>i.name!=='unsupported').length,unsupportedWords:decoded.filter(i=>i.name==='unsupported').length,
    blocks:blocks.length,flagBitsComputed:blocks.reduce((n,b)=>n+b.computed,0),flagBitsEliminated:blocks.reduce((n,b)=>n+b.removed,0)};
  const manifest={schema:'micromusic-avr-transpiled-v1',device:'ATtiny13A',abi,optimizeFlags,maxBlockInstructions,stats,
    blocks:blocks.map(({sequence,...block})=>block),mapping};
  const output=Uint8Array.from(bytes([0,97,115,109,1,0,0,0],section(1,vector(types)),section(2,importSection),section(3,vector(functionTypes.map(uleb))),
    section(4,[1,0x70,1,...uleb(1024),...uleb(1024)]),section(6,vector([bytes(0x7f,1,constant(0),0x0b),bytes(0x7c,1,float(-1),0x0b),bytes(0x7f,1,constant(0),0x0b),bytes(0x7f,1,constant(0),0x0b)])),
    section(7,exports),section(9,bytes(1,0,constant(0),0x0b,vector(table.map(uleb)))),section(10,vector(codes)),
    section(0,bytes(string('micromusic.avr'),Array.from(new TextEncoder().encode(JSON.stringify(manifest)))))));
  return {bytes:output,manifest};
}
