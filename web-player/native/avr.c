/* Configurable firmware-oriented AVR subset. No host calls during execution.
 * The JS reference and Microchip fixtures are the differential test oracles.
 * CPU time uses doubles, retaining exact integer cycles beyond 2^32.
 */
#include <stdint.h>
#include <stddef.h>
#include <math.h>

#define FIELDS(X) \
 X(pc) X(cyc) X(irqDelay) X(timer) X(overflowAt) X(timerDivisor) \
 X(prescalerAt) X(irqStart) X(irqCount) X(lost) X(maxIRQ) X(writes) \
 X(inIRQ) X(minSP) X(workLost) X(duty) X(fastIdle) X(fastBlocks) \
 X(idleCycles) X(blockInstructions) X(eempeUntil) X(clkprUntil) \
 X(frameCount) X(error) X(errorPC) X(dutyLeft) X(leftWrites) \
 X(timerTemp) X(wdtUntil) X(watchdogResetAt) X(watchdogResets)
#define FIELD_ENUM(n) S_##n,
enum { FIELDS(FIELD_ENUM) S_COUNT };
#define FIELD_NAME(n) #n,
static const char *const field_names[] = { FIELDS(FIELD_NAME) };
static double st[S_COUNT], frames[32];
/* Maximum supported geometry; each instance reserves two fixed WASM pages.
 * Numeric register descriptions come only from avr-profiles.js via the bridge. */
static uint8_t rom[8192], eeprom[64], data[768];
static uint8_t op[4096], dst[4096], src[4096], batch[4096], idle[4096];
static int32_t imm[4096];
enum { C_flashBytes, C_eepromBytes, C_sramStart, C_ramEnd, C_cpuHz,
 C_pointerMask, C_sreg, C_spl, C_sph, C_spHighMask, C_eecr, C_eedr, C_eear,
 C_clkpr, C_gtccr, C_prr, C_spmcsr, C_wdt, C_protectedWatchdog, C_mcusr,
 C_adc, C_acsr, C_ext0, C_extMask0, C_ext1, C_extMask1,
 C_a, C_b, C_c, C_counter, C_counterHigh, C_ocra, C_ocraHigh, C_ocrb,
 C_ocrbHigh, C_icr, C_icrHigh, C_timsk, C_tifr, C_vector, C_fastMode,
 C_normalTop, C_prrMask, C_overflowMask, C_flagMask, C_interruptRejectMask,
 C_interruptStoreMask, C_modeAMask, C_modeBMask, C_modeBShift,
 C_controlBMask, C_forceBMask, C_forceCMask, C_COUNT };
static int32_t config[C_COUNT];
#define C(n) config[C_##n]
static int words, pc_mask;
#define S(n) st[S_##n]
#define IO(n) data[32 + (n)]
#define FLAGS data[C(sreg)]
#define PENDING (data[C(tifr)] & C(overflowMask))
#define ERROR S(error)
#define SET_PENDING(v) (data[C(tifr)] = (data[C(tifr)] & ~C(overflowMask)) | ((v) ? C(overflowMask) : 0))
static int get_sp(void){return data[C(spl)] | (C(sph)<0?0:data[C(sph)]<<8);}
static void set_sp(int v){data[C(spl)]=v;if(C(sph)>=0)data[C(sph)]=(v>>8)&C(spHighMask);}
static int pointer(int s){return (data[s]|(data[s+1]<<8))&C(pointerMask);}
static void set_pointer(int s,int v){data[s]=v;if(C(pointerMask)>255)data[s+1]=v>>8;}

enum { NOP=1, CLI, SEI, RETI, RET, CALL, JUMP, BRANCH, SKIP, LDI, CPI,
 SUBI, ORI, ANDI, MOVW, ADD, ADC, SUB, AND, EOR, MOV, INC, DEC, COM,
 LSR, ASR, SWAP, IN, OUT, SBI, PUSH, POP, ST, LPM, FLAG, ROR, LDS, STS, OR, LD, CP, NEG, SBC, SBCI, ADIW, SBIW, WDR };
enum { E_PC=1, E_OPCODE, E_PUSH, E_POP, E_EXTCLK, E_WGM, E_FLASH, E_WDT,
 E_ADC, E_COMPARATOR, E_EXTIRQ, E_CLKDIV, E_COMPAREIRQ, E_EEPROM,
 E_FORCE, E_DATA, E_ST_ALIAS, E_WRITE, E_LD_ALIAS, E_READ, E_LPM_ALIAS,
 E_LPM, E_TIMEOUT, E_AUDIO, E_IO, E_WDT_ENABLED, E_WDT_EXPIRED };
static const char *const errors[] = { "", "PC out of Flash", "Unsupported opcode",
 "Stack overflow or invalid SPL", "Stack underflow or invalid SPL",
 "External Timer0 clock is not implemented", "Timer0 WGM mode is not implemented",
 "Flash programming/fuse access is not implemented", "Watchdog operation is not implemented",
 "ADC operation is not implemented", "Analog comparator interrupts are not implemented",
 "External/pin-change interrupts are not implemented", "Runtime CPU clock division is not implemented",
 "Timer0 compare interrupts are not implemented", "EEPROM programming/ready interrupt is not implemented",
 "Timer0 forced compare output is not implemented", "Data address out of range",
 "Undefined ST with source in updating pointer", "Data write out of range",
 "Undefined LD with destination in updating pointer", "Data read out of range",
 "Undefined LPM Z+ with destination in Z", "LPM out of Flash",
 "Firmware produced no PWM for one emulated second", "Invalid audio configuration",
 "I/O address out of range", "Enabled watchdog operation is not implemented",
 "Watchdog disable window expired with watchdog enabled" };
