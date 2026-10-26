// Compare the actual decoder accessors with the independently retained tables.
#include <stdio.h>
#include "Lpx4HybridCore.cpp"
static const uint16_t originalStep[256]={
#include "scale_table.inc"
};
static const int16_t originalCos[257]={
#include "cos_table.inc"
};
int main(){
    for(unsigned i=0;i<256;i++)if(scaleStep(i)!=originalStep[i])return 1;
    for(unsigned i=0;i<257;i++)if(cosineAt(i)!=originalCos[i])return 2;
    for(unsigned n=0;n<4096;n++){
        const unsigned i=n>>4,f=n&15;
        const int32_t expected=originalCos[i]+(((int32_t)(originalCos[i+1]-originalCos[i])*f)>>4);
        const int32_t actual=cosineAt(i)+(((int32_t)(cosineAt(i+1)-cosineAt(i))*f)>>4);
        if(actual!=expected)return 3;
    }
    puts("256 scales, 257 cosine nodes, 4096 interpolations exact");
}
