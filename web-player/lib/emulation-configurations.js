// Model selection is independent of the JS/WASM CPU execution backend.
// This module must remain loadable without WebAssembly.
export const DEFAULT_EMULATION_CONFIGURATION='site';
export const EMULATION_CONFIGURATIONS=Object.freeze({
  site:Object.freeze({id:'site',label:'Для сайта',description:'Упрощённая модель музыки и PWM.'}),
  verification:Object.freeze({id:'verification',label:'Для проверок',description:'Полная доступная модель, без пропуска ожиданий.'}),
});
export function emulationConfiguration(id=DEFAULT_EMULATION_CONFIGURATION){
  if(typeof id!=='string'||!Object.hasOwn(EMULATION_CONFIGURATIONS,id))throw Error('Unknown emulation configuration: '+id);
  return EMULATION_CONFIGURATIONS[id];
}
export function executionOptions(id){
  emulationConfiguration(id);
  return id==='verification'
    ? {fastIdle:false,fastBlocks:false,optimizeFlags:false,maxBlockInstructions:2,boundedRegions:false,optimizePhaseLocals:false,sramBlocks:false}
    : {fastIdle:true,fastBlocks:true};
}
// Catalog playback has a nominal oscillator, not a measured silicon curve.
// Only the selected factory CAL point is known; unknown OSCCAL writes must fail
// rather than silently inventing a frequency. Tests can supply measured profiles
// directly to ATtiny13A with executionOptions('verification').
export function nominalVerificationDeviceOptions(cpuHz=9600000){
  const osccalHz=Array(128).fill(0);osccalHz[0]=cpuHz;
  return {oscillatorHz:cpuHz,osccalHz,factoryOsccal96:0,resumable:true,
    fuseLow:0x7a,fuseStartupProfile:1,nvmClockProfile:1,nvmCalibrationReferenceHz:cpuHz,
    ...executionOptions('verification')};
}
