#define private public
#include "Lpx4HybridCore.cpp"
#include <stdio.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
static uint32_t state=20261028UL;
static uint16_t randomLsf(){state=state*1664525UL+1013904223UL;return state>>22;}
static void ordered(int16_t* out){
 for(uint8_t i=0;i<10;i++){
  uint16_t value;bool duplicate;
  do{value=randomLsf();duplicate=false;for(uint8_t j=0;j<i;j++)if(out[j]==value)duplicate=true;}while(duplicate);
  uint8_t at=i;while(at && out[at-1]>value){out[at]=out[at-1];--at;}out[at]=value;
 }
}
int main(){
#ifdef _WIN32
 _setmode(_fileno(stdout),_O_BINARY);
#endif
 Lpx4HybridCore core;int16_t out[10];
 for(uint16_t trial=0;trial<4096;trial++){
  ordered(core.prev_);ordered(core.cur_);
  if(trial<16)for(uint8_t i=0;i<10;i++){
   core.prev_[i]=(trial&1)?1014+i:i;core.cur_[i]=(trial&2)?1014+i:i;
   if(trial&4)core.prev_[i]=i*1023/9;if(trial&8)core.cur_[i]=i*1023/9;
  }
  for(uint8_t t=0;t<=16;t++){
   core.convertLsfAt(t,out);
   for(uint8_t i=0;i<10;i++){uint16_t value=out[i];putchar((uint8_t)value);putchar(value>>8);}
  }
 }
}
