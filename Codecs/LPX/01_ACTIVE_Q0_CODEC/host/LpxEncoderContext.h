#pragma once
#include "LpxEncoderOptions.h"
#include "LpxSeed.h"
#include "LpxHostWorkspace.h"
#include <math.h>
#if LPX_ENCODER_ENABLE_CUDA
#include "LpxCuda.h"
#endif

namespace lpx {
// Internal host search context. Returned views belong to this context and are
// invalidated only by its reserve/begin, not by another independent context.
struct SeedEncoder {
#if LPX_ENCODER_ENABLE_CUDA
    using State=LpxCudaState;
    bool cudaEnabled=false;
    LpxCudaJob cudaJob={};
#else
    struct State { int h[10],ring[256],dd; };
#endif
    SeedEncoder()=default;
    SeedEncoder(const SeedEncoder&)=delete;
    SeedEncoder& operator=(const SeedEncoder&)=delete;
#if !defined(__wasm__) || defined(LPX_ADAPTIVE_ENCODER)
    ~SeedEncoder();
#endif
    int pre=13926;
    double analysisBandwidth=.97;
    bool allowZeroScale=true,referenceScaleOrder=false;
    int16_t *source=nullptr,*expected=nullptr,(*coefficients)[10]=nullptr;
    double *emphasized=nullptr,*residual=nullptr;
    uint8_t (*spectra)[10]=nullptr,*packed=nullptr;
    uint16_t (*vectors)[10]=nullptr;
    int (*params)[3]=nullptr,(*pulses)[2]=nullptr;
    uint32_t reservedSamples=0,packedCapacity=0;
    int headerBytes=0,count=0,padded=0,mode=0,rate=0,block=0,bits=0,failure=0;
    const char* backendError="";
    State state={};
    LpxSeedContext seedContext;
    bool hasSeedContext=false;
    LpxWorkspace workspace;
#if !LPX_ENCODER_CACHE_ANALYSIS
    double window[256]={};
#endif
#if LPX_ENCODER_REUSE_PREFIX
    State prefixState[20]={};
    double prefixLoss[20]={};
#endif
    int reserve(uint32_t samples);
    int setBackend(int backend);
    int begin(int samples,int profile,int rate);
    int seedBegin(int samples,int profile,int rate,int emphasis,bool zeroScale,
                  double bandwidth,const LpxSeedContext* context=nullptr);
    int step();
    int finish();
    void release(); // Also available to freestanding callers without C++ teardown.
    LpxSeedView view() const;
    // Private arithmetic seams are exposed only to the existing kernel tests.
    void prepareAnalysis();
    void analyze(int frame);
    void prepareCoefficients();
    double trial20(State& out,const State& initial,int cursor,int scale,int lag,int gain,
                   int pos,int amp,bool save,double bound=HUGE_VAL,bool reusePrefix=false,bool recordPrefix=false);
    double searchBlock(State& result,int scale,int lag,int gain,bool save,double bound=HUGE_VAL);
    void commitSilentBlock(int start);
    void put(int value,int width);
    void rice(int value,int k,int width);
    void word(int offset,int value);
    void dword(int offset,uint32_t value);
};
SeedEncoder& defaultSeedEncoder();
}
