#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
// Restricted hardware-style instruction emulator. ROM only, no RAM writes allowed.
static uint8_t rom[65536],r[8];
static uint16_t pc,sp;
static int zf,cf,inte;
static uint64_t cyc,insns;
static int halted;
static size_t nrom;
static uint8_t rd(uint16_t p){if(p>=nrom){fprintf(stderr,"ROM READ OUT OF RANGE %04X\n",p);exit(4);}return rom[p];}
static uint8_t fetch(void){uint8_t t=rd(pc);pc++;return t;}
static uint16_t fw(void){uint16_t a=fetch();return a+((uint16_t)fetch()<<8);}
static uint16_t hl(void){return ((uint16_t)r[4]<<8)|r[5];}
static void shl(uint16_t a){r[4]=(uint8_t)(a>>8);r[5]=(uint8_t)a;}
static uint8_t get(int x){if(x==6) return rd(hl());return r[x];}
static void set(int x,uint8_t v){if(x==6){fprintf(stderr,"ILLEGAL ROM WRITE PC=%04X\n",pc-1);exit(4);}r[x]=v;}
static void one(void){
  uint8_t op=fetch(); insns++;
  if(op==0xF3){inte=0;cyc+=4;}
  else if(op==0xFB){inte=1;cyc+=4;}
  else if(op==0x76){halted=1;cyc+=7;}
  else if(op==0x00){cyc+=4;}
  else if(op==0x01||op==0x11||op==0x21||op==0x31){int k=(op>>4)&3;uint16_t v=fw(); if(k==3)sp=v;else{r[2*k]=(uint8_t)(v>>8);r[2*k+1]=(uint8_t)v;}cyc+=10;}
  else if(op==0xC1||op==0xD1||op==0xE1){int k=(op>>4)&3;uint8_t lo=rd(sp);sp++;uint8_t hi=rd(sp);sp++;r[2*k]=hi;r[2*k+1]=lo;cyc+=10;}
  else if(op>=0x40&&op<=0x7F){int to=(op>>3)&7,from=op&7;set(to,get(from));cyc+=(from==6||to==6)?7:5;}
  else if(op==0xC2||op==0xD2||op==0xC3){uint16_t v=fw();if(op==0xC3||(op==0xC2&&!zf)||(op==0xD2&&!cf))pc=v;cyc+=10;}
  else if((op&0xC7)==0x06){int k=(op>>3)&7;set(k,fetch());cyc+=7;}
  else if(op>=0xA8&&op<=0xAF){r[7]^=get(op&7);zf=(r[7]==0);cf=0;cyc+=(op&7)==6?7:4;}
  else if(op>=0xB0&&op<=0xB7){r[7]|=get(op&7);zf=(r[7]==0);cf=0;cyc+=(op&7)==6?7:4;}
  else if(op==0xEE){r[7]^=fetch();zf=(r[7]==0);cf=0;cyc+=7;}
  else if(op==0xFE){uint8_t v=fetch();zf=(r[7]==v);cf=(r[7]<v);cyc+=7;}
  else if((op&0xC7)==0x05){int k=(op>>3)&7;uint8_t v=get(k)-1;set(k,v);zf=(v==0);cyc+=k==6?10:5;}
  else if((op&0xC7)==0x04){int k=(op>>3)&7;uint8_t v=get(k)+1;set(k,v);zf=(v==0);cyc+=k==6?10:5;}
  else if(op==0x09||op==0x19||op==0x29||op==0x39){int k=(op>>4)&3;uint32_t v=k==3?sp:((uint16_t)r[2*k]<<8)|r[2*k+1];uint32_t sum=hl()+v;shl((uint16_t)sum);cf=(sum>65535);cyc+=10;}
  else if(op==0x1F){uint8_t old=r[7];r[7]=(old>>1)|(cf<<7);cf=old&1;cyc+=4;}
  else if(op==0x17){uint8_t old=r[7];r[7]=(old<<1)|cf;cf=old>>7;cyc+=4;}
  else if(op==0x0F){uint8_t old=r[7];r[7]=(old>>1)|(old<<7);cf=old&1;cyc+=4;}
  else if(op==0xF9){sp=hl();cyc+=5;}
  else{fprintf(stderr,"UNKNOWN OPCODE %02X PC=%04X\n",op,pc-1);exit(4);}
}
static uint32_t crcraw(const uint8_t *d,size_t n){uint32_t c=0xffffffff;for(size_t i=0;i<n;i++){c^=d[i];for(int j=0;j<8;j++)c=(c>>1)^((c&1)?0x82f63b78U:0);}return c;}
int main(int argc,char**argv){
  if(argc<2){fprintf(stderr,"Usage: emulate8080 binary [flipped-bit-index] [max steps]\n");return 2;}
  FILE *f=fopen(argv[1],"rb");if(!f){perror("open");return 2;}
  nrom=fread(rom,1,sizeof rom,f);fclose(f);
  if(argc>=3){long b=atol(argv[2]);if(b<0||(size_t)b>=nrom*8){fprintf(stderr,"bad bit index %ld\n",b);return 2;}rom[b/8]^=1<<(b%8);}
  uint32_t expected=crcraw(rom,nrom);
  size_t MAX=argc>=4?strtoull(argv[3],NULL,10):25000000;
  while(!halted&&insns<MAX){one();if(inte&&strstr(argv[1],"_spin")!=NULL){halted=1;break;}if(inte&&pc>=nrom){fprintf(stderr,"EXCEEDED ROM PC\n");return 4;}}
  if(!halted){fprintf(stderr,"EXCEEDED INSTRUCTION LIMIT PC=%04X\n",pc);return 4;}
  printf("size=%zu CRCref=%08X INTE=%d SP=%04X CRCregs=%02X%02X%02X%02X cycles=%llu instr=%llu seconds_3.5MHz=%.6f\n",
    nrom,expected,inte,sp,r[0],r[1],r[2],r[3],(unsigned long long)cyc,(unsigned long long)insns,(double)cyc/3500000.);
  if(sp!=nrom||(expected==0)!=(inte==1)||(expected==0&&((r[0]|r[1]|r[2]|r[3])!=0))){fprintf(stderr,"ASSERTION FAIL\n");return 4;}
  return 0;
}
