// Ideal digital CLKI fixture; no electrical pulse qualification is implied.
export const CLKI_PHASE_POLICY='digital-noninverting-zero-seed-v1';
export function normalizeClkiProfile(value){
  if(value===null)return null;
  if(!value||typeof value!=='object'||Array.isArray(value)||
    ![Object.prototype,null].includes(Object.getPrototypeOf(value)))throw Error('Invalid clkiProfile fields');
  const fields=Object.keys(value).sort().join();
  if(fields!=='initialLevel,phasePolicy'&&fields!=='electricalValidation,initialLevel,phasePolicy')throw Error('Invalid clkiProfile fields');
  if(value.phasePolicy!==CLKI_PHASE_POLICY)throw Error('Invalid clkiProfile phasePolicy');
  if(value.initialLevel!==0&&value.initialLevel!==1)throw Error('Invalid clkiProfile initialLevel');
  const electricalValidation=Object.hasOwn(value,'electricalValidation')?value.electricalValidation:'none';
  if(!['none','datasheet-ideal-v1'].includes(electricalValidation))throw Error('Invalid clkiProfile electricalValidation');
  return {phasePolicy:CLKI_PHASE_POLICY,initialLevel:value.initialLevel,electricalValidation};
}
