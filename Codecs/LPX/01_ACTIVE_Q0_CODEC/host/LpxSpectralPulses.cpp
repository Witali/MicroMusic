// Bounded, native-rate magnitude/time excitation proposals. Constants were
// frozen on public tuning material; complete-output admission belongs to the
// common controller, not this local proposal generator.
#include "LpxSpectralPulses.h"
#include "LpxFullBand.h"
#include "LpxQuality.h"
#include <algorithm>
#include <cmath>
#include <utility>

namespace lpx {
namespace {
constexpr int maxRegions=4, horizon=768, pulseSpan=160;
constexpr int fftSamples=512, hopSamples=256, scoreFrames=3;
struct RegionView {
    const Pcm& original;
    int rate,begin,end;
    double window[fftSamples],source[scoreFrames][257],denominator[8];
    RegionView(const Pcm& reference,const Pcm& pcm,int sampleRate,int start,const FullBandMeasurement& full):
        original(pcm),rate(sampleRate),begin(start),end(std::min(int(reference.size()),start+horizon)) {
        double total=0;for(int b=0;b<rate/2000;++b)total+=full.sourcePower[b];
        for(int b=0;b<rate/2000;++b)denominator[b]=total>0?std::max(full.sourcePower[b],total*1e-4):1.;
        for(int i=0;i<fftSamples;++i)window[i]=.5-.5*std::cos(2*3.14159265358979323846*i/511);
        for(int f=0;f<scoreFrames;++f) {
            double input[fftSamples],power[257];int at=begin-hopSamples+f*hopSamples;
            for(int i=0;i<fftSamples;++i)input[i]=at+i>=0&&at+i<int(reference.size())?reference[at+i]*window[i]:0.;
            periodogram(input,fftSamples,power,fftSamples);
            for(int k=0;k<=256;++k)source[f][k]=std::sqrt(power[k]);
        }
    }
    double score(const Pcm& patch,int patchStart) const {
        double loss=0;
        for(int path=0;path<2;++path) {
            double previous[257]={};
            for(int f=0;f<scoreFrames;++f) {
                double input[fftSamples],power[257];int at=begin-hopSamples+f*hopSamples;
                for(int i=0;i<fftSamples;++i) {
                    int pos=at+i,value=pos>=0&&pos<int(original.size())?
                        (pos>=patchStart&&pos<patchStart+int(patch.size())?patch[pos-patchStart]:original[pos]):0;
                    if(path) { int q14=(value+1)>>1;value=(clamp(128+((q14*130+8192)>>14),0,255)-128)*256; }
                    input[i]=value*window[i];
                }
                periodogram(input,fftSamples,power,fftSamples);
                for(int k=0;k<=256;++k) {
                    int band=std::min(rate/2000-1,k*rate/512000);
                    double residual=source[f][k]-std::sqrt(power[k]);
                    double weighted=(k==0||k==256?1:2)/denominator[band];
                    loss+=weighted*residual*residual;
                    if(f) { double change=residual-previous[k];loss+=weighted*change*change; }
                    previous[k]=residual;
                }
            }
        }
        return loss;
    }
};
template<class F> void legalPulses(int profile,F evaluate) {
    for(int position=0;position<20;++position) {
        if(profile==4&&position%5==2)continue;
        for(int amplitude=-8;amplitude<=(profile==4?8:7);++amplitude) {
            if(profile==4&&amplitude!=-8&&amplitude!=8)continue;
            if(!amplitude&&position)continue;
            evaluate(Pulse{{position,amplitude}});
        }
    }
}
struct Patch { int start;std::vector<Pulse> pulses;double benefit; };
}
SpectralPulseProposals proposeSpectralPulses(const Stream& input,const Pcm& reference) {
    SpectralPulseProposals result;
    if(input.samples<1 || size_t(input.samples)!=reference.size()
        || (input.profile!=4&&input.profile!=6)
        || (input.rate!=8000&&input.rate!=12000&&input.rate!=16000))return result;
    const int frames=(input.samples+319)/320;
    if(input.spectra.size()!=size_t(frames)||input.parameters.size()!=size_t(frames*2)
        || input.pulses.size()!=size_t(frames*16)||input.extras.size()!=size_t(frames*8))return result;
    const auto bytes=packV9(input).size();const int compact=compactBytes(input);
    const auto co=coefficientTrace(input);const auto originalPcm=render(input);
    FullBandContext context(reference,input.rate);const auto source=context.measure(originalPcm);
    std::vector<std::pair<double,int>> order;
    for(int at=0;at<input.samples;at+=hopSamples) {
        RegionView view(reference,originalPcm,input.rate,at,source);
        order.push_back({view.score({},input.samples),at});
    }
    std::sort(order.begin(),order.end(),[](const std::pair<double,int>& a,const std::pair<double,int>& b) {
        return a.first!=b.first?a.first>b.first:a.second<b.second;
    });
    std::vector<int> anchors;
    for(const auto& item:order) {
        bool overlap=false;for(int old:anchors)overlap|=std::abs(old-item.second)<horizon;
        if(!overlap)anchors.push_back(item.second);
        if(anchors.size()==maxRegions)break;
    }
    std::sort(anchors.begin(),anchors.end());result.regions=anchors.size();
    SynthesisState prefix;int cursor=0;std::vector<Patch> patches;
    for(int anchor:anchors) {
        const int start=anchor/20*20,stop=std::min(input.samples,start+pulseSpan);
        // Recover each original prefix once, with constant-sized gap buffers.
        while(cursor<start) {int end=std::min(start,cursor+4096);advance(input,co,cursor,end,prefix);cursor=end;}
        RegionView view(reference,originalPcm,input.rate,anchor,source);const int end=view.end;
        Stream working=input;auto before=prefix,trajectoryState=prefix;
        auto trajectory=advance(working,co,start,end,trajectoryState);
        const double initialLoss=view.score(trajectory,start);double loss=initialLoss;
        for(int at=start;at<stop;at+=20) {
            const int index=at/20;const auto old=working.pulses[index];auto best=old;auto bestTrajectory=trajectory;
            legalPulses(input.profile,[&](Pulse pulse) {
                if(pulse==old)return;working.pulses[index]=pulse;auto state=before;
                const auto future=advance(working,co,at,end,state);auto trial=trajectory;
                std::copy(future.begin(),future.end(),trial.begin()+at-start);
                const double score=view.score(trial,start);++result.localEvaluations;
                if(score<loss) {loss=score;best=pulse;bestTrajectory=std::move(trial);}
            });
            working.pulses[index]=best;trajectory=std::move(bestTrajectory);result.changedPulses+=best!=old;
            advance(working,co,at,std::min(stop,at+20),before);
        }
        if(loss<initialLoss) {
            Patch patch;patch.start=start;patch.benefit=initialLoss-loss;
            patch.pulses.assign(working.pulses.begin()+start/20,working.pulses.begin()+(stop+19)/20);
            patches.push_back(std::move(patch));
        }
    }
    std::sort(patches.begin(),patches.end(),[](const Patch& a,const Patch& b) {
        return a.benefit!=b.benefit?a.benefit>b.benefit:a.start<b.start;
    });
    std::vector<int> counts;
    for(int count:{int(patches.size()),std::min(2,int(patches.size())),std::min(1,int(patches.size()))})
        if(count&&std::find(counts.begin(),counts.end(),count)==counts.end())counts.push_back(count);
    for(int count:counts) {
        Stream proposal=input;
        for(int i=0;i<count;++i)std::copy(patches[i].pulses.begin(),patches[i].pulses.end(),proposal.pulses.begin()+patches[i].start/20);
        if(packV9(proposal).size()==bytes&&compactBytes(proposal)==compact)result.proposals.push_back(std::move(proposal));
    }
    return result;
}
}
