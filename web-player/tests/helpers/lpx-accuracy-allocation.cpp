#include "LpxAccuracy.h"
#include "LpxEncoder.h"
#include <cmath>
extern "C" int accuracy_allocation_selftest(){
    if(!enc_reserve(641))return 1;
    lpx::Pcm tone(641);for(int i=0;i<641;++i)tone[i]=int16_t(2000*std::sin(i*.15)+500*std::sin(i*.31));
    auto seed=lpx::fitSeed(tone,6,8000,13926,false);seed.allowExtras=true;
    if(seed.samples!=641)return 2;
    auto target=seed;target.extras[0]={{0,7}};target.extras[1]={{1,-8}};target.extras[2]={{2,7}};
    const auto reference=lpx::render(target),original=lpx::render(seed);
    auto single=seed;single.extras[0]={{0,7}};
    const int base=lpx::packV9(seed).size(),cap=lpx::packV9(single).size();if(cap<=base+2)return 3;
    for(int zeroPosition:{-1,0}){
        for(auto& pulse:seed.extras)pulse={{zeroPosition,0}};
        auto result=lpx::refineAccuracyCorrections(seed,reference,cap);
        int active=0;for(const auto& p:result.extras)active+=p[1]!=0;
        if(active<1||active>1||int(lpx::packV9(result).size())>cap)return 4;
        if(lpx::sse(reference,lpx::render(result))>=lpx::sse(reference,original))return 5;
        if(!lpx::verifyStream(result,lpx::render(result)))return 6;
        auto none=lpx::refineAccuracyCorrections(seed,reference,base);
        if(lpx::packV9(none)!=lpx::packV9(seed))return 7;
    }
    return 0;
}
#ifdef LPX_ACCURACY_NATIVE_TEST
int main(){return accuracy_allocation_selftest();}
#endif
