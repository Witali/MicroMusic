// Exact integer synthesis/packing shared by the native and WASM controllers.
#include "LpxAdaptive.h"
#include "LpxEncoder.h"
#include "LpxSeed.h"
#include "LpxSpectrumQuantizer.h"
#include "LpxEncoderContext.h"
#include "LpxLpcStability.h"
#include "LpxQuality.h"
#include "LpxFullBand.h"
#include <algorithm>
#include <cmath>
#include <memory>
#include <string.h>

namespace lpx {
static const int16_t cosine[] = {
#include "cos_table.inc"
};
static const int16_t steps[] = {
#include "scale_table.inc"
};
int clamp(int value, int low, int high) { return std::min(high, std::max(low, value)); }
static int polyMul(int value, int c) {
    if (value >= -250000 && value <= 250000) return (value * c) >> 12;
    int high = value / 16;
    return ((high * c) >> 8) + (((value - high * 16) * c) >> 12);
}
Stream canonicalAccuracy(const Stream& s){
    if(s.accuracy!=3)return s;
    Stream result=s;int previous[10];bool hasPrevious=s.continuation;
    if(hasPrevious)std::copy(s.previousSpectrum.begin(),s.previousSpectrum.end(),previous);
    for(auto& spectrum:result.spectra){lpxQuantizeSpectrum(spectrum.data(),hasPrevious?previous:nullptr,s.accuracy);std::copy(spectrum.begin(),spectrum.end(),previous);hasPrevious=true;}
    return result;
}
std::vector<Coefficients> coefficientTrace(const Stream& s) {
    if(s.accuracy==3){auto canonical=canonicalAccuracy(s);canonical.accuracy=0;return coefficientTrace(canonical);}
    const int frames = (s.samples + 159) / 160, shift = s.profile == 4 ? 5 : 4;
    std::vector<Coefficients> result((s.samples + 19) / 20);
    for (int fi = 0; fi < frames; ++fi) {
        int endpoints[3][10];
        const auto& previous = fi==0 && s.continuation?s.previousSpectrum:s.spectra[(fi ? fi - 1 : 0) / 2];
        const auto& current = s.spectra[fi / 2];
        for (int point = 0; point < 3; ++point) {
            int t = point * 8, p[2][12] = {{4096,4096},{4096,-4096}};
            for (int j = 0; j < 10; ++j) {
                int a = (previous[j] << shift) + (1 << (shift - 1));
                int b = (current[j] << shift) + (1 << (shift - 1));
                int norm = (a * (16 - t) + b * t) >> 2, index = norm >> 4, frac = norm & 15;
                int c = -(cosine[index] + ((cosine[index+1] - cosine[index]) * frac >> 4));
                int* q = p[j & 1]; int n = 2 + j / 2 * 2;
                q[n+1] = q[n-1]; q[n] = q[n-2] + polyMul(q[n-1], c);
                for (int k = n-1; k > 1; --k) q[k] = q[k-2] + polyMul(q[k-1], c) + q[k];
                q[1] += polyMul(q[0], c);
            }
            for (int j = 0; j < 10; ++j) endpoints[point][j] = clamp((p[0][j+1] + p[1][j+1]) / 2);
        }
        for (int sub = 0; sub < 8 && fi * 8 + sub < int(result.size()); ++sub)
            for (int j = 0; j < 10; ++j) {
                int a = endpoints[sub/4][j], b = endpoints[sub/4+1][j];
                result[fi*8+sub][j] = clamp(a + (b-a) * ((sub*2+1)%8) / 8);
            }
    }
    return result;
}
Pcm advance(const Stream& s, const std::vector<Coefficients>& co, int start, int end,
            SynthesisState& state, std::vector<int>* lpc) {
    Pcm output(end-start);
    if (lpc) lpc->resize(end-start);
    for (int j = start; j < end; ++j) {
        const auto& p = s.parameters[j/160]; const auto& pulse = s.pulses[j/20];
        const auto& extra = s.extras[j/40];
        int q = clamp((p[2]*state.ring[(j-p[1])&255]+8)>>4, -32,31);
        q = clamp(q + (j%20 == pulse[0] ? pulse[1] : 0) + (j%40 == extra[0] ? extra[1] : 0),-32,31);
        state.ring[j&255] = q;
        int acc = 0; for (int k = 0; k < 10; ++k) acc += (co[j/20][k]*state.h[k])>>12;
        int value = clamp(q*steps[p[0]*8]-acc);
        for (int k = 9; k; --k) state.h[k] = state.h[k-1]; state.h[0] = value;
        if (lpc) (*lpc)[j-start] = value;
        state.dd = clamp(value+((s.pre*state.dd)>>14));
        int clipped = clamp(state.dd,-16384,16384);
        int out = clamp(clipped-((s.bright*state.cc)>>14),-16384,16384); state.cc = clipped;
        output[j-start] = clamp(out*2,-32768,32767);
    }
    return output;
}
Pcm render(const Stream& s) { auto co = coefficientTrace(s); auto state=s.initial; return advance(s,co,0,s.samples,state); }
bool stableLpcStream(const Stream& s) {
    const auto co=coefficientTrace(s);
    for(const auto& frame:co)if(!lpxStableLpc(frame.data()))return false;
    return !co.empty();
}
bool safeSynthesisLevel(const Stream& s,const Pcm& reference,const Pcm& actual,int* firstBad) {
    if(reference.empty()||reference.size()!=actual.size())return false;
    // Catastrophic growth only, with fixed PCM units and no fitted gain/delay.
    // A frozen-polynomial Schur test cannot certify the changing integer IIR.
    auto input=[&](int at)->int {
        if(at<0)return s.previousInput[172+at];
        return at<int(reference.size())?reference[at]:s.lookahead[at-reference.size()];
    };
    for(int at=0;at<int(reference.size());at+=160) {
        const int end=std::min(int(reference.size()),at+160),n=end-at;
        const int begin=std::max(s.continuation?-160:0,at-160);
        const int stop=std::min(int(reference.size()+s.lookahead.size()),end+160),m=stop-begin;
        uint64_t source=0,output=0;int originalClips=0,clips=0;
        for(int i=begin;i<stop;++i){int64_t x=input(i);source+=x*x;}
        for(int i=at;i<end;++i) {
            const int64_t x=reference[i],y=actual[i];output+=y*y;
            originalClips+=std::abs(x)>=32766;clips+=std::abs(y)>=32766;
        }
        source=std::max(source,uint64_t(m)*64*64);
        if(output*uint64_t(m)>16*source*n || (clips>originalClips&&output*uint64_t(m)>4*source*n)) {
            if(firstBad)*firstBad=at;return false;
        }
    }
    return true;
}
bool safeSynthesisSpectrum(const Pcm& reference,const Pcm& actual,int* firstBad) {
    if(reference.empty()||reference.size()!=actual.size())return false;
    // Detect source energy replaced by unrelated bands, independently of gain
    // and phase. Broad bands and a generous joint gate tolerate ordinary lossy
    // noise while catching moderate-level off-band oscillation as well.
    double window[512];
    for(int i=0;i<512;++i)window[i]=.5-.5*std::cos(6.28318530717958647692*i/511);
    for(int start=0;start+512<=int(reference.size());start+=256) {
        double source[512],output[512],a[257],b[257],x[32]={},y[32]={};
        double energy=0;
        for(int i=0;i<512;++i) {
            energy+=double(reference[start+i])*reference[start+i];
            source[i]=reference[start+i]*window[i];output[i]=actual[start+i]*window[i];
        }
        if(energy<=512.*64*64)continue;
        periodogram(source,512,a,512);periodogram(output,512,b,512);
        double totalSource=0,totalOutput=0;
        for(int k=0;k<=256;++k) {
            const int band=std::min(31,k/8);const double weight=k==0||k==256?1:2;
            x[band]+=a[k]*weight;y[band]+=b[k]*weight;
            totalSource+=a[k]*weight;totalOutput+=b[k]*weight;
        }
        if(totalSource<=0||totalOutput<=0)continue;
        double overlap=0,unsupported=0;
        for(int k=0;k<32;++k) {
            overlap+=std::sqrt(x[k]/totalSource*y[k]/totalOutput);
            if(x[k]<.005*totalSource)unsupported+=y[k];
        }
        if(1-overlap>.5&&unsupported>.35*totalOutput) {
            if(firstBad)*firstBad=start;return false;
        }
    }
    return true;
}
double emphasizedAt(const Stream& s,const Pcm& reference,int at) {
    auto sample=[&](int i)->double {
        if(i<0)return s.continuation && i>=-172?s.previousInput[172+i]:0;
        if(i<int(reference.size()))return reference[i];
        return i-int(reference.size())<int(s.lookahead.size())?s.lookahead[i-reference.size()]:0;
    };
    return sample(at)/2.0-s.pre*(sample(at-1)/2.0)/16384;
}
double residualBefore(const Stream& s,const Pcm& reference,int at) {
    if(!s.continuation || at<-145 || at>=0)return 0;
    double value=emphasizedAt(s,reference,at);
    for(int k=0;k<10;++k)value+=s.previousCoefficients[(160+at)/20][k]*emphasizedAt(s,reference,at-k-1)/4096;
    return value;
}
uint64_t sse(const Pcm& target, const Pcm& actual, int start) {
    uint64_t sum = 0;
    for (size_t j = 0; j < actual.size(); ++j) { int64_t d = int(target[start+j])-int(actual[j]); sum += d*d; }
    return sum;
}
Pcm pwm(const Pcm& input) {
    Pcm out(input.size());
    for (size_t j = 0; j < input.size(); ++j) {
        int q14 = (int(input[j])+1)>>1;
        out[j] = (clamp(128+((q14*130+8192)>>14),0,255)-128)*256;
    }
    return out;
}
Stream fitSeed(const Pcm& reference,int profile,int rate,int pre,bool zeroScale,double bandwidth,const Stream* context,SeedEncoder* encoder,SeedFitStatus* status) {
    if(status)*status=SeedFitStatus::Failure;
    auto& kernel=encoder?*encoder:defaultSeedEncoder();
    auto rejected=[&]() {
        if(status && kernel.failure==-8)*status=SeedFitStatus::Unsafe;
        return Stream{};
    };
    if(reference.size()>kernel.reservedSamples)return Stream{};
    Stream s=context?*context:Stream{};s.samples=reference.size();s.profile=profile;s.rate=rate;s.pre=pre;
    // Workspace was reserved by the public entry point before any adaptive
    // allocations. Avoid moving it while callers retain views into WASM memory.
    memcpy(kernel.source,reference.data(),reference.size()*2);
    LpxSeedContext history;
    if(context) {
        if(s.lookahead.size()>48 || reference.size()+(s.lookahead.empty()?0:48)>kernel.reservedSamples
            || (!s.lookahead.empty() && reference.size()%320))return Stream{};
        if(!s.lookahead.empty()) {
            std::fill(kernel.source+reference.size(),kernel.source+reference.size()+48,0);
            memcpy(kernel.source+reference.size(),s.lookahead.data(),s.lookahead.size()*2);
        }
        memcpy(history.h,s.initial.h,sizeof(history.h));memcpy(history.ring,s.initial.ring,sizeof(history.ring));history.dd=s.initial.dd;
        history.continuation=s.continuation;history.lookahead=s.lookahead.empty()?0:48;history.lastSample=s.previousInput.back();history.accuracy=s.accuracy;
        for(int at=-48;at<0;++at)history.emphasized[at+48]=emphasizedAt(s,reference,at);
        for(int at=-145;at<0;++at)history.residual[at+145]=residualBefore(s,reference,at);
        const int shift=profile==4?5:4;
        for(int k=0;k<10;++k)history.previousVector[k]=(s.previousSpectrum[k]<<shift)+(1<<(shift-1));
    }
    const int frames=(s.samples+319)/320;
    std::vector<uint8_t> safety(s.accuracy?frames:0,0);
    std::vector<uint8_t> orders(s.accuracy?frames:0,10);
    Stream bestRecovery;double bestRecoveryScore=HUGE_VAL;
    std::unique_ptr<FullBandContext> recoveryQuality;
    bool expandedRecovery=false;int recoveryPass=0;
    for(int attempt=0,fits=0;fits<(s.accuracy?32:1);++attempt,++fits) {
        history.spectralSafety=s.accuracy?safety.data():nullptr;
        history.analysisOrder=s.accuracy?orders.data():nullptr;
        // The same safety recovery for every accuracy alphabet: retain the
        // ordinary analysis when safe, otherwise retry the unexpanded stable
        // predictor before sacrificing spectral detail through regularization.
        const double analysis=attempt>=5?1.0:bandwidth;
        const int blocks=kernel.seedBegin(s.samples,profile,rate,pre,zeroScale,analysis,context?&history:nullptr);
        if(blocks<1)return rejected();
        for(int i=0;i<blocks;++i)if(kernel.step()<0)return rejected();
        const auto view=kernel.view();if(!view.valid)return rejected();
        s.spectra.resize(frames);s.parameters.resize(frames*2);s.pulses.resize(frames*16);s.extras.assign(frames*8,Pulse{{-1,0}});
        for(int f=0;f<frames;++f)for(int k=0;k<10;++k)s.spectra[f][k]=view.spectra[f][k];
        for(int b=0;b<frames*2;++b)for(int k=0;k<3;++k)s.parameters[b][k]=view.params[b][k];
        for(int p=0;p<frames*16;++p)for(int k=0;k<2;++k)s.pulses[p][k]=view.pulses[p][k];
        if(!s.accuracy) {if(status)*status=SeedFitStatus::Success;return s;}
        int bad=0;
        const auto output=render(s);
        const bool safe=safeSynthesisLevel(s,reference,output,&bad)&&safeSynthesisSpectrum(reference,output,&bad);
        if(safe) {
            if(attempt==0||attempt>=5) {if(status)*status=SeedFitStatus::Success;return s;}
            // A two-pole recovery can retain a single ring yet lose another
            // legal partial. Compare every bounded model-order alternative,
            // with actual-rate magnitude and temporal errors, before choosing.
            if(!recoveryQuality)recoveryQuality.reset(new FullBandContext(reference,rate));
            const auto measured=recoveryQuality->measure(output);
            const double score=measured.balancedError[0]+measured.balancedTemporalError[0]
                +measured.balancedError[1]+measured.balancedTemporalError[1];
            if(score<bestRecoveryScore) {bestRecovery=s;bestRecoveryScore=score;}
        }
        if(attempt<4) {
            // A simple resonator must not be forced into a poorly quantized
            // high-order model. Change only the source-error neighborhood;
            // retain the same ten-LSF syntax and original carried state.
            const int nextOrder=2*(attempt+1);
            for(auto& order:orders)if(order!=10)order=nextOrder;
            if(!safe)for(int f=std::max(0,bad/320-8);f<=std::min(frames-1,bad/320+8);++f) {
                if(attempt>0&&orders[f]==10)expandedRecovery=true;
                orders[f]=nextOrder;
            }
            continue;
        }
        if(attempt==4) {
            if(!safe)for(int f=std::max(0,bad/320-8);f<=std::min(frames-1,bad/320+8);++f) {
                if(orders[f]==10)expandedRecovery=true;
                orders[f]=8;
            }
            // Enlarging the source-error region changes every model-order
            // candidate. Revisit the complete bounded set on the enlarged
            // mask, rather than retaining an obsolete rejection of order2.
            if(expandedRecovery&&++recoveryPass<3) {
                expandedRecovery=false;
                for(auto& order:orders)if(order!=10)order=2;
                attempt=0;continue;
            }
            if(bestRecovery.samples) {if(status)*status=SeedFitStatus::Success;return bestRecovery;}
            std::fill(orders.begin(),orders.end(),10);continue;
        }
        // Replay from the exact original carried state; never splice a reset
        // waveform. First localize repairs around the first growth transition.
        for(auto& strength:safety)if(strength)strength=std::min(4,int(strength)+1);
        for(int f=std::max(0,bad/320-8);f<=std::min(frames-1,bad/320+2);++f)
            if(!safety[f])safety[f]=1;
    }
    if(status)*status=SeedFitStatus::Unsafe;
    return Stream{};
}
}
