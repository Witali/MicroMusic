// Explicit per-chip RESET receiver fixture; no universal analog defaults.
export const resetInputProfileFields=Object.freeze([
  'assertThresholdPpm','releaseThresholdPpm','assertQualificationNs',
  'releaseQualificationNs','assertPropagationNs','releasePropagationNs',
]);

export function normalizeResetInputProfile(value){
  if(value===null)return null;
  if(!value||typeof value!=='object'||Array.isArray(value)||
    ![Object.prototype,null].includes(Object.getPrototypeOf(value))||
    Object.keys(value).sort().join()!==[...resetInputProfileFields].sort().join())
    throw Error('Invalid resetInputProfile fields');
  const result={};
  for(const name of resetInputProfileFields){
    const v=value[name],threshold=name.endsWith('Ppm');
    if(!Number.isInteger(v)||v<(threshold?200000:0)||v>(threshold?900000:0xffffffff))
      throw Error('Invalid resetInputProfile: '+name);
    result[name]=v;
  }
  if(result.assertThresholdPpm>=result.releaseThresholdPpm)
    throw Error('Invalid resetInputProfile threshold hysteresis');
  return result;
}
