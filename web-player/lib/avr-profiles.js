// Register maps use DATA-space addresses (IN/OUT adds 0x20). These profiles
// describe the peripherals implemented by the music emulator, not every chip
// peripheral. Firmware must still fail explicitly on unsupported operations.
// Microchip ATtiny13A DS40002307A and ATtiny48/88 doc8008, register summaries:
// https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf
// https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf
const freezeAVRProfile = value => {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    for (const child of Object.values(value)) freezeAVRProfile(child);
    Object.freeze(value);
  }
  return value;
};

export const AVR_PROFILES = freezeAVRProfile({
  attiny13a: {
    id:'attiny13a', name:'ATtiny13A', flashBytes:1024, sramStart:0x60,
    ramEnd:0x9f, eepromBytes:64, cpuHz:9600000, pointerMask:255, strictEeprom:true,
    system:{sreg:0x5f,spl:0x5d,sph:null,spHighMask:0,eecr:0x3c,eedr:0x3d,
      eear:0x3e,clkpr:0x46,gtccr:0x48,prr:0x45,spmcsr:0x57,wdt:0x41,
      protectedWatchdog:false,mcusr:0x54,adc:0x26,acsr:0x28,
      externalInterrupts:[{address:0x5b,mask:0x60}]},
    timer:{name:'Timer0',a:0x4f,b:0x53,c:null,counter:0x52,counterHigh:null,
      ocra:0x56,ocraHigh:null,ocrb:0x49,ocrbHigh:null,icr:null,icrHigh:null,
      timsk:0x59,tifr:0x58,vector:3,fastMode:3,normalTop:255,prrMask:2,
      overflowMask:2,flagMask:14,interruptRejectMask:12,interruptStoreMask:14,
      modeAMask:3,modeBMask:8,modeBShift:1,controlBMask:15,forceBMask:192,
      forceCMask:0,channelA:'OC0A',channelB:'OC0B',
      interruptError:'Timer0 compare interrupts are not implemented'},
    eearHigh:null,
  },
  attiny88: {
    id:'attiny88',name:'ATtiny88',flashBytes:8192,sramStart:0x100,
    ramEnd:0x2ff,eepromBytes:64,cpuHz:8000000,pointerMask:65535,strictEeprom:false,
    system:{sreg:0x5f,spl:0x5d,sph:0x5e,spHighMask:3,eecr:0x3f,eedr:0x40,
      eear:0x41,clkpr:0x61,gtccr:0x43,prr:0x64,spmcsr:0x57,wdt:0x60,
      protectedWatchdog:true,mcusr:0x54,adc:0x7a,acsr:0x50,
      externalInterrupts:[{address:0x3d,mask:255},{address:0x68,mask:255}]},
    timer:{name:'Timer1',a:0x80,b:0x81,c:0x82,counter:0x84,counterHigh:0x85,
      ocra:0x88,ocraHigh:0x89,ocrb:0x8a,ocrbHigh:0x8b,icr:0x86,icrHigh:0x87,
      timsk:0x6f,tifr:0x36,vector:11,fastMode:5,normalTop:65535,prrMask:8,
      overflowMask:1,flagMask:0x27,interruptRejectMask:254,interruptStoreMask:1,
      modeAMask:3,modeBMask:24,modeBShift:1,controlBMask:0xdf,forceBMask:0,
      forceCMask:192,channelA:'OC1A',channelB:'OC1B',
      interruptError:'Timer1 non-overflow interrupts are not implemented'},
    eearHigh:null,
  },
});

// Clock selection reuses the chip register map. UM88 accepts integer F_CPU
// values in 75 kHz..12 MHz. The separate 16-MHz MH-ET LIVE model does not extend
// the manufacturer's rated clock limit or UM88 firmware's allowed range.
const boardClockProfiles = new Map();
export function resolveAVRProfile(target = 'attiny13a', {cpuHz} = {}) {
  const key = ({tiny13:'attiny13a',tiny13a:'attiny13a',attiny13:'attiny13a',
    tiny88:'attiny88'})[target] ?? target;
  const profile = Object.hasOwn(AVR_PROFILES,key) ? AVR_PROFILES[key] : undefined;
  if (!profile) throw new Error('Unsupported AVR target: ' + target);
  if (cpuHz === undefined || cpuHz === profile.cpuHz) return profile;
  const um88Clock=Number.isInteger(cpuHz)&&cpuHz>=75000&&cpuHz<=12000000;
  if (profile.id !== 'attiny88' || (!um88Clock && cpuHz !== 16000000))
    throw new Error('Unsupported AVR clock for ' + profile.name + ': ' + String(cpuHz));
  const clockKey = profile.id + ':' + cpuHz;
  if (!boardClockProfiles.has(clockKey))
    boardClockProfiles.set(clockKey,freezeAVRProfile({...profile,cpuHz}));
  return boardClockProfiles.get(clockKey);
}
