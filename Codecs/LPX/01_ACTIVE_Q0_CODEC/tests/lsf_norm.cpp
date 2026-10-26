// Independent original signed32 arithmetic over every legal LSF10 anchor.
#include <stdint.h>
#include <stdio.h>
#include "Lpx4Math.h"
__attribute__((noinline)) static uint16_t reference(int16_t p,int16_t c,uint8_t t){
    return (uint16_t)(((int32_t)p*(16-t)+(int32_t)c*t)>>2);
}
int main(){
    uint32_t cases=0;
    for(int16_t p=0;p<1024;p++)for(int16_t c=0;c<1024;c++)for(uint8_t t=0;t<=16;t++){
        if(lpx4LsfNorm10(p,c,t)!=reference(p,c,t))return 1;
        ++cases;
    }
    printf("%lu LSF anchors exact\n",(unsigned long)cases);
}
