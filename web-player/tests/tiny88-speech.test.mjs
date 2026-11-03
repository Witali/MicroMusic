import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {lpxTiny88FirmwareEntries} from '../lib/tiny88-preview.js';
import {lpxPreviewEntries,previewWaveform} from '../lib/native-preview.js';
import {parseHex} from '../lib/hex.js';
import {playerApp} from './helpers/player-app.mjs';

const load=path=>JSON.parse(readFileSync(new URL('../'+path,import.meta.url)));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const flush=()=>new Promise(setImmediate);
const cards=app=>app.get('catalog').children.map(item=>item.children[0]);
const base='https://example.test/MicroMusic/web-player/';

// Real existing listening assets, synthetic memory/timing receipts for boundary
// tests. The release test below checks the separately generated public images.
function fixture(){
  const clips=[...load('audio/lpx-speech/manifest.json').clips,{...load('audio/lpx-bread/manifest.json'),clipId:'bread'}];
  return {schema:'micromusic-lpx-attiny88-firmware-v1',device:'attiny88',cpuHz:16000000,sampleHz:8000,pwmHz:62500,
    pwmOutput:'D9 / PB1 / OC1A',flashLimitBytes:8192,bootloaderLimitBytes:6012,physicalBoardMeasured:false,clips,
    variants:clips.flatMap(clip=>clip.variants.map(variant=>({id:variant.id,clipId:clip.clipId,
      source:`firmware/attiny88/lpx-tiny88-${clip.clipId}-${variant.id}.hex`,hexSha256:'a'.repeat(64),
      streamSha256:hash(readFileSync(new URL('../'+variant.stream,import.meta.url))),
      flashBytes:6000,programFlashBytes:6000-variant.bytes,staticSramBytes:300,peakStackBytes:100,stackMarginBytes:111,
      fitsStandardBootloader:true,requiresIsp:false,timing:{playedSamples:clip.samples,underruns:0,
        minTickCycles:1991,maxTickCycles:2009,irqEntryCycles:4,irqRetiComplete:true,minQueuedSamplesBeforeOutput:1}})))};
}

function resize(data,bytes,index=0){
  const variant=data.variants[index],clip=data.clips.find(item=>item.clipId===variant.clipId);
  variant.flashBytes=bytes;variant.programFlashBytes=bytes-clip.variants.find(item=>item.id===variant.id).bytes;
  variant.fitsStandardBootloader=bytes<=6012;variant.requiresIsp=bytes>6012;
  return data;
}

test('Tiny88 catalog preserves all nine preview identities and binds D9/rates to same-origin HEX files',()=>{
  const data=fixture();
  for(const prefix of ['/','/MicroMusic/']){
    const url='https://example.test'+prefix+'web-player/';
    const entries=lpxTiny88FirmwareEntries(data,url),previews=data.clips.flatMap(clip=>lpxPreviewEntries(clip,url));
    assert.deepEqual(entries.map(entry=>entry.id),previews.map(entry=>entry.id));
    assert.equal(entries.length,9);
    for(const entry of entries){
      assert.equal(entry.device,'attiny88');assert.equal(entry.sampleHz,8000);
      assert.equal(entry.cpuHz,16000000);assert.equal(entry.pwmHz,62500);
      assert.equal(entry.firmware.pwmOutput,'D9 / PB1 / OC1A');assert.equal(entry.firmware.pwmPin,9);
      assert.equal(entry.flashMeasurement,undefined);
      assert.equal(entry.nativeAudioUrl,previews.find(item=>item.id===entry.id).nativeAudioUrl);
      assert.equal(entry.firmware.source,url+data.variants.find(item=>'lpx-'+item.clipId+'-'+item.id===entry.id).source);
      assert.equal(entry.firmware.staticSramBytes+entry.firmware.peakStackBytes+entry.firmware.stackMarginBytes,511);
      assert.notEqual(entry.codec,'speex');
    }
  }
});

