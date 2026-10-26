import test from 'node:test';
import assert from 'node:assert/strict';
import { cReference } from '../voice32/reference.mjs';
import { auditAll } from './audit.mjs';
import { carrierAlias } from './audio-check.mjs';

test('Fast PCM4 codec stays portable C on every CPU; ASM availability requires real 8080 plus explicit opt-in', async()=>{
  for(const [i,defines] of [[],['__8080=1'],['MICROMUSIC_ENABLE_I8080_ASM=1'],['__8080=1','MICROMUSIC_ENABLE_I8080_ASM=1']].entries()){
    const {api}=await cReference({defines,suffix:'-fast-gate'+i});assert.equal(api.asm_enabled(),Number(i===3));
    for(let byte=0;byte<256;byte++)for(let n=0;n<2;n++){
      const q=api.nibble(byte,n),packed=api.storage(byte&15)<<4|api.storage(byte>>4);
      assert.equal(api.fast_level(packed,n),q);assert.equal(api.width(q),4+4*q);
    }
  }
});

test('Six full 82T ROMs: lossless PCM storage, exact C and independent clock, all level/branch cases, live Z and CRC failures',async()=>{
  const reports=await auditAll({check:true});assert.equal(reports.length,6);
  assert.equal(reports.reduce((sum,r)=>sum+r.pulses,0),606184);
  assert.ok(reports.every(r=>r.pulses_per_sample===2&&r.maximum_grid_error_t===0&&r.maximum_width_error_t===0));
});

test('Band-limited preview rejects 82T carrier foldover below -80dBFS with the default single RC pole',()=>{
  for(const deviceRate of [44100,48000]){
    const measurement=carrierAlias(10000,1,{deviceRate});
    assert.ok(measurement.alias_dbfs < -80);
  }
});
