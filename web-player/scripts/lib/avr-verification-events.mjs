// Acceptance tooling only. This tolerance never rounds or changes device time.
import {isDeepStrictEqual} from 'node:util';

export const VERIFICATION_EVENT_TOLERANCE_PS=10000n;
const uint64Max=0xffffffffffffffffn;
const check=(condition,message)=>{if(!condition)throw new Error(message);};
const plain=value=>value!==null&&typeof value==='object'&&
  (Object.getPrototypeOf(value)===Object.prototype||Object.getPrototypeOf(value)===null);

function structured(value,seen=new Set()){
  if(value===null||['string','boolean','bigint'].includes(typeof value))return true;
  if(typeof value==='number')return Number.isFinite(value)&&(!Number.isInteger(value)||Number.isSafeInteger(value));
  if(!Array.isArray(value)&&!plain(value)||seen.has(value))return false;
  seen.add(value);
  const keys=Reflect.ownKeys(value),array=Array.isArray(value);
  let valid=keys.every(key=>{
    if(array&&key==='length')return true;
    const descriptor=Object.getOwnPropertyDescriptor(value,key);
    return typeof key==='string'&&(!array||Number.isInteger(Number(key))&&String(Number(key))===key&&Number(key)>=0&&Number(key)<value.length)&&
      descriptor.enumerable&&Object.hasOwn(descriptor,'value')&&structured(descriptor.value,seen);
  });
  if(array)valid=valid&&keys.length===value.length+1;
  seen.delete(value);return valid;
}
function timestamp(value){
  check(typeof value==='bigint'||typeof value==='string'&&/^(?:0|[1-9]\d{0,19})$/.test(value),
    'Event timePs must be a bigint or canonical unsigned decimal string');
  const time=BigInt(value);check(time>=0n&&time<=uint64Max,'Event timePs is outside uint64');return time;
}
function trace(events){
  check(Array.isArray(events),'Verification event trace must be an array');
  const length=Object.getOwnPropertyDescriptor(events,'length').value;
  check(Reflect.ownKeys(events).length===length+1,'Malformed verification trace array');
  const entries=[];
  for(let ordinal=0;ordinal<length;ordinal++){
    const descriptor=Object.getOwnPropertyDescriptor(events,String(ordinal));
    check(descriptor&&descriptor.enumerable&&Object.hasOwn(descriptor,'value'),'Malformed verification trace array');
    entries.push(descriptor.value);
  }
  const result=[];let previous=0n;
  for(let ordinal=0;ordinal<entries.length;ordinal++){
    const event=entries[ordinal];
    check(plain(event)&&structured(event)&&Object.hasOwn(event,'timePs'),'Malformed verification event metadata');
    const time=timestamp(event.timePs);check(!ordinal||time>=previous,'Verification event times must be nondecreasing');previous=time;
    const state=Object.fromEntries(Object.entries(event).filter(([key])=>key!=='timePs'));
    result.push({time,state});
  }
  return result;
}

export function compareVerificationEvents(reference,actual,options){
  check(plain(options)&&structured(options)&&Reflect.ownKeys(options).length===2&&
    Object.hasOwn(options,'configuration')&&Object.hasOwn(options,'device')&&
    options.configuration==='verification'&&options.device==='attiny13a',
    'Event comparison requires the ATtiny13A verification configuration');
  const expected=trace(reference),observed=trace(actual);
  check(expected.length===observed.length,'Verification event count differs');
  let maxErrorPs=0n;
  for(let ordinal=0;ordinal<expected.length;ordinal++){
    const a=expected[ordinal],b=observed[ordinal];
    check(isDeepStrictEqual(a.state,b.state),'Verification event state/order differs at ordinal '+ordinal);
    const difference=a.time>b.time?a.time-b.time:b.time-a.time;
    check(difference<=VERIFICATION_EVENT_TOLERANCE_PS,'Verification event time exceeds 10 ns at ordinal '+ordinal);
    if(difference>maxErrorPs)maxErrorPs=difference;
  }
  return {eventCount:expected.length,maxErrorPs,tolerancePs:VERIFICATION_EVENT_TOLERANCE_PS};
}
