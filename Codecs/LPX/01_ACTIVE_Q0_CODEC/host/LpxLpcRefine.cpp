// Bounded quantized LSF-run proposals, with optional local pulse adaptation.
// Local magnitude/time losses rank proposals only; they do not admit output.
#include "LpxLpcRefine.h"
#include "LpxFullBand.h"
#include <algorithm>
#include <cmath>
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
    // P3's dead zone depends on the complete previously transmitted sequence,
    // not merely the preceding raw analysis frame. Resolve it before cropping.
    if(stream.accuracy==3) {
        auto canonical=canonicalAccuracy(stream);
        canonical.accuracy=0; // Do not quantize the synthetic context again.
        localCoefficients(canonical,start,end,output);
        return;
    }
    Stream local;local.qualityTarget=stream.qualityTarget;local.profile=stream.profile;local.samples=320+end-start;
    local.spectra.resize((local.samples+319)/320);
    for(int i=0;i<int(local.spectra.size());++i) {
        int frame=clamp(start/320+i-1,0,int(stream.spectra.size())-1);
        local.spectra[i]=i==0&&start==0&&stream.continuation?stream.previousSpectrum:stream.spectra[frame];
    }
    const auto coefficients=coefficientTrace(local);
    std::copy(coefficients.begin()+16,coefficients.end(),output.begin()+start/20);
}
double localScore(const FullBandContext& context,const Pcm& pcm) {
    const auto measured=context.measure(pcm);
    if(context.target==QualityTarget::Pcm)return measured.balancedError[0]+measured.balancedTemporalError[0];
    return measured.balancedError[0]+measured.balancedError[1]
        +measured.balancedTemporalError[0]+measured.balancedTemporalError[1];
}
bool sameBytes(const Stream& a,const Stream& b) { return packV9(a)==packV9(b); }
bool sameContinuation(const Stream& a,const Stream& b) {
    return a.qualityTarget==b.qualityTarget&&a.continuation==b.continuation&&a.allowExtras==b.allowExtras&&a.accuracy==b.accuracy
        &&a.previousSpectrum==b.previousSpectrum&&a.previousInput==b.previousInput
        &&a.previousCoefficients==b.previousCoefficients&&a.lookahead==b.lookahead
        &&a.initial.dd==b.initial.dd&&a.initial.cc==b.initial.cc
        &&std::equal(a.initial.h,a.initial.h+10,b.initial.h)
        &&std::equal(a.initial.ring,a.initial.ring+256,b.initial.ring);
}
}
LpcRunProposals proposeLpcRuns(const Stream& input,const Pcm& reference,int cap,bool finalV9Budget) {
    LpcRunProposals result;
    if(!validQualityTarget(input.qualityTarget)||input.samples<1||size_t(input.samples)!=reference.size()||(input.profile!=4&&input.profile!=6)
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
    auto prefix=input.initial;int cursor=0;
    for(const auto& run:order) {
        const int start=run.first*320,end=std::min(input.samples,start+horizon);
        while(cursor<start) {int stop=std::min(start,cursor+4096);advance(input,baselineCo,cursor,stop,prefix);cursor=stop;}
        ++result.runs;
        Pcm source(reference.begin()+start,reference.begin()+end),initial(baselinePcm.begin()+start,baselinePcm.begin()+end);
        FullBandContext context(source,input.rate,input.qualityTarget);const double baselineLoss=localScore(context,initial);
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
std::vector<Stream> composeLpcRuns(const Stream& anchor,const std::vector<Stream>& singles,
    const std::vector<double>& safeScores,int cap,bool finalV9Budget) {
    std::vector<Stream> result;
    if(anchor.samples<1||(anchor.profile!=4&&anchor.profile!=6)
        ||(anchor.rate!=8000&&anchor.rate!=12000&&anchor.rate!=16000)
        ||singles.size()!=safeScores.size()||singles.size()>maxRuns*2)return result;
    const int frames=(anchor.samples+319)/320;
    if(anchor.spectra.size()!=size_t(frames)||anchor.parameters.size()!=size_t(frames*2)
        ||anchor.pulses.size()!=size_t(frames*16)||anchor.extras.size()!=size_t(frames*8))return result;
    for(const auto& spectrum:anchor.spectra)if(!legalSpectrum(spectrum,anchor.profile))return result;
    const auto bytes=[&](const Stream& stream) {return finalV9Budget?int(packV9(stream).size()):compactBytes(stream);};
    if(bytes(anchor)>cap)return result;
    struct Edit {int first,last,index;double score;std::vector<uint8_t> packed;};
    std::vector<Edit> edits;
    std::vector<std::vector<uint8_t>> singleBytes;
    for(int index=0;index<int(singles.size());++index) {
        if(!std::isfinite(safeScores[index])||safeScores[index]<0)continue;
        const auto& single=singles[index];
        if(single.samples!=anchor.samples||single.rate!=anchor.rate||single.profile!=anchor.profile
            ||single.pre!=anchor.pre||single.bright!=anchor.bright||single.parameters!=anchor.parameters
            ||single.extras!=anchor.extras||single.spectra.size()!=anchor.spectra.size()
            ||single.pulses.size()!=anchor.pulses.size()||!sameContinuation(single,anchor))continue;
        int first=0;while(first<frames&&single.spectra[first]==anchor.spectra[first])++first;
        if(first==frames||(first&&anchor.spectra[first]==anchor.spectra[first-1]))continue;
        int last=first+1;while(last<frames&&anchor.spectra[last]==anchor.spectra[first])++last;
        if(!legalSpectrum(single.spectra[first],anchor.profile))continue;
        int fields=0;for(int k=0;k<10;++k)if(single.spectra[first][k]!=anchor.spectra[first][k])
            fields+=std::abs(single.spectra[first][k]-anchor.spectra[first][k])==1?1:100;
        if(fields!=1)continue;
        bool valid=true;
        for(int f=0;f<frames;++f)
            valid&=single.spectra[f]==(f>=first&&f<last?single.spectra[first]:anchor.spectra[f]);
        for(int p=0;p<int(single.pulses.size());++p)if(single.pulses[p]!=anchor.pulses[p]) {
            const auto& pulse=single.pulses[p];
            valid&=p>=first*16&&p<first*16+8&&p*20<anchor.samples&&pulse[0]>=0&&pulse[0]<20
                &&pulse[1]>=-8&&pulse[1]<=(anchor.profile==4?8:7);
            if(anchor.profile==4)valid&=pulse[0]%5!=2&&(pulse[1]==-8||pulse[1]==8);
        }
        if(!valid||bytes(single)>cap)continue;
        Edit edit{first,last,index,safeScores[index],packV9(single)};
        singleBytes.push_back(edit.packed);
        auto old=std::find_if(edits.begin(),edits.end(),[&](const Edit& item){return item.first==first;});
        if(old==edits.end())edits.push_back(std::move(edit));
        else if(edit.score<old->score||(edit.score==old->score
            &&(edit.packed.size()<old->packed.size()||(edit.packed.size()==old->packed.size()&&edit.packed<old->packed))))*old=std::move(edit);
    }
    std::sort(edits.begin(),edits.end(),[](const Edit& a,const Edit& b) {return a.score!=b.score?a.score<b.score:a.first<b.first;});
    std::vector<int> counts;
    for(int count:{int(edits.size()),std::min(2,int(edits.size()))})
        if(count>1&&std::find(counts.begin(),counts.end(),count)==counts.end())counts.push_back(count);
    for(int count:counts) {
        Stream bundle=anchor;bool overlap=false;
        for(int i=0;i<count;++i) {
            const auto& edit=edits[i];const auto& single=singles[edit.index];
            for(int j=0;j<i;++j)overlap|=edit.first<edits[j].last&&edits[j].first<edit.last;
            std::copy(single.spectra.begin()+edit.first,single.spectra.begin()+edit.last,bundle.spectra.begin()+edit.first);
            std::copy(single.pulses.begin()+edit.first*16,single.pulses.begin()+edit.first*16+8,bundle.pulses.begin()+edit.first*16);
        }
        if(overlap||bytes(bundle)>cap)continue;
        const auto packed=packV9(bundle);bool duplicate=packed==packV9(anchor);
        for(const auto& single:singleBytes)duplicate|=packed==single;
        for(const auto& previous:result)duplicate|=sameBytes(bundle,previous);
        if(!duplicate)result.push_back(std::move(bundle));
    }
    return result;
}
}
