/* Standalone Intel 8080 dual-CRC validator. No external library.
   Emulates instruction bytes of both ROM routines, not ASM-level pseudocode.
   Build: cc -O3 -std=c11 -o test_v2_fast test_v2_fast.c
   Run:   ./test_v2_fast original.bin optimized_v2.bin [reset_only.bin]
*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ROM_SIZE 65536
static uint8_t rom[ROM_SIZE];
static uint32_t seed=0x80801976U;
static uint8_t rand8(void) {seed ^=seed<<13;seed ^=seed>>17;seed ^=seed<<5;return seed>>24;}
static uint16_t crc16(uint16_t poly) {
    uint16_t c=0;
    for(int i=0;i<ROM_SIZE;i++) {
        c ^= ((uint16_t)rom[i])<<8;
        for(int b=0;b<8;b++) c=(uint16_t)((c<<1)^ ((c&0x8000) ? poly:0));
    }
    return c;
}
static uint32_t crc32prefix(void) {
    uint32_t c=0;
    for (int i=0;i<ROM_SIZE-4;i++) {
        c ^= ((uint32_t)rom[i])<<24;
        for(int j=0;j<8;j++) c=(c<<1)^ ((c&0x80000000u)?0x000E003Fu:0u);
    }
    return c;
}
static int readcode(const char *path,uint8_t *buf){
    FILE *f=fopen(path,"rb");if(!f){perror(path);exit(1);}
    int n=(int)fread(buf,1,512,f);fclose(f);
    if(n<1||n>512){fprintf(stderr,"bad code size: %s %d\n",path,n);exit(1);}
    return n;
}
struct Result {uint32_t cycles, steps, physical_reads;uint32_t data_reads;uint16_t bc,de,sp;int inte;};
static struct Result exec8080(const uint8_t *rom){
    uint8_t r[8]={0}; uint16_t pc=0,sp=0;int z=0,cy=0,inte=0;
    uint32_t cycles=0,steps=0,reads=0;
    uint32_t used=0; static uint8_t visited[ROM_SIZE]; memset(visited,0,sizeof(visited));
    for(;steps<5000000;steps++){
        uint8_t op=rom[pc++];
        if(op==0x76){cycles+=7;struct Result res={cycles,steps+1,reads*2,reads,
            (uint16_t)((r[0]<<8)|r[1]),(uint16_t)((r[2]<<8)|r[3]),sp,inte};
            if(used!=ROM_SIZE || reads!=ROM_SIZE){fprintf(stderr,"data addresses missing (%u unique, %u reads)\n",used,reads);exit(2);}return res;}
        if(op>=0x40 && op<=0x7f){r[(op>>3)&7]=r[op&7];cycles+=5;continue;}
        if(op>=0xA8 && op<=0xAF){r[7]^=r[op&7];z=r[7]==0;cy=0;cycles+=4;continue;}
        if(op>=0xB0 && op<=0xB7){r[7]|=r[op&7];z=r[7]==0;cy=0;cycles+=4;continue;}
        switch(op){
        case 0xF3: inte=0;cycles+=4;break;
        case 0xFB: inte=1;cycles+=4;break;
        case 0x31: sp=rom[pc]|(rom[(uint16_t)(pc+1)]<<8);pc+=2;cycles+=10;break;
        case 0x21: r[5]=rom[pc];r[4]=rom[(uint16_t)(pc+1)];pc+=2;cycles+=10;break;
        case 0xF1:{
          uint8_t f=rom[sp];uint16_t a=(uint16_t)(sp+1);
          r[7]=rom[a];z=(f&0x40)!=0;cy=(f&1)!=0;sp+=2;
          if(!visited[a]){visited[a]=1;used++;}
          reads++;cycles+=10;break;
        }
        case 0x3B:sp--;cycles+=5;break;
        case 0xAF:r[7]=0;z=1;cy=0;cycles+=4;break;
        case 0x67:r[4]=r[7];cycles+=5;break;
        case 0x6F:r[5]=r[7];cycles+=5;break;
        case 0x07:{uint8_t a=r[7];cy=(a>>7)&1;r[7]=(uint8_t)((a<<1)|(a>>7));cycles+=4;break;}
        case 0x1F:{uint8_t a=r[7];int c=cy;cy=a&1;r[7]=(uint8_t)((a>>1)|(c<<7));cycles+=4;break;}
        case 0xE6:r[7]&=rom[pc++];z=r[7]==0;cy=0;cycles+=7;break;
        case 0x87:{int v=r[7]*2;cy=v>255;r[7]=(uint8_t)v;z=r[7]==0;cycles+=4;break;}
        case 0x2C:r[5]++;z=r[5]==0;cycles+=5;break;
        case 0xC2:case 0xD2:{uint16_t addr=rom[pc]|(rom[(uint16_t)(pc+1)]<<8);pc+=2; if ((op==0xC2 && !z)||(op==0xD2&&!cy))pc=addr;cycles+=10;break;}
        case 0x39:{uint32_t s=((uint32_t)r[4]<<8|r[5])+sp;cy=s>65535;r[4]=(s>>8)&255;r[5]=s&255;cycles+=10;break;}
        default:fprintf(stderr,"unknown opcode %02X at %04X\n",op,(uint16_t)(pc-1));exit(2);
        }
    }
    fprintf(stderr,"timeout\n");exit(2);
}
static void fail(const char *why){fprintf(stderr,"FAIL %s\n",why);exit(3);}
static void repair_footer(void){uint32_t c=crc32prefix();
    rom[ROM_SIZE-4]=c>>24;rom[ROM_SIZE-3]=c>>16;rom[ROM_SIZE-2]=c>>8;rom[ROM_SIZE-1]=c;
    if(crc16(7)||crc16(9)) fail("composite footer");
}
static void assert_case(const uint8_t *code,int n,uint32_t correct_cycles,int mode){
    uint16_t r7=crc16(7),r9=crc16(9);
    struct Result sim=exec8080(rom);
    if(sim.bc!=r7||sim.de!=r9||sim.inte!=(r7==0&&r9==0)||sim.sp!=65535)fail("cpu vs independent CRC");
    if(!mode && sim.cycles!=correct_cycles)fail("known cycle count");
    if(sim.data_reads!=65536||sim.physical_reads!=131072)fail("reading counts");
    (void)code;(void)n;
}
static void flip(int bitpos){rom[bitpos>>3]^=(uint8_t)(1u<<(7-(bitpos&7)));}
int main(int argc,char**argv){
    if(argc<2||argc>7){fprintf(stderr,"usage: %s checker68.bin checker66.bin checker65.bin checker103.bin checker177.bin checker325.bin\n",argv[0]);return 1;}
    uint8_t codes[6][512];int counts[6];uint32_t expected[6];
    for(int i=1;i<argc;i++) {
        counts[i-1]=readcode(argv[i],codes[i-1]);
        switch(counts[i-1]) {
          case 68: expected[i-1]=12066385;break;
          case 66: expected[i-1]=11738705;break;
          case 65: expected[i-1]=11738701;break;
          case 103:expected[i-1]=11243345;break;
          case 177:expected[i-1]=10995665;break;
          case 325:expected[i-1]=10871825;break;
          default:fail("unrecognized firmware length");
        }
    }
    int cases=0;
    for(int prof=0;prof<argc-1;prof++){
      for(int data_mode=0;data_mode<4;data_mode++){
        memset(rom,data_mode==1?0:255,sizeof(rom));
        memcpy(rom,codes[prof],counts[prof]);
        if(data_mode>=2)for(int k=counts[prof];k<ROM_SIZE-4;k++)rom[k]=rand8();
        repair_footer(); assert_case(codes[prof],counts[prof],expected[prof],0);cases++;
        for(int k=0;k<24;k++){
           int addr=counts[prof] + (rand8()*257 + rand8())%(65532-counts[prof]);
           int bit=(addr<<3)+(rand8()&7);
           flip(bit);assert_case(codes[prof],counts[prof],0,1);flip(bit);cases++;
        }
        for(int k=0;k<2;k++){
          int b=100000;int dist=k?57337:32767;
          flip(b);flip(b+dist);
          if((crc16(7)==0)==(crc16(9)==0))fail("single CRC collision expected");
          assert_case(codes[prof],counts[prof],0,1);
          flip(b);flip(b+dist);cases++;
        }
        if(data_mode==0){int start=524288-1-50000;int offsets[]={0,777,1076,2007};
            for(int i=0;i<4;i++)flip(start-offsets[i]);
            if(crc16(7)||crc16(9))fail("known 4-bit collision missed");
            assert_case(codes[prof],counts[prof],expected[prof],0);
            for(int i=0;i<4;i++)flip(start-offsets[i]);
            cases++;
        }
      }
      printf("%s: %d bytes, %u T, %.6f T/B, all test ROMs OK\n",argv[prof+1],counts[prof],expected[prof],(double)expected[prof]/65536.0);
    }
    printf("PASS: %d full-ROM emulated checks, 65536 data addresses, independent CRCs, corrupted ROMs, collision cases\n",cases);
    return 0;
}
