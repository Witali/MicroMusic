// Microchip ATmega328P device geometry, independent of the CPU backend.
// https://www.microchip.com/en-us/product/ATmega328P
export const ARDUINO_BOARD='arduino-16mhz';
export const ATMEGA328P_PROFILE=Object.freeze({
  id:'atmega328p',name:'ATmega328P',flashBytes:32768,sramBytes:2048,
  sramStart:256,ramEnd:2303,eepromBytes:1024,cpuHz:16000000,hardwareMultiply:true,
});
export function resolveATmega328PProfile(target,{cpuHz=16000000}={}){
  if(target!=='atmega328p'||cpuHz!==ATMEGA328P_PROFILE.cpuHz)
    throw Error('ATmega328P playback requires the 16 MHz target');
  return ATMEGA328P_PROFILE;
}
