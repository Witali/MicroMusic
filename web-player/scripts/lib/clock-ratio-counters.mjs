// Offline diagnostic instrumentation. Never used by production clock helpers.
import assert from 'node:assert/strict';

export const ratioSource='web-player/native/peripherals/device_clock.h';
export const ratioGroupFields=Object.freeze(['b','divisor','calls','minA','maxA','minCarry','maxCarry','zeroA','zeroCarry','a32','properCarry']);
export const ratioExports=Object.freeze(['mm_ratio_group_count','mm_ratio_value','mm_ratio_untracked']);
export const ratioHeader='void mm_ratio_observe(uint64_t a,uint64_t b,uint64_t carry,uint64_t divisor);\nvoid mm_ratio_reset(void);\n';
export const ratioSupport=`
typedef struct { uint64_t values[11]; } mm_ratio_group_t;
static mm_ratio_group_t mm_ratio_groups[32];
static uint32_t mm_ratio_length;
static uint64_t mm_ratio_dropped;
void mm_ratio_observe(uint64_t a,uint64_t b,uint64_t carry,uint64_t divisor) {
 uint32_t i=0;
 for(;i<mm_ratio_length;i++)if(mm_ratio_groups[i].values[0]==b&&mm_ratio_groups[i].values[1]==divisor)break;
 if(i==mm_ratio_length) {
  if(i==32) { ++mm_ratio_dropped; return; }
  ++mm_ratio_length;
  uint64_t *v=mm_ratio_groups[i].values;
  v[0]=b;v[1]=divisor;v[3]=v[4]=a;v[5]=v[6]=carry;
 }
 uint64_t *v=mm_ratio_groups[i].values;
 ++v[2];if(a<v[3])v[3]=a;if(a>v[4])v[4]=a;
 if(carry<v[5])v[5]=carry;if(carry>v[6])v[6]=carry;
 v[7]+=a==0;v[8]+=carry==0;v[9]+=a<=UINT32_MAX;v[10]+=divisor&&carry<divisor;
}
void mm_ratio_reset(void) {
 for(unsigned i=0;i<32;i++)for(unsigned j=0;j<11;j++)mm_ratio_groups[i].values[j]=0;
 mm_ratio_length=0;mm_ratio_dropped=0;
}
uint32_t mm_ratio_group_count(void) { return mm_ratio_length; }
uint64_t mm_ratio_value(uint32_t group,uint32_t field) {
 return group<mm_ratio_length&&field<11?mm_ratio_groups[group].values[field]:0;
}
uint64_t mm_ratio_untracked(void) { return mm_ratio_dropped; }
`;

export function instrumentClockRatio(source,register) {
  assert.equal(typeof source,'string');assert.equal(typeof register,'function');
  const once=(needle,replacement)=>{
    assert.equal(source.split(needle).length,2,'Clock-ratio instrumentation anchor differs');
    source=source.replace(needle,replacement);
  };
  const hit=name=>'MM_TRACE_HIT('+register('clock_ratio:'+name)+');';
  once('uint64_t divisor,uint64_t *quotient,uint64_t *remainder) {',
    'uint64_t divisor,uint64_t *quotient,uint64_t *remainder) { '+hit('entry')+' mm_ratio_observe(a,b,carry,divisor);');
  once('if (!divisor) return 0;','if (!divisor) { '+hit('zero-divisor')+' return 0; }');
  once('if (!b || a<=(UINT64_MAX-carry)/b) {','if (!b || a<=(UINT64_MAX-carry)/b) { '+hit('short'));
  once('unsigned shift=(unsigned)__builtin_ctzll(b|divisor);',hit('wide')+' unsigned shift=(unsigned)__builtin_ctzll(b|divisor);');
  once('if (tail<=(UINT64_MAX-carry)/b) {','if (tail<=(UINT64_MAX-carry)/b) { '+hit('decomposed'));
  once('if (whole>UINT64_MAX/b) return 0;','if (whole>UINT64_MAX/b) { '+hit('whole-overflow')+' return 0; }');
  once('if (extra>UINT64_MAX-q) return 0;','if (extra>UINT64_MAX-q) { '+hit('sum-overflow')+' return 0; }');
  once('*quotient=q+extra;',hit('decomposed-ok')+' *quotient=q+extra;');
  once('uint64_t a0=(uint32_t)a,',hit('long-division')+' uint64_t a0=(uint32_t)a,');
  once('if (high>=divisor) return 0;','if (high>=divisor) { '+hit('quotient-overflow')+' return 0; }');
  once('*quotient=q; *remainder=r*scale+carry_low;',hit('long-ok')+' *quotient=q; *remainder=r*scale+carry_low;');
  return source;
}