static int fail(int code) { ERROR = code; return 0; }
static int sign_extend(int v, int sign) { return v & sign ? v - sign * 2 : v; }
static int mode(void) {return (data[C(a)]&C(modeAMask))|((data[C(b)]&C(modeBMask))>>C(modeBShift));}
static int timer_top(void){return mode()==0?C(normalTop):255;}
static int timer_counter(void){return data[C(counter)]|(C(counterHigh)<0?0:data[C(counterHigh)]<<8);}
static int nzvs_flags(int flags, int value, int overflow) {
 int negative = value >> 7;
 return (flags & 0xe1) | ((value == 0) << 1) | (negative << 2) |
  (overflow << 3) | ((negative ^ overflow) << 4);
}
static void nzvs(int value,int overflow) {FLAGS=nzvs_flags(FLAGS,value,overflow);}
/* Return flags:value so both executors share exactly the same ALU. */
static int arithmetic_result(int flags,int x, int y, int carry, int subtract) {
 int total = subtract ? x - y - carry : x + y + carry, value = total & 255;
 int overflow = ((subtract ? x ^ y : ~(x ^ y)) & (x ^ value) & 128) >> 7;
 int negative = value >> 7;
 flags = (flags & 0xc0) | ((value == 0) << 1) | (negative << 2) |
  (overflow << 3) | ((negative ^ overflow) << 4) |
  (subtract ? total < 0 : total > 255) |
  ((subtract ? (x & 15) < (y & 15) + carry : (x & 15) + (y & 15) + carry > 15) << 5);
 return (flags<<8)|value;
}
static int arithmetic(int x,int y,int carry,int subtract) {
 int result=arithmetic_result(FLAGS,x,y,carry,subtract);FLAGS=result>>8;return result&255;
}
static int word_arithmetic(int flags,int x,int k,int subtract) {
 int total=subtract?x-k:x+k,value=total&65535,negative=value>>15;
 int overflow=((subtract?x&~value:~x&value)>>15)&1;
 flags=(flags&0xe0)|((negative^overflow)<<4)|(overflow<<3)|(negative<<2)|
  ((value==0)<<1)|(subtract?total<0:total>65535);
 return (flags<<16)|value;
}
static void decode_idle(int p) {
 idle[p] = 0;
 if (imm[p] == -1) {
  if (op[p] == JUMP) idle[p] = 1;
  if (op[p] == BRANCH && dst[p] == 6 && src[p] == 0) idle[p] = 2;
 }
 int sub=(p+1)&pc_mask, mask=(p+2)&pc_mask, cmp=(p+3)&pc_mask, branch=(p+4)&pc_mask, d=dst[p];
 if (op[p]==MOV && op[sub]==SUB && op[mask]==ANDI && op[cmp]==CPI &&
  op[branch]==BRANCH && dst[sub]==d && dst[mask]==d && dst[cmp]==d &&
  src[p]!=d && src[sub]!=d && dst[branch]==0 && src[branch]==0 && imm[branch]==-5) idle[p]=3;
}
static void decode(int p) {
 int w=rom[p*2] | (rom[p*2+1]<<8), o=0, d=(w>>4)&31, s=(w&15)|((w>>5)&16), k=0;
 if (w==0) o=NOP;
 else if (w==0x95a8 && C(protectedWatchdog)) o=WDR;
 else if (w==0x94f8) o=CLI;
 else if (w==0x9478) o=SEI;
 else if (w==0x9518) o=RETI;
 else if (w==0x9508) o=RET;
 else if ((w&0xff0f)==0x9408) {o=FLAG;d=(w>>4)&7;k=!(w&128);}
 else if ((w&0xf000)==0xd000) {o=CALL;k=sign_extend(w&4095,2048);}
 else if ((w&0xf000)==0xc000) {o=JUMP;k=sign_extend(w&4095,2048);}
 else if ((w&0xfc00)==0xf000 || (w&0xfc00)==0xf400) {o=BRANCH;d=w&7;s=(w&0xfc00)==0xf000;k=sign_extend((w>>3)&127,64);}
 else if ((w&0xfe08)==0xfc00 || (w&0xfe08)==0xfe00) {o=SKIP;s=w&7;k=(w&0xfe08)==0xfe00;}
 else if ((w&0xf000)==0xe000) {o=LDI;d=16+((w>>4)&15);k=(w&15)|((w>>4)&240);}
 else if ((w&0xf000)==0x3000 || (w&0xf000)==0x4000 || (w&0xf000)==0x5000 || (w&0xf000)==0x6000 || (w&0xf000)==0x7000) {
  o=(w&0xf000)==0x3000?CPI:(w&0xf000)==0x4000?SBCI:(w&0xf000)==0x5000?SUBI:(w&0xf000)==0x6000?ORI:ANDI;
  d=16+((w>>4)&15);k=(w&15)|((w>>4)&240);
 } else if ((w&0xff00)==0x9600 || (w&0xff00)==0x9700) {
  o=(w&0xff00)==0x9600?ADIW:SBIW;d=24+((w>>3)&6);k=(w&15)|((w>>2)&48);
 } else if ((w&0xff00)==0x0100) {o=MOVW;d=2*((w>>4)&15);s=2*(w&15);}
 else if ((w&0xfc00)==0x0c00) o=ADD;
 else if ((w&0xfc00)==0x1c00) o=ADC;
 else if ((w&0xfc00)==0x1800) o=SUB;
 else if ((w&0xfc00)==0x0800) o=SBC;
 else if ((w&0xfc00)==0x2000) o=AND;
 else if ((w&0xfc00)==0x2400) o=EOR;
 else if ((w&0xfc00)==0x2800) o=OR;
 else if ((w&0xfc00)==0x2c00) o=MOV;
 else if ((w&0xfc00)==0x1400) o=CP;
 else if ((w&0xfe0f)==0x9401) o=NEG;
 else if ((w&0xfe0f)==0x9403) o=INC;
 else if ((w&0xfe0f)==0x940a) o=DEC;
 else if ((w&0xfe0f)==0x9400) o=COM;
 else if ((w&0xfe0f)==0x9406) o=LSR;
 else if ((w&0xfe0f)==0x9405) o=ASR;
 else if ((w&0xfe0f)==0x9407) o=ROR;
 else if ((w&0xfe0f)==0x9402) o=SWAP;
 else if ((w&0xfe0f)==0x9000 || (w&0xfe0f)==0x9200) {o=(w&0xfe0f)==0x9000?LDS:STS;int n=((p+1)&pc_mask)*2;k=rom[n]|(rom[n+1]<<8);}
 else if ((w&0xf800)==0xb000) {o=IN;k=((w>>5)&48)|(w&15);}
 else if ((w&0xf800)==0xb800) {o=OUT;k=((w>>5)&48)|(w&15);}
 else if ((w&0xff00)==0x9a00) {o=SBI;d=(w>>3)&31;k=w&7;}
 else if ((w&0xfe0f)==0x920f) o=PUSH;
 else if ((w&0xfe0f)==0x900f) o=POP;
 else if ((w&0xfe0f)==0x900c || (w&0xfe0f)==0x900d || (w&0xfe0f)==0x900e ||
          (w&0xfe0f)==0x9009 || (w&0xfe0f)==0x900a || (w&0xfe0f)==0x9001 || (w&0xfe0f)==0x9002 ||
          (w&0xfe0f)==0x920c || (w&0xfe0f)==0x920d || (w&0xfe0f)==0x920e ||
          (w&0xfe0f)==0x9209 || (w&0xfe0f)==0x920a || (w&0xfe0f)==0x9201 || (w&0xfe0f)==0x9202) {
  int low=w&15;o=w&0x200?ST:LD;s=low>=12?26:low>=9?28:30;
  k=low==1||low==9||low==13?1:low==2||low==10||low==14?-1:2;
 }
 else if ((w&0xd200)==0x8000 || (w&0xd200)==0x8200) {
  o=w&0x200?ST:LD;s=w&8?28:30;k=2+((w&7)|((w>>7)&0x18)|((w>>8)&0x20));
 }
 else if ((w&0xfe0f)==0x9004 || (w&0xfe0f)==0x9005) {o=LPM;k=w&1;}
 op[p]=o;dst[p]=d;src[p]=s;imm[p]=k;
 batch[p] = (o==JUMP || o==BRANCH || o==LD || o==ST || o==ADIW || o==SBIW)?2:(o==SKIP || o==LPM)?3:
  (o==NOP || (o>=LDI && o<=SWAP) || o==ROR || o==OR || o==SBC || o==SBCI)?1:0;
 if((o==LD||o==ST)&&k!=1)batch[p]=0;
 for (int n=0;n<5;n++) decode_idle((p-n)&pc_mask);
}
static void push(int v) {
 int sp=get_sp();if(sp<C(sramStart)||sp>C(ramEnd)){fail(E_PUSH);return;}
 data[sp]=v;set_sp(sp-1);if(get_sp()<S(minSP))S(minSP)=get_sp();
}
static int pop(void){int sp=get_sp();if(sp<C(sramStart)-1||sp>=C(ramEnd))return fail(E_POP);set_sp(sp+1);return data[sp+1];}
static void push_pc(int v){push(v&255);if(!ERROR)push(v>>8);}
static int pop_pc(void){int hi=pop();if(ERROR)return 0;int lo=pop();return ((hi<<8)|lo)&pc_mask;}
static void update_timer(void) {
 static const int divisors[]={0,1,8,64,256,1024};
 int source=data[C(b)]&7,m=mode();
 if(source>=6){fail(E_EXTCLK);return;}
 if(source&&m!=0&&m!=C(fastMode)){fail(E_WGM);return;}
 S(timerDivisor)=divisors[source];
 S(timer)=divisors[source]&&!(data[C(prr)]&C(prrMask))&&(data[C(gtccr)]&0x81)!=0x81;
 if(!S(timer)){S(overflowAt)=INFINITY;return;}
 int top=timer_top(),target=m==0?0:top,ticks=(target-timer_counter())&top;
 if(!ticks)ticks=top+1;
 S(overflowAt)=S(prescalerAt)+(floor((S(cyc)-S(prescalerAt))/S(timerDivisor))+ticks)*S(timerDivisor);
}
static int read_data(int a){
 if(a<0||a>C(ramEnd))return fail(E_READ);
 if(C(counterHigh)>=0){
  if(a==C(counter)){S(timerTemp)=data[C(counterHigh)];return data[a];}
  if(a==C(counterHigh))return (int)S(timerTemp);
 }
 return data[a];
}
static int write_io(int io,int v) {
 int a=io+32;v&=255;
 if(a<32||a>=C(sramStart))return fail(E_IO);
 if(a==C(spmcsr)&&(v&31))return fail(E_FLASH);
 if(a==C(wdt)){
  if(C(protectedWatchdog)){
   if((v&0x18)==0x18&&((v^data[a])&0x27)==0){data[a]=v&0x7f;S(wdtUntil)=S(cyc)+4;return 0;}
   if(v==0&&!(data[C(mcusr)]&8)&&(!(data[a]&8)||S(wdtUntil)>S(cyc))){data[a]=0;S(wdtUntil)=0;return 0;}
   return fail(E_WDT_ENABLED);
  }
  if(v&0x58)return fail(E_WDT);
 }
 if(a==C(adc)&&(v&128))return fail(E_ADC);
 if(a==C(acsr)&&(v&8))return fail(E_COMPARATOR);
 if((a==C(ext0)&&(v&C(extMask0)))||(a==C(ext1)&&(v&C(extMask1))))return fail(E_EXTIRQ);
 if(a==C(clkpr)){
  if(v&128){if(v==128&&!(S(clkprUntil)>S(cyc))){data[a]=128;S(clkprUntil)=S(cyc)+4;}}
  else if(S(clkprUntil)>S(cyc)){if(v&15)return fail(E_CLKDIV);data[a]=0;S(clkprUntil)=0;}
  return 0;
 }
 if(a==C(tifr)){data[a]&=~(v&C(flagMask));return 0;}
 if(a==C(timsk)&&(v&C(interruptRejectMask)))return fail(E_COMPAREIRQ);
 if(a==C(eecr)){
  if(v&10)return fail(E_EEPROM);
  data[a]=v&0x3c;if(v&4)S(eempeUntil)=S(cyc)+4;
  if(v&1){data[C(eedr)]=eeprom[data[C(eear)]&(C(eepromBytes)-1)];return 4;}return 0;
 }
 if(a==C(eear))v&=C(eepromBytes)-1;
 if(a==C(timsk))v&=C(interruptStoreMask);
 if(a==C(b)){if(v&C(forceBMask))return fail(E_FORCE);v&=C(controlBMask);}
 if(a==C(c)){if(v&C(forceCMask))return fail(E_FORCE);v=0;}
 if(a==C(counterHigh)||a==C(ocraHigh)||a==C(ocrbHigh)||a==C(icrHigh)){S(timerTemp)=v;return 0;}
 if(C(counterHigh)>=0&&(a==C(counter)||a==C(ocra)||a==C(ocrb)||a==C(icr)))data[a+1]=(int)S(timerTemp);
 if(a==C(gtccr)){v&=0x81;if((v&1)||(data[a]&1))S(prescalerAt)=S(cyc);if(!(v&128))v&=~1;}
 data[a]=v;
 if(a==C(prr)||a==C(gtccr)||a==C(a)||a==C(counter)||a==C(b))update_timer();
 if(a==C(ocrb)&&S(timer)){S(duty)=v;S(writes)++;}
 if(a==C(ocra)&&S(timer)){S(dutyLeft)=v;S(leftWrites)++;}
 return 0;
}
static int write_data(int a,int v){
 if(a<0||a>C(ramEnd))return fail(E_WRITE);
 if(a>=32&&a<C(sramStart))return write_io(a-32,v);
 data[a]=v;return 0;
}
/* Keep the common timer path in the caller; Clang otherwise outlines it. */
static __attribute__((always_inline)) inline void clock_cycles(double n) {
 double before=S(cyc);S(cyc)+=n;
 if(S(eempeUntil)<=S(cyc))data[C(eecr)]&=~4;
 if(S(clkprUntil)<=S(cyc))data[C(clkpr)]&=~128;
 if(S(wdtUntil)&&S(wdtUntil)<=S(cyc)){
  data[C(wdt)]&=~16;S(wdtUntil)=0;
  if(data[C(wdt)]&0x48){fail(E_WDT_EXPIRED);return;}
 }
 int top=timer_top();
 if(S(timer)&&S(overflowAt)<=S(cyc)){
  double period=(top+1)*S(timerDivisor),events=1+floor((S(cyc)-S(overflowAt))/period);
  S(lost)+=events-!PENDING;SET_PENDING(1);S(overflowAt)+=events*period;
 }
 if(S(timer)){
  double ticks=S(timerDivisor)==1?n:floor((S(cyc)-S(prescalerAt))/S(timerDivisor))-floor((before-S(prescalerAt))/S(timerDivisor));
  int delta=ticks>=0&&ticks<2147483648.0?(int)ticks:(int)fmod(ticks,top+1);
  int count=(timer_counter()+(delta&top))&top;data[C(counter)]=count;
  if(C(counterHigh)>=0)data[C(counterHigh)]=count>>8;
 }
}
static void interrupt_cpu(void) {
 if(S(irqDelay)){S(irqDelay)--;return;}
 if(!(FLAGS&128)||!(data[C(timsk)]&C(overflowMask))||!PENDING)return;
 SET_PENDING(0);push_pc((int)S(pc));if(ERROR)return;S(pc)=C(vector);FLAGS&=127;
 S(irqStart)=S(cyc);frames[(int)S(frameCount)++]=S(irqStart);
 clock_cycles(4);if(ERROR)return;S(inIRQ)=1;S(irqCount)++;
}
/* Execute effects and return cycles not already consumed by I/O. */
static int execute(void) {
 int p=(int)S(pc);if(p<0||p>=words)return fail(E_PC);
 int d=dst[p],s=src[p],k=imm[p],n=1,v,z,o=op[p];
 S(errorPC)=p;S(pc)=(p+1)&pc_mask;
 switch(o){
 case NOP:break;
 case WDR:S(watchdogResetAt)=S(cyc)+1;S(watchdogResets)=isnan(S(watchdogResets))?1:S(watchdogResets)+1;break;
 case CLI:FLAGS&=127;break;
 case SEI:FLAGS|=128;S(irqDelay)=1;break;
 case FLAG:if(d==6&&k&&(FLAGS&64)&&S(inIRQ))S(workLost)++;FLAGS=(FLAGS&~(1<<d))|(k<<d);break;
 case RETI:
  v=pop_pc();if(ERROR)return 0;S(pc)=v;FLAGS|=128;S(irqDelay)=1;n=4;
  if(S(frameCount)>0){double at=frames[(int)--S(frameCount)];if(S(cyc)+n-at>S(maxIRQ))S(maxIRQ)=S(cyc)+n-at;}
  S(inIRQ)=S(frameCount)>0;S(irqStart)=S(inIRQ)?frames[(int)S(frameCount)-1]:0;break;
 case RET:v=pop_pc();if(ERROR)return 0;S(pc)=v;n=4;break;
 case CALL:push_pc((int)S(pc));if(ERROR)return 0;S(pc)+=k;n=3;break;
 case JUMP:S(pc)+=k;n=2;break;
 case BRANCH:if(((FLAGS>>d)&1)==s){S(pc)+=k;n=2;}break;
 case SKIP:if(((data[d]>>s)&1)==k){int next=(int)S(pc),w=rom[next*2]|(rom[next*2+1]<<8);int words=(w&0xfe0f)==0x9000||(w&0xfe0f)==0x9200||(w&0xfe0e)==0x940c||(w&0xfe0e)==0x940e?2:1;S(pc)+=words;n=1+words;}break;
 case LDI:data[d]=k;break;
 case CPI:arithmetic(data[d],k,0,1);break;
 case SUBI:data[d]=arithmetic(data[d],k,0,1);break;
 case ORI:data[d]|=k;nzvs(data[d],0);break;
 case ANDI:data[d]&=k;nzvs(data[d],0);break;
 case MOVW:data[d]=data[s];data[d+1]=data[s+1];break;
 case ADIW:case SBIW:
  v=word_arithmetic(FLAGS,data[d]|(data[d+1]<<8),k,o==SBIW);
  data[d]=v;data[d+1]=v>>8;FLAGS=v>>16;n=2;break;
 case ADD:data[d]=arithmetic(data[d],data[s],0,0);break;
 case ADC:data[d]=arithmetic(data[d],data[s],FLAGS&1,0);break;
 case SUB:data[d]=arithmetic(data[d],data[s],0,1);break;
 case SBC:case SBCI:{int previous=FLAGS;data[d]=arithmetic(data[d],o==SBC?data[s]:k,previous&1,1);if(!(previous&2))FLAGS&=~2;break;}
 case CP:arithmetic(data[d],data[s],0,1);break;
 case NEG:data[d]=arithmetic(0,data[d],0,1);break;
 case AND:data[d]&=data[s];nzvs(data[d],0);break;
 case EOR:data[d]^=data[s];nzvs(data[d],0);break;
 case OR:data[d]|=data[s];nzvs(data[d],0);break;
 case MOV:data[d]=data[s];break;
 case INC:data[d]++;nzvs(data[d],data[d]==128);break;
 case DEC:data[d]--;nzvs(data[d],data[d]==127);break;
 case COM:data[d]^=255;nzvs(data[d],0);FLAGS|=1;break;
 case LSR:v=data[d]&1;data[d]>>=1;FLAGS=(FLAGS&~1)|v;nzvs(data[d],v);break;
 case ROR:v=data[d];data[d]=(v>>1)|((FLAGS&1)<<7);FLAGS=(FLAGS&~1)|(v&1);nzvs(data[d],(data[d]>>7)^(FLAGS&1));break;
 case ASR:v=data[d]&1;data[d]=(data[d]>>1)|(data[d]&128);FLAGS=(FLAGS&~1)|v;nzvs(data[d],(data[d]>>7)^v);break;
 case SWAP:data[d]=((data[d]&15)<<4)|(data[d]>>4);break;
 case LDS:case STS:
  if(k<0||k>C(ramEnd))return fail(E_DATA);
  v=data[d];S(pc)=((int)S(pc)+1)&pc_mask;clock_cycles(2);if(ERROR)return 0;n=0;
  if(o==LDS)data[d]=read_data(k);else n=write_data(k,v);break;
 case IN:clock_cycles(1);if(ERROR)return 0;n=0;data[d]=read_data(k+32);break;
 case OUT:clock_cycles(1);if(ERROR)return 0;n=write_io(k,data[d]);break;
 case SBI:clock_cycles(2);if(ERROR)return 0;n=write_io(d,IO(d)|(1<<k));break;
 case PUSH:push(data[d]);n=2;break;
 case POP:v=pop();if(ERROR)return 0;data[d]=v;n=2;break;
 case ST:
  z=(pointer(s)+(k<0?-1:k>=2?k-2:0))&C(pointerMask);
  if(k<2&&(d==s||d==s+1))return fail(E_ST_ALIAS);if(z>C(ramEnd))return fail(E_WRITE);
  if(k<0)set_pointer(s,z);
  v=data[d];clock_cycles(2);if(ERROR)return 0;n=0;
  n=write_data(z,v);
  if(ERROR)return 0;if(k==1)set_pointer(s,(z+1)&C(pointerMask));break;
 case LD:
  z=(pointer(s)+(k<0?-1:k>=2?k-2:0))&C(pointerMask);
  if(k<2&&(d==s||d==s+1))return fail(E_LD_ALIAS);if(z>C(ramEnd))return fail(E_READ);
  if(k<0)set_pointer(s,z);
  clock_cycles(2);if(ERROR)return 0;n=0;data[d]=read_data(z);
  if(k==1)set_pointer(s,(z+1)&C(pointerMask));break;
 case LPM:
  if(k&&d>=30)return fail(E_LPM_ALIAS);z=data[30]|(data[31]<<8);if(z>=C(flashBytes))return fail(E_LPM);
  data[d]=rom[z];if(k){z++;data[30]=z&255;data[31]=z>>8;}n=3;break;
 default:return fail(E_OPCODE);
 }
 if(!ERROR)S(pc)=(int)S(pc)&pc_mask;return n;
}
static void step_cpu(void) {
 int n=execute();
 /* I/O instructions already advanced to their bus cycle. A positive return
  * still includes EEPROM stalls; the public avr_clock(0) remains observable. */
 if(!ERROR){if(n)clock_cycles(n);if(!ERROR)interrupt_cpu();}
}
static int skip_idle(void) {
 if(!S(timer)||!(FLAGS&128)||S(irqDelay)||PENDING||!(data[C(timsk)]&C(overflowMask)))return 0;
 int p=(int)S(pc),kind=idle[p];if(!kind)return 0;double n;
 if(kind==3){int v=(data[src[p]]-data[src[(p+1)&pc_mask]])&imm[(p+2)&pc_mask],limit=imm[(p+3)&pc_mask];
  if(v<limit)return 0;n=floor((S(overflowAt)-S(cyc)-1)/6)*6;if(n<=0)return 0;
  data[dst[p]]=v;arithmetic(v,limit,0,1);
 }else{if(kind==2&&(FLAGS&64))return 0;n=fmax(2,ceil((S(overflowAt)-S(cyc))/2)*2);}
 S(idleCycles)+=n;clock_cycles(n);if(!ERROR)interrupt_cpu();return 1;
}
static int run_block(double deadline) {
 if(S(irqDelay)||PENDING)return 0;
 double budget=64,remaining=S(overflowAt)-S(cyc)-1;
 if(remaining<budget)budget=remaining;
 remaining=deadline-S(cyc);if(remaining<budget)budget=remaining;
 int elapsed=0,count=0,p=(int)S(pc),flags=FLAGS;
 /* PC and SREG remain integers in locals until the event boundary. Register
  * and SRAM writes cannot alias SREG: I/O always takes the single-step path. */
 while(p>=0&&p<words&&batch[p]&&elapsed+batch[p]<=budget){
  int o=op[p],d=dst[p],s=src[p],k=imm[p],next=(p+1)&pc_mask,cycles=batch[p],x,v,z,result;
  switch(o){
  case NOP:break;
  case LDI:data[d]=k;break;
  case MOV:data[d]=data[s];break;
  case MOVW:data[d]=data[s];data[d+1]=data[s+1];break;
  case ADIW:case SBIW:
   result=word_arithmetic(flags,data[d]|(data[d+1]<<8),k,o==SBIW);
   data[d]=result;data[d+1]=result>>8;flags=result>>16;break;
  case ADD:case ADC:
   result=arithmetic_result(flags,data[d],data[s],o==ADC?flags&1:0,0);
   flags=result>>8;data[d]=result&255;break;
  case SUB:case CPI:case SUBI:
   result=arithmetic_result(flags,data[d],o==SUB?data[s]:k,0,1);
   flags=result>>8;if(o!=CPI)data[d]=result&255;break;
  case SBC:case SBCI:
   result=arithmetic_result(flags,data[d],o==SBC?data[s]:k,flags&1,1);
   if(!(flags&2))result&=~(2<<8);
   flags=result>>8;data[d]=result&255;break;
  case AND:data[d]&=data[s];flags=nzvs_flags(flags,data[d],0);break;
  case EOR:data[d]^=data[s];flags=nzvs_flags(flags,data[d],0);break;
  case OR:data[d]|=data[s];flags=nzvs_flags(flags,data[d],0);break;
  case ANDI:data[d]&=k;flags=nzvs_flags(flags,data[d],0);break;
  case ORI:data[d]|=k;flags=nzvs_flags(flags,data[d],0);break;
  case INC:data[d]++;flags=nzvs_flags(flags,data[d],data[d]==128);break;
  case DEC:data[d]--;flags=nzvs_flags(flags,data[d],data[d]==127);break;
  case COM:data[d]^=255;flags=nzvs_flags(flags,data[d],0)|1;break;
  case LSR:case ASR:case ROR:
   x=data[d];v=(x>>1)|(o==ASR?x&128:o==ROR?(flags&1)<<7:0);data[d]=v;
   flags=nzvs_flags((flags&~1)|(x&1),v,(v>>7)^(x&1));break;
  case SWAP:data[d]=((data[d]&15)<<4)|(data[d]>>4);break;
  case JUMP:next=(next+k)&pc_mask;break;
  case BRANCH:
   cycles=1;if(((flags>>d)&1)==s){next=(next+k)&pc_mask;cycles=2;}break;
  case SKIP:
   cycles=1;if(((data[d]>>s)&1)==k){
    int w=rom[next*2]|(rom[next*2+1]<<8);
    int words=(w&0xfe0f)==0x9000||(w&0xfe0f)==0x9200||(w&0xfe0e)==0x940c||(w&0xfe0e)==0x940e?2:1;
    next=(next+words)&pc_mask;cycles=1+words;
   }break;
  case LD:case ST:
   z=pointer(s);if(z<C(sramStart)||z>C(ramEnd)||d==s||d==s+1)goto done;
   if(o==LD)data[d]=data[z];else data[z]=data[d];
   set_pointer(s,(z+1)&C(pointerMask));break;
  case LPM:
   z=data[30]|(data[31]<<8);if(z>=C(flashBytes)||(k&&d>=30))goto done;
   data[d]=rom[z];if(k){z++;data[30]=z&255;data[31]=z>>8;}break;
  default:goto done;
  }
  p=next;elapsed+=cycles;count++;if(idle[p])break;
 }
done:
 if(!count)return 0;S(pc)=p;FLAGS=flags;clock_cycles(elapsed);if(ERROR)return 0;S(blockInstructions)+=count;return 1;
}
static int next_duty(void) {
 double before=S(writes),deadline=S(cyc)+C(cpuHz);
 while(S(writes)==before&&!ERROR){
  int p=(int)S(pc);
  if(!(S(fastIdle)&&p>=0&&p<words&&idle[p]&&skip_idle()) &&
     !(S(fastBlocks)&&p>=0&&p<words&&batch[p]&&run_block(deadline)))step_cpu();
  if(S(cyc)>deadline)fail(E_TIMEOUT);
 }return (int)S(duty);
}

