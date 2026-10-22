// Exact count of weight-4 undetectable error patterns confined to <= WINDOW bits;
// input: composite 32-bit CRC polynomial lower word, WINDOW<=~6000 recommended.
#include <cstdint>
#include <cstdio>
#include <vector>
#include <cstdlib>
#include <cstring>
#include <inttypes.h>
using namespace std;
static inline uint32_t hash32(uint32_t x){x^=x>>16;x*=0x7feb352dU;x^=x>>15;x*=0x846ca68bU;x^=x>>16;return x;}
int main(int argc,char **argv){
 if(argc<3){fprintf(stderr,"Usage: %s WINDOW CRC32_HEX [CRC32_HEX ...]\n",argv[0]);return 1;}
 const int N=524288,W=atoi(argv[1]);
 const uint32_t SIZE=1u<<25;
 vector<uint32_t> keys(SIZE),counts(SIZE),s(W);
 for(int q=2;q<argc;q++){
   uint32_t poly=(uint32_t)strtoul(argv[q],nullptr,16);
   fill(keys.begin(),keys.end(),0);fill(counts.begin(),counts.end(),0);
   s[0]=1;for(int k=1;k<W;k++)s[k]=(s[k-1]<<1)^((s[k-1]&0x80000000)?poly:0);
   int first=0;uint64_t normalized=0,total=0;
   for(int m=3;m<W;m++){
     uint32_t target=s[0]^s[m]; uint32_t h=hash32(target)&(SIZE-1);
     while(keys[h] && keys[h]!=target)h=(h+1)&(SIZE-1);
     if(keys[h]==target){
       if(!first)first=m+1;
       normalized+=counts[h];total+=(uint64_t)counts[h]*(N-m);
     }
     for(int i=1;i<m;i++){
       uint32_t key=s[i]^s[m]; if(!key){fprintf(stderr,"WARNING: two-bit syndrome collision\n");}
       uint32_t p=hash32(key)&(SIZE-1);
       while(keys[p] && keys[p]!=key)p=(p+1)&(SIZE-1);
       if(!keys[p])keys[p]=key;
       counts[p]++;
     }
   }
   printf("poly=%08X window=%d, minimum_span=%d, normalized_undetected_4bit=%" PRIu64 ", placements_within_64KiB=%" PRIu64 "\n",poly,W,first,normalized,total);
 }
}
