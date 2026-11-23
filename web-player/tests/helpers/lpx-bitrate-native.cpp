// Test-only native entry to the same API exported by scalar/SIMD WASM.
#include "LpxEncoder.h"
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <cstring>

extern "C" uint8_t* enc_adaptive_output();
int main(int argc,char** argv) {
    if(argc!=3)return 2;
    std::vector<int16_t> pcm;int low;
    while((low=getchar())!=EOF) {
        int high=getchar();if(high==EOF)return 3;
        pcm.push_back(int16_t(low|(high<<8)));
    }
    if(!enc_reserve(pcm.size()))return 4;
    memcpy(enc_input(),pcm.data(),pcm.size()*2);
    int size=enc_bitrate(pcm.size(),atoi(argv[1]),8000,0,atoi(argv[2]));
    if(size<13) { fprintf(stderr,"encoder error %d\n",size);return 5; }
    return fwrite(enc_adaptive_output(),1,size,stdout)==size?0:6;
}