/* PCM resampling and filtering share the CPU's WebAssembly instance. */
typedef struct {double b0,b1,b2,a1,a2,z1,z2;} Biquad;
static Biquad hp[2],lp[2];
static double sample_rate,ratio,phase,v0,v1,cutoff,target_cutoff,volume,target_volume,smoothing;
static int first_audio,filter_audio,audio_channels=1;
static float pcm[4096],raw[4096],scope[512];
static double average_pwm;
static void coefficients(Biquad *f,double hz,int highpass) {
 double w=6.283185307179586476925286766559*hz/sample_rate,c=cos(w),alpha=sin(w),a0=1+alpha;
 f->b0=(1+(highpass?c:-c))/(2*a0);f->b1=(highpass?-(1+c):1-c)/a0;f->b2=f->b0;
 f->a1=-2*c/a0;f->a2=(1-alpha)/a0;
}
static double filtered(Biquad *f,double x) {
 double y=f->b0*x+f->z1;f->z1=f->b1*x-f->a1*y+f->z2;f->z2=f->b2*x-f->a2*y;return y;
}
static void update_controls(void) {
 if(cutoff!=target_cutoff){cutoff=target_cutoff+(cutoff-target_cutoff)*smoothing;if(fabs(cutoff-target_cutoff)<1e-9)cutoff=target_cutoff;for(int ch=0;ch<audio_channels;ch++)coefficients(&lp[ch],cutoff,0);}
 volume=target_volume+(volume-target_volume)*smoothing;
}
static double process_sample(double x,int ch) {return filtered(&lp[ch],filtered(&hp[ch],x))*volume;}
static int next_stereo_duty(void) {
 double before=S(leftWrites);int right=next_duty();
 if(S(leftWrites)!=before+1)fail(E_AUDIO);
 return (int)S(dutyLeft)|(right<<8);
}
static int next_audio_value(void) {return audio_channels==2?next_stereo_duty():next_duty();}
void avr_audio_init(double rate,double pwm,double hz,double gain,int filters) {
 ERROR=0;if(!isfinite(rate)||rate<8000||rate>192000||!isfinite(pwm)||pwm<=0||!isfinite(hz)||hz<=0||!isfinite(gain)||gain<0||gain>1){fail(E_AUDIO);return;}
 sample_rate=rate;ratio=pwm/rate;phase=0;first_audio=1;filter_audio=filters;audio_channels=1;
 cutoff=target_cutoff=fmin(hz,rate*.45);volume=target_volume=gain;smoothing=exp(-1/(rate*.015));
 for(int ch=0;ch<2;ch++){hp[ch]=(Biquad){0};lp[ch]=(Biquad){0};coefficients(&hp[ch],35,1);coefficients(&lp[ch],cutoff,0);}
}
void avr_audio_channels(int channels) {ERROR=0;if(channels!=1&&channels!=2){fail(E_AUDIO);return;}audio_channels=channels;}
void avr_audio_controls(double hz,double gain) {
 ERROR=0;if(!isfinite(hz)||hz<=0||!isfinite(gain)||gain<0||gain>1){fail(E_AUDIO);return;}
 target_cutoff=fmin(hz,sample_rate*.45);target_volume=gain;
}
int avr_render(int count) {
 ERROR=0;if(count<1||count>4096/audio_channels||sample_rate==0)return fail(E_AUDIO);
 if(first_audio){v0=next_audio_value();v1=next_audio_value();first_audio=0;}
 double sum=0;
 for(int i=0;i<count&&!ERROR;i++){
  if(filter_audio)update_controls();
  for(int ch=0;ch<audio_channels;ch++){
   int at=i*audio_channels+ch;
   double a=audio_channels==2?((int)v0>>(ch*8))&255:v0,b=audio_channels==2?((int)v1>>(ch*8))&255:v1;
   double x=(a+(b-a)*phase-128)/128;raw[at]=(float)x;sum+=raw[at];
   pcm[at]=(float)(filter_audio?process_sample(raw[at],ch):x);
  }
  phase+=ratio;while(phase>=1&&!ERROR){phase--;v0=v1;v1=next_audio_value();}
 }
 average_pwm=128+128*sum/(count*audio_channels);
 for(int i=0;i<512;i++)scope[i]=raw[i*count/512*audio_channels];
 return ERROR?0:count;
}
int avr_filter(int count) {
 ERROR=0;if(count<1||count>4096||sample_rate==0)return fail(E_AUDIO);
 for(int i=0;i<count;i++){if(filter_audio)update_controls();pcm[i]=(float)(filter_audio?process_sample(raw[i],0):raw[i]);}
 return count;
}
double avr_average(void){return average_pwm;}

