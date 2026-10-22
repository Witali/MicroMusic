
/*
 * MicroMusic: small cycle-counting ATtiny13A AVR interpreter.
 * Extended from the 2026 four-voice player.html emulator.
 * This implements the instructions used by tinylpc.S, not arbitrary AVR chips.
 * Flash: 1024 bytes; SRAM: 64 bytes (0x60..0x9F); clock: 9600000 Hz.
 * Timer0 overflows every 256 cycles, IRQ vector 3; OCR0B is PWM duty.
 */
'use strict';
class AVRCore {
  constructor(program){
    if(program.length>1024)throw Error('ATtiny13A Flash overflow: '+program.length+' bytes');
    this.rom=new Uint8Array(1024); this.rom.set(program);
    this.r=new Uint8Array(32);this.io=new Uint8Array(64);this.sram=new Uint8Array(64);
    this.pc=0;this.cycles=0;this.C=0;this.Z=0;this.N=0;this.V=0;this.S=0;this.H=0;this.T=0;this.I=0;
    this.stack=[];this.maxStack=0;this.irqCount=0;this.missedOverflows=0;this.maxISR=0;
    this.timerEnabled=false;this.overflowAt=Infinity;this.pending=false;this.inIRQ=false;this.irqStart=0;
    this.samples=[];this.latestPWM=128;this.pwmWrites=0;this.iterations=0;
  }
  get sreg(){return this.C|(this.Z<<1)|(this.N<<2)|(this.V<<3)|(this.S<<4)|(this.H<<5)|(this.T<<6)|(this.I<<7)}
  set sreg(v){this.C=v&1;this.Z=(v>>1)&1;this.N=(v>>2)&1;this.V=(v>>3)&1;this.S=(v>>4)&1;this.H=(v>>5)&1;this.T=(v>>6)&1;this.I=(v>>7)&1}
  setNZ(v,ov=0){this.Z=+(v===0);this.N=v>>7;this.V=+!!ov;this.S=this.N^this.V}
  subFlags(a,b,c=0,retain=false){
    const result=(a-b-c)&255;
    this.C=+(a<(b+c));this.V=+!!((a^b)&(a^result)&128);
    this.H=+!!(((~a&b)|(b&result)|(result&~a))&8);
    this.N=result>>7;this.S=this.N^this.V;
    this.Z=+(result===0 && (!retain||this.Z));
    return result;
  }
  addFlags(a,b,c=0,retain=false){
    const full=a+b+c,res=full&255;
    this.C=+(full>255);this.V=+!!((~(a^b))&(a^res)&128);
    this.H=+((((a&15)+(b&15)+c)>15));
    this.N=res>>7;this.S=this.N^this.V;this.Z=+(res===0 && (!retain||this.Z));
    return res;
  }
  readMemory(a){if(a>=0x60&&a<=0x9f)return this.sram[a-0x60];if(a>=0x20&&a<0x60)return a===0x5f?this.sreg:this.io[a-0x20];if(a<0x20)return this.r[a];throw Error('SRAM address out of range: 0x'+a.toString(16))}
  writeMemory(a,v){v&=255;if(a>=0x60&&a<=0x9f)this.sram[a-0x60]=v;else if(a>=0x20&&a<0x60)this.writeIO(a-0x20,v);else if(a<0x20)this.r[a]=v;else throw Error('SRAM address out of range: 0x'+a.toString(16))}
  readIO(a){return a===0x3f?this.sreg:this.io[a]}
  writeIO(a,v){
    v&=255;
    if(a===0x3f){this.sreg=v;return}
    this.io[a]=v;
    if(a===0x33){
      if((v&7)===1&&!this.timerEnabled){this.timerEnabled=true;this.overflowAt=this.cycles+256}
      if((v&7)===0)this.timerEnabled=false;
    }
    if(a===0x29&&this.timerEnabled){this.latestPWM=v;this.samples.push(v);this.pwmWrites++}
  }
  push(v){this.stack.push(v);this.maxStack=Math.max(this.stack.length,this.maxStack);if(this.stack.length>64)throw Error('ATtiny13 stack overflow')}
  pop(){if(!this.stack.length)throw Error('Stack underflow');return this.stack.pop()}
  step(){
    const rr=this.r, addr=this.pc*2;
    if(addr>=this.rom.length)throw Error('PC exceeds Flash at '+addr.toString(16));
    const w=this.rom[addr] | this.rom[addr+1]<<8;
    this.pc++;let n=1;
    if(w===0x0000){} // NOP
    else if(w===0x94f8)this.I=0; // CLI
    else if(w===0x9478)this.I=1; // SEI
    else if(w===0x9508){this.pc=this.pop();n=4} // RET
    else if(w===0x9518){this.pc=this.pop();this.I=1;n=4;this.inIRQ=false;this.maxISR=Math.max(this.maxISR,this.cycles+n-this.irqStart)} // RETI
    else if((w&0xf000)===0xc000 || (w&0xf000)===0xd000){ // RJMP, RCALL
      let k=w&4095;if(k&2048)k-=4096;
      if((w&0xf000)===0xd000){this.push(this.pc);n=3}else n=2;
      this.pc+=k;
    }
    else if((w&0xfc00)===0xf000 || (w&0xfc00)===0xf400){ // BRBS / BRBC
      const f=w&7;
      const flags=[this.C,this.Z,this.N,this.V,this.S,this.H,this.T,this.I];
      const bit=flags[f],branch=(w&0xfc00)===0xf000;
      if(!!bit===branch){let k=w>>3&127;if(k&64)k-=128;this.pc+=k;n=2}
    }
    else if((w&0xfe08)===0xfc00 || (w&0xfe08)===0xfe00){ // SBRC, SBRS
      const r=w>>4&31,bit=w&7, set=(w&0xfe08)===0xfe00;
      if(!!(rr[r]>>bit&1)===set){
        const nxt=this.rom[this.pc*2] | this.rom[this.pc*2+1]<<8;
        const two=(nxt&0xfe0f)===0x9000||(nxt&0xfe0f)===0x9200;
        this.pc+=two?2:1;n=two?3:2;
      }
    }
    else if((w&0xf000)===0xe000){ // LDI
      rr[16+(w>>4&15)]=(w&15)|(w>>4&240);
    }
    else if([0x3000,0x5000,0x7000,0x6000,0x4000].includes(w&0xf000)){ // CPI, SUBI, ANDI, ORI, SBCI
      const d=16+(w>>4&15),k=(w&15)|(w>>4&240),a=rr[d],op=w&0xf000;
      if(op===0x7000){rr[d]=a&k;this.setNZ(rr[d])}
      else if(op===0x6000){rr[d]=a|k;this.setNZ(rr[d])}
      else if(op===0x3000)this.subFlags(a,k);
      else if(op===0x4000)rr[d]=this.subFlags(a,k,this.C,true);
      else rr[d]=this.subFlags(a,k);
    }
    else if((w&0xff00)===0x0100){ // MOVW
      let d=2*(w>>4&15),r=2*(w&15);rr[d]=rr[r];rr[d+1]=rr[r+1];
    }
    else if([0x0c00,0x1c00,0x1800,0x0800,0x1400,0x0400,0x2000,0x2400,0x2800,0x2c00].includes(w&0xfc00)){
      const d=w>>4&31,r=(w&15)|(w>>5&16),a=rr[d],b=rr[r],op=w&0xfc00;
      if(op===0x0c00||op===0x1c00)rr[d]=this.addFlags(a,b,op===0x1c00?this.C:0,op===0x1c00);
      else if(op===0x1800||op===0x0800||op===0x1400||op===0x0400){
        const v=this.subFlags(a,b,op===0x0800||op===0x0400?this.C:0,op===0x0800||op===0x0400);
        if(op!==0x1400&&op!==0x0400)rr[d]=v;
      }
      else if(op===0x2000){rr[d]=a&b;this.setNZ(rr[d])}
      else if(op===0x2400){rr[d]=a^b;this.setNZ(rr[d])}
      else if(op===0x2800){rr[d]=a|b;this.setNZ(rr[d])}
      else rr[d]=b;
    }
    else if([0x9403,0x940a,0x9400,0x9406,0x9401,0x9402,0x9405,0x9407].includes(w&0xfe0f)){
      const d=w>>4&31,a=rr[d],op=w&0xfe0f;let b;
      if(op===0x9403){b=(a+1)&255;this.setNZ(b,b===0x80)} // INC
      else if(op===0x940a){b=(a-1)&255;this.setNZ(b,b===0x7f)} // DEC
      else if(op===0x9400){b=a^255;this.setNZ(b);this.C=1} // COM
      else if(op===0x9401){b=(-a)&255;this.setNZ(b,b===0x80);this.C=+(b!==0)} // NEG
      else if(op===0x9402)b=(a<<4|a>>4)&255; // SWAP
      else if(op===0x9406){this.C=a&1;b=a>>1;this.setNZ(b,this.C)} // LSR
      else if(op===0x9405){this.C=a&1;b=(a>>1)|(a&128);this.setNZ(b,((b>>7)&1)^this.C)} // ASR
      else if(op===0x9407){const prev=this.C;this.C=a&1;b=(a>>1)|(prev<<7);this.setNZ(b,((b>>7)&1)^this.C)} // ROR
      rr[d]=b;
    }
    else if((w&0xf800)===0xb800){ // OUT
      this.writeIO((w>>5&48)|(w&15),rr[w>>4&31]);
    }
    else if((w&0xf800)===0xb000){ // IN
      rr[w>>4&31]=this.readIO((w>>5&48)|(w&15));
    }
    else if((w&0xff00)===0x9a00){ // SBI
      const a=w>>3&31;this.writeIO(a,this.readIO(a)|(1<<(w&7)));n=2;
    }
    else if((w&0xfe0f)===0x900a || (w&0xfe0f)===0x900e){ // LD Rd, -Y or -X
      const r=w>>4&31, isY=(w&0xfe0f)===0x900a;
      const ptr=isY?28:26;
      let a=(rr[ptr]|rr[ptr+1]<<8)-1;
      a&=65535; rr[ptr]=a&255;rr[ptr+1]=a>>8;
      rr[r]=this.readMemory(a);n=2;
    }
    else if((w&0xd208)===0x8208){ // STD Y+q, Rr
      const r=w>>4&31, q=(w&7)|((w>>7)&0x18)|((w>>8)&0x20);
      const a=(rr[28]|rr[29]<<8)+q;
      this.writeMemory(a,rr[r]);n=2;
    }
    else if((w&0xfe0f)===0x920c){ // ST X, Rr
      const r=w>>4&31,a=rr[26]|rr[27]<<8;
      this.writeMemory(a,rr[r]);n=2;
    }
    else if((w&0xfe0f)===0x900c){ // LD Rd, X
      const r=w>>4&31,a=rr[26]|rr[27]<<8;
      rr[r]=this.readMemory(a);n=2;
    }
    else if((w&0xfe0f)===0x9209){ // ST Y+,Rr
      const r=w>>4&31,a=rr[28]|rr[29]<<8;
      this.writeMemory(a,rr[r]);rr[28]=(a+1)&255;rr[29]=(a+1)>>8;n=2;
    }
    else if((w&0xfe0f)===0x9000 || (w&0xfe0f)===0x9200){ // LDS, STS (2 words)
      const r=w>>4&31,a=this.rom[this.pc*2]|(this.rom[this.pc*2+1]<<8);
      this.pc++;n=2;
      if((w&0xfe0f)===0x9000)rr[r]=this.readMemory(a);
      else this.writeMemory(a,rr[r]);
    }
    else if((w&0xfe0f)===0x900f){rr[w>>4&31]=this.pop();n=2} // POP
    else if((w&0xfe0f)===0x920f){this.push(rr[w>>4&31]);n=2} // PUSH
    else if((w&0xfe0f)===0x8008){ // LD Rd,Y
      const a=rr[28]|rr[29]<<8;rr[w>>4&31]=this.readMemory(a);n=2;
    }
    else if((w&0xfe0f)===0x8208){ // ST Y,Rr
      const a=rr[28]|rr[29]<<8;this.writeMemory(a,rr[w>>4&31]);n=2;
    }
    else if((w&0xfe0f)===0x9004 || (w&0xfe0f)===0x9005){ // LPM Rd,Z[+]
      const r=w>>4&31,a=rr[30]|rr[31]<<8;
      rr[r]=this.rom[a];if(w&1){rr[30]=(a+1)&255;rr[31]=(a+1)>>8}n=3;
    }
    else throw Error('Unsupported AVR instruction 0x'+w.toString(16)+' at flash 0x'+addr.toString(16));

    this.iterations++;
    this.cycles+=n;
    if(this.timerEnabled){
      if(this.overflowAt<=this.cycles){
        if(this.pending)this.missedOverflows++;
        this.pending=true;this.overflowAt+=256;
        while(this.overflowAt<=this.cycles){this.missedOverflows++;this.overflowAt+=256}
      }
      if(this.I&&(this.io[0x39]&2)&&this.pending){
        this.pending=false;this.push(this.pc);this.pc=3;this.I=0;
        this.irqStart=this.cycles;this.cycles+=4;this.inIRQ=true;this.irqCount++;
      }
    }
  }
  takeSample(){
    let budget=30000;
    while(!this.samples.length){if(--budget===0)throw Error('CPU stalled: no PWM updates');this.step()}
    return this.samples.shift();
  }
  static fromHex(hex){
    let data=[];
    for(const row of hex.trim().split(/\s+/)){
      if(!row.startsWith(':'))continue;
      let b=[];for(let j=1;j+1<row.length;j+=2)b.push(parseInt(row.substring(j,j+2),16));
      if(b.reduce((v,x)=>v+x,0)%256!==0)throw Error('Incorrect HEX checksum');
      if(b[3]===1)break;
      if(b[3]!==0)throw Error('Only simple Intel HEX is supported');
      let addr=b[1]*256+b[2];for(let j=0;j<b[0];j++)data[addr+j]=b[4+j];
    }
    return new AVRCore(Uint8Array.from(data));
  }
}
if(typeof module!=='undefined'&&module.exports)module.exports={AVRCore};

