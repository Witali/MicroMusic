// Public counter semantics, including complete streams beyond uint16 duration.
#include <fstream>
#include <iterator>
#include <vector>
#include "Lpx4HybridCore.h"
int main(int argc,char** argv){
    if(argc!=2)return 1;
    std::ifstream in(argv[1],std::ios::binary);
    std::vector<uint8_t> blob((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
    if(blob.size()>65535)return 2;
    Lpx4HybridCore d;
    for(unsigned restart=0;restart<2;restart++){
        if(!d.begin(blob.data(),(uint16_t)blob.size()))return 3;
        const uint32_t count=d.samples();
        if(!count || d.produced() || d.finished())return 4;
        for(uint32_t n=1;n<=count;n++){
            int16_t value=1;
            if(!d.nextS16(value) || value!=0 || d.produced()!=n || d.finished()!=(n==count))return 5;
        }
        int16_t value;
        if(d.nextS16(value) || d.produced()!=count || d.error())return 6;
        if(d.begin(0,0) || d.produced()!=0 || d.finished() || d.error()!=Lpx4HybridCore::BAD_HEADER)return 7;
    }
}
