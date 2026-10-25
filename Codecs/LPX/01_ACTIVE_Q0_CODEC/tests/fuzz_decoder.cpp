// Public-interface reset/mutation test. Run under ASan + UBSan on a host.
#include <stdint.h>
#include <stdio.h>
#include <fstream>
#include <iterator>
#include <vector>
#include "Lpx4HybridCore.h"
static uint32_t cases,rejected,capped;
static Lpx4HybridCore decoder;
struct Result {uint32_t hash,produced;uint8_t error,done;};
static Result decode(const std::vector<uint8_t>& b){
    Result r={2166136261UL,0,0,0};
    decoder.begin(b.empty()?0:b.data(),(uint16_t)b.size());
    uint8_t value;
    while(r.produced<4096 && decoder.next(value)){r.hash=(r.hash*16777619UL)^value;++r.produced;}
    r.error=decoder.error();r.done=decoder.finished();return r;
}
static bool check(const std::vector<uint8_t>& b){
    const Result a=decode(b),c=decode(b);
    ++cases;if(a.error)++rejected;if(!a.error&&!a.done)++capped;
    return a.hash==c.hash&&a.produced==c.produced&&a.error==c.error&&a.done==c.done;
}
int main(int argc,char** argv){
    for(int index=1;index<argc;index++){
        std::ifstream in(argv[index],std::ios::binary);
        if(!in)return 2;
        const std::vector<uint8_t> original((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
        if(!check(original))return 3;
        for(size_t n=0;n<original.size();n++){
            if(!check(std::vector<uint8_t>(original.begin(),original.begin()+n)))return 4;
            for(uint8_t bit=0;bit<8;bit++){
                std::vector<uint8_t> changed=original;changed[n]^=(1u<<bit);
                if(!check(changed))return 5;
            }
        }
        printf("input %d checked, cases %lu\n",index,(unsigned long)cases);fflush(stdout);
    }
    printf("{\"cases\":%lu,\"rejected\":%lu,\"sample_capped\":%lu,\"reset_exact\":true}\n",
        (unsigned long)cases,(unsigned long)rejected,(unsigned long)capped);
}
