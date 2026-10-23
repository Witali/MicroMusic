#include <cstdint>
#include <cstdio>
#include <vector>
#include <cstdlib>
using namespace std;
static inline uint32_t h32(uint32_t x){x^=x>>16;x*=0x7feb352dU;x^=x>>15;x*=0x846ca68bU;x^=x>>16;return x;}
int main(int argc,char**argv){
 int W= argc>1 ? atoi(argv[1]):4096;
 constexpr uint32_t poly=0x006209BB;
 const uint32_t SZ=1u<<25, MASK=SZ-1;
 vector<uint32_t> keys(SZ),pair(SZ),s(W);
 s[0]=1;
 for(int k=1;k<W;k++)s[k]=(s[k-1]<<1)^((s[k-1]&0x80000000U)?poly:0);
 for(int m=3;m<W;m++){
   uint32_t target=s[0]^s[m],h=h32(target)&MASK;
   while(keys[h] && keys[h]!=target)h=(h+1)&MASK;
   if(keys[h]==target){int i=(pair[h]>>13),j=pair[h]&8191;
      printf("poly=0x%08X witness=[0,%d,%d,%d] min_span=%d bits\n",poly,i,j,m,m+1);
      printf("syndrome=%08X ^ %08X ^ %08X ^ %08X = %08X\n",s[0],s[i],s[j],s[m],s[0]^s[i]^s[j]^s[m]);
      return 0;
   }
   for(int i=1;i<m;i++){
      uint32_t v=s[i]^s[m],p=h32(v)&MASK;
      while(keys[p] && keys[p]!=v)p=(p+1)&MASK;
      if(!keys[p]) {keys[p]=v;pair[p]=(i<<13)|m;}
   }
 }
 return 1;
}
