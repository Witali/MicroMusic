// Explicit shared reference fixture. Startup is caller-supplied physical time;
// it is not a universal calibration of the ADC/comparator/BOD reference.
export const BANDGAP_PROFILE_DOMAIN='physical-ns-v1';
const fields=Object.freeze(['domain','startupNs']);

export function normalizeBandgapProfile(value){
  if(value===null)return null;
  if(!value||typeof value!=='object'||Array.isArray(value)||
    ![Object.prototype,null].includes(Object.getPrototypeOf(value)))throw Error('Invalid bandgapProfile fields');
  const keys=Reflect.ownKeys(value);
  if(keys.length!==fields.length||keys.some(name=>typeof name!=='string'||!fields.includes(name)||
    !Object.getOwnPropertyDescriptor(value,name).enumerable||
    !Object.hasOwn(Object.getOwnPropertyDescriptor(value,name),'value')))
    throw Error('Invalid bandgapProfile fields');
  if(value.domain!==BANDGAP_PROFILE_DOMAIN)throw Error('Invalid bandgapProfile domain');
  if(!Number.isInteger(value.startupNs)||value.startupNs<0||value.startupNs>0xffffffff)
    throw Error('Invalid bandgapProfile: startupNs');
  return {domain:BANDGAP_PROFILE_DOMAIN,startupNs:value.startupNs===0?0:value.startupNs};
}

export function validateBandgapOptions(profile,options){
  if(profile===null)return;
  if(options.resumable!==true||(!options.osccalHz&&!options.clkiProfile))
    throw Error('bandgapProfile requires resumable:true and a physical OSCCAL table or clkiProfile');
  if(!options.comparatorTimingProfile||options.comparatorTimingProfile.bandgapStartupNs!==0)
    throw Error('bandgapProfile requires comparatorTimingProfile with zero bandgapStartupNs');
  if((options.bandgapStartupHalf??0)!==0)throw Error('bandgapProfile requires zero bandgapStartupHalf');
}
