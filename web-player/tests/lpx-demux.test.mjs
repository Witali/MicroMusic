import test from'node:test';import assert from'node:assert/strict';
import{openAudio,openElementary}from'../lpx/audio-demux.js';
const u32=n=>{const b=Buffer.alloc(4);b.writeUInt32BE(n);return b;};
function box(type,data,wide=false){const h=Buffer.alloc(wide?16:8);h.writeUInt32BE(wide?1:h.length+data.length);h.write(type,4);if(wide)h.writeBigUInt64BE(BigInt(h.length+data.length),8);return Buffer.concat([h,data]);}
const full=payload=>Buffer.concat([u32(0),payload]),desc=(tag,body)=>Buffer.concat([Buffer.from([tag,body.length]),body]);
function mp4({early=false,wide=false,co64=false}={}){
  const ftyp=box('ftyp',Buffer.from('M4A \0\0\0\0M4A ')),media=box('mdat',Buffer.alloc(50),wide),decoder=Buffer.alloc(13);decoder[0]=64;decoder[1]=21;
  const esds=box('esds',full(desc(3,Buffer.concat([Buffer.from([0,1,0]),desc(4,Buffer.concat([decoder,desc(5,Buffer.from([0x12,0x10]))]))]))));
  const entry=Buffer.alloc(28);entry.writeUInt16BE(2,16);entry.writeUInt32BE(44100*65536,24);
  function movie(offset){const mvhd=Buffer.alloc(16);mvhd.writeUInt32BE(44100,12);const mdhd=Buffer.alloc(20);mdhd.writeUInt32BE(44100,12);mdhd.writeUInt32BE(2048,16);const hdlr=Buffer.alloc(12);hdlr.write('soun',8);
    let off=u32(offset);if(co64){off=Buffer.alloc(8);off.writeBigUInt64BE(BigInt(offset));}
    const tables=Buffer.concat([box('stsd',full(Buffer.concat([u32(1),box('mp4a',Buffer.concat([entry,esds]))]))),box('stsz',full(Buffer.concat([u32(0),u32(2),u32(20),u32(30)]))),box(co64?'co64':'stco',full(Buffer.concat([u32(1),off]))),box('stsc',full(Buffer.concat([u32(1),u32(1),u32(2),u32(1)]))),box('stts',full(Buffer.concat([u32(1),u32(2),u32(1024)])))]);
    return box('moov',Buffer.concat([box('mvhd',mvhd),box('trak',box('mdia',Buffer.concat([box('mdhd',mdhd),box('hdlr',hdlr),box('minf',box('stbl',tables))])))]));
  }
  const provisional=movie(0),offset=ftyp.length+(early?provisional.length:0)+(wide?16:8),moov=movie(offset);
  return Buffer.concat(early?[ftyp,moov,media]:[ftyp,media,moov]);
}
test('AAC tables support early/late moov, co64 and extended mdat without whole-file reads',async()=>{
  for(const early of[false,true])for(const wide of[false,true])for(const co64 of[false,true]){
    const blob=new Blob([mp4({early,wide,co64})]);blob.arrayBuffer=()=>{throw Error('Whole input read');};const t=await openAudio(blob),p=[...t.packets()];
    assert.equal(t.packetCount,2);assert.deepEqual(p.map(x=>x.size),[20,30]);assert.equal(p[1].offset,p[0].offset+20);assert.equal(t.config.codec,'mp4a.40.2');assert.ok(t.reader.maxRead<=65536);
  }
});
test('untrusted MP4 tables reject impossible indexes, fragmented containers and truncated payloads',async()=>{
  const original=mp4();for(const type of['stsz','stts','stsc','stco']){const b=Buffer.from(original),at=b.indexOf(Buffer.from(type));b.writeUInt32BE(0xffffffff,at+8);await assert.rejects(()=>openAudio(new Blob([b])));}
  await assert.rejects(()=>openAudio(new Blob([original.subarray(0,-1)])));
  const fragmented=Buffer.concat([original,box('moof',Buffer.alloc(0))]);await assert.rejects(()=>openAudio(new Blob([fragmented])),/фрагментированный/);
});
test('MP3 and ADTS frame scans preserve every packet and reject damaged changes',async()=>{
  const mp3=Buffer.alloc(417);mp3.set([255,251,144,0]);const id3=Buffer.from([73,68,51,4,0,0,0,0,0,3,0,0,0]);
  const aac=Buffer.alloc(16);aac.set([255,241,80,128,2,31,252]);
  for(const[kind,frame]of[['mp3',mp3],['aac',aac]]){
    const blob=new Blob([id3,frame,frame]);blob.arrayBuffer=()=>{throw Error('Whole input read');};const t=await openAudio(blob),packets=[];for await(const p of t.packets())packets.push(p);
    assert.equal(t.kind,kind);assert.equal(t.packetCount,2);assert.equal(packets[1].offset,id3.length+frame.length);
    await assert.rejects(()=>openElementary(new Blob([frame,frame.subarray(0,-1)]),kind));
  }
});
