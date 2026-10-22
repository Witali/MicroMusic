// node verify.js — truly execute the firmware and write unsigned 8-bit PCM.
'use strict';
const fs=require('fs');const path=require('path');const {AVRCore}=require('./avr_emulator.js');
const P=__dirname,rom=fs.readFileSync(path.join(P,'tinylpc.hex'),'utf8');
const core=AVRCore.fromHex(rom);
// 87 decoded frames, packed with variable-length silence runs.
const frames=Number.parseInt(process.env.FRAMES||'87',10),n=frames*256;let pcm=Buffer.alloc(n),last=0,maxGap=0,underruns=0;
for(let i=0;i<n;i++){
  pcm[i]=core.takeSample();
  if(i>0){const gap=core.cycles-last;maxGap=Math.max(maxGap,gap);if(gap>1290)underruns++}
  last=core.cycles;
}
fs.writeFileSync(path.join(P,'emu_pwm_u8.raw'),pcm);
console.log({flashBytes:fs.readFileSync(path.join(P,'tinylpc.bin')).length, speechBytes:fs.readFileSync(path.join(P,'voice_tinylpc.bin')).length,
 cycles:core.cycles, irqCount:core.irqCount, maxISR:core.maxISR, missedTimerOverflows:core.missedOverflows,
 pcmSamples:n,maxOutputGapCycles:maxGap, possibleAudioUnderruns:underruns,
 stackDepth:core.maxStack,peakMin:Math.min(...pcm),peakMax:Math.max(...pcm)});
if(core.missedOverflows||core.maxISR>=256||maxGap>1290||core.maxStack>64)process.exit(1);
