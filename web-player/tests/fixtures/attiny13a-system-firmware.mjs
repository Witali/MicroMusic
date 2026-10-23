// Source-only, hand-encoded AVR fixtures. No compiler or binary fixture files.
// Encodings/cycles: Microchip AVR instruction-set manual DS40002198A and
// ATtiny13A DS40002307A section21. Addresses below are I/O offsets/PC words.
export const IO = Object.freeze({
  ADCL:0x04, ADCH:0x05, ADCSRA:0x06, ADMUX:0x07, ACSR:0x08,
  DIDR0:0x14, PCMSK:0x15, PINB:0x16, DDRB:0x17, PORTB:0x18,
  WDTCR:0x21, CLKPR:0x26, MCUSR:0x34, MCUCR:0x35,
  GIFR:0x3a, GIMSK:0x3b, SPL:0x3d, SREG:0x3f,
});
const register = d => {
  if(!Number.isInteger(d)||d<0||d>31)throw new Error('Invalid fixture register');
  return d;
};
const io = a => {
  if(!Number.isInteger(a)||a<0||a>63)throw new Error('Invalid fixture I/O offset');
  return a;
};
export const avr = Object.freeze({
  nop:()=>[0x0000], cli:()=>[0x94f8], sei:()=>[0x9478],
  reti:()=>[0x9518], sleep:()=>[0x9588], wdr:()=>[0x95a8],
  ldi:(d,k)=>{
    if(register(d)<16||k<0||k>255)throw new Error('Invalid fixture LDI');
    return [0xe000|((d-16)<<4)|(k&15)|((k&240)<<4)];
  },
  in:(d,a)=>[0xb000|(register(d)<<4)|(io(a)&15)|((a&48)<<5)],
  out:(a,d)=>[0xb800|(register(d)<<4)|(io(a)&15)|((a&48)<<5)],
  sbi:(a,b)=>{
    if(io(a)>31||b<0||b>7)throw new Error('Invalid fixture SBI');
    return [0x9a00|(a<<3)|b];
  },
  cbi:(a,b)=>{
    if(io(a)>31||b<0||b>7)throw new Error('Invalid fixture CBI');
    return [0x9800|(a<<3)|b];
  },
  inc:d=>[0x9403|(register(d)<<4)],
  lds:(d,a)=>[0x9000|(register(d)<<4),a],
  sts:(a,d)=>[0x9200|(register(d)<<4),a],
  ldx:d=>[0x900c|(register(d)<<4)],
  stx:d=>[0x920c|(register(d)<<4)],
  rjmp:(from,to)=>[0xc000|((to-from-1)&0xfff)],
});

export function flash(...segments) {
  const image=new Uint8Array(1024).fill(0xff);
  const occupied=new Set();
  for(const {at=0,instructions} of segments) {
    const words=instructions.flat();
    for(let n=0;n<words.length;n++) {
      const word=at+n;
      if(word<0||word>=512||occupied.has(word))throw new Error('Overlapping/out-of-range fixture');
      occupied.add(word); image[2*word]=words[n]; image[2*word+1]=words[n]>>8;
    }
  }
  return image;
}

export function sequential(instructions) {
  const end=instructions.flat().length;
  return flash({instructions:[...instructions,avr.rjmp(end,end)]});
}

export function interruptFixture() {
  return flash(
    {instructions:[avr.rjmp(0,16)]},
    {at:1,instructions:[avr.rjmp(1,64),avr.rjmp(2,66)]},
    {at:16,instructions:[...Array.from({length:8},avr.nop),avr.sei(),avr.inc(16),avr.inc(17),avr.rjmp(27,27)]},
    {at:64,instructions:[avr.inc(20),avr.reti(),avr.inc(21),avr.reti()]},
  );
}

export function sleepFixture(mode,watchdogControl=0x40) {
  return flash(
    {instructions:[avr.rjmp(0,16)]},
    {at:8,instructions:[avr.rjmp(8,40)]},
    {at:16,instructions:[avr.ldi(16,watchdogControl),avr.out(IO.WDTCR,16),
      avr.ldi(16,0x20|(mode<<3)),avr.out(IO.MCUCR,16),avr.sei(),avr.sleep(),
      avr.inc(18),avr.cli(),avr.rjmp(24,24)]},
    {at:40,instructions:[avr.inc(20),avr.reti()]},
  );
}
