import {coreProbeCases} from './avr-core-probe-cases.mjs';

// A decoder compares observations; it cannot certify the debugger/tool origin.
export function decodeAttiny13aOracle(record,descriptor,{captureKind='unverified-debugger'}={}){
  if(!['synthetic-emulator','unverified-debugger'].includes(captureKind))throw Error('Unverified source kind');
  if(descriptor?.schema!=='micromusic-attiny13a-studio-control-v1'||descriptor.device!=='ATtiny13A')throw Error('Wrong oracle descriptor');
  if(!(record instanceof Uint8Array)||record.length!==12+coreProbeCases.length*4)throw Error('Wrong oracle record length');
  if(descriptor.recordBytes!==record.length||descriptor.cases?.length!==coreProbeCases.length||
    coreProbeCases.some((c,n)=>['id','result','sreg','cycles'].some(k=>c[k]!==descriptor.cases[n][k])))throw Error('Wrong stimulus catalog');
  if(String.fromCharCode(...record.subarray(0,4))!=='AV13')throw Error('Incomplete oracle record');
  if(!descriptor?.buildId||descriptor.buildId.length!==4||descriptor.buildId.some((b,n)=>b!==record[n+4]))throw Error('Oracle build mismatch');
  const delta=at=>(record[at+3]-record[at+2])&255;
  if(record[8]!==0||record[9]!==0)throw Error('Invalid empty control result');
  const overhead=delta(8);
  const cases=coreProbeCases.map((c,n)=>{
    const at=12+n*4,rawDelta=delta(at),cycles=(rawDelta-overhead)&255;
    return {id:c.id,result:record[at],sreg:record[at+1],rawDelta,cycles,
      expected:{result:c.result,sreg:c.sreg,cycles:c.cycles},
      passed:record[at]===c.result&&record[at+1]===c.sreg&&cycles===c.cycles};
  });
  return {schema:'micromusic-attiny13a-oracle-result-v1',captureKind,hostVerified:false,
    buildId:descriptor.buildId,overheadTicks:overhead,passed:cases.every(c=>c.passed),cases};
}