/* Small, stable ABI: memory views plus explicit execution and control calls. */
uintptr_t avr_layout(int item) {
 switch(item){case 0:return (uintptr_t)st;case 1:return S_COUNT;case 2:return (uintptr_t)rom;
 case 3:return (uintptr_t)eeprom;case 4:return (uintptr_t)data;case 5:return (uintptr_t)op;
 case 6:return (uintptr_t)dst;case 7:return (uintptr_t)src;case 8:return (uintptr_t)imm;
 case 9:return (uintptr_t)batch;case 10:return (uintptr_t)idle;case 11:return (uintptr_t)frames;
 case 12:return (uintptr_t)pcm;case 13:return (uintptr_t)raw;case 14:return (uintptr_t)scope;case 15:return (uintptr_t)config;case 16:return C_COUNT;default:return 0;}
}
const char *avr_field_name(int i){return i>=0&&i<S_COUNT?field_names[i]:"";}
const char *avr_error_message(void){int e=(int)ERROR;return e>0&&e<=E_WDT_EXPIRED?errors[e]:"";}
void avr_reset(int fast_idle,int fast_blocks) {
 for(int i=0;i<S_COUNT;i++)st[i]=0;for(int i=0;i<=C(ramEnd);i++)data[i]=0;
 words=C(flashBytes)/2;pc_mask=words-1;
 set_sp(C(ramEnd));S(minSP)=get_sp();S(overflowAt)=INFINITY;S(duty)=S(dutyLeft)=128;S(fastIdle)=fast_idle;S(fastBlocks)=fast_blocks;
 S(eempeUntil)=NAN;S(clkprUntil)=NAN;S(watchdogResetAt)=NAN;S(watchdogResets)=NAN;sample_rate=0;
 for(int p=0;p<words;p++)decode(p);for(int p=0;p<words;p++)decode_idle(p);
}
void avr_decode(int p){ERROR=0;if(p<0||p>=words){fail(E_PC);return;}decode(p);}
void avr_decode_idle(int p){ERROR=0;decode_idle(p&pc_mask);}
void avr_step(void){ERROR=0;step_cpu();}
int avr_next(void){ERROR=0;return next_duty();}
int avr_block(double deadline){ERROR=0;return run_block(deadline);}
int avr_idle(void){ERROR=0;return skip_idle();}
void avr_clock(double n){ERROR=0;clock_cycles(n);}
void avr_interrupt(void){ERROR=0;interrupt_cpu();}
int avr_write_io(int a,int v){ERROR=0;return write_io(a,v);}
void avr_update_timer(void){ERROR=0;update_timer();}
int avr_timer_mode(void){ERROR=0;return mode();}
void avr_push(int v){ERROR=0;push(v);}
int avr_pop(void){ERROR=0;return pop();}
void avr_push_pc(int v){ERROR=0;push_pc(v);}
int avr_pop_pc(void){ERROR=0;return pop_pc();}
void avr_nzvs(int value,int overflow){ERROR=0;nzvs(value,overflow);}
int avr_arithmetic(int x,int y,int carry,int subtract){ERROR=0;return arithmetic(x,y,carry,subtract);}

int avr_read_data(int a){ERROR=0;return read_data(a);}
int avr_write_data(int a,int v){ERROR=0;return write_data(a,v);}
int avr_timer_top(void){ERROR=0;return timer_top();}
int avr_timer_counter(void){ERROR=0;return timer_counter();}
