/*
 * Independent machine-code Intel 8080 emulator and two-CRC regression suite.
 * Same test vectors are run against 1-pass and 2-pass ROM scanners.
 * Build: cc -O3 -std=c11 -Wall -Wextra test_firmware.c -o test_firmware
 * Usage: ./test_firmware small76.bin fast80.bin unroll2.bin unroll4.bin unroll8.bin fused92.bin
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SZ 65536u
#define COMBINED_POLY 0x006209BBU
static uint8_t rom[SZ];
static uint32_t rng=0x13A60780U;
static uint8_t rand8(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return (uint8_t)(rng>>24);}
static void die(const char*msg){fprintf(stderr,"FAIL: %s\n",msg);exit(2);}
static uint16_t crc16(const uint8_t *src, uint16_t poly){
  uint16_t c=0;
  for(size_t i=0;i<SZ;i++){
    c^=(uint16_t)src[i]<<8;
    for(int j=0;j<8;j++)c=(uint16_t)((c<<1)^((c&0x8000U)?poly:0));
  }
  return c;
}
static uint32_t crc32prefix(const uint8_t *src){
  uint32_t c=0;
  for(size_t i=0;i<SZ-4;i++){
    c^=(uint32_t)src[i]<<24;
    for(int j=0;j<8;j++)c=(c<<1)^((c&0x80000000U)?COMBINED_POLY:0);
  }
  return c;
}
static void footer(void){
  uint32_t f=crc32prefix(rom);
  rom[SZ-4]=(uint8_t)(f>>24);rom[SZ-3]=(uint8_t)(f>>16);
  rom[SZ-2]=(uint8_t)(f>>8);rom[SZ-1]=(uint8_t)f;
  if(crc16(rom,0x25)||crc16(rom,0x47))die("footer does not close both residues");
}
static uint16_t rd16(uint16_t addr){return (uint16_t)rom[addr] | ((uint16_t)rom[(uint16_t)(addr+1)]<<8);}
static int loadfile(const char*path,uint8_t *dst){
  FILE*f=fopen(path,"rb");if(!f){perror(path);exit(2);}
  int n=(int)fread(dst,1,8192,f);
  if(!feof(f) && ferror(f)) die("fread");
  fclose(f);
  if(n<1||n>8192)die("input code length invalid");
  return n;
}
struct CPU { uint8_t r[8]; uint16_t pc,sp; uint32_t cycles,steps; unsigned reads,phys_reads,unique; int cy,z,inte; };
static struct CPU emulate(int trace,int reset_only){
  struct CPU c;memset(&c,0,sizeof(c));
  for(int i=0;i<8;i++)c.r[i]=rand8();
  c.sp=((uint16_t)rand8()<<8)|rand8(); c.cy=rand8()&1;c.z=rand8()&1;c.inte=reset_only?0:(rand8()&1);
  uint8_t visited[SZ]; if(trace)memset(visited,0,sizeof(visited));
  for(c.steps=0;c.steps<6000000;){
    uint16_t addr=c.pc;
    uint8_t op=rom[c.pc++];c.steps++;
    if(op==0x76){c.cycles+=7;return c;}
    if((op&0xc0)==0x40){if((op&7)==6 || ((op>>3)&7)==6)die("MOV M not allowed");
      c.r[(op>>3)&7]=c.r[op&7]; c.cycles+=5;continue;}
    if(op>=0xA8&&op<=0xAF){c.r[7]^=c.r[op&7];c.z=(c.r[7]==0);c.cy=0;c.cycles+=4;continue;}
    if(op>=0xB0&&op<=0xB7){c.r[7]|=c.r[op&7];c.z=(c.r[7]==0);c.cy=0;c.cycles+=4;continue;}
    switch(op){
    case 0xF3:c.inte=0;c.cycles+=4;break;
    case 0xFB:c.inte=1;c.cycles+=4;break;
    case 0xAF:c.r[7]=0;c.cy=0;c.z=1;c.cycles+=4;break;
    case 0x31:c.sp=rd16(c.pc);c.pc+=2;c.cycles+=10;break;
    case 0x26:c.r[4]=rom[c.pc++];c.cycles+=7;break;
    case 0xF1:{uint16_t a=(uint16_t)(c.sp+1);uint8_t flag=rom[c.sp];
      c.r[7]=rom[a];c.cy=flag&1;c.z=(flag&0x40)!=0;
      c.sp+=2;c.reads++;c.phys_reads+=2;
      if(trace){if(!visited[a]){visited[a]=1;c.unique++;}else die("repeat data address in single pass");}
      c.cycles+=10;break;}
    case 0x3B:c.sp--;c.cycles+=5;break;
    case 0x1A:{uint16_t a=((uint16_t)c.r[2]<<8)|c.r[3];c.r[7]=rom[a];
      c.reads++;c.phys_reads++;
      if(trace){ if(!visited[a]) {visited[a]=1;c.unique++;} }
      c.cycles+=7;break;}
    case 0x29:{uint32_t v=(((uint32_t)c.r[4]<<8)|c.r[5])*2;
      c.cy=v>65535; c.r[4]=(v>>8)&255;c.r[5]=v&255;c.cycles+=10;break;}
    case 0x39:{uint32_t v=(((uint32_t)c.r[4]<<8)|c.r[5])+c.sp;
      c.cy=v>65535;c.r[4]=(v>>8)&255;c.r[5]=v&255;c.cycles+=10;break;}
    case 0x13:{uint16_t v=(uint16_t)((c.r[2]<<8)|c.r[3]);v++;
      c.r[2]=(v>>8)&255;c.r[3]=v&255;c.cycles+=5;break;}
    case 0x14:case 0x1C:case 0x2C:{int i=(op>>3)&7;
      c.r[i]++;c.z=(c.r[i]==0);c.cycles+=5;break;}
    case 0x87:{uint16_t v=c.r[7]*2;
      c.r[7]=(uint8_t)v;c.z=(c.r[7]==0);c.cy=v>255;c.cycles+=4;break;}
    case 0x07:{uint8_t a=c.r[7];c.cy=!!(a&0x80);
      c.r[7]=(uint8_t)((a<<1)|(a>>7));c.cycles+=4;break;}
    case 0x0F:{uint8_t a=c.r[7];c.cy=!!(a&1);
      c.r[7]=(uint8_t)((a>>1)|(a<<7));c.cycles+=4;break;}
    case 0x1F:{uint8_t a=c.r[7];int prev=c.cy;c.cy=a&1;
      c.r[7]=(uint8_t)((a>>1)|(prev<<7));c.cycles+=4;break;}
    case 0xE6:c.r[7]&=rom[c.pc++];c.z=(c.r[7]==0);c.cy=0;c.cycles+=7;break;
    case 0xC2:case 0xD2:{uint16_t dst=rd16(c.pc);c.pc+=2;
      if((op==0xC2 && !c.z)||(op==0xD2 && !c.cy))c.pc=dst;
      c.cycles+=10;break;}
    default:{fprintf(stderr,"unsupported opcode=%02X at %04X\n",op,addr);exit(2);}
    }
  }
  die("machine didn't halt within instruction cap");return c;
}
static void flip(unsigned bit_from_beginning){
  rom[bit_from_beginning>>3] ^= (uint8_t)(0x80u>>(bit_from_beginning&7));
}
static unsigned ntests=0;
static void testcase(int fused, int reset_only, unsigned goodcycles){
  uint16_t c25=crc16(rom,0x25),c47=crc16(rom,0x47);
  struct CPU r=emulate(1, reset_only);
  if(r.inte!=(c25==0 && c47==0))die("PASS/FAIL mismatch");
  if(fused){
    if(r.reads!=SZ || r.phys_reads!=SZ*2||r.sp!=65535)die("single-pass memory traversal");
    if((uint16_t)((r.r[0]<<8)|r.r[1])!=c25 ||(uint16_t)((r.r[2]<<8)|r.r[3])!=c47)die("single-pass CRC mismatch");
  } else {
    unsigned expected=(c25? SZ : SZ*2);
    if(r.reads!=expected ||r.phys_reads!=expected)die("two-pass memory traversal");
    if((c25? (((uint16_t)r.r[4]<<8)|r.r[1])!=c25:
             (((uint16_t)r.r[4]<<8)|r.r[1])!=c47))die("two-pass CRC mismatch");
  }
  if(r.unique!=SZ)die("ROM addresses not all visited");
  if(!c25&&!c47 && goodcycles &&r.cycles!=goodcycles) {
    fprintf(stderr,"cycles: got %u expected %u\n",r.cycles,goodcycles);die("cycles mismatch");
  }
  ntests++;
}
static void set_rom(const uint8_t*code, int code_length,int mode){
  memset(rom,mode==1?0:255,SZ);
  memcpy(rom,code,code_length);
  if(mode>=2)for(int i=code_length;i<(int)SZ-4;i++)rom[i]=rand8();
  footer();
}
int main(int argc,char**argv){
  if(argc<2 || argc>20){fprintf(stderr,"Usage: %s firmware.bin [firmware.bin ...]\n",argv[0]);return 1;}
  uint8_t codes[19][8192];int lengths[19];
  for(int i=0;i<argc-1;i++)lengths[i]=loadfile(argv[i+1],codes[i]);
  for(int prof=0;prof<argc-1;prof++){
    int n=lengths[prof],fused=(n==92),reset_only=(n==72 || n==74),case_before=ntests; unsigned cycles=0;
    switch(n){case 72:cycles=20119625;break;case 73:cycles=20119629;break;
      case 74:cycles=18947647;break;case 75:cycles=18947651;break;
      case 92:cycles=19013201;break;case 120:cycles=18292291;break;
      case 210:cycles=17964611;break;case 390:cycles=17800771;break;
      default: die("unexpected binary length");}
    for(int mode=0;mode<4;mode++){
      set_rom(codes[prof],n,mode);
      testcase(fused,reset_only,cycles);
      /* Check both 16-bit CRC footer words and distinct ROM address boundaries. */
      const unsigned addresses[]={0x0100,0x01FF,0x0200,0x7FFF,0x8000,0xF000,0xFFFB,0xFFFC,0xFFFD,0xFFFE,0xFFFF};
      for(unsigned k=0;k<sizeof(addresses)/sizeof(addresses[0]);k++) {
        unsigned a=addresses[k],bit=(8*a+(rand8()&7));flip(bit);
        testcase(fused,reset_only,0);
        flip(bit);
      }
      for(int k=0;k<12;k++){
        unsigned a=(unsigned)n+((unsigned)rand8()<<8)+rand8();
        a=(unsigned)n+(a%(65532u-(unsigned)n));
        unsigned bit=8*a+(rand8()&7);
        flip(bit);testcase(fused,reset_only,0);flip(bit);
      }
      /* Double errors separated by individual polynomial periods. */
      for(int kind=0;kind<2;kind++){
        int sep=kind?21845:1023;
        unsigned b=100000;
        flip(b);flip(b+(unsigned)sep);
        if((crc16(rom,0x25)==0)==(crc16(rom,0x47)==0))die("one-CRC-only syndrome collision expected");
        testcase(fused,reset_only,0);
        flip(b);flip(b+(unsigned)sep);
      }
      /* Odd-parity (3-bit) errors must always fail. */
      for(int k=0;k<4;k++){
        unsigned base=100000u+(rand8()*80u), delta=128u+(rand8()*3u);
        flip(base);flip(base+delta);flip(base+delta+31u);
        testcase(fused,reset_only,0);
        flip(base);flip(base+delta);flip(base+delta+31u);
      }
      /* Deliberate 4-bit error polynomial divisible by G25*G47. */
      const unsigned witness[]={0,1065,1278,3920};
      for(unsigned k=0;k<4;k++)flip(400000u+3920u-witness[k]);
      if(crc16(rom,0x25)||crc16(rom,0x47))die("known undetected 4-bit witness");
      testcase(fused,reset_only,cycles);
      for(unsigned k=0;k<4;k++)flip(400000u+3920u-witness[k]);
    }
    printf("%s %d bytes PASS %u cases\n",argv[prof+1],n,ntests-case_before);
  }
  printf("PASS %u full ROM emulations\n",ntests);
  return 0;
}
