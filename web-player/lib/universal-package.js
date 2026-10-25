// Portable, local UM88 firmware bundle. Validation does not execute AVR code.
import {parseHex} from './hex.js';
const encoder=new TextEncoder();
export async function sha256(value){
 if(!globalThis.crypto?.subtle)throw Error('Для проверки пакета нужен HTTPS или localhost');
 const bytes=typeof value==='string'?encoder.encode(value):value;
 return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
}
const requireValue=(condition,message)=>{if(!condition)throw Error(message);};
export async function universalPackageEntry(input){
 const pkg=typeof input==='string'?JSON.parse(input):structuredClone(input);
 requireValue(pkg?.schema==='micromusic-um88-package'&&pkg.version===1,'Expected UM88 package v1');
 const {build,score,verification}=pkg;
 const usb=build?.board==='mh-et-live-16mhz',limit=usb?6012:8192;
 requireValue(build?.engine==='UM88'&&score?.schema==='micromusic-um88-score'&&score.version===1,'Unsupported UM88 source');
 requireValue(score.channels===1&&build.channels===1,'This import supports mono UM88');
 requireValue(Number.isInteger(build.cpuHz)&&(usb?build.cpuHz===16000000:build.cpuHz>=75000&&build.cpuHz<=12000000),'Invalid F_CPU');
 if(usb)requireValue(build.applicationFlashLimit===6012&&build.requiredFuses===null&&build.eepromRequired===false,'Invalid Micronucleus profile');
 requireValue(build.pwmHz===build.cpuHz/256&&build.synthesisHz===build.cpuHz/1024,'Clock/divider mismatch');
 requireValue(Number.isInteger(build.flashBytes)&&build.flashBytes>0&&build.flashBytes<=limit,'Invalid Flash size');
 requireValue(Number.isInteger(build.engineBytes)&&build.engineBytes>0&&build.engineBytes<=build.songAddress,'Invalid engine boundary');
 requireValue(Number.isInteger(build.songAddress)&&build.songAddress+26<build.flashBytes,'Invalid UM88 data address');
 requireValue(Number.isInteger(score.voices)&&score.voices>=1&&score.voices<=8&&score.voices===build.voices,'Invalid voice count');
 requireValue(Number.isInteger(score.controlTicks)&&score.controlTicks>=1&&score.controlTicks<=65535&&score.controlTicks===build.controlTicks,'Invalid duration');
 const flash=parseHex(pkg.flashHex,limit),hash=await sha256(flash);
 requireValue(flash.length===build.flashBytes&&hash===build.flashSha256,'Flash SHA-256 or size mismatch');
 requireValue(await sha256(flash.subarray(0,build.engineBytes))===build.engineSha256,'Engine SHA-256 mismatch');
 requireValue(String.fromCharCode(...flash.subarray(build.songAddress,build.songAddress+4))==='UM88','UM88 header missing');
 requireValue(flash[build.songAddress+4]===score.voices&&flash[build.songAddress+5]===1,'Header/source mismatch');
 requireValue(verification?.passed===true&&verification.allControlFramesMatch===true&&verification.allTonalMixesMatch===true&&verification.allPwmFramesMatch===true&&verification.allPercussionStatesMatch===true,'A complete digital playback audit is required');
 requireValue(verification.flashSha256===hash&&verification.engineSha256===build.engineSha256&&verification.cpuHz===build.cpuHz&&verification.backend===build.backend,'Audit/image profile mismatch');
 requireValue(verification.scoreSha256===await sha256(JSON.stringify(score)),'Audit/score SHA-256 mismatch');
 requireValue(verification.completeLoops>=1&&verification.fifoUnderruns===0&&verification.lostInterrupts===0,'Playback did not meet real-time requirements');
 if(usb)requireValue(verification.board===build.board&&verification.bootloaderHandoffChecked&&verification.erasedEepromChecked,'Micronucleus handoff was not checked');
 requireValue(verification.checkedGeneratedFrames>0&&verification.checkedIRQOutputs>0,'PWM/IRQ output was not checked');
 requireValue(verification.clippedChannelSamples===0,'PWM clipping detected; increase gainShift');
 const title=score.title||score.name;
 requireValue(typeof title==='string'&&title.length<=160&&title.length>0,'Invalid title');
 const steals=pkg.arrangementReport?.voiceSteals?.length||0;
 const omitted=pkg.arrangementReport?.omittedNotes?.length||0;
 const collapsed=pkg.arrangementReport?.collapsedNotes?.length||0;
 const unsupported=Object.values(pkg.arrangementReport?.ignoredEvents||{}).reduce((sum,n)=>sum+(Number.isInteger(n)&&n>0?n:0),0);
 const changes=[steals?'сокращено нот/хвостов: '+steals:'',omitted?'исключено нот: '+omitted:'',
  collapsed?'нот короче тика: '+collapsed:'',unsupported?'неподдержанных событий: '+unsupported:''].filter(Boolean);
 return {id:'um88-'+hash.slice(0,16),order:'UM',kind:'universal',device:'attiny88',firmwareEngine:'UM88',
  ...(usb?{board:build.board,applicationFlashLimit:limit,uploadProtocol:'micronucleus'}:{}),
  title,description:['Моно',score.voices+' голосов',(build.cpuHz/1000000).toLocaleString('ru')+' МГц',...changes].join(' · '),
  flashHex:pkg.flashHex,flashBytes:flash.length,flashSha256:hash,eepromBytes:0,eepromRequired:false,
  audioChannels:1,voices:score.voices,cpuHz:build.cpuHz,pwmHz:build.pwmHz,sampleHz:build.pwmHz,synthesisHz:build.synthesisHz,
  controlTicks:score.controlTicks,durationSeconds:score.controlTicks/(18750/256),
  universalPackage:pkg,verification};
}
