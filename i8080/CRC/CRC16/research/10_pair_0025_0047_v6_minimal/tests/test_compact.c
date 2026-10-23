/* Standalone Intel 8080 machine-code test for shared dual CRC-16. CC0/public domain.
   Build: cc -std=c11 -O2 -Wall -Wextra tests/test_compact.c -o test_compact
   Run : ./test_compact bin/bitwise_shared.bin
*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#define N 65536
static uint8_t rom[N];
static uint32_t rng=0xDADA8080;
static uint32_t rnd(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static void fail(const char *s){fprintf(stderr,"FAIL: %s\n",s);exit(2);}
static uint16_t crc16(const uint8_t *p,unsigned count,uint16_t poly){
  uint16_t c=0;
  for(unsigned i=0;i<count;i++){
    c^=(uint16_t)p[i]<<8;
    for(int j=0;j<8;j++)c=(uint16_t)((c<<1)^((c&0x8000)?poly:0));
  }
  return c;
}
static uint32_t crc32(const uint8_t *p,unsigned count){
  uint32_t c=0;
  for(unsigned i=0;i<count;i++){
    c^=(uint32_t)p[i]<<24;
    for(int j=0;j<8;j++)c=(c<<1)^((c&0x80000000U)?0x006209BBU:0);
  }
  return c;
}
static void patch(void){
  uint32_t r=crc32(rom,N-4);
  for(int i=0;i<4;i++)rom[N-4+i]=(uint8_t)(r>>(24-i*8));
  if(crc16(rom,N,0x25)!=0||crc16(rom,N,0x47)!=0)fail("ROM footer");
}
typedef struct {uint8_t r[8];uint16_t pc;unsigned reads;uint32_t cycles,steps;int inte;uint16_t result;} State;
static State execute(int reset_only,int trace){
  State s={0};
  uint8_t visited[N]={0};
  int carry=(int)(rnd()&1),z=(int)(rnd()&1),parity=(int)(rnd()&1);
  for(int i=0;i<8;i++)s.r[i]=(uint8_t)rnd();
  s.inte=reset_only?0:(int)(rnd()&1);
  for(unsigned k=0;k<12500000;k++){
    uint16_t pc=s.pc;uint8_t op=rom[s.pc++];s.steps++;
    if(op>=0x40 && op<0x80 && op!=0x76){
      uint8_t dst=(op>>3)&7,src=op&7;
      if(src==6||dst==6)fail("MOV memory not supported");
      s.r[dst]=s.r[src];s.cycles+=5;continue;
    }
    if(op>=0xA8&&op<=0xAF){s.r[7]^=s.r[op&7];carry=0;z=s.r[7]==0;parity=(!__builtin_parity((unsigned)s.r[7]));s.cycles+=4;continue;}
    if(op>=0xB0&&op<=0xB7){s.r[7]|=s.r[op&7];carry=0;z=s.r[7]==0;parity=(!__builtin_parity((unsigned)s.r[7]));s.cycles+=4;continue;}
    if(op>=0xA0&&op<=0xA7){s.r[7]&=s.r[op&7];carry=0;z=s.r[7]==0;parity=(!__builtin_parity((unsigned)s.r[7]));s.cycles+=4;continue;}
    if(op>=0x98&&op<=0x9F){unsigned c=s.r[op&7]+(unsigned)carry;unsigned a=s.r[7];s.r[7]=(uint8_t)(a-c);carry=a<c;z=s.r[7]==0;parity=(!__builtin_parity((unsigned)s.r[7]));s.cycles+=4;continue;}
    switch(op){
    case 0xF3:s.inte=0;s.cycles+=4;break;
    case 0xFB:s.inte=1;s.cycles+=4;break;
    case 0x76:s.cycles+=7;s.result=(uint16_t)((s.r[4]<<8)|s.r[5]);if(trace){unsigned expected=(s.reads==N*2?2:1);if(s.reads!=N*2&&s.reads!=N)fail("Incorrect ROM read count");for(int j=0;j<N;j++)if(visited[j]!=expected)fail("Incorrect address coverage");}return s;
    case 0x1A:{unsigned a=(s.r[2]<<8)|s.r[3];s.r[7]=rom[a];s.reads++;if(trace && visited[a]>=2)fail("Read address more than twice");visited[a]++;s.cycles+=7;break;}
    case 0xAF:s.r[7]=0;z=1;parity=1;carry=0;s.cycles+=4;break;
    case 0x29:{unsigned a=(s.r[4]<<8)|s.r[5];carry=(a&0x8000)!=0;a=(a<<1)&0xFFFF;s.r[4]=a>>8;s.r[5]=a&255;s.cycles+=10;break;}
    case 0x13:{unsigned a=((unsigned)s.r[2]<<8)|s.r[3];a=(a+1)&0xFFFF;s.r[2]=a>>8;s.r[3]=a&255;s.cycles+=5;break;}
    case 0x05:s.r[0]--;z=s.r[0]==0;s.cycles+=5;break;
    case 0x0E:s.r[1]=rom[s.pc++];s.cycles+=7;break;
    case 0x06:s.r[0]=rom[s.pc++];s.cycles+=7;break;
    case 0xC2:case 0xEA:{unsigned dest=rom[s.pc]|(rom[(uint16_t)(s.pc+1)]<<8);s.pc+=2;if((op==0xC2&&!z)||(op==0xEA&&parity))s.pc=(uint16_t)dest;s.cycles+=10;break;}
    case 0xEE:s.r[7]^=rom[s.pc++];z=s.r[7]==0;parity=(!__builtin_parity((unsigned)s.r[7]));carry=0;s.cycles+=7;break;
    case 0xE6:s.r[7]&=rom[s.pc++];z=s.r[7]==0;parity=(!__builtin_parity((unsigned)s.r[7]));carry=0;s.cycles+=7;break;
    default:fprintf(stderr,"unsupported 0x%02x at %04x\n",op,pc);exit(2);
    }
  }
  fail("execution exceeded instruction limit");return s;
}
int main(int argc,char **argv){
 if(argc!=2){fprintf(stderr,"usage: %s firmware.bin\n",argv[0]);return 1;}
 FILE *f=fopen(argv[1],"rb");if(!f){perror(argv[1]);return 1;}
 uint8_t binary[1024];int len=fread(binary,1,sizeof(binary),f);fclose(f);
 printf("machine code: %d bytes\n",len);
 int count=0;
 const int reset_only=(strstr(argv[1],"_reset")!=NULL);
 for(int mode=0;mode<4;mode++){
   memset(rom,mode==0?0xff:0,N);
   memcpy(rom,binary,len);
   if(mode==2||mode==3)for(int i=len;i<N-4;i++)rom[i]=(uint8_t)rnd();
   patch();
   State good=execute(reset_only,1);
   if(!good.inte||good.result!=0||good.reads!=N*2)fail("normal ROM");
   printf("mode=%d: good: cycles=%u  T/byte=%.5f\n",mode,good.cycles,good.cycles/(double)N);
   count++;
   const int addrs[]={0x0100,0x7fff,0x8000,0xfffb,0xfffc,0xfffd,0xfffe,0xffff};
   for(unsigned j=0;j<sizeof(addrs)/sizeof(addrs[0]);j++){
     int a=addrs[j];uint8_t mask=(uint8_t)(1u<<(rnd()%8));rom[a]^=mask;
     uint16_t p25=crc16(rom,N,0x25),p47=crc16(rom,N,0x47);
     if(p25==0||p47==0)fail("single bit not detected independently");
     State bad=execute(reset_only,0);
     if(bad.inte||bad.result!=(p25?p25:p47)||bad.reads!=N)fail("fault detection: residue");
     count++;rom[a]^=mask;
   }
   // Test 2-bit error invisible only to the first CRC (distance 1023 bits)
   unsigned bit=80000, sep=1023;
   rom[bit>>3] ^= (uint8_t)(0x80u>>(bit&7));
   rom[(bit+sep)>>3] ^= (uint8_t)(0x80u>>((bit+sep)&7));
   if(crc16(rom,N,0x25)!=0||crc16(rom,N,0x47)==0)fail("collision expectation");
   State bad=execute(reset_only,0);
   if(bad.inte||bad.reads!=N*2||bad.result!=crc16(rom,N,0x47))fail("second CRC detection");
   count++;
   rom[bit>>3] ^= (uint8_t)(0x80u>>(bit&7));
   rom[(bit+sep)>>3] ^= (uint8_t)(0x80u>>((bit+sep)&7));
   // Error invisible only to the second CRC: first pass must still reject it.
   sep=21845;
   rom[bit>>3] ^= (uint8_t)(0x80u>>(bit&7));
   rom[(bit+sep)>>3] ^= (uint8_t)(0x80u>>((bit+sep)&7));
   if(crc16(rom,N,0x25)==0||crc16(rom,N,0x47)!=0)fail("CRC47 two-bit collision expectation");
   bad=execute(reset_only,0);
   if(bad.inte||bad.reads!=N||bad.result!=crc16(rom,N,0x25))fail("first CRC detection");
   count++;
   rom[bit>>3] ^= (uint8_t)(0x80u>>(bit&7));
   rom[(bit+sep)>>3] ^= (uint8_t)(0x80u>>((bit+sep)&7));
   // Three widely spaced corrupted bits must be detected.
   unsigned tri[]={88731,88731+100001,88731+210003};
   for(int i=0;i<3;i++)rom[tri[i]>>3]^=(uint8_t)(0x80u>>(tri[i]&7));
   if(crc16(rom,N,0x25)==0&&crc16(rom,N,0x47)==0)fail("triple-bit collision");
   bad=execute(reset_only,0);
   if(bad.inte)fail("undetected triple bit pattern");
   count++;
   for(int i=0;i<3;i++)rom[tri[i]>>3]^=(uint8_t)(0x80u>>(tri[i]&7));
   // 4-bit fault invisible to both CRCs
   unsigned positions[]={80000+3920,80000+3920-1065,80000+3920-1278,80000};
   for(int i=0;i<4;i++)rom[positions[i]>>3]^=(uint8_t)(0x80u>>(positions[i]&7));
   if(crc16(rom,N,0x25)!=0||crc16(rom,N,0x47)!=0)fail("4-bit collision expectation");
   State coll=execute(reset_only,0);
   if(!coll.inte||coll.result!=0)fail("4bit collision should be missed");
   for(int i=0;i<4;i++)rom[positions[i]>>3]^=(uint8_t)(0x80u>>(positions[i]&7));
   count++;
 }
 printf("PASS: %d full-ROM simulations, independent CRC references and expected collisions\n",count);
 return 0;
}
