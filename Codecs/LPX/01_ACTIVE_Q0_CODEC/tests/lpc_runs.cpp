// Exercise the private coefficient-slice seam without exporting runtime APIs.
#include "LpxLpcRefine.cpp"
#include "LpxAdaptiveController.h"
#include <cstdio>

static lpx::Stream fixture(int n,int profile,int rate) {
    lpx::Stream s;s.samples=n;s.profile=profile;s.rate=rate;s.pre=8192;s.bright=4096;
    const int frames=(n+319)/320;lpx::Spectrum a,b;
    for(int i=0;i<10;++i)a[i]=profile==4?1+3*i:3+5*i;b=a;++b[4];
    for(int f=0;f<frames;++f)s.spectra.push_back(f>=frames/3&&f<2*frames/3?b:a);
    s.parameters.assign(frames*2,lpx::Parameters{{18,95,10}});
    s.pulses.assign(frames*16,lpx::Pulse{{0,-8}});
    s.extras.assign(frames*8,lpx::Pulse{{-1,0}});s.extras[0]=lpx::Pulse{{7,2}};
    return s;
}
int main() {
    int cases=0,proposals=0,slices=0;
    for(int profile:{4,6})for(int rate:{8000,12000,16000})
        for(int n:{1,19,20,21,39,40,41,319,320,321,1027,65537}) {
        const auto input=fixture(n,profile,rate);auto target=input;
        const auto originalBytes=lpx::packV9(input);
        int last=1;while(last<int(input.spectra.size())&&input.spectra[last]==input.spectra[0])++last;
        for(int f=0;f<last;++f)++target.spectra[f][5];
        const auto reference=lpx::render(target);
        const auto originalCo=lpx::coefficientTrace(input);
        for(int frame=0;frame<int(input.spectra.size());++frame)if(!frame||input.spectra[frame]!=input.spectra[frame-1]) {
            auto changed=input;int endFrame=frame+1;while(endFrame<int(input.spectra.size())&&input.spectra[endFrame]==input.spectra[frame])++endFrame;
            for(int f=frame;f<endFrame;++f)++changed.spectra[f][5];
            auto local=originalCo;const auto full=lpx::coefficientTrace(changed);
            const int start=frame*320,end=std::min(n,start+1280);
            lpx::localCoefficients(changed,start,end,local);
            for(int i=start/20;i<(end+19)/20;++i)if(local[i]!=full[i])return 1;
            lpx::SynthesisState prefix;lpx::advance(input,originalCo,0,start,prefix);
            const auto actual=lpx::advance(changed,local,start,end,prefix),complete=lpx::render(changed);
            if(!std::equal(actual.begin(),actual.end(),complete.begin()+start))return 2;
            ++slices;
        }
        for(bool finalBudget:{false,true}) {
            const int originalCost=finalBudget?int(originalBytes.size()):lpx::compactBytes(input),cap=originalCost+8;
            const auto result=lpx::proposeLpcRuns(input,reference,cap,finalBudget);
            if(lpx::packV9(input)!=originalBytes)return 3;
            if(result.runs>4||result.proposals.size()>8||result.spectralEvaluations>80
                ||result.pulseEvaluations>1536||result.synthesizedSamples>2080000)return 4;
            for(const auto& candidate:result.proposals) {
                if((finalBudget?int(lpx::packV9(candidate).size()):lpx::compactBytes(candidate))>cap)return 5;
                if(candidate.parameters!=input.parameters||candidate.extras!=input.extras||candidate.pre!=input.pre
                    ||candidate.bright!=input.bright||candidate.profile!=profile||candidate.rate!=rate||candidate.samples!=n)return 6;
                int changedRuns=0;
                for(int first=0;first<int(input.spectra.size());) {
                    int last=first+1;while(last<int(input.spectra.size())&&input.spectra[last]==input.spectra[first])++last;
                    if(candidate.spectra[first]!=input.spectra[first]) {
                        ++changedRuns;int differences=0;
                        for(int k=0;k<10;++k)if(candidate.spectra[first][k]!=input.spectra[first][k]) {
                            ++differences;if(std::abs(candidate.spectra[first][k]-input.spectra[first][k])!=1)return 7;
                        }
                        if(differences!=1)return 8;
                        for(int f=first;f<last;++f)if(candidate.spectra[f]!=candidate.spectra[first])return 9;
                    } else for(int f=first;f<last;++f)if(candidate.spectra[f]!=input.spectra[f])return 10;
                    first=last;
                }
                if(changedRuns!=1)return 11;
                for(const auto& spectrum:candidate.spectra)if(!lpx::legalSpectrum(spectrum,profile))return 12;
                if(!lpx::verifyStream(candidate,lpx::render(candidate)))return 13;
                ++proposals;
            }
            const auto noFit=lpx::proposeLpcRuns(input,reference,originalCost-1,finalBudget);
            if(!noFit.proposals.empty()||noFit.spectralEvaluations||noFit.pulseEvaluations)return 14;
            ++cases;
        }
    }
    if(!proposals)return 15;
    std::printf("PASS: %d LPC-run cap/profile/rate/tail/Long cases, %d exact coefficient/prefix slices, %d legal unguarded proposals.\n",cases,slices,proposals);
}