test('Tiny88 rejects oversized images, inaccurate receipts and foreign or ambiguous download URLs',()=>{
  for(const mutate of [
    d=>{d.schema='unknown';},d=>{d.device='atmega328p';},d=>{d.cpuHz=8000000;},d=>{d.sampleHz=16000;},
    d=>{d.pwmHz=31250;},d=>{d.pwmOutput='D10 / PB2 / OC1B';},d=>{d.flashLimitBytes=8193;},
    d=>{d.bootloaderLimitBytes=6144;},d=>{d.physicalBoardMeasured=true;},d=>{resize(d,8193);},
    d=>{d.variants[0].programFlashBytes++;},d=>{d.variants[0].staticSramBytes++;},
    d=>{d.variants[0].peakStackBytes=0;},d=>{d.variants[0].stackMarginBytes=0;},
    d=>{d.variants[0].hexSha256='invalid';},d=>{d.variants[0].streamSha256='invalid';},
    d=>{d.variants[0].fitsStandardBootloader=false;},d=>{d.variants[0].requiresIsp=true;},
    d=>{d.variants[0].source='https://example.net/player.hex';},
    d=>{d.variants[0].source='firmware/attiny88/other.hex';},
    d=>{d.variants[0].source+='?other';},d=>{d.variants[0].source+='#other';},
    d=>{d.variants[0].timing.playedSamples--;},d=>{d.variants[0].timing.underruns=1;},
    d=>{d.variants[0].timing.irqEntryCycles=3;},d=>{d.variants[0].timing.irqRetiComplete=false;},
    d=>{d.variants[0].timing.minQueuedSamplesBeforeOutput=0;},d=>{d.variants[0].timing.minTickCycles=1979;},
    d=>{d.variants[0].timing.maxTickCycles=2021;},d=>{d.variants[0].timing.minTickCycles=2010;},
    d=>{d.variants[1]=d.variants[0];},d=>{d.clips[1]=d.clips[0];},d=>{d.variants.pop();}
  ]){
    const data=fixture();mutate(data);assert.throws(()=>lpxTiny88FirmwareEntries(data,base));
  }
});

test('Tiny88 download warnings use the exact board limit, 6 KiB threshold and full 8192-byte cap',async()=>{
  for(const [bytes,requiresIsp,over6KiB] of [[6012,false,false],[6013,true,false],[6144,true,false],[6145,true,true],[8192,true,true]]){
    const data=resize(fixture(),bytes);
    const app=await playerApp({device:'attiny88',firmware:'lpx-chego-compact',catalogs:{'firmware-lpx-attiny88.json':data}});await flush();
    assert.equal(app.get('download').getAttribute('aria-disabled'),null);
    assert.equal(app.get('download').href,base+'firmware/attiny88/lpx-tiny88-chego-compact.hex');
    assert.equal(app.get('download').download,'lpx-chego-compact.hex');
    assert.equal(app.get('speech-upload-warning').hidden,!requiresIsp);
    if(requiresIsp){
      assert.match(app.get('speech-upload-warning').textContent,/6.?012 байт/);
      assert.match(app.get('speech-upload-warning').textContent,/ISP/);
      assert.match(app.get('download').title,/ISP/);
    }
    assert.equal(app.get('speech-upload-warning').textContent.includes('больше 6 КиБ'),over6KiB);
  }
});

test('verified Tiny88 firmware replaces previews once and retains quality across all phrases and URLs',async()=>{
  const data=fixture();
  for(const prefix of ['/','/MicroMusic/']){
    const app=await playerApp({prefix,device:'attiny88',firmware:'lpx-vinni-quality',catalogs:{'firmware-lpx-attiny88.json':data}});await flush();
    assert.equal(app.get('speech-profile-select').children.length,2);
    assert.match(app.get('tiny88-power').textContent,/D9 \/ PB1 \/ OC1A/);
    assert.match(app.get('tiny88-power').textContent,/речь 8 кГц · PWM 62,5 кГц/);
    assert.match(app.get('chip-attiny88').getAttribute('aria-label'),/D9 \/ PB1 \/ OC1A/);
    assert.equal(app.body.dataset.pwmPin,'9');
    assert.match(app.get('preview-playback-note').textContent,/HEX для ATtiny88.*активными прерываниями/);
    assert.equal(app.get('flash-measurement-note').hidden,true);
    assert.match(app.get('speech-profile-details').textContent,/Прошивка: .* байт · Звук: .* байт/);
    for(const [index,clip] of ['chego','otvechaesh','vinni','bread'].entries()){
      cards(app)[index].onclick();await flush();
      assert.equal(app.location.searchParams.get('firmware'),`lpx-${clip}-quality`);
      assert.equal(app.location.searchParams.get('device'),'attiny88');
      assert.equal(app.location.searchParams.get('board'),'mh-et-live-16mhz');
      assert.equal(app.get('speech-profile-select').children.length,2);
      assert.deepEqual(app.get('speech-profile-select').children.map(option=>option.value),[`lpx-${clip}-compact`,`lpx-${clip}-quality`]);
      assert.deepEqual(app.get('speech-profile-select').children.map(option=>option.textContent),['Компактный','Повышенное качество']);
      assert.ok(app.get('speech-profile-select').children.every(option=>!option.value.startsWith('speex-')));
      const download=new URL(app.get('download').href);
      assert.equal(download.origin+download.pathname,'https://example.test'+prefix+`web-player/firmware/attiny88/lpx-tiny88-${clip}-quality.hex`);
      const level=data.clips.find(c=>c.clipId===clip).variants.find(v=>v.id==='quality').outputLevel;
      assert.equal(download.searchParams.get('v'),level?.numerator>128?'a'.repeat(16):null);
      assert.equal(cards(app).length,4);
    }
    app.get('speech-profile-select').value='lpx-bread-low15';app.get('speech-profile-select').onchange();await flush();
    assert.equal(app.get('speech-profile-select').value,'lpx-bread-quality');
    assert.equal(app.get('download').download,'lpx-bread-quality.hex');
    assert.ok(cards(app).every(card=>!card.disabled));
    assert.equal(app.workers.length,0);
    const reopened=await playerApp({prefix,device:'attiny88',firmware:'lpx-bread-low15',board:'mh-et-live-16mhz',catalogs:{'firmware-lpx-attiny88.json':data}});await flush();
    assert.equal(reopened.location.searchParams.get('firmware'),'lpx-bread-compact');
    assert.equal(reopened.get('download').download,'lpx-bread-compact.hex');
    assert.deepEqual(reopened.get('speech-profile-select').children.map(option=>option.value),['lpx-bread-compact','lpx-bread-quality']);
    cards(reopened)[0].onclick();await flush();
    assert.equal(reopened.location.searchParams.get('firmware'),'lpx-chego-compact');
    reopened.get('device-select').value='atmega328p';await reopened.get('device-select').onchange();await flush();
    assert.equal(reopened.get('speech-upload-warning').hidden,true);
  }
});