const DATA=JSON.parse(document.getElementById('db').textContent), $=id=>document.getElementById(id), SR=7500;
let ctx=null,active=null,revision=0;const cache=new Map();
function base64Bytes(s){const raw=atob(s),a=new Uint8Array(raw.length);for(let i=0;i<a.length;i++)a[i]=raw.charCodeAt(i);return a}
function pcm(name,codec){const key=name+':'+codec;if(cache.has(key))return cache.get(key);const src=DATA[name][codec];let bytes=base64Bytes(src.audio),view=new DataView(bytes.buffer);const out=new Float32Array(bytes.length/2);for(let i=0;i<out.length;i++)out[i]=view.getInt16(i*2,true)/32768;cache.set(key,out);return out}
function choose(){return [$('voice').value,$('codec').value]}
function metrics(){const [name,codec]=choose(),x=DATA[name][codec],isFirmware=!!x.firmware;$('flash').textContent=isFirmware?x.flash_bytes+' Б':'—';$('stoi').textContent=isFirmware?x.stoi.toFixed(4):'—';$('spectral').textContent=isFirmware?x.spectral_error.toFixed(4):'—';$('hex').disabled=!isFirmware;$('verify').disabled=!isFirmware;draw(pcm(name,codec))}
function draw(p){let c=$('wave'),g=c.getContext('2d');g.fillStyle='#0a111e';g.fillRect(0,0,c.width,c.height);g.strokeStyle='#324562';g.beginPath();g.moveTo(0,c.height/2);g.lineTo(c.width,c.height/2);g.stroke();g.strokeStyle='#76c7ff';g.lineWidth=1.7;g.beginPath();let block=Math.max(1,Math.floor(p.length/c.width));for(let i=0;i<c.width;i++){let idx=i*block;let v=p[idx]||0;let y=c.height/2-v*c.height*.42;if(!i)g.moveTo(i,y);else g.lineTo(i,y)}g.stroke()}
function rms(x){let s=0;for(const v of x)s+=v*v;return Math.sqrt(s/(x.length||1))}
async function playAudio(a){stop();ctx=ctx&&ctx.state!=='closed'?ctx:new (window.AudioContext||window.webkitAudioContext)();await ctx.resume();let b=ctx.createBuffer(1,a.length,SR);b.copyToChannel(a,0);let node=ctx.createBufferSource();node.buffer=b;node.connect(ctx.destination);active=node;node.onended=()=>{if(active===node)active=null};node.start();$('status').textContent='Воспроизводится. Для корректной работы на Android откройте HTML в Chrome.'}
function stop(){if(active){try{active.stop()}catch(e){}active.disconnect();active=null}}
$('play').onclick=async()=>{try{const [a,b]=choose();await playAudio(pcm(a,b))}catch(e){$('status').textContent='Ошибка воспроизведения: '+e.message}};
$('compare').onclick=async()=>{try{let [n,c]=choose();let original=pcm(n,'original'),selected=pcm(n,c);let silence=Math.floor(SR*.3),both=new Float32Array(original.length+silence+selected.length);let oa=.17/Math.max(.02,rms(original)),ob=.17/Math.max(.02,rms(selected));for(let i=0;i<original.length;i++)both[i]=Math.min(.96,Math.max(-.96,original[i]*oa));for(let i=0;i<selected.length;i++)both[original.length+silence+i]=Math.min(.96,Math.max(-.96,selected[i]*ob));await playAudio(both);$('status').textContent='A/B: оригинал → выбранный кодек, громкость выровнена по RMS.'}catch(e){$('status').textContent='Ошибка A/B: '+e.message}};
$('stop').onclick=()=>{stop();$('status').textContent='Остановлено.'};
function download(name,bytes,mime){let url=URL.createObjectURL(new Blob([bytes],{type:mime})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1200)}
function wavBytes(p){let n=p.length;const b=new ArrayBuffer(44+n*2),d=new DataView(b);function st(o,v){for(let i=0;i<v.length;i++)d.setUint8(o+i,v.charCodeAt(i))}st(0,'RIFF');d.setUint32(4,36+n*2,true);st(8,'WAVE');st(12,'fmt ');d.setUint32(16,16,true);d.setUint16(20,1,true);d.setUint16(22,1,true);d.setUint32(24,SR,true);d.setUint32(28,SR*2,true);d.setUint16(32,2,true);d.setUint16(34,16,true);st(36,'data');d.setUint32(40,n*2,true);for(let i=0;i<n;i++)d.setInt16(44+i*2,Math.max(-32768,Math.min(32767,Math.round(p[i]*32767))),true);return b}
$('wav').onclick=()=>{let [n,c]=choose();download('MiniLPC_'+n+'_'+c+'.wav',wavBytes(pcm(n,c)),'audio/wav')};
function hex(bytes){let l=[];for(let i=0;i<bytes.length;i+=16){let r=[Math.min(16,bytes.length-i),(i>>8)&255,i&255,0,...bytes.slice(i,i+16)];r.push(-r.reduce((a,b)=>a+b,0)&255);l.push(':'+r.map(z=>z.toString(16).toUpperCase().padStart(2,'0')).join(''))}return l.join('\n')+'\n:00000001FF\n'}
$('hex').onclick=()=>{let [n,c]=choose(),x=DATA[n][c];if(x.firmware)download('MiniLPC_'+n+'_'+c+'.hex',hex(base64Bytes(x.firmware)),'text/plain')};
$('verify').onclick=async()=>{
 let [n,c]=choose(),entry=DATA[n][c];if(!entry.firmware)return;let v=++revision;stop();$('verify').disabled=true;$('verifyReport').textContent='Исполнение настоящего HEX...';$('status').textContent='Проверка может занять некоторое время на телефоне.';
 try{let core=new AVRCore(base64Bytes(entry.firmware));let expected=pcm(n,c);let errors=0,lastIRQ=0,irregular=0;for(let i=0;i<expected.length;i++){let got=core.takeSample(),expectedUint8=Math.max(0,Math.min(255,Math.round(expected[i]*128+128)));if(got!==expectedUint8)errors++;let delta=core.irqCount-lastIRQ;if(i>0&&(delta<4||delta>6))irregular++;lastIRQ=core.irqCount;if(i%700===0){$('verifyReport').textContent='Проверено '+i+' / '+expected.length;await new Promise(r=>setTimeout(r,0))}}if(revision!==v)return;
 $('verifyReport').textContent=`Отсчётов: ${expected.length}
Несовпадений PCM: ${errors}
Пропусков Timer0: ${core.missedOverflows}
Нерегулярных интервалов PWM: ${irregular}
Макс. длительность ISR: ${core.maxISR} тактов
Flash: ${entry.flash_bytes} / 1024 байт`;
 $('status').textContent=errors||core.missedOverflows||irregular?'Обнаружено расхождение.':'Проверка HEX пройдена, PCM совпадает с эталоном.';
 }catch(e){$('verifyReport').textContent=e.stack||e.message;$('status').textContent='Ошибка эмуляции'}finally{metrics()}
};
$('voice').onchange=()=>{revision++;stop();metrics()};$('codec').onchange=()=>{revision++;stop();metrics()};metrics();
