#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include "Lpx4Math.h"
// Independent mathematical reference: signed division with floor semantics,
// not the production word decomposition or implementation-defined shifts.
static int32_t floor_div(int64_t value,int64_t denominator){
    return (int32_t)(value<0?-((-value+denominator-1)/denominator):value/denominator);
}
static unsigned long long count=0;
static int fail(const char* name,int32_t x,int32_t old,int32_t current){
    fprintf(stderr,"%s mismatch input=%ld expected=%ld actual=%ld\n",name,(long)x,(long)old,(long)current);return 1;
}
static int shift(int32_t x){
    ++count;
    if(lpx4Shift12(x)!=floor_div(x,4096))return fail("shift12",x,floor_div(x,4096),lpx4Shift12(x));
    if(lpx4Shift14(x)!=floor_div(x,16384))return fail("shift14",x,floor_div(x,16384),lpx4Shift14(x));
    return 0;
}
int main(){
    const int32_t endpoints[]={INT32_MIN,INT32_MIN+1,INT32_MAX,INT32_MAX-1,-1,0,1,-4097,-4096,-4095,4095,4096,4097,-16385,-16384,-16383,16383,16384,16385};
    for(unsigned i=0;i<sizeof(endpoints)/sizeof(*endpoints);++i)if(shift(endpoints[i]))return 1;
    const uint16_t lows[]={0,1,2,4095,4096,4097,8191,16383,16384,16385,32767,32768,49151,65534,65535};
    for(uint32_t high=0;high<65536;++high)for(unsigned l=0;l<sizeof(lows)/sizeof(*lows);++l)
        if(shift((int32_t)((high<<16)|lows[l])))return 1;
    uint32_t random=0x739bd861;
    for(unsigned i=0;i<2000000;++i){
        random^=random<<13;random^=random>>17;random^=random<<5;
        if(shift((int32_t)random))return 1;
        const int16_t a=(int16_t)random,b=(int16_t)(random>>16);
        const int32_t old=floor_div((int64_t)a*b,16384);
        if(lpx4MulQ14(a,b)!=old)return fail("mulQ14",a,old,lpx4MulQ14(a,b));
    }
    const uint16_t cs[]={0,1,2,3,63,64,65,127,128,255,256,511,512,1023,1024,4095,4096,8191,8192,8193,11468,13158,13926,16382,16383,16384};
    unsigned long long atten_count=0,pwm_count=0;
    for(int32_t s=-32768;s<=32767;++s){
        for(unsigned i=0;i<sizeof(cs)/sizeof(*cs);++i){
            const int16_t old=(int16_t)floor_div((int64_t)cs[i]*s,16384);
            if(lpx4AttenuateQ14(cs[i],(int16_t)s)!=old)return fail("attenuate",s,old,lpx4AttenuateQ14(cs[i],(int16_t)s));
            ++atten_count;
        }
        for(unsigned gain=0;gain<256;++gain){
            int32_t old=128+floor_div((int64_t)s*gain+8192,16384);old=old<0?0:old>255?255:old;
            if(lpx4PwmQ14((int16_t)s,gain)!=old)return fail("pwm",s,old,lpx4PwmQ14((int16_t)s,gain));
            ++pwm_count;
        }
    }
    printf("exact shifts=%llu random_full_q14=2000000 attenuations=%llu pwm=%llu\n",count,atten_count,pwm_count);
}
