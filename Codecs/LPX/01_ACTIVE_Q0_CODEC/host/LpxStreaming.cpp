#include "LpxStreaming.h"
#include "LpxBitrateProfiles.h"
#include "LpxProfileQuality.h"
#include "LpxEncoder.h"
#include "LpxHostWorkspace.h"
#include "LpxAccuracy.h"
#include <algorithm>
#include <cmath>

namespace lpx {
StreamingEncoder::StreamingEncoder(uint32_t samples,int selected,int sampleRate,int sizeAllowance,int refinements,bool normalization,bool accuracyMode,QualityTarget target)
    :total(samples),profile(selected),rate(sampleRate),allowance(sizeAllowance),calls(refinements),
     header(v9HeaderBytes(samples)),policy(encodingPolicy(selected,accuracyMode)),qualityTarget(target),normalize(normalization),accuracy(accuracyMode),controlWriter(policy.corrections),candidateWriter(policy.corrections),sourceMeter(rate),preparedMeter(rate),controlMeter(rate),candidateMeter(rate) {
    controlContext.qualityTarget=candidateContext.qualityTarget=qualityTarget;
    controlContext.allowExtras=candidateContext.allowExtras=accuracy;
    if(accuracy)controlContext.accuracy=candidateContext.accuracy=profile;
    planned=!normalize;
    const uint32_t sampleLimit=accuracyMode && !refinements?kLpxMaxStreamingSamples:kLpxMaxSamples;
    if((target!=QualityTarget::Pcm && target!=QualityTarget::Pwm) || !total || total>sampleLimit || !policy.supports(rate,allowance) || calls<0 || calls>4)error=-1;
    if(!error && !enc_reserve(kLpxStreamWindow+320))error=-2;
    if(!calls)candidateLive=false;
}
int StreamingEncoder::measure(const Pcm& pcm) {
    if(error)return error;
    if(planned || pcm.empty() || pcm.size()>kLpxStreamWindow || measured+pcm.size()>total)return -1;
    sourceMeter.add(pcm.data(),pcm.size());measured+=pcm.size();return measured==total?1:0;
}
int StreamingEncoder::plan(int target,int maximum) {
    if(error)return error;
    if(!normalize || planned || measured!=total)return -1;
    level=sourceMeter.plan(target,maximum);if(level.status<1)return -1;
    planned=true;return level.status;
}
Pcm StreamingEncoder::scaled(const Pcm& input) const {
    Pcm pcm=input;
    if(normalize && level.status==1)for(auto& x:pcm)x=int16_t(std::max(-29204,std::min(29204,int(std::round(x*level.factor)))));
    return pcm;
}
Stream StreamingEncoder::nextContext(const Stream& stream,const Pcm& input,const std::vector<Coefficients>& co,const SynthesisState& state) {
    Stream context;context.qualityTarget=stream.qualityTarget;context.allowExtras=stream.allowExtras;context.accuracy=stream.accuracy;context.continuation=true;context.pre=stream.pre;context.bright=stream.bright;
    context.initial=state;context.previousSpectrum=stream.spectra.back();
    std::copy(input.end()-172,input.end(),context.previousInput.begin());
    std::copy(co.end()-8,co.end(),context.previousCoefficients.begin());return context;
}
uint64_t StreamingEncoder::cap() const {
    if(accuracy)return accuracyBudget(total,profile,header+int((controlWriter.bits()+7)/8));
    if(policy.targetBitrate)return bitrateBudget(total,policy.targetBitrate,rate);
    const int wire=policy.wireProfile;
    uint64_t bits=controlWriter.spectrumBits()+controlWriter.frameCount()*(wire==4?110:166);
    return (22+(bits+7)/8)*(100+allowance)/100;
}
int StreamingEncoder::process(const Pcm& input,const Pcm& future,StreamingChunk& output) {
    output=StreamingChunk{};
    if(error)return error;
    bool last=done+input.size()==total;
    if(!planned || ended || input.empty() || input.size()>kLpxStreamWindow || done+input.size()>total
       || (!last && input.size()!=kLpxStreamWindow) || future.size()>48 || (!last && future.empty()) || (last && !future.empty()))return -1;
    auto reference=scaled(input),lookahead=scaled(future);
    controlContext.lookahead=lookahead;candidateContext.lookahead=lookahead;
    Stream control;
    const int wire=policy.wireProfile;
    if(accuracy){AdaptiveReport report;control=encodeAccuracy(reference,profile,rate,report,0,&controlContext,qualityTarget);if(report.error)return error=report.error;}
    else if(policy.targetBitrate) {
        uint64_t cumulative=bitrateBudget(done+reference.size(),policy.targetBitrate,rate);
        int available=int(cumulative)-header-int((controlWriter.bits()+7)/8)-1+13;
        if(available<13)return error=-6;
        if(profile==3) {
            BitrateReport report;control=encodeThreeK(reference,available,report,.97,nullptr,&controlContext,qualityTarget);
            if(report.error)return error=report.error;
        } else {
            AdaptiveReport report;control=adaptiveEncode(reference,wire,rate,report,false,available+9,0,true,false,0,false,&controlContext,nullptr,nullptr,qualityTarget);
            if(report.error)return error=report.error;
        }
    } else {
        control=fitSeed(reference,wire,rate,13926,false,.97,&controlContext,nullptr,nullptr,qualityTarget);
        if(control.samples!=int(reference.size()))return error=-7;
    }
    auto co=coefficientTrace(control);auto controlState=control.initial;
    output.controlPcm=advance(control,co,0,control.samples,controlState);
    controlMeter.add(output.controlPcm.data(),output.controlPcm.size());
    if(!controlWriter.append(control))return error=-3;
    output.controlBytes=controlWriter.drain();
    if(!done) { controlContext.pre=control.pre;controlContext.bright=control.bright; }
    if(!last)controlContext=nextContext(control,reference,co,controlState);
    if(candidateLive) {
        uint64_t cumulative=policy.targetBitrate?bitrateBudget(done+reference.size(),policy.targetBitrate,rate):cap();
        int available=int(cumulative)-header-int((candidateWriter.bits()+7)/8)-1+13;
        Stream candidate;int failed=0;bool unsafeSeed=false;
        if(accuracy){
            AdaptiveReport report;candidate=encodeAccuracy(reference,profile,rate,report,calls,&candidateContext,qualityTarget);
            failed=report.error;
            unsafeSeed=failed==-7 && report.originalSeedStatus==SeedFitStatus::Unsafe;
            available=accuracyPacketBound(reference.size(),profile);
        }
        else if(available<13)failed=-6;
        else if(profile==3) {
            BitrateReport report;candidate=encodeThreeK(reference,available,report,.97,nullptr,&candidateContext,qualityTarget);failed=report.error;
            if(!failed && calls) { ProfileQualityReport quality;candidate=refineProfileQuality(candidate,reference,available,true,quality,true);failed=quality.error; }
#if LPX_ENCODER_JOINT_REFINEMENT
            if(!failed && calls) {
                JointQualityReport quality;
                candidate=refineJointQuality(candidate,reference,available,true,quality,true);
                failed=quality.selection.error;
            }
#endif
        } else {
            AdaptiveReport report;
            candidate=adaptiveEncode(reference,wire,rate,report,false,available+9,calls,true,true,0,false,&candidateContext,nullptr,nullptr,qualityTarget);failed=report.error;
        }
        // A separately carried candidate may reject its seed while the complete
        // continuous control remains admissible. Keep that entire control;
        // argument, backend and decoder failures still abort the encode.
        if(unsafeSeed || failed==-6 || available<13)candidateLive=false;
        else if(failed)return error=failed;
        else if(candidate.samples!=int(reference.size()) || packV9(candidate).size()>size_t(available))candidateLive=false;
        if(candidateLive) {
            auto coefficients=coefficientTrace(candidate);auto state=candidate.initial;
            output.candidatePcm=advance(candidate,coefficients,0,candidate.samples,state);
            candidateMeter.add(output.candidatePcm.data(),output.candidatePcm.size());
            if(!candidateWriter.append(candidate))return error=-3;
            output.candidateBytes=candidateWriter.drain();
            if(!done) { candidateContext.pre=candidate.pre;candidateContext.bright=candidate.bright; }
            if(!last)candidateContext=nextContext(candidate,reference,coefficients,state);
        }
    }
    if(normalize)preparedMeter.add(reference.data(),reference.size());
    done+=reference.size();return last?1:0;
}
int StreamingEncoder::finish(StreamingChunk& output) {
    output=StreamingChunk{};if(error)return error;
    if(ended || done!=total)return -1;ended=true;
    output.controlBytes=controlWriter.finish();
    if(candidateLive)output.candidateBytes=candidateWriter.finish();
    if((controlWriter.bits()+7)/8+header>cap())return error=-6;
    if(candidateLive && (candidateWriter.bits()+7)/8+header>cap())candidateLive=false;
    return candidateLive?1:0;
}
std::vector<uint8_t> StreamingEncoder::getHeader(bool candidate) const {
    if(!ended || error || (candidate && !candidateLive))return {};
    const auto& writer=candidate?candidateWriter:controlWriter;
    const auto& context=candidate?candidateContext:controlContext;
    return v9Header(total,policy.wireProfile,rate,context.pre,context.bright,policy.corrections,(writer.bits()+7)/8);
}
int StreamingEncoder::verifyPut(int kind,uint32_t offset,const int16_t* pcm,int count) {
    if(!ended || error || kind<0 || kind>2 || count<1 || count>kLpxStreamWindow || offset!=received[kind]
       || offset+count>total || (kind==2 && !candidateLive))return -1;
    if(!candidateLive) { received[kind]+=count;return received[kind]==total?1:0; }
    if(verification[kind].empty())verification[kind].resize(total);
    for(int i=0;i<count;++i) {
        int x=pcm[i];if(kind==0 && normalize && level.status==1)x=std::max(-29204,std::min(29204,int(std::round(x*level.factor))));
        verification[kind][offset+i]=x;
    }
    received[kind]+=count;return received[kind]==total?1:0;
}
int StreamingEncoder::admit() {
    if(!ended || error || received[1]!=total || (candidateLive && (received[0]!=total || received[2]!=total)))return -1;
    choice=candidateLive && profileQualityAdmission(verification[0],verification[1],verification[2],rate,true,false,qualityTarget)?1:0;
    for(auto& pcm:verification)Pcm{}.swap(pcm);
    return choice;
}
LoudnessReport StreamingEncoder::loudness() const {
    if(!normalize)return LoudnessReport{};
    auto report=level;if(report.status==1)report.prepared=preparedMeter.measure();
    report.decoded=choice==1?candidateMeter.measure():controlMeter.measure();return report;
}
}
