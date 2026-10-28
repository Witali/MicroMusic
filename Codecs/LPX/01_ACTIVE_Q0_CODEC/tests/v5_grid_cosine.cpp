// Exact generic cosine oracle plus legal centered-v5 scalar/vector domains.
#include <stdint.h>
#include <stdio.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define private public
#include "Lpx4HybridCore.h"
#undef private
#include "Lpx4HybridCore.cpp"
static const int16_t originalCos[]={
#include "cos_table.inc"
};
static_assert(sizeof(originalCos)/sizeof(originalCos[0])==257,"Full cosine oracle must have257 nodes");
static uint32_t rng=0x28a05b31;
static uint32_t nextRandom(){rng=rng*1664525UL+1013904223UL;return rng;}
static int16_t reference(uint16_t n){
 const unsigned i=n>>4,f=n&15;
 return originalCos[i]+(((int32_t)(originalCos[i+1]-originalCos[i])*(int32_t)f)>>4);
}
int main(){
#ifdef _WIN32
 _setmode(_fileno(stdout),_O_BINARY);
#endif
 unsigned nodes=0,anchors=0;
 for(unsigned n=0;n<4096;n++){
#if LPX4_COMPACT_ONLY && LPX3_LPC_SEGMENTS!=4 && defined(TEST_GRID)
  if(!(n&31) && cosineEvenNode(n>>5)!=reference(n))return 6;
#endif
  if(cosineInterpolate(n)!=reference(n))return 1;
  ++nodes;
 }
 for(unsigned bits=5;bits<=6;bits++)for(unsigned p=0;p<(1U<<bits);p++)for(unsigned c=0;c<(1U<<bits);c++){
  const unsigned shift=10-bits;const int16_t prev=(p<<shift)+(1U<<(shift-1)),cur=(c<<shift)+(1U<<(shift-1));
  for(unsigned t=0;t<=16;t+=16/LPX3_LPC_SEGMENTS){
   const uint16_t norm=lpx4LsfNorm10(prev,cur,t);
   const uint16_t expected=((int32_t)prev*(16-t)+(int32_t)cur*t)>>2;
   if(norm!=expected)return 2;
#if LPX4_COMPACT_ONLY && LPX3_LPC_SEGMENTS!=4 && defined(TEST_GRID)
   if(norm&31)return 3;
   if(cosineEvenNode(norm>>5)!=reference(norm))return 7;
#endif
   if(cosineInterpolate(norm)!=reference(norm))return 4;
   ++anchors;
  }
 }
 fprintf(stderr,"%u cosine inputs, %u scalar anchors exact\n",nodes,anchors);
 Lpx4HybridCore decoder;
 for(unsigned bits=5;bits<=6;bits++)for(unsigned test=0;test<2048;test++){
  uint8_t a[64],b[64];unsigned size=1U<<bits;
  for(unsigned i=0;i<size;i++)a[i]=b[i]=i;
  for(unsigned i=size-1;i;i--){unsigned j=nextRandom()%(i+1);uint8_t tmp=a[i];a[i]=a[j];a[j]=tmp;j=nextRandom()%(i+1);tmp=b[i];b[i]=b[j];b[j]=tmp;}
  // Sort ten legal LSF indices, with endpoint clusters and repeated vectors.
  for(unsigned i=0;i<10;i++)for(unsigned j=i+1;j<10;j++){if(a[j]<a[i]){uint8_t z=a[i];a[i]=a[j];a[j]=z;}if(b[j]<b[i]){uint8_t z=b[i];b[i]=b[j];b[j]=z;}}
  decoder.speechProfile_=bits==5?4:6;
  for(unsigned i=0;i<10;i++){
   if(test<4){a[i]=(test&1)?size-10+i:i;b[i]=(test&2)?size-10+i:i;}
   if(test%4==0)b[i]=a[i];
   const unsigned shift=10-bits;
   decoder.prev_[i]=sizeof(decoder.prev_[0])==1 ? a[i]+1 : (a[i]<<shift)+(1U<<(shift-1));
   decoder.cur_[i]=sizeof(decoder.cur_[0])==1 ? b[i]+1 : (b[i]<<shift)+(1U<<(shift-1));
  }
  for(unsigned t=0;t<=16;t+=16/LPX3_LPC_SEGMENTS){
   int16_t out[10];decoder.convertLsfAt(t,out);
   for(unsigned i=0;i<10;i++){const uint16_t word=(uint16_t)out[i];if(putchar((uint8_t)word)==EOF||putchar((uint8_t)(word>>8))==EOF)return 5;}
  }
 }
 return 0;
}
