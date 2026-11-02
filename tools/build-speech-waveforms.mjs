// Exact complete-phrase duties from the retained Flash/EEPROM, never originals.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore} from '../web-player/lib/avr-reference.js';
import {parseHex} from '../web-player/lib/hex.js';
const root=new URL('../',import.meta.url),read=path=>readFileSync(new URL(path,root));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const entries=[...JSON.parse(read('web-player/hq4-firmware.json')).entries,
  ...JSON.parse(read('web-player/firmware-attiny13a-speech-extra.json')).entries];
const folder=new URL('web-player/audio/speech-waveforms/',root);mkdirSync(folder,{recursive:true});
const result=[];
for(const entry of entries){
  const flash=parseHex(entry.flashHex),eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):null;
  if(hash(flash)!==entry.flashSha256||(eeprom&&hash(eeprom)!==entry.eepromSha256))throw Error('Firmware waveform source hash differs');
  const cpu=new AVRCore(flash,eeprom);
  const duties=Buffer.alloc(entry.phraseSamples);
  for(let i=0;i<duties.length;i++)duties[i]=cpu.nextDuty();
  if(cpu.lost||cpu.workLost)throw Error('Speech waveform missed a deadline');
  const wav=Buffer.alloc(44+duties.length*2);
  wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);
  wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(entry.sampleHz,24);
  wav.writeUInt32LE(entry.sampleHz*2,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);
  wav.write('data',36);wav.writeUInt32LE(duties.length*2,40);
  for(let i=0;i<duties.length;i++)wav.writeInt16LE((duties[i]-128)*256,44+i*2);
  const name=entry.id+'.wav';writeFileSync(new URL(name,folder),wav);
  result.push({id:entry.id,audio:'audio/speech-waveforms/'+name,sampleHz:entry.sampleHz,phraseSamples:entry.phraseSamples,
    flashSha256:entry.flashSha256,eepromSha256:entry.eepromSha256??null,pwmSha256:hash(duties),wavSha256:hash(wav)});
}
writeFileSync(new URL('manifest.json',folder),JSON.stringify({schemaVersion:1,generator:'tools/build-speech-waveforms.mjs',entries:result},null,2)+'\n');
console.log('Captured four complete firmware waveforms with active IRQ and no missed samples.');
