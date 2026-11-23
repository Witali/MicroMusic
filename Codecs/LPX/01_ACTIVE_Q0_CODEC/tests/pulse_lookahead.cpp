// Native contract check for the host-only fixed-width pairwise operator.
#include "LpxPulseLookahead.h"
#include "LpxAdaptiveController.h"
#include <cstdio>

static lpx::Stream fixture(int n,int profile) {
    lpx::Stream s;s.samples=n;s.profile=profile;s.pre=0;
    const int frames=(n+319)/320;
    lpx::Spectrum spectrum;
    for(int j=0;j<10;++j)spectrum[j]=profile==4?1+3*j:3+5*j;
    s.spectra.assign(frames,spectrum);
    s.parameters.assign(frames*2,lpx::Parameters{{18,18,0}});
    s.pulses.assign(frames*16,lpx::Pulse{{0,-8}});
    s.extras.assign(frames*8,lpx::Pulse{{-1,0}});
    return s;
}
static bool gate(const lpx::Measurement& a,const lpx::Measurement& b) {
    return a.score<=b.score+1e-12 && lpx::noRegression(a.quality,b.quality)
        && a.clipped<=b.clipped && a.diagnostic[0].within>=b.diagnostic[0].within
        && a.diagnostic[1].within>=b.diagnostic[1].within;
}
int main() {
    int cases=0;
    for(int profile : {4,6})for(int n : {1,19,20,21,39,40,41,159,160,161,319,320,321,65537}) {
        auto input=fixture(n,profile),target=input;
        target.pulses[0]=lpx::Pulse{{n>17?18:0,profile==4?8:7}};
        target.pulses[1]=lpx::Pulse{{9,profile==4?8:7}};
        auto reference=lpx::render(target);lpx::QualityContext context(reference);
        const auto originalBytes=lpx::packV9(input);
        const auto originalPcm=lpx::render(input);
        const auto baseline=context.measure(originalPcm);
        for(bool finalBudget : {false,true}) {
            int cap=finalBudget?originalBytes.size():lpx::compactBytes(input);
            auto result=lpx::refinePulseLookahead(input,context,cap,finalBudget);
            auto actual=lpx::render(result.selected);
            if(lpx::packV9(input)!=originalBytes)return 1;
            if(lpx::packV9(result.selected).size()!=originalBytes.size())return 2;
            if(result.selected.spectra!=input.spectra || result.selected.parameters!=input.parameters
                || result.selected.extras!=input.extras || result.selected.samples!=n
                || result.selected.pre!=input.pre || result.selected.bright!=input.bright
                || result.selected.rate!=input.rate || result.selected.profile!=profile)return 3;
            if(!gate(context.measure(actual),baseline))return 4;
            if(!lpx::verifyStream(result.selected,actual))return 5;
            if(result.localEvaluations>246000 || result.fullEvaluations>4)return 6;
            for(const auto& candidate:result.alternatives) {
                auto pcm=lpx::render(candidate);
                if(!gate(context.measure(pcm),baseline)||!lpx::verifyStream(candidate,pcm))return 7;
            }
            auto noFit=lpx::refinePulseLookahead(input,context,cap-1,finalBudget);
            if(lpx::packV9(noFit.selected)!=originalBytes || noFit.localEvaluations || noFit.fullEvaluations)return 8;
            ++cases;
        }
    }
    std::printf("PASS: %d pulse-lookahead tail, cap, protected-input, complete-gate, Long and native-output contracts.\n",cases);
}
