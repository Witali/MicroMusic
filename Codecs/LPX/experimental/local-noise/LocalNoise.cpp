#include "LocalNoise.h"
#include "LpxAdaptiveController.h"
#include "LpxCandidateEvaluation.h"
#include "LpxFullBand.h"
#include "LpxQuality.h"
#include <algorithm>
#include <cmath>
#include <numeric>

namespace lpx {
namespace {
using namespace localnoise;
const std::array<double,FftSamples>& hann() {
    static const std::array<double,FftSamples> values=[] {
        std::array<double,FftSamples> result={};
        for(int i=0;i<FftSamples;++i)result[i]=.5-.5*std::cos(6.28318530717958647692*i/(FftSamples-1));
        return result;
    }();
    return values;
}
double binWeight(int bin) { return bin==0||bin==256?1.:2.; }

template<class Samples>
LocalNoiseMeasurement measureWindows(const std::vector<LocalNoiseWindow>& windows,
    QualityTarget target,int first,int count,Samples sample) {
    LocalNoiseMeasurement result;result.target=target;
    if(!validQualityTarget(target)||first<0||count<1||first>=int(windows.size()))return result;
    const int stop=std::min(int(windows.size()),first+count);
    for(int path=0;path<qualityPathCount(target);++path)result.magnitude[path]=result.interharmonic[path]=0;
    const auto& window=hann();
    for(int index=first;index<stop;++index) {
        const auto& source=windows[index];
        ++result.windows;result.voicedWindows+=source.voiced;result.quietWindows+=source.quiet;
        result.transientWindows+=source.transient;result.unsupportedWindows+=!source.supported;
        for(int path=0;path<qualityPathCount(target);++path) {
            double input[FftSamples],power[257];
            for(int i=0;i<FftSamples;++i)input[i]=sample(path,source.start+i)*window[i];
            periodogram(input,FftSamples,power,FftSamples);
            double magnitude=0,excess=0;
            for(int k=0;k<=256;++k) {
                const double difference=std::sqrt(power[k])-source.sourceMagnitude[k];
                magnitude+=binWeight(k)*difference*difference;
                if(source.interharmonic[k]&&difference>0)excess+=binWeight(k)*difference*difference;
            }
            result.magnitude[path]+=magnitude/source.normalization;
            result.interharmonic[path]+=excess/source.normalization;
        }
    }
    result.score=0;
    for(int path=0;path<qualityPathCount(target);++path) {
        result.magnitude[path]/=result.windows;result.interharmonic[path]/=result.windows;
        result.score+=result.magnitude[path]+NoiseWeight*result.interharmonic[path];
    }
    result.score/=qualityPathCount(target);result.valid=std::isfinite(result.score);
    return result;
}

uint64_t activeSse(const Pcm& reference,const Pcm& candidate,int start,QualityTarget target,
    uint64_t* pcmLoss=nullptr) {
    const uint64_t native=sse(reference,candidate,start);
    if(pcmLoss)*pcmLoss=native;
    return target==QualityTarget::Pwm?native+sse(reference,pwm(candidate),start):native;
}

bool validSpectrum(const Spectrum& spectrum,int profile) {
    for(int i=0;i<10;++i)if(spectrum[i]<0||spectrum[i]>=(profile==4?32:64)
        ||(i&&spectrum[i]<=spectrum[i-1]))return false;
    return true;
}
bool validInput(const Stream& stream,const Pcm& reference) {
    if(!validQualityTarget(stream.qualityTarget)||stream.samples<1||size_t(stream.samples)!=reference.size()
        ||(stream.profile!=4&&stream.profile!=6)||(stream.rate!=8000&&stream.rate!=12000&&stream.rate!=16000)
        ||stream.pre<0||stream.pre>16384||stream.bright<0||stream.bright>11469)return false;
    const size_t frames=1+(size_t(stream.samples)-1)/320;
    if(stream.spectra.size()!=frames||stream.parameters.size()!=frames*2
        ||stream.pulses.size()!=frames*16||stream.extras.size()!=frames*8||stream.lookahead.size()>48)return false;
    for(const auto& spectrum:stream.spectra)if(!validSpectrum(spectrum,stream.profile))return false;
    if(stream.continuation&&!validSpectrum(stream.previousSpectrum,stream.profile))return false;
    for(const auto& parameters:stream.parameters) {
        if(parameters[0]<0||parameters[0]>31||parameters[2]<0||parameters[2]>14||parameters[2]%2
            ||parameters[1]<0||parameters[1]>145||(parameters[2]&&parameters[1]<18))return false;
    }
    for(const auto& pulse:stream.pulses)if(pulse[0]<0||pulse[0]>=20
        ||(stream.profile==4?(pulse[0]%5==2||(pulse[1]!=-8&&pulse[1]!=8&&pulse[1]!=0))
                            :(pulse[1]<-8||pulse[1]>7)))return false;
    for(const auto& extra:stream.extras)if(extra[0]<-1||extra[0]>=40||extra[1]<-8||extra[1]>7)return false;
    for(int value:stream.initial.h)if(value<-32767||value>32767)return false;
    for(int value:stream.initial.ring)if(value<-32||value>31)return false;
    return stream.initial.dd>=-32767&&stream.initial.dd<=32767&&stream.initial.cc>=-16384&&stream.initial.cc<=16384;
}

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

struct Region { int start,end,firstWindow,count;double loss; };
struct Choice {
    Pulse first,second;
    uint64_t pcm=0,active=0,ordinal=0;
    double noise=std::numeric_limits<double>::infinity();
    Pcm output;
};
bool sseOrder(const Choice& a,const Choice& b) {
    if(a.active!=b.active)return a.active<b.active;
    if(a.pcm!=b.pcm)return a.pcm<b.pcm;
    return a.ordinal<b.ordinal;
}
void shortlist(std::vector<Choice>& choices,Choice candidate) {
    choices.push_back(std::move(candidate));
    std::stable_sort(choices.begin(),choices.end(),sseOrder);
    if(choices.size()>SseShortlist)choices.resize(SseShortlist);
}
void appendChoice(std::vector<Choice>& choices,const Choice& candidate) {
    for(const auto& old:choices)if(old.first==candidate.first&&old.second==candidate.second)return;
    choices.push_back(candidate);
}
struct Patch { int start;Pulse first,second;double benefit; };

// Exact original prefix snapshots: no region's unadmitted edits influence the
// candidates for another pair or another region.
void walkTo(const Stream& stream,const std::vector<Coefficients>& coefficients,
    int stop,int& cursor,SynthesisState& state) {
    while(cursor<stop) {
        const int end=std::min(stop,cursor+4096);
        advance(stream,coefficients,cursor,end,state);cursor=end;
    }
}

std::vector<Stream> bundles(const Stream& baseline,std::vector<Patch> patches,size_t bytes) {
    std::vector<Stream> proposals;
    std::stable_sort(patches.begin(),patches.end(),[](const Patch& a,const Patch& b) {
        return a.benefit!=b.benefit?a.benefit>b.benefit:a.start<b.start;
    });
    const int n=int(patches.size());std::vector<int> counts;
    for(int count:{n,(n+1)/2,(n+3)/4,1})if(count&&count<=n
        &&std::find(counts.begin(),counts.end(),count)==counts.end())counts.push_back(count);
    const int compact=compactBytes(baseline);
    for(int count:counts) {
        Stream proposal=baseline;
        for(int index=0;index<count;++index) {
            const auto& patch=patches[index];proposal.pulses[patch.start/20]=patch.first;
            if(patch.start+20<proposal.samples)proposal.pulses[patch.start/20+1]=patch.second;
        }
        const auto packed=packV9(proposal);
        if(packed.size()==bytes&&compactBytes(proposal)==compact)proposals.push_back(std::move(proposal));
    }
    return proposals;
}

Stream admit(const Stream& baseline,const Pcm& reference,const Pcm& baselinePcm,
    const std::vector<Stream>& proposals,LocalNoiseReport& report,bool noisePool) {
    Stream selected=baseline;double selectedScore=std::numeric_limits<double>::infinity();
    QualityContext quality(reference,true,baseline.rate,baseline.qualityTarget);
    FullBandContext bands(reference,baseline.rate,baseline.qualityTarget);
    CandidateEvaluation evaluation(reference,baseline.rate,true,baseline.qualityTarget);
    const auto floor=quality.measure(baselinePcm);const auto bandFloor=bands.measure(baselinePcm);
    const size_t bytes=packV9(baseline).size();
    auto& aggregate=noisePool?report.noiseSelection:report.sseSelection;
    for(const auto& proposal:proposals) {
        ++report.fullEvaluations;
        if(packV9(proposal).size()!=bytes) { ++report.rejectedSize;continue; }
        if(!stableLpcStream(proposal)) { ++report.rejectedStability;continue; }
        const auto output=render(proposal);
        if(!verifyStream(proposal,output)) { ++report.rejectedNative;continue; }
        if(!safeSynthesisLevel(proposal,reference,output)) { ++report.rejectedLevel;continue; }
        if(!safeSynthesisSpectrum(reference,output)) { ++report.rejectedSpectrum;continue; }
        const auto measured=quality.measure(output);const auto spectrum=bands.measure(output);
        if(!noRegression(measured.quality,floor.quality)) { ++report.rejectedQuality;continue; }
        if(!bands.accepts(spectrum,bandFloor)) { ++report.rejectedFullBand;continue; }
        bool oldNoise=true;
        for(int path=0;path<qualityPathCount(baseline.qualityTarget);++path)
            oldNoise&=std::isfinite(measured.noise[path])&&measured.noise[path]<=floor.noise[path]+1e-12;
        if(!oldNoise) { ++report.rejectedOldNoise;continue; }
        ProfileQualityReport one;
        const auto winner=selectQualityProposals(baseline,reference,{&proposal},one,true,int(bytes),&evaluation);
        aggregate.candidates+=one.candidates;aggregate.accepted+=one.accepted;aggregate.octaveRejected+=one.octaveRejected;
        aggregate.initialObjective=one.initialObjective;
        if(one.error) { aggregate.error=one.error;report.error=one.error;return baseline; }
        if(packV9(winner)==packV9(baseline)) { ++report.rejectedComplete;continue; }
        if(noisePool)++report.admittedNoiseProposals;else ++report.admittedSseProposals;
        if(one.finalObjective<selectedScore) { selected=winner;selectedScore=one.finalObjective; }
    }
    aggregate.finalObjective=std::isfinite(selectedScore)?selectedScore:aggregate.initialObjective;
    return selected;
}
}

LocalNoiseContext::LocalNoiseContext(const Pcm& source,int sampleRate,QualityTarget selectedTarget):
    reference(source),rate(sampleRate),target(selectedTarget) {
    if(source.empty()||!validQualityTarget(target)||(rate!=8000&&rate!=12000&&rate!=16000))return;
    const auto& window=hann();double windowPower=0;
    for(double value:window)windowPower+=value*value;
    const int frame=rate*80/1000;std::vector<double> analysis(frame);
    for(int start=-256;start<int(source.size());start+=HopSamples) {
        LocalNoiseWindow descriptor;descriptor.start=start;
        double input[FftSamples],power[257],weightedEnergy=0;
        for(int i=0;i<FftSamples;++i) {
            const int at=start+i;input[i]=(at>=0&&at<int(source.size())?source[at]:0)*window[i];
            weightedEnergy+=input[i]*input[i];
        }
        periodogram(input,FftSamples,power,FftSamples);double totalPower=0;
        for(int k=0;k<=256;++k) { descriptor.sourceMagnitude[k]=std::sqrt(power[k]);totalPower+=binWeight(k)*power[k]; }
        descriptor.normalization=std::max(totalPower,FftSamples*windowPower*QuietRms*QuietRms);
        descriptor.quiet=weightedEnergy<windowPower*QuietRms*QuietRms;
        const int analysisStart=start+256-frame/2;
        descriptor.supported=analysisStart>=0&&analysisStart+frame<=int(source.size());
        if(descriptor.supported) {
            double mean=0,rms=0;
            for(int i=0;i<frame;++i) { analysis[i]=source[analysisStart+i];mean+=analysis[i]; }
            mean/=frame;descriptor.period=estimatePeriod(analysis.data(),frame,rms,rate);descriptor.quiet=rms<QuietRms;
            double minimum=std::numeric_limits<double>::infinity(),maximum=0;
            for(int part=0;part<4;++part) {
                double energy=0;
                for(int i=part*frame/4;i<(part+1)*frame/4;++i) { const double value=analysis[i]-mean;energy+=value*value; }
                minimum=std::min(minimum,energy);maximum=std::max(maximum,energy);
            }
            descriptor.transient=!descriptor.quiet&&(minimum<=0||maximum>MaxSliceEnergyRatio*minimum);
            if(std::isfinite(descriptor.period)&&descriptor.period>0) {
                const int lag=int(descriptor.period);const double fraction=descriptor.period-lag;
                double xx=0,yy=0,xy=0;
                for(int i=0;i+lag+1<frame;++i) {
                    const double a=analysis[i]-mean,b=(analysis[i+lag]-mean)*(1-fraction)+(analysis[i+lag+1]-mean)*fraction;
                    xx+=a*a;yy+=b*b;xy+=a*b;
                }
                descriptor.periodicity=xx>0&&yy>0?xy/std::sqrt(xx*yy):0;
                const double frequency=rate/descriptor.period,halfWidth=std::min(1.5*rate/FftSamples,frequency/4);
                double harmonic=0,acPower=0;
                for(int k=1;k<=256;++k) {
                    const double binFrequency=double(k)*rate/FftSamples;
                    const int nearest=int(std::floor(binFrequency/frequency+.5));
                    const bool near=nearest>=1&&std::abs(binFrequency-nearest*frequency)<=halfWidth;
                    acPower+=binWeight(k)*power[k];if(near)harmonic+=binWeight(k)*power[k];
                    descriptor.interharmonic[k]=!near;
                }
                descriptor.harmonicFraction=acPower>0?harmonic/acPower:0;
                descriptor.voiced=!descriptor.quiet&&!descriptor.transient&&descriptor.periodicity>=MinPeriodicity
                    &&descriptor.harmonicFraction>=MinHarmonicFraction;
            }
        }
        if(!descriptor.voiced)descriptor.interharmonic.fill(0);
        descriptors.push_back(std::move(descriptor));
    }
}

LocalNoiseMeasurement LocalNoiseContext::measure(const Pcm& candidate) const {
    if(candidate.size()!=reference.size()) { LocalNoiseMeasurement invalid;invalid.target=target;return invalid; }
    Pcm fixed;if(target==QualityTarget::Pwm)fixed=pwm(candidate);
    return measureWindows(descriptors,target,0,int(descriptors.size()),[&](int path,int at) {
        return at>=0&&at<int(candidate.size())?(path?fixed[at]:candidate[at]):0;
    });
}

Stream refineLocalNoise(const Stream& baseline,const Pcm& reference,LocalNoiseReport& report,
    Stream* rawProposal,Stream* sseProposal,Stream* sseControl) {
    report=LocalNoiseReport{};
    if(rawProposal)*rawProposal=baseline;if(sseProposal)*sseProposal=baseline;if(sseControl)*sseControl=baseline;
    if(!validInput(baseline,reference)) { report.error=-1;return baseline; }
    if(!stableLpcStream(baseline)) { report.error=-2;return baseline; }
    const auto original=render(baseline);const auto packed=packV9(baseline);
    if(!verifyStream(baseline,original)||packed.empty()) { report.error=-3;return baseline; }
    const LocalNoiseContext noise(reference,baseline.rate,baseline.qualityTarget);
    const auto& windows=noise.analysis();Pcm originalFixed;
    if(baseline.qualityTarget==QualityTarget::Pwm)originalFixed=pwm(original);
    auto scorePatch=[&](const Pcm& patch,int start,const Region& region) {
        Pcm fixed;if(baseline.qualityTarget==QualityTarget::Pwm)fixed=pwm(patch);
        ++report.noiseEvaluations;
        return measureWindows(windows,baseline.qualityTarget,region.firstWindow,region.count,[&](int path,int at) {
            if(at<0||at>=baseline.samples)return 0;
            if(at>=start&&at<start+int(patch.size()))return int(path?fixed[at-start]:patch[at-start]);
            return int(path?originalFixed[at]:original[at]);
        }).score;
    };
    std::vector<Region> ordered;
    for(int index=0;index<int(windows.size());++index) {
        const int center=windows[index].start+256,start=center/40*40;
        if(start>=baseline.samples)continue;
        const int count=std::min(int(ScoreWindows),int(windows.size())-index);
        const int end=std::min(baseline.samples,windows[index+count-1].start+FftSamples);
        Region region{start,end,index,count,0};region.loss=scorePatch(Pcm{},baseline.samples,region);ordered.push_back(region);
    }
    std::stable_sort(ordered.begin(),ordered.end(),[](const Region& a,const Region& b) {
        return a.loss!=b.loss?a.loss>b.loss:a.start<b.start;
    });
    std::vector<Region> regions;
    for(const auto& region:ordered) {
        bool overlap=false;for(const auto& old:regions)overlap|=region.start<old.end&&old.start<region.end;
        if(!overlap)regions.push_back(region);if(regions.size()==MaxRegions)break;
    }
    std::sort(regions.begin(),regions.end(),[](const Region& a,const Region& b){return a.start<b.start;});
    report.regions=int(regions.size());
    const auto coefficients=coefficientTrace(baseline);auto prefix=baseline.initial;int cursor=0;
    std::vector<Patch> noisePatches,ssePatches;
    for(const auto& region:regions)for(int pair=0;pair<PairsPerRegion;++pair) {
        const int start=region.start+pair*40;if(start>=baseline.samples||start>=region.end)break;
        ++report.pairs;walkTo(baseline,coefficients,start,cursor,prefix);
        const int firstIndex=start/20;const auto first=baseline.pulses[firstIndex],second=baseline.pulses[firstIndex+1];
        Stream trial=baseline;uint64_t ordinal=0;
        auto evaluate=[&](Pulse a,Pulse b) {
            trial.pulses[firstIndex]=a;if(start+20<baseline.samples)trial.pulses[firstIndex+1]=b;
            Choice choice;choice.first=a;choice.second=b;choice.ordinal=ordinal++;
            auto state=prefix;choice.output=advance(trial,coefficients,start,region.end,state);
            choice.active=activeSse(reference,choice.output,start,baseline.qualityTarget,&choice.pcm);
            ++report.localEvaluations;++report.pcmSseEvaluations;++report.activeSseEvaluations;
            report.pwmSseEvaluations+=baseline.qualityTarget==QualityTarget::Pwm;
            report.synthesizedSamples+=region.end-start;return choice;
        };
        const Choice incumbent=evaluate(first,second);
        if(!incumbent.active)continue;
        Choice bestPcm=incumbent;std::vector<Choice> firstPool;shortlist(firstPool,incumbent);
        legalPulses(baseline.profile,[&](Pulse pulse) {
            if(pulse==first)return;auto choice=evaluate(pulse,second);
            if(choice.pcm<bestPcm.pcm)bestPcm=choice;shortlist(firstPool,std::move(choice));
        });
        appendChoice(firstPool,incumbent);appendChoice(firstPool,bestPcm);
        Choice bestNoise=incumbent;bestNoise.noise=scorePatch(incumbent.output,start,region);
        const double baselineNoise=bestNoise.noise;
        for(auto& choice:firstPool) {
            choice.noise=scorePatch(choice.output,start,region);
            if(choice.noise<bestNoise.noise)bestNoise=choice;
        }
        std::vector<Choice> firstChoices;appendChoice(firstChoices,incumbent);appendChoice(firstChoices,bestPcm);
        appendChoice(firstChoices,firstPool.front());appendChoice(firstChoices,bestNoise);
        std::vector<Choice> finalPool;shortlist(finalPool,incumbent);Choice finalPcm=incumbent;
        for(const auto& a:firstChoices) {
            auto visit=[&](Pulse b) {
                auto choice=evaluate(a.first,b);if(choice.pcm<finalPcm.pcm)finalPcm=choice;
                shortlist(finalPool,std::move(choice));
            };
            visit(second);
            if(start+20<baseline.samples)legalPulses(baseline.profile,[&](Pulse b){if(b!=second)visit(b);});
        }
        const auto bestActive=finalPool.front();appendChoice(finalPool,incumbent);appendChoice(finalPool,finalPcm);
        bestNoise=incumbent;bestNoise.noise=baselineNoise;
        for(auto& choice:finalPool) {
            choice.noise=scorePatch(choice.output,start,region);
            if(choice.noise<bestNoise.noise)bestNoise=choice;
        }
        if(bestNoise.noise<baselineNoise)noisePatches.push_back({start,bestNoise.first,bestNoise.second,baselineNoise-bestNoise.noise});
        if(bestActive.active<incumbent.active)ssePatches.push_back({start,bestActive.first,bestActive.second,double(incumbent.active-bestActive.active)});
    }
    report.noisePatches=int(noisePatches.size());report.ssePatches=int(ssePatches.size());
    const auto noiseBundles=bundles(baseline,std::move(noisePatches),packed.size());
    const auto sseBundles=bundles(baseline,std::move(ssePatches),packed.size());
    report.noiseProposals=int(noiseBundles.size());report.sseProposals=int(sseBundles.size());
    report.proposals=report.noiseProposals+report.sseProposals;
    double rawNoise=std::numeric_limits<double>::infinity();uint64_t rawSse=std::numeric_limits<uint64_t>::max();
    for(const auto& proposal:noiseBundles) {
        const auto output=render(proposal);const double score=noise.measure(output).score;
        if(score<rawNoise) { rawNoise=score;if(rawProposal)*rawProposal=proposal; }
    }
    for(const auto& proposal:sseBundles) {
        const auto output=render(proposal);const uint64_t score=activeSse(reference,output,0,baseline.qualityTarget);
        if(score<rawSse) { rawSse=score;if(sseProposal)*sseProposal=proposal; }
    }
    const auto selected=admit(baseline,reference,original,noiseBundles,report,true);
    const auto control=admit(baseline,reference,original,sseBundles,report,false);
    if(sseControl)*sseControl=control;
    report.selectedNoise=packV9(selected)!=packed;report.selectedSse=packV9(control)!=packed;
    report.accepted=report.selectedNoise;
    return selected;
}
}