export function readClockRatioCounters(exports,counts) {
  const size=exports.mm_ratio_group_count();assert.ok(Number.isInteger(size)&&size>=0&&size<=32,'Invalid clock-ratio table size');
  const value=n=>BigInt.asUintN(64,n).toString();
  const groups=Array.from({length:size},(_,i)=>Object.fromEntries(ratioGroupFields.map((field,j)=>[field,value(exports.mm_ratio_value(i,j))])));
  const paths=Object.fromEntries(counts.filter(c=>c.name.startsWith('clock_ratio:')).map(c=>[c.name.slice(12),c.count]));
  const result={paths,groups,untracked:value(exports.mm_ratio_untracked()),capacity:32,
    meaning:'Actual source branch entries and bounded (b,divisor) operand groups; not native-call counts, exclusive time or a performance measurement.'};
  validateClockRatioCounters(result);return result;
}

export function validateClockRatioCounters(result) {
  const number=s=>{assert.ok(typeof s==='string'&&/^(0|[1-9][0-9]*)$/.test(s),'Invalid clock-ratio count');
    const n=BigInt(s);assert.ok(n<=0xffffffffffffffffn,'Clock-ratio count overflow');return n;};
  const p=result.paths,names=['entry','zero-divisor','short','wide','decomposed','whole-overflow','sum-overflow','decomposed-ok','long-division','quotient-overflow','long-ok'];
  assert.deepEqual(Object.keys(p).sort(),[...names].sort(),'Clock-ratio path inventory differs');
  const n=Object.fromEntries(names.map(k=>[k,number(p[k])]));
  assert.equal(n.entry,n['zero-divisor']+n.short+n.wide,'Clock-ratio entry partition differs');
  assert.equal(n.wide,n.decomposed+n['long-division'],'Clock-ratio wide partition differs');
  assert.equal(n.decomposed,n['whole-overflow']+n['sum-overflow']+n['decomposed-ok'],'Clock-ratio decomposed partition differs');
  assert.equal(n['long-division'],n['quotient-overflow']+n['long-ok'],'Clock-ratio long partition differs');
  assert.equal(result.capacity,32);assert.ok(Array.isArray(result.groups)&&result.groups.length<=32,'Invalid clock-ratio groups');
  let tracked=0n;const keys=new Set();
  for(const group of result.groups){
    assert.deepEqual(Object.keys(group).sort(),[...ratioGroupFields].sort(),'Clock-ratio operand inventory differs');
    const g=Object.fromEntries(ratioGroupFields.map(k=>[k,number(group[k])])),key=g.b+':'+g.divisor;
    assert.ok(!keys.has(key),'Duplicate clock-ratio group');keys.add(key);
    assert.ok(g.calls>0n&&g.minA<=g.maxA&&g.minCarry<=g.maxCarry,'Invalid clock-ratio bounds');
    for(const k of ['zeroA','zeroCarry','a32','properCarry'])assert.ok(g[k]<=g.calls,'Clock-ratio class exceeds group');
    if(!g.divisor)assert.equal(g.properCarry,0n);
    tracked+=g.calls;
  }
  assert.equal(tracked+number(result.untracked),n.entry,'Clock-ratio table budget differs');
}
