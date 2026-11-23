import{BlobRangeReader,openM4a}from'./m4a-demux.js?v=20261123-precision-input-v1';
const fail=message=>{throw Error(`Аудиофайл: ${message}`);};
const text=(b,p,n)=>String.fromCharCode(...b.subarray(p,p+n));
function mp3Header(b){
  if(b.length<4||b[0]!==255||(b[1]&224)!==224)return null;
  const version=(b[1]>>3)&3,layer=(b[1]>>1)&3,index=b[2]>>4,ri=(b[2]>>2)&3;
  if(version===1||layer!==1||!index||index===15||ri===3)return null;
  const rate=[44100,48000,32000][ri]/(version===3?1:version===2?2:4);
  const kbps=(version===3?[0,32,40,48,56,64,80,96,112,128,160,192,224,256,320]:[0,8,16,24,32,40,48,56,64,80,96,112,128,144,160])[index];
  return{rate,channels:(b[3]>>6)===3?1:2,samples:version===3?1152:576,size:Math.floor((version===3?144000:72000)*kbps/rate)+((b[2]>>1)&1),version,crc:!(b[1]&1)};
}
async function skipId3(reader){let at=0;
  for(let i=0;i<8&&at+10<=reader.blob.size;i++){const b=await reader.read(at,10);if(text(b,0,3)!=='ID3')return at;
    if(b[3]<2||b[3]>4||b.subarray(6,10).some(x=>x&128))fail('повреждён ID3.');
    const size=b[6]*2097152+b[7]*16384+b[8]*128+b[9];at+=10+size+(b[3]===4&&(b[5]&16)?10:0);if(at>reader.blob.size)fail('оборван ID3.');
  }return at;
}
export async function openElementary(blob,kind){
  const reader=new BlobRangeReader(blob),start=await skipId3(reader);let end=blob.size;
  if(kind==='mp3'&&end-start>=128&&text(await reader.read(end-128,3),0,3)==='TAG')end-=128;
  if(kind==='mp3'&&end-start>=32){const tail=await reader.read(end-32,32);if(text(tail,0,8)==='APETAGEX'){
    const view=new DataView(tail.buffer,tail.byteOffset,tail.byteLength),size=view.getUint32(12,true);if(size<32||size>end-start)fail('повреждён APE tag.');end-=size;
  }}
  let config=null,total=0,packetCount=0,first=start,delay=0,padding=0,declared=0;
  async function header(at){
    const b=await reader.read(at,Math.min(9,end-at));let h;
    if(kind==='mp3'){h=mp3Header(b);if(!h)fail('повреждён заголовок MP3 (нужен MPEG Layer III).');}
    else{
      if(b.length<7||b[0]!==255||(b[1]&246)!==240)fail('повреждён AAC/ADTS.');
      const rate=[96000,88200,64000,48000,44100,32000,24000,22050,16000,12000,11025,8000,7350][(b[2]>>2)&15];
      const object=(b[2]>>6)+1,channels=((b[2]&1)<<2)|(b[3]>>6),size=((b[3]&3)<<11)|(b[4]<<3)|(b[5]>>5);
      if(!rate||object!==2||![1,2].includes(channels)||size<(b[1]&1?7:9))fail('нужен моно/стерео AAC-LC в ADTS.');
      h={rate,channels,size,samples:1024*((b[6]&3)+1)};
    }
    if(h.size>end-at)fail('оборван звуковой пакет.');return h;
  }
  for(let at=start;at<end;){
    const h=await header(at);
    if(!config)config={codec:kind==='mp3'?'mp3':'mp4a.40.2',sampleRate:h.rate,numberOfChannels:h.channels};
    if(config.sampleRate!==h.rate||config.numberOfChannels!==h.channels)fail('изменение частоты или числа каналов не поддерживается.');
    if(at===start&&kind==='mp3'){
      const packet=await reader.read(at,h.size),p=4+(h.crc?2:0)+(h.version===3?(h.channels===1?17:32):(h.channels===1?9:17));
      const marker=text(packet,p,4);
      if(marker==='Xing'||marker==='Info'){
        const v=new DataView(packet.buffer,packet.byteOffset,packet.byteLength);if(p+8>packet.length)fail('оборван Xing.');
        const flags=v.getUint32(p+4);let q=p+8;
        if(flags&1){if(q+4>packet.length)fail('оборван счётчик Xing.');declared=v.getUint32(q);q+=4;}
        if(flags&2)q+=4;if(flags&4)q+=100;if(flags&8)q+=4;
        if(q+24<=packet.length&&['LAME','Lavc','Lavf'].some(tag=>text(packet,q,4)===tag)){
          delay=(packet[q+21]<<4)|(packet[q+22]>>4);padding=((packet[q+22]&15)<<8)|packet[q+23];
        }
        // Do not submit the metadata frame: WebCodecs may otherwise apply its
        // own priming discard. Apply LAME+LayerIII decoder delay once below.
        first=at+h.size;at=first;continue;
      }
    }
    total+=h.samples;packetCount++;if(packetCount>2000000)fail('слишком много пакетов.');at+=h.size;
  }
  if(!config||!packetCount)fail('нет звуковых пакетов.');
  if(declared&&Math.ceil(total/(config.sampleRate>=32000?1152:576))!==declared)fail('счётчик Xing не совпал с пакетами.');
  const trimSamples=kind==='mp3'&&declared&&delay+padding?delay+529:0;
  const length=kind==='mp3'&&trimSamples?total-delay-padding:total;
  if(length<=0||trimSamples+length>total)fail('неверная информация о задержке MP3.');
  const packets=async function*(){let clock=0;for(let at=first;at<end;){const h=await header(at);yield{offset:at,size:h.size,timestamp:Math.round(clock*1e6/h.rate),duration:Math.round(h.samples*1e6/h.rate)};clock+=h.samples;at+=h.size;}};
  return{kind,config,packetCount,packets,reader,trimStart:trimSamples/config.sampleRate,trimDuration:length/config.sampleRate,leading:0,duration:length/config.sampleRate,metadataBytes:0};
}
export async function openWav(blob){
  const reader=new BlobRangeReader(blob),first=await reader.read(0,Math.min(12,blob.size));
  if(text(first,0,4)!=='RIFF'||text(first,8,4)!=='WAVE')fail('нужен RIFF PCM WAV.');
  let format=null,data=null;const view=new DataView(first.buffer,first.byteOffset,first.byteLength),limit=view.getUint32(4,true)+8;
  if(limit!==blob.size)fail('неверная длина RIFF.');
  for(let at=12;at+8<=limit;){const b=await reader.read(at,8),v=new DataView(b.buffer,b.byteOffset,b.byteLength),size=v.getUint32(4,true),type=text(b,0,4);if(at+8+size>limit)fail('оборван блок WAV.');
    if(type==='fmt '){if(format||size<16)fail('повреждён fmt WAV.');const f=await reader.read(at+8,16),fv=new DataView(f.buffer,f.byteOffset,f.byteLength);format={code:fv.getUint16(0,true),channels:fv.getUint16(2,true),rate:fv.getUint32(4,true),bytes:fv.getUint32(8,true),align:fv.getUint16(12,true),bits:fv.getUint16(14,true)};}
    if(type==='data'){if(data)fail('несколько data блоков WAV не поддерживаются.');data={at:at+8,size};}at+=8+size+(size&1);
  }
  if(!format||!data||format.code!==1||format.bits!==16||![1,2].includes(format.channels)||format.align!==format.channels*2||format.bytes!==format.rate*format.align||data.size%format.align)fail('для потокового WAV нужен PCM16, моно или стерео.');
  const frames=data.size/format.align;if(!frames)fail('пустой WAV.');
  return{kind:'wav',reader,frames,...format,...data,duration:frames/format.rate,metadataBytes:0};
}
export async function openAudio(blob){
  const b=new Uint8Array(await blob.slice(0,16).arrayBuffer());
  if(b.length>=12&&text(b,4,4)==='ftyp')return{...await openM4a(blob),kind:'m4a'};
  if(text(b,0,4)==='RIFF')return openWav(blob);
  // ID3 can prefix either MP3 or raw ADTS; inspect the first actual frame.
  const r=new BlobRangeReader(blob),at=await skipId3(r),h=await r.read(at,Math.min(9,blob.size-at));
  return openElementary(blob,mp3Header(h)?'mp3':'aac');
}
