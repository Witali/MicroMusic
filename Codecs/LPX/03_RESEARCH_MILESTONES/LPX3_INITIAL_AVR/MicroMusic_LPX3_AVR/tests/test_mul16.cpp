#include "../src/Lpx3AvrCore.cpp"
#include <cstdio>
#include <cstdlib>
#include <cstdint>
int main(){
 const int16_t extremes[]={-32768,-32767,-16384,-255,-1,0,1,255,16384,32767};
 for(int16_t a:extremes)for(int16_t b:extremes)
  if(mul16x16(a,b)!=(int32_t)a*b){printf("FAIL %d %d\n",a,b);return 1;}
 uint32_t seed=0x834ACFFEU;
 for(int i=0;i<1000000;i++){
  seed=1664525u*seed+1013904223u;int16_t a=(int16_t)(seed>>16);
  seed=1664525u*seed+1013904223u;int16_t b=(int16_t)(seed>>16);
  if(mul16x16(a,b)!=(int32_t)a*b){printf("FAIL %d %d\n",a,b);return 2;}
 }
 puts("PASS mul16x16: 1,000,100 randomized/boundary cases");return 0;
}
