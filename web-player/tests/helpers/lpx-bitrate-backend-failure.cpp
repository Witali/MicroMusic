// Test-only failing CUDA transport: verify that seed failures cannot publish
// an empty V9 stream or silently fall back to CPU. No GPU hardware is used.
#include "LpxEncoder.h"
#include "LpxCuda.h"
#include <cstdio>
#include <initializer_list>

bool lpxCudaAvailable() { return true; }
bool lpxCudaSearch(const LpxCudaJob&, LpxCudaResult&) { return false; }
const char* lpxCudaError() { return "intentional test transport failure"; }

int main() {
    const int n=8193;
    if(!enc_reserve(n))return 1;
    for(int i=0;i<n;++i)enc_input()[i]=int16_t((i*73)%4001-2000);
    for(int kbps : {3,8}) {
        if(enc_set_backend(1)!=0)return 2;
        if(enc_bitrate(n,kbps,8000,0,0)!=-7)return 3;
    }
    if(enc_set_backend(0)!=0)return 4;
    for(int kbps : {3,8}) {
        int size=enc_bitrate(n,kbps,8000,0,0);
        if(size<13 || size>n*kbps/64)return 5;
    }
    puts("PASS: both presets reject failed CUDA seeds and recover only after explicit CPU selection.");
}
