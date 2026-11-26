// Same searched public C ABI workload, linked to old/current host objects.
#include "LpxEncoder.h"
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>
extern "C" {
int enc_adaptive_extended(int,int,int,int,int,int,int);
uint8_t* enc_adaptive_output();
}
int main(int argc,char** argv) {
    if(argc<2||argc>3)return 1;
    const bool threeK=!std::strcmp(argv[1],"three-k");
    if(!threeK&&std::strcmp(argv[1],"adaptive"))return 2;
    const int samples=threeK?6401:641;
    if(enc_set_backend(0)||!enc_reserve(samples))return 3;
    const double pi=3.14159265358979323846;
    for(int i=0;i<samples;++i) {
        const double t=double(i)/8000;
        const double envelope=.65+.25*std::sin(2*pi*7*t);
        enc_input()[i]=int16_t(std::nearbyint(4500*envelope*(std::sin(2*pi*213*t)
            +.35*std::sin(2*pi*1278*t)+.2*std::sin(2*pi*3440*t))));
    }
    int bytes;
#ifdef LPX_POLICY_CURRENT
    if(argc==3)bytes=threeK?enc_bitrate_target(samples,3,8000,0,1,1)
        :enc_adaptive_extended_target(samples,6,8000,0,0,1,10,1);
    else
#endif
    bytes=threeK?enc_bitrate(samples,3,8000,0,1):enc_adaptive_extended(samples,6,8000,0,0,1,10);
    if(bytes<1) {std::fprintf(stderr,"encode error %d\n",bytes);return 4;}
    return std::fwrite(enc_adaptive_output(),1,bytes,stdout)==size_t(bytes)?0:5;
}
