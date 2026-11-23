// Standalone numerical seam for native/scalar/SIMD evaluator comparisons.
// Link LpxQuality.cpp, LpxStoi.cpp and LpxAdaptiveDsp.cpp with dead stripping.
#include "LpxQuality.h"
#include "LpxFullBand.h"
#include <cstdio>
#include <cstdlib>

static lpx::Pcm reference, candidate;
static std::vector<double> analysis;
static double result[18];
static double fullBand[90];
extern "C" int quality_reserve(int count) {
    if(count<1)return 0;reference.resize(count);candidate.resize(count);return 1;
}
extern "C" int16_t* quality_reference() { return reference.data(); }
extern "C" int16_t* quality_candidate() { return candidate.data(); }
extern "C" double* quality_measure(int rate) {
#ifdef LPX_QUALITY_LEGACY
    lpx::QualityContext context(reference);
#else
    // rate=0 exercises the existing source-compatible default constructor.
    lpx::QualityContext context=rate?lpx::QualityContext(reference,true,rate):lpx::QualityContext(reference);
#endif
    auto m=context.measure(candidate);
    result[0]=double(m.quality.error[0]);result[1]=double(m.quality.error[1]);
    result[2]=m.quality.stoi[0];result[3]=m.quality.stoi[1];
    result[4]=m.voice[0];result[5]=m.voice[1];result[6]=m.noise[0];result[7]=m.noise[1];
    result[8]=m.score;result[9]=m.clipped;
    for(int path=0;path<2;++path) {
        const auto& d=m.diagnostic[path];int at=10+path*4;
        result[at]=d.within;result[at+1]=d.collapsed;result[at+2]=d.period;result[at+3]=d.shape;
    }
    return result;
}
extern "C" int quality_resample(int rate) {
#ifndef LPX_QUALITY_LEGACY
    analysis=lpx::qualityAnalysis8k(reference,rate);
#endif
    return int(analysis.size());
}
extern "C" double* quality_analysis() { return analysis.data(); }
extern "C" double* quality_fullband(int rate) {
#ifndef LPX_QUALITY_LEGACY
    lpx::FullBandContext context(reference,rate);auto m=context.measure(candidate);
    fullBand[0]=m.valid;fullBand[1]=m.bands;fullBand[2]=m.totalError[0];fullBand[3]=m.totalError[1];
    for(int b=0;b<8;++b) {
        int at=4+b*8;fullBand[at]=m.sourcePower[b];fullBand[at+1]=m.supported[b];
        for(int path=0;path<2;++path) {
            fullBand[at+2+path*3]=m.outputPower[path][b];
            fullBand[at+3+path*3]=m.error[path][b];fullBand[at+4+path*3]=m.retention[path][b];
        }
    }
    for(int path=0;path<2;++path) {
        for(int b=0;b<8;++b)fullBand[68+path*8+b]=m.temporalError[path][b];
        fullBand[84+path]=m.totalTemporalError[path];fullBand[86+path]=m.balancedError[path];
        fullBand[88+path]=m.balancedTemporalError[path];
    }
#endif
    return fullBand;
}
extern "C" int quality_fullband_selftest() {
#ifndef LPX_QUALITY_LEGACY
    int checks=0;
    for(int rate:{8000,12000,16000}) {
        // Genuine native-Nyquist detail, independent of any 8 kHz resampling.
        lpx::Pcm high(1027),zero(1027),quiet(1027),tail(1027);
        for(int i=0;i<1027;++i) { high[i]=i&1?10000:-10000;quiet[i]=i&1?1:-1; }
        tail.back()=20000;
        for(const auto* source:{&high,&quiet,&tail}) {
            lpx::FullBandContext context(*source,rate);
            auto same=context.measure(*source),lost=context.measure(zero);
            if(!context.accepts(same,same) || context.accepts(lost,same))return -1;
            if(context.measure(lpx::Pcm(3)).valid)return -2;
            ++checks;
        }
        lpx::FullBandContext silence(zero,rate);auto floor=silence.measure(zero);
        for(int at:{0,513,1026}) {
            lpx::Pcm impulse(1027);impulse[at]=1;
            auto m=silence.measure(impulse);
            if(!(m.totalError[0]>0) || silence.accepts(m,floor))return -3;
            ++checks;
        }
        lpx::FullBandContext context(high,rate);auto m=context.measure(high);
        if(m.bands!=rate/2000 || !m.supported[m.bands-1])return -4;
        ++checks;
    }
    lpx::FullBandContext invalid(reference,11025);
    if(invalid.measure(candidate).valid || invalid.accepts({},{}))return -5;
    return checks;
#else
    return 0;
#endif
}

#ifdef LPX_QUALITY_NATIVE
int main(int argc,char** argv) {
    if(argc!=4)return 1;
    int rate=std::atoi(argv[1]),count=std::atoi(argv[3]);
    if(!quality_reserve(count))return 2;
    for(auto* pcm:{&reference,&candidate})for(int i=0;i<count;++i) {
        int low=std::getchar(),high=std::getchar();if(low<0||high<0)return 3;
        (*pcm)[i]=int16_t(low|(high<<8));
    }
    if(argv[2][0]=='t') std::fwrite(quality_fullband(rate),sizeof(double),90,stdout);
    else if(argv[2][0]=='f') std::fwrite(quality_fullband(rate),sizeof(double),68,stdout);
    else if(argv[2][0]=='a') {
        quality_resample(rate);std::fwrite(analysis.data(),sizeof(double),analysis.size(),stdout);
    } else std::fwrite(quality_measure(rate),sizeof(double),18,stdout);
}
#endif