test('unavailable or invalid Tiny88 release retains the existing complete WAV-only previews',async()=>{
  for(const corrupt of [false,true]){
    const data=fixture();if(corrupt)resize(data,8193);
    const app=await playerApp({device:'attiny88',firmware:'lpx-bread-quality',catalogs:{'firmware-lpx-attiny88.json':data},
      fetchHook:({url,response})=>!corrupt&&url.pathname.endsWith('/firmware-lpx-attiny88.json')?{ok:false,status:503}:response});await flush();
    assert.equal(app.get('error').hidden,true);assert.equal(cards(app).length,4);
    assert.equal(app.get('speech-profile-select').children.length,2);
    assert.deepEqual(app.get('speech-profile-select').children.map(option=>option.textContent),['Компактный','Повышенное качество']);
    assert.equal(app.get('download').getAttribute('aria-disabled'),'true');
    assert.equal(app.get('speech-upload-warning').hidden,true);
    assert.ok(app.preview.src.endsWith('/audio/lpx-bread/quality.wav'));
    assert.match(app.get('speech-profile-details').textContent,/Тестовая сборка/);
  }
});

test('published Tiny88 releases match retained HEX, streams, WAVs and optional source provenance',()=>{
  const data=load('firmware-lpx-attiny88.json'),entries=lpxTiny88FirmwareEntries(data,base);
  assert.equal(entries.length,9);
  for(const variant of data.variants){
    const hex=readFileSync(new URL('../'+variant.source,import.meta.url)),bytes=Buffer.from(parseHex(hex.toString(),8192));
    assert.equal(hash(hex),variant.hexSha256);assert.equal(bytes.length,variant.flashBytes);
    const clip=data.clips.find(item=>(item.clipId??'bread')===variant.clipId),preview=clip.variants.find(item=>item.id===variant.id);
    const stream=readFileSync(new URL('../'+preview.stream,import.meta.url));
    assert.equal(hash(stream),variant.streamSha256);
    const start=bytes.indexOf(stream);assert.ok(start>=0);assert.equal(bytes.indexOf(stream,start+1),-1);
    assert.equal(variant.programFlashBytes+stream.length,variant.flashBytes);
    const entry=entries.find(item=>item.id===`lpx-${variant.clipId}-${variant.id}`);
    const wav=readFileSync(new URL('../'+preview.audio,import.meta.url));
    assert.equal(previewWaveform(wav.buffer.slice(wav.byteOffset,wav.byteOffset+wav.byteLength),entry).length,clip.samples);
  }
  if(data.sourceSha256){
    assert.equal(data.sourceHashEncoding,'text-lf');
    for(const [path,expected] of Object.entries(data.sourceSha256))
      assert.equal(hash(readFileSync(new URL('../../'+path,import.meta.url),'utf8').replaceAll('\r\n','\n')),expected,path);
  }
});
