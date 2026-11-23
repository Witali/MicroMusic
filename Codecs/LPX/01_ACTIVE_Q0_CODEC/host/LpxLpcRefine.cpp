// Bounded quantized LSF-run proposals, with optional local pulse adaptation.
// Local magnitude/time losses rank proposals only; they do not admit output.
#include "LpxLpcRefine.h"
#include "LpxFullBand.h"
#include <algorithm>
#include <cstdlib>
#include <tuple>
#include <utility>

namespace lpx {
namespace {
constexpr int maxRuns=4, horizon=1280, shortlist=2, pulseSpan=160;
struct Run { int first,last;uint64_t error=0; };
struct Shape { Spectrum spectrum;double loss;int field,delta; };
bool legalSpectrum(const Spectrum& spectrum,int profile) {
    for(int i=0;i<10;++i)
        if(spectrum[i]<0||spectrum[i]>=(profile==4?32:64)||(i&&spectrum[i]<=spectrum[i-1]))return false;
    return true;
}
void setRun(Stream& stream,const Run& run,const Spectrum& spectrum) {
    std::fill(stream.spectra.begin()+run.first,stream.spectra.begin()+run.last,spectrum);
}
// One preceding spectrum reproduces the decoder's interpolation at the run
// boundary. The extra leading 320 samples are metadata context, never audio.
void localCoefficients(const Stream& stream,int start,int end,std::vector<Coefficients>& output) {
    Stream local;local.profile=stream.profile;local.samples=320+end-start;
    local.spectra.resize((local.samples+319)/320);
    for(int i=0;i<int(local.spectra.size());++i) {
        int frame=clamp(start/320+i-1,0,int(stream.spectra.size())-1);
        local.spectra[i]=stream.spectra[frame];
    }
    const auto coefficients=coefficientTrace(local);
    std::copy(coefficients.begin()+16,coefficients.end(),output.begin()+start/20);
}
double localScore(const FullBandContext& context,const Pcm& pcm) {
    const auto measured=context.measure(pcm);
    return measured.balancedError[0]+measured.balancedError[1]
        +measured.balancedTemporalError[0]+measured.balancedTemporalError[1];
}
bool sameBytes(const Stream& a,const Stream& b) { return packV9(a)==packV9(b); }
}
LpcRunProposals proposeLpcRuns(const Stream& input,const Pcm& reference,int cap,bool finalV9Budget) {
    LpcRunProposals result;
    if(input.samples<1||size_t(input.samples)!=reference.size()||(input.profile!=4&&input.profile!=6)
        ||(input.rate!=8000&&input.rate!=12000&&input.rate!=16000))return result;
    const int frames=(input.samples+319)/320;
    if(input.spectra.size()!=size_t(frames)||input.parameters.size()!=size_t(frames*2)
        ||input.pulses.size()!=size_t(frames*16)||input.extras.size()!=size_t(frames*8))return result;
    for(const auto& spectrum:input.spectra)if(!legalSpectrum(spectrum,input.profile))return result;
    const auto bytes=[&](const Stream& stream) { return finalV9Budget?int(packV9(stream).size()):compactBytes(stream); };
    if(bytes(input)>cap)return result;
    const auto baselineCo=coefficientTrace(input);auto co=baselineCo;const auto baselinePcm=render(input);
    std::vector<Run> order;
    for(int first=0;first<frames;) {
        int last=first+1;while(last<frames&&input.spectra[last]==input.spectra[first])++last;
        Run run;run.first=first;run.last=last;
        for(int at=first*320;at<std::min(input.samples,last*320);++at) {
            int64_t difference=int(reference[at])-int(baselinePcm[at]);run.error+=uint64_t(difference*difference);
        }
        order.push_back(run);first=last;
    }
    std::sort(order.begin(),order.end(),[](const Run& a,const Run& b) {return a.error!=b.error?a.error>b.error:a.first<b.first;});
    if(order.size()>maxRuns)order.resize(maxRuns);
    std::sort(order.begin(),order.end(),[](const Run& a,const Run& b) {return a.first<b.first;});
    SynthesisState prefix;int cursor=0;
    for(const auto& run:order) {
        const int start=run.first*320,end=std::min(input.samples,start+horizon);
        while(cursor<start) {int stop=std::min(start,cursor+4096);advance(input,baselineCo,cursor,stop,prefix);cursor=stop;}
        ++result.runs;
        Pcm source(reference.begin()+start,reference.begin()+end),initial(baselinePcm.begin()+start,baselinePcm.begin()+end);
        FullBandContext context(source,input.rate);const double baselineLoss=localScore(context,initial);
        if(!baselineLoss)continue;
        const auto originalSpectrum=input.spectra[run.first];Stream trial=input;std::vector<Shape> shapes;
        for(int field=0;field<10;++field)for(int delta:{-1,1}) {
            auto spectrum=originalSpectrum;spectrum[field]+=delta;
            if(!legalSpectrum(spectrum,input.profile))continue;
            setRun(trial,run,spectrum);if(bytes(trial)>cap)continue;
            localCoefficients(trial,start,end,co);auto state=prefix;
            const auto pcm=advance(trial,co,start,end,state);++result.spectralEvaluations;result.synthesizedSamples+=end-start;
            shapes.push_back({spectrum,localScore(context,pcm),field,delta});
        }
        std::sort(shapes.begin(),shapes.end(),[](const Shape& a,const Shape& b) {
            return std::tie(a.loss,a.field,a.delta)<std::tie(b.loss,b.field,b.delta);
        });
        if(shapes.size()>shortlist)shapes.resize(shortlist);
        Stream bestRaw,bestJoint;double rawLoss=baselineLoss,jointLoss=baselineLoss;
        for(const auto& shape:shapes) {
            trial=input;setRun(trial,run,shape.spectrum);localCoefficients(trial,start,end,co);
            if(shape.loss<rawLoss) {bestRaw=trial;rawLoss=shape.loss;}
            auto before=prefix,state=prefix;auto trajectory=advance(trial,co,start,end,state);result.synthesizedSamples+=end-start;
            double loss=shape.loss;const int stop=std::min(input.samples,start+pulseSpan);
            for(int at=start;at<stop;at+=20) {
                const int index=at/20;const auto original=trial.pulses[index];auto best=original;auto bestTrajectory=trajectory;
                for(int position=std::max(0,original[0]-2);position<std::min({20,input.samples-at,original[0]+3});++position) {
                    if(input.profile==4&&position%5==2)continue;
                    for(int amplitude=-8;amplitude<=(input.profile==4?8:7);++amplitude) {
                        if(input.profile==4?(amplitude!=-8&&amplitude!=8):std::abs(amplitude-original[1])>2)continue;
                        if(Pulse{{position,amplitude}}==original)continue;
                        trial.pulses[index]=Pulse{{position,amplitude}};auto after=before;
                        const auto future=advance(trial,co,at,end,after);auto pcm=trajectory;
                        std::copy(future.begin(),future.end(),pcm.begin()+at-start);
                        const double candidateLoss=localScore(context,pcm);++result.pulseEvaluations;result.synthesizedSamples+=end-at;
                        if(candidateLoss<loss) {loss=candidateLoss;best=trial.pulses[index];bestTrajectory=std::move(pcm);}
                    }
                }
                trial.pulses[index]=best;trajectory=std::move(bestTrajectory);
                const int next=std::min(stop,at+20);advance(trial,co,at,next,before);result.synthesizedSamples+=next-at;
            }
            if(loss<jointLoss&&bytes(trial)<=cap) {bestJoint=trial;jointLoss=loss;}
        }
        for(const auto* candidate:{&bestRaw,&bestJoint})if(candidate->samples&&bytes(*candidate)<=cap) {
            bool duplicate=sameBytes(*candidate,input);
            for(const auto& previous:result.proposals)duplicate|=sameBytes(previous,*candidate);
            if(!duplicate)result.proposals.push_back(*candidate);
        }
    }
    return result;
}
}
