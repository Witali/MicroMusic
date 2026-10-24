// Full songs and restart on both profiles, independently of audio resampling.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {parseArgs} from 'node:util';
import {audit,VARIANTS} from './audit-attiny88-music.mjs';

const {values,positionals}=parseArgs({allowPositionals:true,options:{
  output:{type:'string',default:'web-player/reports/common-avr-verification.json'},
}});
const names=positionals.length?positionals:VARIANTS;
const baseline=JSON.parse(fs.readFileSync('tools/fixtures/attiny-music-startup-baseline.json'));
const sources=['web-player/lib/avr-profiles.js','web-player/lib/avr-reference.js',
  'web-player/lib/avr-wasm.js','web-player/native/avr.c','web-player/wasm/avr.wasm'];
const sha=data=>createHash('sha256').update(data).digest('hex');
const entries=[];
for(const variant of names){
  assert.ok(VARIANTS.includes(variant),'Unknown variant: '+variant);
  for(const engine of ['js','wasm']){
    console.log(`${variant} / ${engine}: complete songs on ATtiny13A and ATtiny88`);
    const result=audit(variant,{engine,writeReport:false,log:false});
    for(const target of ['original','port']){
      const actual=result[target],expected=baseline.variants[variant];
      for(const field of ['controlTicks','firstRestartControlTick','snapshotSha256','musicalCommands','commandSha256'])
        assert.equal(actual[field],expected[field],`${variant}/${engine}/${target}: ${field}`);
    }
    entries.push({variant,engine,...result});
    console.log(`${variant} / ${engine}: all notes, envelopes, commands, FIFO and restart verified`);
  }
}
fs.writeFileSync(values.output,JSON.stringify({
  baselineCommit:baseline.commit,
  method:'All CPU samples through each complete song and one second of restart, on both profiles and execution engines. Every control-tick voice state and every musical command match the retained baseline.',
  sourceHashes:Object.fromEntries(sources.map(source=>[source,sha(source.endsWith('.wasm')
    ?fs.readFileSync(source):fs.readFileSync(source,'utf8').replace(/\r\n/g,'\n'))])),
  entries,
},null,2)+'\n');
