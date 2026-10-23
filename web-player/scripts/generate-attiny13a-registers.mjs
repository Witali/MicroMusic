// Project adaptation only. The pinned manufacturer files are never rewritten.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
const root=fileURLToPath(new URL('../../',import.meta.url));
const vendor='web-player/vendor/microchip/ATtiny_DFP/3.4.278';
const read=path=>readFileSync(resolve(root,path));
const text=path=>read(path).toString('utf8');
const hash=value=>createHash('sha256').update(value).digest('hex');
const provenance=JSON.parse(text(vendor+'/provenance.json'));
for(const [path,record] of Object.entries(provenance.files)){
  const original=read(vendor+'/'+path);assert.equal(original.length,record.bytes,path+' size');
  assert.equal(hash(original),record.sha256,path+' byte hash');
}
const header=text(vendor+'/include/avr/iotn13a.h'),atdf=text(vendor+'/atdf/ATtiny13A.atdf');
const assembler=text(vendor+'/avrasm/inc/tn13Adef.inc');
const clean=header.replace(/\/\*[\s\S]*?\*\//g,'');
const macros=new Map([...clean.matchAll(/^\s*#\s*define\s+(\w+)(?:[^\S\r\n]+([^\r\n]*))?$/gm)].map(m=>[m[1],(m[2]||'').trim()]));
const attrs=source=>Object.fromEntries([...source.matchAll(/([\w-]+)="([^"]*)"/g)].map(m=>[m[1],m[2]]));
const modules=atdf.match(/<modules>([\s\S]*?)<\/modules>/)[1],registers=[],fuseFields={};
for(const module of modules.matchAll(/<module\s+([^>]+)>([\s\S]*?)<\/module>/g)){
  const owner=attrs(module[1]).name;
  for(const register of module[2].matchAll(/<register\s+([^>]*?)(?:\/>|>([\s\S]*?)<\/register>)/g)){
    const record=attrs(register[1]),fields=[...(register[2]||'').matchAll(/<bitfield\s+([^>]+)\/>/g)].map(m=>attrs(m[1]));
    if(owner==='FUSE'){
      for(const field of fields)fuseFields[record.name+'_'+field.name]=Number(field.mask);
    }else if(owner!=='LOCKBIT')registers.push({...record,owner,offset:Number(record.offset),size:Number(record.size),fields});
  }
}
const fuseMacros={};
for(const [byte,part] of [['LOW',header.split('/* Low Fuse Byte */')[1].split('/* High Fuse Byte */')[0]],
  ['HIGH',header.split('/* High Fuse Byte */')[1].split('/* Lock Bits */')[0]]]){
  for(const match of part.matchAll(/#define\s+(FUSE_(\w+))\s+\(unsigned char\)~_BV\(([0-7])\)/g)){
    const name=byte+'_'+match[2],mask=1<<Number(match[3]);
    if(Object.hasOwn(fuseFields,name))assert.equal(fuseFields[name],mask,'C/ATDF fuse '+name);
    fuseFields[name]=mask;fuseMacros[name]=match[1];
  }
}
const byName=new Map();
for(const register of registers){
  if(byName.has(register.name))assert.equal(byName.get(register.name).offset,register.offset,'ATDF duplicate register offset');
  byName.set(register.name,register);
}
const io={},data={},width={},bits={},vectors={};
for(const [name,value] of macros){
  const m=value.match(/^_SFR_IO(8|16)\((0x[\da-f]+)\)$/i);
  if(m){io[name]=Number(m[2]);width[name]=Number(m[1])/8;}
}
const offsets=new Set(Object.entries(io).filter(([name])=>byName.has(name)).map(([name,value])=>byName.get(name).offset-value));
assert.equal(offsets.size,1,'I/O/data offset must agree across every matched C/ATDF register');
const ioDataOffset=[...offsets][0];assert.equal(ioDataOffset,32);
for(const name of ['SPL','SREG']){
  const entry=byName.get(name);assert.ok(entry,'Missing ATDF CPU '+name);
  const asm=assembler.match(new RegExp('^\\.equ\\s+'+name+'\\s*=\\s*(0x[\\da-f]+)','mi'));assert.ok(asm,'Missing assembler '+name);
  io[name]=entry.offset-ioDataOffset;width[name]=entry.size;assert.equal(io[name],Number(asm[1]),name+' ATDF/assembler disagreement');
}
for(const [name,value] of Object.entries(io)){
  data[name]=value+ioDataOffset;
  if(byName.has(name))assert.equal(data[name],byName.get(name).offset,name+' C/ATDF disagreement');
}
// Associated single-bit macros before the vector section, plus aliases EEPE/EEMPE.
const bitSource=header.split('/* Registers and associated bit numbers. */')[1].split('/* Interrupt vectors */')[0];
for(const m of bitSource.matchAll(/^#define\s+(\w+)\s+([0-7])\s*$/gm))bits[m[1]]=Number(m[2]);
for(const [name,value] of macros)if(/^[A-Z]\w*$/.test(name)&&Object.hasOwn(bits,value))bits[name]=bits[value];
const sregMasks=Object.fromEntries(byName.get('SREG').fields.map(field=>[field.name,Number(field.mask)]));
for(const [name,mask] of Object.entries(sregMasks))bits['SREG_'+name]=Math.log2(mask);
const masks=Object.fromEntries(Object.entries(bits).map(([name,bit])=>[name,1<<bit]));
for(const [name,value] of macros)if(name.endsWith('_vect_num'))vectors[name.slice(0,-9)]=Number(value);
for(const match of atdf.matchAll(/<interrupt\s+([^>]+)\/>/g)){
  const interrupt=attrs(match[1]);
  if(interrupt.name==='RESET')vectors.RESET=Number(interrupt.index);
  else assert.equal(vectors[interrupt.name],Number(interrupt.index),'C/ATDF vector '+interrupt.name);
}
const segments=[...atdf.matchAll(/<memory-segment\s+([^>]+)\/>/g)].map(m=>attrs(m[1]));
const segment=name=>{const found=segments.find(item=>item.name===name);assert.ok(found,'Missing ATDF '+name);return found;};
const flash=segment('FLASH'),ram=segment('IRAM'),eeprom=segment('EEPROM');
const constants={IO_DATA_OFFSET:ioDataOffset,FLASH_BYTES:Number(flash.size),FLASH_PAGE_BYTES:Number(flash.pagesize),
  EEPROM_BYTES:Number(eeprom.size),EEPROM_PAGE_BYTES:Number(eeprom.pagesize),RAM_BYTES:Number(ram.size),
  RAM_START:Number(ram.start),RAM_END:Number(ram.start)+Number(ram.size)-1,
  FUSE_LOW_DEFAULT:0,FUSE_HIGH_DEFAULT:0,VECTOR_BYTES:Number(macros.get('_VECTOR_SIZE')),
  SLEEP_MODE_IDLE:0,SLEEP_MODE_ADC:0,SLEEP_MODE_PWR_DOWN:0};
for(const match of modules.matchAll(/<register\s+name="(LOW|HIGH)"[^>]*initval="([^"]+)"/g))constants['FUSE_'+match[1]+'_DEFAULT']=Number(match[2]);
for(const name of ['SLEEP_MODE_IDLE','SLEEP_MODE_ADC','SLEEP_MODE_PWR_DOWN']){
  const match=macros.get(name).match(/^\((0x[\da-f]+)<<([0-7])\)$/i);assert.ok(match,name+' expression');constants[name]=Number(match[1])<<Number(match[2]);
}
const rawConstants={FLASH_BYTES:'(FLASHEND + 1)',FLASH_PAGE_BYTES:'SPM_PAGESIZE',EEPROM_BYTES:'(E2END + 1)',
  EEPROM_PAGE_BYTES:'E2PAGESIZE',RAM_BYTES:'RAMSIZE',RAM_START:'RAMSTART',RAM_END:'RAMEND',
  FUSE_LOW_DEFAULT:'LFUSE_DEFAULT',FUSE_HIGH_DEFAULT:'HFUSE_DEFAULT',VECTOR_BYTES:'_VECTOR_SIZE',
  SLEEP_MODE_IDLE:'SLEEP_MODE_IDLE',SLEEP_MODE_ADC:'SLEEP_MODE_ADC',SLEEP_MODE_PWR_DOWN:'SLEEP_MODE_PWR_DOWN'};
const memory={RAMSTART:constants.RAM_START,RAMSIZE:constants.RAM_BYTES,RAMEND:constants.RAM_END,
  FLASHEND:constants.FLASH_BYTES-1,SPM_PAGESIZE:constants.FLASH_PAGE_BYTES,
  E2END:constants.EEPROM_BYTES-1,E2PAGESIZE:constants.EEPROM_PAGE_BYTES};
const sorted=object=>Object.entries(object).sort(([a],[b])=>a.localeCompare(b,'en'));
const hex=n=>'0x'+n.toString(16);
let c='/* Generated by scripts/generate-attiny13a-registers.mjs; do not edit. */\n';
c+='/* Included only by the numeric host adapter, while vendor macros exist. */\n';
c+='enum {\n';
for(const [name,value] of sorted(io))c+=` AT13_IO_${name} = ${['SPL','SREG'].includes(name)?hex(value):name},\n`;
for(const [name,value] of sorted(data))c+=` AT13_DATA_${name} = AT13_IO_${name} + ${hex(ioDataOffset)},\n`;
for(const [name,value] of sorted(width))c+=` AT13_WIDTH_${name} = ${value},\n`;
for(const [name,value] of sorted(bits))c+=` AT13_BIT_${name} = ${name.startsWith('SREG_')?value:name},\n AT13_MASK_${name} = (1u << AT13_BIT_${name}),\n`;
for(const [name,value] of sorted(vectors))c+=` AT13_VECTOR_${name} = ${name==='RESET'?value:name+'_vect_num'},\n`;
for(const [name,value] of sorted(constants))c+=` AT13_${name} = ${rawConstants[name]||hex(value)},\n`;
for(const [name,value] of sorted(fuseFields))c+=` AT13_FUSE_${name}_MASK = ${fuseMacros[name]?'((unsigned char)~'+fuseMacros[name]+')':hex(value)},\n`;
for(const [name] of sorted(memory))c+=` AT13_MEMORY_${name} = ${name},\n`;
c+='};\n';
for(const [name,value] of sorted(constants))c+=`AT13_DEFINITION_ASSERT(AT13_${name} == ${hex(value)}, "C header/ATDF ${name}");\n`;
for(const [name,value] of sorted(memory))c+=`AT13_DEFINITION_ASSERT(AT13_MEMORY_${name} == ${hex(value)}, "C header/ATDF memory ${name}");\n`;
for(const name of [...macros.keys()].sort())c+=`#undef ${name}\n`;
const maps={AT13_IO:io,AT13_DATA:data,AT13_WIDTH:width,AT13_BIT:bits,AT13_MASK:masks,AT13_VECTOR:vectors,
  AT13_CONST:constants,AT13_FUSE_MASK:fuseFields,AT13_MEMORY:memory};
let js='// Generated by scripts/generate-attiny13a-registers.mjs; do not edit.\n';
js+='// Source: Microchip.ATtiny_DFP.3.4.278; see vendor provenance/licenses.\n';
for(const [name,map] of Object.entries(maps))js+=`export const ${name}=Object.freeze(${JSON.stringify(Object.fromEntries(sorted(map)),null,2)});\n`;
let asm='/* Generated by scripts/generate-attiny13a-registers.mjs; do not edit. */\n';
asm+='/* Numeric AVR I/O offsets, original bit positions and memory constants. */\n';
for(const [name,value] of sorted({...io,...bits,...memory}))asm+=`.set ${name},${hex(value)}\n`;
for(const [name,value] of sorted(vectors))asm+=`.set ${name}_vect_num,${value}\n`;
asm+=`.set AT13_IO_DATA_OFFSET,${hex(ioDataOffset)}\n`;
const json=JSON.stringify({schema:'micromusic-attiny13a-register-map-v1',
  manufacturerPackage:provenance.package,version:provenance.version,
  packageSha256:provenance.packageSha256,maps},null,2)+'\n';
const outputs={'web-player/native/attiny13a-registers.generated.h':c,
  'web-player/lib/attiny13a-registers.js':js,'web-player/lib/attiny13a-registers.json':json,
  'web-player/native/attiny13a-registers.generated.inc':asm};
assert.ok(process.argv.slice(2).every(arg=>arg==='--check'),'Only --check is accepted');
for(const [path,content] of Object.entries(outputs)){
  if(process.argv.includes('--check'))assert.equal(text(path).replaceAll('\r\n','\n'),content,'Stale generated '+path);
  else writeFileSync(resolve(root,path),content);
}
console.log(`Official ATtiny13A definitions ${process.argv.includes('--check')?'verified':'generated'}: ${Object.keys(io).length} register aliases, ${Object.keys(bits).length} bit names, ${Object.keys(vectors).length} vectors`);
