'use strict';
// Host-side LPX3 v1 reference decoder, writes raw float32 little-endian PCM.
// Usage: node tools/decode_original_lpx3.js input.lpx3 out_f32_le.pcm
const fs = require('fs'), vm=require('vm'), path=require('path');
if(process.argv.length!==4){console.error('usage: node decode_original_lpx3.js input.lpx3 output_f32.pcm');process.exit(2);}
const bytes=new Uint8Array(fs.readFileSync(process.argv[2]));
const js=fs.readFileSync(path.join(__dirname,'../reference/lpx3_decoder.js'),'utf8');
const sandbox={Float64Array,Float32Array,Uint8Array,DataView,Array,Math};vm.createContext(sandbox);vm.runInContext(js,sandbox);
sandbox.rawBytes=bytes;
vm.runInContext(`globalThis.out=decodeLPX3(rawBytes);`,sandbox);
const f=sandbox.out.pcm,b=Buffer.alloc(f.length*4);
for(let i=0;i<f.length;i++)b.writeFloatLE(f[i],i*4);
fs.writeFileSync(process.argv[3],b);
console.log(JSON.stringify({samples:f.length,sampleRate:sandbox.out.sampleRate,bytes:b.length}));
