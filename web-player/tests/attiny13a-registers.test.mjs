import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';
import * as definitions from '../lib/attiny13a-registers.js';
import {compileAnalog} from './analog-test-build.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
test('generated maps and byte-exact manufacturer inputs pass the reproducible check',()=>{
  const run=spawnSync(process.execPath,['web-player/scripts/generate-attiny13a-registers.mjs','--check'],{cwd:root,encoding:'utf8'});
  assert.equal(run.status,0,run.stderr||run.stdout);
});
const groups={AT13_IO:'AT13_IO_',AT13_DATA:'AT13_DATA_',AT13_WIDTH:'AT13_WIDTH_',
  AT13_BIT:'AT13_BIT_',AT13_MASK:'AT13_MASK_',AT13_VECTOR:'AT13_VECTOR_',AT13_CONST:'AT13_',
  AT13_FUSE_MASK:'AT13_FUSE_',AT13_MEMORY:'AT13_MEMORY_'};
const entries=Object.entries(groups).flatMap(([group,prefix])=>Object.entries(definitions[group])
  .map(([name,value])=>({name:prefix+name+(group==='AT13_FUSE_MASK'?'_MASK':''),value})));
const make=compileAnalog('manufacturer-registers',[],`
#include "../attiny13a-registers.h"
#include "../attiny13a-registers.h"
#if defined(ADC) || defined(ADCSRA) || defined(ADEN) || defined(_SFR_IO8) || defined(_AVR_IO_H_) || defined(_AVR_IOXXX_H_)
#error "Numeric adapter leaked unprefixed vendor macros"
#endif
static const unsigned values[]={${entries.map(entry=>entry.name).join(',')}};
int definition_count(void){return sizeof(values)/sizeof(values[0]);}
unsigned definition_value(unsigned index){return values[index];}
`);
test('numeric official C header values match every JS register/bit/vector/fuse constant',()=>{
  const exports=make();assert.equal(exports.definition_count(),entries.length);
  entries.forEach((entry,index)=>assert.equal(exports.definition_value(index),entry.value,entry.name));
});
test('CPU registers, I/O/data distinction and chip-specific fuse positions come from official inputs',()=>{
  const {AT13_IO:io,AT13_DATA:data,AT13_MASK:mask,AT13_FUSE_MASK:fuse,AT13_VECTOR:vector}=definitions;
  assert.equal(io.OCR0A,0x36);assert.equal(data.OCR0A,0x56);
  assert.equal(io.SPL,0x3d);assert.equal(data.SPL,0x5d);assert.equal(io.SREG,0x3f);assert.equal(data.SREG,0x5f);
  assert.equal(mask.SREG_I,0x80);assert.equal(mask.EEPE,mask.EEWE);assert.equal(mask.EEMPE,mask.EEMWE);
  assert.equal(fuse.LOW_CKDIV8,0x10);assert.equal(fuse.LOW_WDTON,0x20);
  assert.equal(fuse.HIGH_RSTDISBL,1);assert.equal(fuse.HIGH_SELFPRGEN,0x10);
  assert.equal(vector.TIM0_COMPA,6);assert.ok(Object.isFrozen(io));
});
test('JSON and assembler outputs carry the same generated maps without manual copies',()=>{
  const json=JSON.parse(readFileSync(new URL('../lib/attiny13a-registers.json',import.meta.url)));
  for(const [name,map] of Object.entries(definitions))assert.deepEqual(json.maps[name],map,name);
  const asm=readFileSync(new URL('../native/attiny13a-registers.generated.inc',import.meta.url),'utf8');
  const symbols=new Map([...asm.matchAll(/^\.set (\w+),(0x[\da-f]+|\d+)$/gm)].map(m=>[m[1],Number(m[2])]));
  for(const group of ['AT13_IO','AT13_BIT','AT13_MEMORY'])
    for(const [name,value] of Object.entries(definitions[group]))assert.equal(symbols.get(name),value,group+'.'+name);
});
