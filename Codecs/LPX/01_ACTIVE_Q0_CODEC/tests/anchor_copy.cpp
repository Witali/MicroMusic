// Value-copy snapshots must not retain pointers into the original LPC storage.
#include <stdint.h>
#include <fstream>
#include <iterator>
#include <vector>
#include "Lpx4HybridCore.h"
int main(int argc,char** argv){
    if(argc!=2)return 1;
    std::ifstream in(argv[1],std::ios::binary);
    std::vector<uint8_t> blob((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
    Lpx4HybridCore full;if(!full.begin(blob.data(),blob.size()))return 2;
    std::vector<int16_t> expected;int16_t value;
    while(full.nextS16(value))expected.push_back(value);
    if(!full.finished() || expected.size()!=full.samples())return 3;
    const uint32_t cuts[]={1,19,20,39,40,79,80,159,160,161,(uint32_t)expected.size()/2,(uint32_t)expected.size()-1};
    for(unsigned i=0;i<sizeof(cuts)/sizeof(cuts[0]);i++){
        const uint32_t cut=cuts[i];if(cut>expected.size())continue;
        Lpx4HybridCore original;if(!original.begin(blob.data(),blob.size()))return 4;
        for(uint32_t n=0;n<cut;n++)if(!original.nextS16(value))return 5;
        Lpx4HybridCore copied=original,assigned;assigned=original;
        original.begin(0,0);
        Lpx4HybridCore* snapshots[]={&copied,&assigned};
        for(unsigned k=0;k<2;k++){
            for(uint32_t n=cut;n<expected.size();n++)
                if(!snapshots[k]->nextS16(value) || value!=expected[n] || snapshots[k]->produced()!=n+1)return 6;
            if(!snapshots[k]->finished() || snapshots[k]->nextS16(value))return 7;
        }
    }
}
