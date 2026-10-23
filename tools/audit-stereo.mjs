// Check the complete stereo song against the retained mono score and grid.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
// Per-instruction observation belongs in the reference audit. Avoid crossing
// the JS/WASM boundary for every observed instruction of the complete song.
import {AVRCore} from '../web-player/lib/avr-reference.js';
import {AT13_IO,AT13_DATA,AT13_MEMORY} from '../web-player/lib/attiny13a-registers.js';
const folder='ATtiny13A/Music/variants/lumiere-stereo';
const read=(dir,name)=>fs.readFileSync(`${dir}/${name}`);
const meta=JSON.parse(read(folder,'build-report.json')),sourceMeta=meta;
const source=JSON.parse(read(folder,'score.json')),sourceRom=read(folder,'synth.bin');
const {labels,timing}=meta,units=[1,2,3,4,6,8,16],expected=[];
const outAddresses=[];
for(let at=0;at<meta.codeBytes;at+=2){const word=sourceRom[at]|sourceRom[at+1]<<8;
  if((word&0xf800)===0xb800)outAddresses.push(((word>>5)&48)|(word&15));}
assert.equal(outAddresses.filter(address=>address===AT13_IO.OCR0A).length,2);
assert.ok(outAddresses.every(address=>Object.values(AT13_IO).includes(address)),'Stereo must not write undefined I/O');
let totalUnits=0;
for(const section of meta.score.playlist){
  let address=sourceMeta.labels[`section_${section}`];
  for(;;){const token=sourceRom[address++];if(token===255)break;
    expected.push({token,unit:totalUnits});if(token<224)totalUnits+=units[token&7];}
}
assert.equal(createHash('sha256').update(Uint8Array.from(expected,e=>e.token)).digest('hex'),meta.score.compression.originalStreamSha256);
const ticks=[];let phase=Math.ceil((65536-timing.phaseStep)/256)<<8;
for(let tick=1;ticks.length<=totalUnits;tick++){
  phase+=timing.phaseStep;if(phase>=65536){phase-=65536;ticks.push(tick);}
}
const c=new AVRCore(read(folder,'synth.bin'),read(folder,'eeprom.bin'));
let index=0,envTick=0,anchor,finished=false,maximumTimingErrorMs=0,maxForeground=0,foregroundStart=null,minimumPublishMargin=Infinity;
let min=[255,255],max=[0,0],sum=[0,0],sumSquares=[0,0],cross=0,frames=0;
const step=c.step.bind(c);
c.step=()=>{
  if(!c.inIRQ){
    if(c.pc===labels.music_tick/2)envTick++;
    if(c.pc===labels.audio_step/2)foregroundStart=c.cyc;
    if(c.pc===(labels.idle+6)/2&&foregroundStart!==null){maxForeground=Math.max(maxForeground,c.cyc-foregroundStart);foregroundStart=null;}
    if(c.pc===labels.publish_wait/2+2){
      minimumPublishMargin=Math.min(minimumPublishMargin,c.overflowAt-c.cyc);
      assert.ok(c.overflowAt-c.cyc>=8,'Stereo buffers must finish publishing before the next IRQ');
    }
    if(c.pc===labels.read_event/2&&!finished){
      const token=c.rom[c.r[30]|c.r[31]<<8];
      if(index===expected.length){
        assert.equal(token,255);assert.equal(envTick,ticks[totalUnits]);finished=true;
      } else if(token!==255){
        const e=expected[index++];assert.equal(token,e.token,`Command ${index}`);
        assert.equal(envTick,ticks[e.unit],`Sixteenth grid at command ${index}`);
        anchor??=c.cyc;
        maximumTimingErrorMs=Math.max(maximumTimingErrorMs,Math.abs((c.cyc-anchor)/9600-e.unit/4*60000/source.tempo_bpm));
      }
    }
  }
  step();
};
while(!finished&&c.cyc<225*9600000){
  const packed=c.nextStereoDuty(),values=[packed&255,packed>>8];
  for(let ch=0;ch<2;ch++){min[ch]=Math.min(min[ch],values[ch]);max[ch]=Math.max(max[ch],values[ch]);sum[ch]+=values[ch];sumSquares[ch]+=values[ch]**2;}
  cross+=values[0]*values[1];frames++;
}
assert.ok(finished);assert.equal(index,expected.length);assert.equal(c.lost+c.workLost,0);assert.ok(maximumTimingErrorMs<25);
assert.ok(maxForeground<512);assert.ok(c.minSP>=AT13_MEMORY.RAMSTART+7);assert.equal(c.leftWrites,c.writes);
assert.ok(min.every(x=>x>0)&&max.every(x=>x<255),'No PWM clipping');
const correlation=(cross-sum[0]*sum[1]/frames)/Math.sqrt((sumSquares[0]-sum[0]**2/frames)*(sumSquares[1]-sum[1]**2/frames));
assert.ok(correlation<.999,'Stereo channels must contain different music mixes');
const report={image:'lumiere-stereo',flashSha256:meta.flashSha256,flashBytes:meta.flashBytes,channels:2,
  hardwareAddressFix:{register:'OCR0A',previousIoAddress:0x2a,ioAddress:AT13_IO.OCR0A,dataAddress:AT13_DATA.OCR0A,
    binaryOutInstructionCount:2,reservedAliasOutInstructionCount:0,datasheet:'Microchip DS40002307A section11.9.4 and register summary'},
  completeSong:{commands:index,beats:totalUnits/4,idealSeconds:totalUnits/4*60/source.tempo_bpm,elapsedSeconds:(c.cyc-anchor)/9600000,maximumTimingErrorMs,missingCommands:0},
  outputs:meta.outputs,panorama:meta.panorama,pwm:{frames,min,max,mean:sum.map(x=>x/frames),correlation,channelWriteCountMismatch:0},
  timing:{isrCycles:c.maxIRQ,maxForegroundCyclesIncludingWaitAndIrq:maxForeground,minimumBufferPublishMarginCycles:minimumPublishMargin,lostTimerEvents:c.lost,lostWorkEvents:c.workLost},
  memory:{stateBytes:7,maxStackBytes:AT13_MEMORY.RAMEND-c.minSP},
  model:'Paired OCR0A/OCR0B duty writes, one AVR execution. Physical PWM edges and double-buffer latch timing are not synthesized.'};
fs.writeFileSync('web-player/reports/lumiere-stereo-verification.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
