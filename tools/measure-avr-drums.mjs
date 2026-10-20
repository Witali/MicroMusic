// Audition candidate percussion changes by executing their real AVR opcodes.
import fs from 'node:fs';
import { AVRCore } from '../web-player/lib/avr-core.js';
const folder='ATtiny13A/Music/variants/fluid-violin',out='build/fluid-grid/avr-drums';fs.mkdirSync(out,{recursive:true});
const rom=fs.readFileSync(`${folder}/synth.bin`),ep=fs.readFileSync(`${folder}/eeprom.bin`);
const ldi=(d,k)=>0xe000|((d-16)<<4)|(k&15)|((k&240)<<4);
const rr=(base,d,r)=>base|(d<<4)|(r&15)|((r&16)<<5);
if(rom.readUInt16LE(644)!==ldi(17,4)||rom.readUInt16LE(668)!==ldi(17,29))throw Error('Percussion addresses moved');
function capture(name,type,words,sourceImage=rom) {
  const image=Buffer.from(sourceImage);for(const [address,word]of words)image.writeUInt16LE(word,address);
  if(name!=='original'&&type===1){image.writeUInt16LE(0,634);image.writeUInt16LE(0,636);}
  const c=new AVRCore(image,ep);while(c.irqCount<30||c.inIRQ)c.step();
  c.r[1]=c.r[19]=c.r[20]=0;c.r[21]=0;c.r[29]=type;c.r[14]=167;c.r[22]=255;c.r[24]=0;c.r[15]=0;c.r[23]=0;
  const n=Math.round(.3*37500),pcm=new Float32Array(n);
  for(let i=0;i<n;i++)pcm[i]=(c.nextDuty()-128)/128;
  fs.writeFileSync(`${out}/${name}-${type}.f32`,new Uint8Array(pcm.buffer));
  if(c.lost)throw Error('Lost percussion IRQ');
  return Buffer.from(pcm.buffer);
}
if(process.argv.includes('--verify')) {
  const actual='ATtiny13A/Music/variants/fluid-instruments';
  const image=fs.readFileSync(`${actual}/synth.bin`),report=JSON.parse(fs.readFileSync(`${actual}/build-report.json`));
  for(const [type,name]of [[0,report.percussion.kick.name],[1,report.percussion.noise.name],[2,report.percussion.noise.name]]){
    const result=capture('actual',type,[],image);
    if(!result.equals(fs.readFileSync(`${out}/${name}-${type}.f32`)))throw Error(`Final AVR percussion mismatch: ${type}`);
  }
  console.log('Final AVR percussion exactly matches all three selected candidate signals.');
  process.exit(0);
}
for(const type of [0,1,2])capture('original',type,[]);
for(const step of [1,2,3])capture(`kick-${step}`,0,[[644,ldi(17,step)],[646,0]]);
const shiftWords={0:[0,0],1:[0x0f11,0],2:[0x0f11,0x0f11],'-1':[0x9516,0],'-2':[0x9516,0x9516]};
for(const tap of [29,43,45,77,95,99,101,105,113,135,141,169,195,207,231,245]) {
  for(const shift of [-2,-1,0,1,2]) {
    // Shift zero would XOR a value with itself; use the unmodified state instead.
    const words=[[668,ldi(17,tap)],[674,shiftWords[shift][0]],[676,shiftWords[shift][1]],[678,shift===0?0:rr(0x2400,17,14)]];
    for(const type of [1,2])capture(`xor-${tap}-${shift}`,type,words);
  }
  for(const [label,word]of [['left',0x0f11],['right',0x9516]]) {
    const words=[[668,ldi(17,tap)],[674,word],[676,0xfdd0],[678,rr(0x2400,17,14)]];
    for(const type of [1,2])capture(`split-${tap}-${label}`,type,words);
  }
  // r27 is dead after the tonal mixer; it is available as a percussion scratch.
  const words=[[668,ldi(17,tap)],[672,rr(0x2c00,17,14)],[674,0x9516],[676,0x731f],[678,rr(0x2c00,27,14)],[680,0x73bf],[682,rr(0x1800,17,27)],[684,0x9515]];
  for(const type of [1,2])capture(`difference-${tap}`,type,words);
}
console.log('Real AVR percussion candidates written:',out);
