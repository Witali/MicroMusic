// Explicit comparator timing fixture in elapsed physical time. These delays
// are supplied by the caller; no universal silicon calibration is implied.
export const COMPARATOR_TIMING_DOMAIN='physical-ns-v1';
export const comparatorTimingProfileFields=Object.freeze(['domain','propagationNs','bandgapStartupNs']);

export function normalizeComparatorTimingProfile(value){
  if(value===null)return null;
  if(!value||typeof value!=='object'||Array.isArray(value)||
    ![Object.prototype,null].includes(Object.getPrototypeOf(value)))throw Error('Invalid comparatorTimingProfile fields');
  const keys=Reflect.ownKeys(value);
  if(keys.length!==comparatorTimingProfileFields.length||keys.some(name=>
    typeof name!=='string'||!comparatorTimingProfileFields.includes(name)||
    !Object.getOwnPropertyDescriptor(value,name).enumerable||
    !Object.hasOwn(Object.getOwnPropertyDescriptor(value,name),'value')))
    throw Error('Invalid comparatorTimingProfile fields');
  if(value.domain!==COMPARATOR_TIMING_DOMAIN)throw Error('Invalid comparatorTimingProfile domain');
  const result={domain:COMPARATOR_TIMING_DOMAIN};
  for(const name of ['propagationNs','bandgapStartupNs']){
    const delay=value[name];
    if(!Number.isInteger(delay)||delay<0||delay>0xffffffff)throw Error('Invalid comparatorTimingProfile: '+name);
    result[name]=delay===0?0:delay;
  }
  return result;
}

export function validateComparatorTimingOptions(profile,options){
  if(profile===null)return;
  if(options.resumable!==true||(!options.osccalHz&&!options.clkiProfile))
    throw Error('comparatorTimingProfile requires resumable:true and a physical OSCCAL table or clkiProfile');
  if((options.comparatorPropagationHalf??0)!==0||(options.bandgapStartupHalf??0)!==0)
    throw Error('comparatorTimingProfile requires zero comparatorPropagationHalf and bandgapStartupHalf');
}
