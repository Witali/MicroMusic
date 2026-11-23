// Small, range-read ISO BMFF demuxer for unencrypted, non-fragmented AAC audio.
// No sample payload or file-name metadata is retained in the sample tables.
const MAX_METADATA=16*1024*1024, MAX_PACKETS=2000000, MAX_PACKET=1024*1024;
const fail=message=>{throw Error(`M4A: ${message}`);};
const number64=(hi,lo)=>{const n=hi*4294967296+lo;if(!Number.isSafeInteger(n))fail('слишком большое смещение.');return n;};
const code=(b,p)=>String.fromCharCode(...b.subarray(p,p+4));
function boxes(bytes,start=0,end=bytes.length){
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),result=[];
  for(let p=start;p<end;){
    if(p+8>end)fail('оборван заголовок блока.');
    let size=view.getUint32(p),header=8;const type=code(bytes,p+4);
    if(size===1){if(p+16>end)fail('оборван длинный заголовок.');size=number64(view.getUint32(p+8),view.getUint32(p+12));header=16;}
    if(!size)size=end-p;
    if(size<header||size>end-p)fail('повреждён размер блока.');
    result.push({type,start:p,data:p+header,end:p+size});p+=size;
    if(result.length>100000)fail('слишком много блоков.');
  }
  return result;
}
function only(items,type,required=true){const found=items.filter(x=>x.type===type);if(found.length>1||(!found.length&&required))fail(`неоднозначный или отсутствующий ${type}.`);return found[0];}
function descriptor(bytes,start,end){
  if(start>=end)fail('оборван дескриптор AAC.');
  const tag=bytes[start++];let size=0,done=false;
  for(let i=0;i<4&&start<end;i++){const b=bytes[start++];size=size*128+(b&127);if(!(b&128)){done=true;break;}}
  if(!done||size>end-start)fail('повреждён дескриптор AAC.');return {tag,start,end:start+size};
}
function audioConfig(bytes,box){
  let d=descriptor(bytes,box.data+4,box.end);if(d.tag!==3||d.start+3>d.end)fail('неизвестный ES descriptor.');
  let p=d.start+3;const flags=bytes[d.start+2];
  if(flags&128)p+=2;if(flags&64){if(p>=d.end)fail('оборван ES URL.');p+=1+bytes[p];}if(flags&32)p+=2;
  d=descriptor(bytes,p,d.end);if(d.tag!==4||d.start+13>d.end||bytes[d.start]!==0x40)fail('нужен MPEG-4 AAC.');
  d=descriptor(bytes,d.start+13,d.end);if(d.tag!==5||d.end-d.start<2||d.end-d.start>256)fail('отсутствует AudioSpecificConfig.');
  const asc=bytes.slice(d.start,d.end);let bit=0;
  const get=n=>{let value=0;for(let i=0;i<n;i++,bit++){if(bit>=asc.length*8)fail('оборван AudioSpecificConfig.');value=value*2+((asc[bit>>3]>>(7-(bit&7)))&1);}return value;};
  let object=get(5);if(object===31)object=32+get(6);
  const frequencies=[96000,88200,64000,48000,44100,32000,24000,22050,16000,12000,11025,8000,7350];
  const frequency=()=>{const index=get(4);return index===15?get(24):frequencies[index]||fail('неизвестная частота AAC.');};
  let rate=frequency();const channels=get(4);
  if(![2,5,29].includes(object)||![1,2].includes(channels))fail('поддерживается AAC-LC/HE-AAC, моно или стерео.');
  if(object===5||object===29){rate=frequency();if(get(5)!==2)fail('неподдерживаемый основной профиль HE-AAC.');}
  if(rate<8000||rate>96000)fail('неподдерживаемая частота AAC.');
  return {codec:`mp4a.40.${object}`,description:asc,sampleRate:rate,numberOfChannels:channels};
}
export class BlobRangeReader{
  constructor(blob){this.blob=blob;this.cache=null;this.at=0;this.maxRead=0;this.bytesRead=0;}
  async read(at,size){
    if(!Number.isSafeInteger(at)||!Number.isSafeInteger(size)||at<0||size<0||size>MAX_PACKET||at+size>this.blob.size)fail('неверный диапазон чтения.');
    if(!size)return new Uint8Array();
    if(!this.cache||at<this.at||at+size>this.at+this.cache.length){
      this.at=at;const count=Math.min(this.blob.size-at,Math.max(size,65536));
      this.cache=new Uint8Array(await this.blob.slice(at,at+count).arrayBuffer());
      if(this.cache.length!==count)fail('файл прочитан не полностью.');this.maxRead=Math.max(this.maxRead,count);this.bytesRead+=count;
    }
    return this.cache.subarray(at-this.at,at-this.at+size);
  }
}
export async function openM4a(blob){
  if(!blob||!Number.isSafeInteger(blob.size)||blob.size<8)fail('пустой файл.');
  const reader=new BlobRangeReader(blob),media=[];let moov=null,seenFtyp=false;
  for(let at=0,count=0;at<blob.size;){
    if(++count>100000||at+8>blob.size)fail('повреждён список блоков.');
    const h=await reader.read(at,Math.min(16,blob.size-at));const v=new DataView(h.buffer,h.byteOffset,h.byteLength);
    let size=v.getUint32(0),header=8;const type=code(h,4);
    if(size===1){if(h.length<16)fail('оборван большой блок.');size=number64(v.getUint32(8),v.getUint32(12));header=16;}
    if(!size)size=blob.size-at;
    if(size<header||size>blob.size-at)fail('повреждён верхний блок.');
    if(type==='ftyp')seenFtyp=true;
    if(type==='moof')fail('фрагментированный MP4 пока не поддерживается.');
    if(type==='mdat')media.push({start:at+header,end:at+size});
    if(type==='moov'){if(moov||size>MAX_METADATA)fail('слишком большая или повторная таблица moov.');moov={start:at+header,size:size-header};}
    at+=size;
  }
  if(!seenFtyp||!moov||!media.length)fail('не найден обычный аудиоконтейнер MP4.');
  const bytes=new Uint8Array(moov.size);
  for(let at=0;at<bytes.length;at+=65536)bytes.set(await reader.read(moov.start+at,Math.min(65536,bytes.length-at)),at);
  const v=new DataView(bytes.buffer),children=box=>boxes(bytes,box.data,box.end),top=boxes(bytes);
  const need=(box,count)=>{if(!box||count>box.end-box.data)fail('оборвана таблица.');};
  const full=(box,min)=>{need(box,min);if(bytes[box.data]!==0)fail(`неподдерживаемая версия ${box.type}.`);};
  const mvhd=only(top,'mvhd');need(mvhd,bytes[mvhd.data]===1?24:16);
  const movieScale=v.getUint32(mvhd.data+(bytes[mvhd.data]===1?20:12));if(!movieScale)fail('нулевая шкала времени.');
  if(top.some(b=>b.type==='mvex'))fail('фрагментированный MP4 пока не поддерживается.');
  const tracks=[];
  for(const trak of top.filter(x=>x.type==='trak')){
    const tc=children(trak),mdia=only(tc,'mdia'),mc=children(mdia),handler=only(mc,'hdlr');need(handler,12);
    if(code(bytes,handler.data+8)!=='soun')continue;
    const mdhd=only(mc,'mdhd');need(mdhd,bytes[mdhd.data]===1?32:20);
    const version=bytes[mdhd.data];if(version>1)fail('неизвестная версия mdhd.');
    const scale=v.getUint32(mdhd.data+(version?20:12));
    const duration=version?number64(v.getUint32(mdhd.data+24),v.getUint32(mdhd.data+28)):v.getUint32(mdhd.data+16);
    if(!scale||!duration)fail('нулевая длительность аудио.');
    const minf=only(mc,'minf'),stbl=only(children(minf),'stbl'),tables=children(stbl),stsd=only(tables,'stsd');full(stsd,8);
    if(v.getUint32(stsd.data+4)!==1)fail('нужен один неизменный AAC sample description.');
    const entry=only(boxes(bytes,stsd.data+8,stsd.end),'mp4a');need(entry,28);
    if(v.getUint16(entry.data+8)!==0)fail('неподдерживаемая версия audio sample entry.');
    const entryChildren=boxes(bytes,entry.data+28,entry.end);
    if(entryChildren.some(x=>x.type==='sinf'))fail('защищённое аудио не поддерживается.');
    const config=audioConfig(bytes,only(entryChildren,'esds'));
    const stsz=only(tables,'stsz');full(stsz,12);const fixedSize=v.getUint32(stsz.data+4),packetCount=v.getUint32(stsz.data+8);
    if(!packetCount||packetCount>MAX_PACKETS)fail('слишком много AAC пакетов.');
    need(stsz,12+(fixedSize?0:packetCount*4));
    const offsets=only(tables,'stco',false)||only(tables,'co64',false);full(offsets,8);
    if(tables.some(x=>x.type==='stco')&&tables.some(x=>x.type==='co64'))fail('две таблицы смещений.');
    const chunkCount=v.getUint32(offsets.data+4),width=offsets.type==='co64'?8:4;
    if(!chunkCount||chunkCount>packetCount)fail('неверное количество чанков.');need(offsets,8+chunkCount*width);
    const stsc=only(tables,'stsc');full(stsc,8);const mapCount=v.getUint32(stsc.data+4);need(stsc,8+mapCount*12);
    if(!mapCount||mapCount>chunkCount)fail('повреждённая карта чанков.');
    let previous=0;
    for(let i=0;i<mapCount;i++){const at=stsc.data+8+i*12,first=v.getUint32(at);if(first<=previous||(i===0&&first!==1)||first>chunkCount||!v.getUint32(at+4)||v.getUint32(at+8)!==1)fail('неверная карта AAC пакетов.');previous=first;}
    const stts=only(tables,'stts');full(stts,8);const timeCount=v.getUint32(stts.data+4);need(stts,8+timeCount*8);
    if(!timeCount||timeCount>packetCount)fail('неверная таблица времени.');
    let covered=0,totalTime=0;
    for(let i=0;i<timeCount;i++){const at=stts.data+8+i*8,c=v.getUint32(at),delta=v.getUint32(at+4);if(!c||!delta)fail('пустая длительность AAC.');covered+=c;totalTime+=c*delta;}
    if(covered!==packetCount||!Number.isSafeInteger(totalTime)||totalTime!==duration)fail('длительность пакетов не совпала с mdhd.');
    const ctts=only(tables,'ctts',false);if(ctts){full(ctts,8);const count=v.getUint32(ctts.data+4);need(ctts,8+count*8);for(let i=0;i<count;i++)if(v.getUint32(ctts.data+12+i*8))fail('смещение времени AAC пока не поддерживается.');}
    let trimStart=0,trimDuration=duration/scale,leading=0;
    const edts=only(tc,'edts',false);
    if(edts){const elst=only(children(edts),'elst');need(elst,8);const ev=bytes[elst.data],count=v.getUint32(elst.data+4),stride=ev===1?20:12;if(ev>1||!count||count>2)fail('сложный монтаж AAC пока не поддерживается.');need(elst,8+count*stride);
      for(let i=0;i<count;i++){const at=elst.data+8+i*stride;const span=ev?number64(v.getUint32(at),v.getUint32(at+4)):v.getUint32(at);const p=at+(ev?8:4);let mediaTime=ev?v.getInt32(p)*4294967296+v.getUint32(p+4):v.getInt32(p);const rateAt=p+(ev?8:4);if(v.getInt32(rateAt)!==65536)fail('изменение скорости AAC не поддерживается.');
        if(mediaTime===-1&&i===0&&count===2){leading=span/movieScale;continue;}if(mediaTime<0||(count===2&&i!==1))fail('сложный монтаж AAC не поддерживается.');trimStart=mediaTime/scale;trimDuration=span/movieScale;
      }
      if(trimStart+trimDuration>duration/scale+1/movieScale)fail('монтаж выходит за длительность аудио.');
    }
    const packetSize=i=>fixedSize||v.getUint32(stsz.data+12+i*4);
    const chunkOffset=i=>{const at=offsets.data+8+i*width;return width===8?number64(v.getUint32(at),v.getUint32(at+4)):v.getUint32(at);};
    const packets=function*(){let index=0,map=0,time=0,tr=0,left=v.getUint32(stts.data+8),delta=v.getUint32(stts.data+12);
      for(let c=0;c<chunkCount;c++){while(map+1<mapCount&&v.getUint32(stsc.data+8+(map+1)*12)<=c+1)map++;let at=chunkOffset(c),n=v.getUint32(stsc.data+12+map*12);
        for(let j=0;j<n;j++){if(index>=packetCount)fail('лишний пакет в чанке.');const size=packetSize(index++);if(!size||size>MAX_PACKET||!media.some(m=>at>=m.start&&at+size<=m.end))fail('пакет вне mdat.');yield {offset:at,size,timestamp:Math.round(time*1e6/scale),duration:Math.round(delta*1e6/scale)};at+=size;time+=delta;if(!--left&&index<packetCount){tr++;left=v.getUint32(stts.data+8+tr*8);delta=v.getUint32(stts.data+12+tr*8);}}
      }
      if(index!==packetCount)fail('недостаточно пакетов в чанках.');
    };
    // Validate the complete index before creating a decoder or temporary PCM.
    let lastEnd=0;for(const p of packets()){if(p.offset<lastEnd)fail('перекрывающиеся AAC пакеты.');lastEnd=p.offset+p.size;}
    tracks.push({config,packetCount,packets,trimStart,trimDuration,leading,duration:leading+trimDuration});
  }
  if(tracks.length!==1)fail('нужна одна звуковая дорожка AAC.');
  return {...tracks[0],reader,metadataBytes:bytes.length};
}
