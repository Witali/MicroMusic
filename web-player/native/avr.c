/* ATtiny13A firmware-oriented AVR subset. No host calls during execution.
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
 X(frameCount) X(error) X(errorPC) X(dutyLeft) X(leftWrites)
#define FIELD_ENUM(n) S_##n,
enum { FIELDS(FIELD_ENUM) S_COUNT };
#define FIELD_NAME(n) #n,
static const char *const field_names[] = { FIELDS(FIELD_NAME) };
static double st[S_COUNT], frames[32];
static uint8_t rom[1024], eeprom[64], data[160];
static uint8_t op[512], dst[512], src[512], batch[512], idle[512];
static int16_t imm[512];
#define S(n) st[S_##n]
#define IO(n) data[32 + (n)]
#define FLAGS IO(0x3f)
#define SP IO(0x3d)
#define PENDING (IO(0x38) & 2)
#define ERROR S(error)
#define SET_PENDING(v) (IO(0x38) = (IO(0x38) & ~2) | ((v) ? 2 : 0))
enum { NOP=1, CLI, SEI, RETI, RET, CALL, JUMP, BRANCH, SKIP, LDI, CPI,
 SUBI, ORI, ANDI, MOVW, ADD, ADC, SUB, AND, EOR, MOV, INC, DEC, COM,
 LSR, ASR, SWAP, IN, OUT, SBI, PUSH, POP, ST, LPM, FLAG, ROR, LDS, STS, OR, LD, CP, NEG };
enum { E_PC=1, E_OPCODE, E_PUSH, E_POP, E_EXTCLK, E_WGM, E_FLASH, E_WDT,
 E_ADC, E_COMPARATOR, E_EXTIRQ, E_CLKDIV, E_COMPAREIRQ, E_EEPROM,
 E_FORCE, E_DATA, E_ST_ALIAS, E_WRITE, E_LD_ALIAS, E_READ, E_LPM_ALIAS,
 E_LPM, E_TIMEOUT, E_AUDIO };
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
 "Firmware produced no PWM for one emulated second", "Invalid audio configuration" };
static int fail(int code) { ERROR = code; return 0; }
static int sign_extend(int v, int sign) { return v & sign ? v - sign * 2 : v; }
static int mode(void) { return (IO(0x2f) & 3) | ((IO(0x33) & 8) >> 1); }
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
static void decode_idle(int p) {
 idle[p] = 0;
 if (imm[p] == -1) {
  if (op[p] == JUMP) idle[p] = 1;
  if (op[p] == BRANCH && dst[p] == 6 && src[p] == 0) idle[p] = 2;
 }
 int sub=(p+1)&511, mask=(p+2)&511, cmp=(p+3)&511, branch=(p+4)&511, d=dst[p];
 if (op[p]==MOV && op[sub]==SUB && op[mask]==ANDI && op[cmp]==CPI &&
  op[branch]==BRANCH && dst[sub]==d && dst[mask]==d && dst[cmp]==d &&
  src[p]!=d && src[sub]!=d && dst[branch]==0 && src[branch]==0 && imm[branch]==-5) idle[p]=3;
}
static void decode(int p) {
 int w=rom[p*2] | (rom[p*2+1]<<8), o=0, d=(w>>4)&31, s=(w&15)|((w>>5)&16), k=0;
 if (w==0) o=NOP;
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
 else if ((w&0xf000)==0x3000 || (w&0xf000)==0x5000 || (w&0xf000)==0x6000 || (w&0xf000)==0x7000) {
  o=(w&0xf000)==0x3000?CPI:(w&0xf000)==0x5000?SUBI:(w&0xf000)==0x6000?ORI:ANDI;
  d=16+((w>>4)&15);k=(w&15)|((w>>4)&240);
 } else if ((w&0xff00)==0x0100) {o=MOVW;d=2*((w>>4)&15);s=2*(w&15);}
 else if ((w&0xfc00)==0x0c00) o=ADD;
 else if ((w&0xfc00)==0x1c00) o=ADC;
 else if ((w&0xfc00)==0x1800) o=SUB;
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
 else if ((w&0xfe0f)==0x9000 || (w&0xfe0f)==0x9200) {o=(w&0xfe0f)==0x9000?LDS:STS;int n=((p+1)&511)*2;k=rom[n]|(rom[n+1]<<8);}
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
 batch[p] = (o==JUMP || o==BRANCH || o==LD || o==ST)?2:(o==SKIP || o==LPM)?3:
  (o==NOP || (o>=LDI && o<=SWAP) || o==ROR || o==OR)?1:0;
 if((o==LD||o==ST)&&k!=1)batch[p]=0;
 for (int n=0;n<5;n++) decode_idle((p-n)&511);
}
static void push(int v) {
 if (SP<0x60 || SP>0x9f) {fail(E_PUSH);return;}
 data[SP--]=v;if (SP<S(minSP)) S(minSP)=SP;
}
static int pop(void) {if (SP<0x5f || SP>=0x9f) return fail(E_POP);return data[++SP];}
static void push_pc(int v) {push(v&255);if(!ERROR)push(v>>8);}
static int pop_pc(void) {int hi=pop();if(ERROR)return 0;int lo=pop();return ((hi<<8)|lo)&511;}
static void update_timer(void) {
 static const int divisors[]={0,1,8,64,256,1024};
 int source=IO(0x33)&7,m=mode();
 if(source>=6){fail(E_EXTCLK);return;}
 if(source && m!=0 && m!=3){fail(E_WGM);return;}
 S(timerDivisor)=divisors[source];
 S(timer)=divisors[source] && !(IO(0x25)&2) && (IO(0x28)&0x81)!=0x81;
 if(!S(timer)){S(overflowAt)=INFINITY;return;}
 int target=m==3?255:0,ticks=(target-IO(0x32))&255;if(!ticks)ticks=256;
 S(overflowAt)=S(prescalerAt)+(floor((S(cyc)-S(prescalerAt))/S(timerDivisor))+ticks)*S(timerDivisor);
}
static int write_io(int a,int v) {
 v&=255;
 if(a==0x37 && (v&31)) return fail(E_FLASH);
 if(a==0x21 && (v&0x58)) return fail(E_WDT);
 if(a==0x06 && (v&128)) return fail(E_ADC);
 if(a==0x08 && (v&8)) return fail(E_COMPARATOR);
 if(a==0x3b && (v&0x60)) return fail(E_EXTIRQ);
 if(a==0x26){
  if(v&128){if(v==128 && !(S(clkprUntil)>S(cyc))){IO(a)=128;S(clkprUntil)=S(cyc)+4;}}
  else if(S(clkprUntil)>S(cyc)){if(v&15)return fail(E_CLKDIV);IO(a)=0;S(clkprUntil)=0;}
  return 0;
 }
 if(a==0x38){IO(a)&=~(v&14);return 0;}
 if(a==0x39 && (v&12)) return fail(E_COMPAREIRQ);
 if(a==0x1c){
  if(v&10)return fail(E_EEPROM);
  IO(a)=v&0x3c;if(v&4)S(eempeUntil)=S(cyc)+4;
  if(v&1){IO(0x1d)=eeprom[IO(0x1e)&63];return 4;}return 0;
 }
 if(a==0x1e)v&=63;
 if(a==0x39)v&=14;
 if(a==0x33){if(v&0xc0)return fail(E_FORCE);v&=15;}
 if(a==0x28){v&=0x81;if((v&1)||(IO(a)&1))S(prescalerAt)=S(cyc);if(!(v&128))v&=~1;}
 IO(a)=v;
 if(a==0x25||a==0x28||a==0x2f||a==0x32||a==0x33)update_timer();
 if(a==0x29 && S(timer)){S(duty)=v;S(writes)++;}
 if(a==0x2a && S(timer)){S(dutyLeft)=v;S(leftWrites)++;}
 return 0;
}
static void clock_cycles(double n) {
 double before=S(cyc);S(cyc)+=n;
 if(S(eempeUntil)<=S(cyc))IO(0x1c)&=~4;
 if(S(clkprUntil)<=S(cyc))IO(0x26)&=~128;
 if(S(timer) && S(overflowAt)<=S(cyc)){
  double events=1+floor((S(cyc)-S(overflowAt))/(256*S(timerDivisor)));
  S(lost)+=events-!PENDING;SET_PENDING(1);S(overflowAt)+=events*256*S(timerDivisor);
 }
 if(S(timer)){
  double ticks=S(timerDivisor)==1?n:floor((S(cyc)-S(prescalerAt))/S(timerDivisor))-floor((before-S(prescalerAt))/S(timerDivisor));
  int delta=ticks>=0&&ticks<2147483648.0?(int)ticks:(int)fmod(ticks,256);
  IO(0x32)=(IO(0x32)+(delta&255))&255;
 }
}
static void interrupt_cpu(void) {
 if(S(irqDelay)){S(irqDelay)--;return;}
 if(!(FLAGS&128)||!(IO(0x39)&2)||!PENDING)return;
 SET_PENDING(0);push_pc((int)S(pc));if(ERROR)return;S(pc)=3;FLAGS&=127;
 S(irqStart)=S(cyc);frames[(int)S(frameCount)++]=S(irqStart);
 clock_cycles(4);S(inIRQ)=1;S(irqCount)++;
}
/* Execute effects and return cycles not already consumed by I/O. */
static int execute(void) {
 int p=(int)S(pc);if(p<0||p>=512)return fail(E_PC);
 int d=dst[p],s=src[p],k=imm[p],n=1,v,z,o=op[p];
 S(errorPC)=p;S(pc)=(p+1)&511;
 switch(o){
 case NOP:break;
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
 case ADD:data[d]=arithmetic(data[d],data[s],0,0);break;
 case ADC:data[d]=arithmetic(data[d],data[s],FLAGS&1,0);break;
 case SUB:data[d]=arithmetic(data[d],data[s],0,1);break;
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
  if(k<0||k>=160)return fail(E_DATA);
  v=data[d];S(pc)=((int)S(pc)+1)&511;clock_cycles(2);n=0;
  if(o==LDS)data[d]=data[k];else if(k>=32&&k<96)n=write_io(k-32,v);else data[k]=v;break;
 case IN:clock_cycles(1);n=0;data[d]=IO(k);break;
 case OUT:clock_cycles(1);n=write_io(k,data[d]);break;
 case SBI:clock_cycles(2);n=write_io(d,IO(d)|(1<<k));break;
 case PUSH:push(data[d]);n=2;break;
 case POP:v=pop();if(ERROR)return 0;data[d]=v;n=2;break;
 case ST:
  z=(data[s]+(k<0?-1:k>=2?k-2:0))&255;
  if(k<2&&(d==s||d==s+1))return fail(E_ST_ALIAS);if(z>=160)return fail(E_WRITE);
  if(k<0)data[s]=z;
  v=data[d];clock_cycles(2);n=0;
  if(z>=32&&z<96)n=write_io(z-32,v);else data[z]=v;
  if(ERROR)return 0;if(k==1)data[s]=(z+1)&255;break;
 case LD:
  z=(data[s]+(k<0?-1:k>=2?k-2:0))&255;
  if(k<2&&(d==s||d==s+1))return fail(E_LD_ALIAS);if(z>=160)return fail(E_READ);
  if(k<0)data[s]=z;
  clock_cycles(2);n=0;data[d]=data[z];
  if(k==1)data[s]=(z+1)&255;break;
 case LPM:
  if(k&&d>=30)return fail(E_LPM_ALIAS);z=data[30]|(data[31]<<8);if(z>=1024)return fail(E_LPM);
  data[d]=rom[z];if(k){z++;data[30]=z&255;data[31]=z>>8;}n=3;break;
 default:return fail(E_OPCODE);
 }
 if(!ERROR)S(pc)=(int)S(pc)&511;return n;
}
static void step_cpu(void) {int n=execute();if(!ERROR){clock_cycles(n);interrupt_cpu();}}
static int skip_idle(void) {
 if(!S(timer)||!(FLAGS&128)||S(irqDelay)||PENDING||!(IO(0x39)&2))return 0;
 int p=(int)S(pc),kind=idle[p];if(!kind)return 0;double n;
 if(kind==3){int v=(data[src[p]]-data[src[(p+1)&511]])&imm[(p+2)&511],limit=imm[(p+3)&511];
  if(v<limit)return 0;n=floor((S(overflowAt)-S(cyc)-1)/6)*6;if(n<=0)return 0;
  data[dst[p]]=v;arithmetic(v,limit,0,1);
 }else{if(kind==2&&(FLAGS&64))return 0;n=fmax(2,ceil((S(overflowAt)-S(cyc))/2)*2);}
 S(idleCycles)+=n;clock_cycles(n);interrupt_cpu();return 1;
}
static int run_block(double deadline) {
 if(S(irqDelay)||PENDING)return 0;
 double budget=fmin(64,fmin(S(overflowAt)-S(cyc)-1,deadline-S(cyc)));
 int elapsed=0,count=0,p=(int)S(pc),flags=FLAGS;
 /* PC and SREG remain integers in locals until the event boundary. Register
  * and SRAM writes cannot alias SREG: I/O always takes the single-step path. */
 while(p>=0&&p<512&&batch[p]&&elapsed+batch[p]<=budget){
  int o=op[p],d=dst[p],s=src[p],k=imm[p],next=(p+1)&511,cycles=batch[p],x,v,z,result;
  switch(o){
  case NOP:break;
  case LDI:data[d]=k;break;
  case MOV:data[d]=data[s];break;
  case MOVW:data[d]=data[s];data[d+1]=data[s+1];break;
  case ADD:case ADC:case SUB:case CPI:case SUBI:
   result=arithmetic_result(flags,data[d],o==CPI||o==SUBI?k:data[s],o==ADC?flags&1:0,o!=ADD&&o!=ADC);
   flags=result>>8;if(o!=CPI)data[d]=result&255;break;
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
  case JUMP:next=(next+k)&511;break;
  case BRANCH:
   cycles=1;if(((flags>>d)&1)==s){next=(next+k)&511;cycles=2;}break;
  case SKIP:
   cycles=1;if(((data[d]>>s)&1)==k){
    int w=rom[next*2]|(rom[next*2+1]<<8);
    int words=(w&0xfe0f)==0x9000||(w&0xfe0f)==0x9200||(w&0xfe0e)==0x940c||(w&0xfe0e)==0x940e?2:1;
    next=(next+words)&511;cycles=1+words;
   }break;
  case LD:case ST:
   z=data[s];if(z<96||z>=160||d==s||d==s+1)goto done;
   if(o==LD)data[d]=data[z];else data[z]=data[d];
   data[s]=(z+1)&255;break;
  case LPM:
   z=data[30]|(data[31]<<8);if(z>=1024||(k&&d>=30))goto done;
   data[d]=rom[z];if(k){z++;data[30]=z&255;data[31]=z>>8;}break;
  default:goto done;
  }
  p=next;elapsed+=cycles;count++;if(idle[p])break;
 }
done:
 if(!count)return 0;S(pc)=p;FLAGS=flags;clock_cycles(elapsed);S(blockInstructions)+=count;return 1;
}
static int next_duty(void) {
 double before=S(writes),deadline=S(cyc)+9600000;
 while(S(writes)==before&&!ERROR){
  int p=(int)S(pc);
  if(!(S(fastIdle)&&p>=0&&p<512&&idle[p]&&skip_idle()) &&
     !(S(fastBlocks)&&p>=0&&p<512&&batch[p]&&run_block(deadline)))step_cpu();
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
 case 12:return (uintptr_t)pcm;case 13:return (uintptr_t)raw;case 14:return (uintptr_t)scope;default:return 0;}
}
const char *avr_field_name(int i){return i>=0&&i<S_COUNT?field_names[i]:"";}
const char *avr_error_message(void){int e=(int)ERROR;return e>0&&e<=E_AUDIO?errors[e]:"";}
void avr_reset(int fast_idle,int fast_blocks) {
 for(int i=0;i<S_COUNT;i++)st[i]=0;for(int i=0;i<160;i++)data[i]=0;
 SP=0x9f;S(minSP)=SP;S(overflowAt)=INFINITY;S(duty)=S(dutyLeft)=128;S(fastIdle)=fast_idle;S(fastBlocks)=fast_blocks;
 S(eempeUntil)=NAN;S(clkprUntil)=NAN;sample_rate=0;
 for(int p=0;p<512;p++)decode(p);for(int p=0;p<512;p++)decode_idle(p);
}
void avr_decode(int p){ERROR=0;if(p<0||p>=512){fail(E_PC);return;}decode(p);}
void avr_decode_idle(int p){ERROR=0;decode_idle(p&511);}
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
