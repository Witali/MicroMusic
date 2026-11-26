// Independent policy/ownership audit. No production implementation is copied.
#include "LpxQuality.h"
#include "LpxFullBand.h"
#include "LpxProfileQuality.h"
#include "LpxCandidateEvaluation.h"
#include "LpxStreaming.h"
#include "LpxEncoder.h"
#include "Lpx4HybridCore.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <future>
#include <limits>
#include <string>

extern "C" {
int enc_accuracy(int,int,int,int,int,int,int);
int enc_adaptive(int,int,int,int,int,int);
int enc_adaptive_extended(int,int,int,int,int,int,int);
int enc_adaptive_loudness(int,int,int,int,int,int,int);
int enc_adaptive_level(int,int,int,int,int,int,int,int,int);
int enc_bitrate_loudness(int,int,int,int);
int enc_bitrate_level(int,int,int,int,int,int);
uint8_t* enc_adaptive_output();
int enc_stream_create(int,int,int,int,int,int,int,int);
int enc_stream_create_accuracy(int,int,int,int,int,int,int,int);
}

namespace {
using lpx::QualityTarget;
constexpr QualityTarget pcmTarget=QualityTarget::Pcm,pwmTarget=QualityTarget::Pwm;
void require(bool condition,const char* message) {
    if(!condition) { std::fprintf(stderr,"FAIL: %s\n",message);std::exit(1); }
}
void equal(double a,double b,const char* message) {
    require((std::isnan(a)&&std::isnan(b))||a==b,message);
}

void metrics() {
    // These are actual PCM16/PWM boundary crossings, not fabricated summaries.
    for(int rate:{8000,12000,16000}) for(int fixture:{0,1}) {
        const lpx::Pcm reference(400,fixture?1136:126);
        const lpx::Pcm incumbent(400,fixture?1134:110);
        const lpx::Pcm candidate(400,fixture?1136:127);
        require(lpx::sse(reference,candidate)<lpx::sse(reference,incumbent),"fixture PCM did not improve");
        require(lpx::sse(reference,lpx::pwm(candidate))>lpx::sse(reference,lpx::pwm(incumbent)),"fixture PWM did not worsen");
        lpx::QualityContext pcm(reference,false,rate,pcmTarget),pwm(reference,false,rate,pwmTarget),legacy(reference,false,rate);
        const auto oldPcm=pcm.quality(incumbent),nextPcm=pcm.quality(candidate);
        const auto oldPwm=pwm.quality(incumbent),nextPwm=pwm.quality(candidate);
        require(lpx::noRegression(nextPcm,oldPcm),"PCM SSE gate used the PWM path");
        require(!lpx::noRegression(nextPwm,oldPwm),"PWM SSE gate ignored PWM regression");
        require(!lpx::noRegression(nextPcm,oldPwm)&&!lpx::noRegression(nextPwm,oldPcm),"mixed-target quality summaries were admitted");
        require(legacy.quality(candidate).error[1]==nextPwm.error[1],"default quality policy changed");
        const auto measuredPcm=pcm.measure(candidate),measuredPwm=pwm.measure(candidate);
        equal(measuredPcm.score,measuredPcm.voice[0]+measuredPcm.noise[0],"PCM score includes another output path");
        equal(measuredPwm.score,(measuredPwm.voice[0]+measuredPwm.noise[0]+measuredPwm.voice[1]+measuredPwm.noise[1])/2,"PWM score changed");
        lpx::FullBandContext nativeBands(reference,rate,pcmTarget),pwmBands(reference,rate,pwmTarget);
        require(nativeBands.accepts(nativeBands.measure(candidate),nativeBands.measure(incumbent)),"PCM band gate retained a PWM floor");
        require(!pwmBands.accepts(pwmBands.measure(candidate),pwmBands.measure(incumbent)),"PWM band gate lost its PWM floor");
        require(!nativeBands.accepts(pwmBands.measure(candidate),nativeBands.measure(incumbent)),"mixed-target band summaries were admitted");
        require(lpx::profileQualityAdmission(reference,incumbent,candidate,rate,false,true,pcmTarget),"complete PCM admission rejected PCM-only improvement");
        require(!lpx::profileQualityAdmission(reference,incumbent,candidate,rate,false,true,pwmTarget),"complete PWM admission accepted a PWM regression");
        require(!lpx::profileQualityAdmission(reference,incumbent,candidate,rate,false,true),"default complete admission is not PWM");
    }
    lpx::Quality floor,next;
    floor.target=next.target=pcmTarget;floor.error[0]=10;next.error[0]=9;
    floor.error[1]=1;next.error[1]=999;floor.stoi[0]=.8;next.stoi[0]=.9;
    floor.stoi[1]=.99;next.stoi[1]=std::numeric_limits<double>::quiet_NaN();
    require(lpx::noRegression(next,floor),"PCM policy considered disabled PWM STOI");
    next.stoi[0]=std::numeric_limits<double>::quiet_NaN();
    require(!lpx::noRegression(next,floor),"PCM policy lost finite PCM STOI floor");
    next.stoi[0]=.79;require(!lpx::noRegression(next,floor),"PCM policy admitted worse PCM STOI");

    // Independent owners run concurrently; there is no mutable global policy.
    const lpx::Pcm reference(641,126),incumbent(641,110),candidate(641,127);
    auto work=[&](QualityTarget target) {
        lpx::QualityContext context(reference,false,8000,target);
        const auto before=context.quality(incumbent);
        for(int i=0;i<12;++i) {
            const auto after=context.measure(candidate);
            if(lpx::noRegression(after.quality,before)!=(target==pcmTarget))return false;
        }
        return true;
    };
    auto pcmTask=std::async(std::launch::async,work,pcmTarget);
    auto pwmTask=std::async(std::launch::async,work,pwmTarget);
    require(pcmTask.get()&&pwmTask.get(),"parallel contexts contaminated quality targets");
    std::puts("PASS metrics: real crossing, rates, gates, scores, mismatch, STOI, parallel owners");
}

lpx::Stream stream(QualityTarget target) {
    lpx::Stream value;value.samples=641;value.profile=6;value.pre=0;value.bright=0;value.qualityTarget=target;
    lpx::Spectrum spectrum;for(int i=0;i<10;++i)spectrum[i]=3+5*i;
    value.spectra.assign(3,spectrum);value.parameters.assign(6,lpx::Parameters{{24,18,0}});
    value.pulses.assign(48,lpx::Pulse{{0,0}});value.extras.assign(24,lpx::Pulse{{-1,0}});
    return value;
}
void cache() {
    const lpx::Pcm reference(641,126);
    lpx::CandidateEvaluation pcm(reference,8000,false,pcmTarget),pwm(reference,8000,false,pwmTarget);
    require(pcm.matches(reference,8000,false,pcmTarget)&&!pcm.matches(reference,8000,false,pwmTarget),"PCM cache matches another target");
    require(pwm.matches(reference,8000,false,pwmTarget)&&!pwm.matches(reference,8000,false,pcmTarget),"PWM cache matches another target");
    lpx::Pcm sameContent=reference;
    require(!pcm.matches(sameContent,8000,false,pcmTarget),"cache lost reference identity");
    require(!pcm.matches(reference,12000,false,pcmTarget)&&!pcm.matches(reference,8000,true,pcmTarget),"cache lost rate/speech identity");
    for(QualityTarget target:{pcmTarget,pwmTarget}) {
        auto value=stream(target);auto& evaluation=target==pcmTarget?pcm:pwm;
        const auto packed=lpx::packV9(value);lpx::Measurement before,again;lpx::FullBandMeasurement spectral,repeated;
        require(evaluation.measure(value,packed,before,spectral),"initial cache measurement failed");
        require(evaluation.hits()==0,"cache hit before insertion");
        require(evaluation.measure(value,packed,again,repeated)&&evaluation.hits()==1,"same target failed to reuse its own summary");
        equal(before.score,again.score,"cached score differs");
        require(before.quality.target==target&&spectral.target==target,"cache returned another policy's summaries");
        value.continuation=true;value.previousSpectrum=value.spectra[0];value.initial.dd=5;value.initial.cc=7;
        value.initial.h[0]=2;value.initial.ring[0]=1;
        require(evaluation.measure(value,packed,again,repeated)&&evaluation.hits()==1,"continuation reused initial-state cache");
        require(evaluation.measure(value,packed,again,repeated)&&evaluation.hits()==2,"continuation summary did not cache");
        ++value.initial.dd;
        require(evaluation.measure(value,packed,again,repeated)&&evaluation.hits()==2,"changed synthesis history reused cached output");
        ++value.previousSpectrum[0];
        require(evaluation.measure(value,packed,again,repeated)&&evaluation.hits()==2,"changed previous spectrum reused cached output");
    }
    require(pcm.hits()==2&&pwm.hits()==2,"independent caches shared hit counters");
    std::puts("PASS cache: target/reference/rate/speech ownership, state and previous-spectrum keys");
}

void api() {
    constexpr int count=641;
    require(enc_set_backend(0)==0&&enc_reserve(count),"API CPU workspace failed");
    std::fill(enc_input(),enc_input()+count,int16_t(0));
    struct Route { const char* name;std::function<int(int)> explicitTarget;std::function<int()> legacy;bool streaming; };
    const Route routes[]={
        {"accuracy",[](int q){return enc_accuracy_target(count,4,8000,0,0,-18,12,q);},[]{return enc_accuracy(count,4,8000,0,0,-18,12);},false},
        {"adaptive",[](int q){return enc_adaptive_target(count,4,8000,0,0,0,q);},[]{return enc_adaptive(count,4,8000,0,0,0);},false},
        {"extended",[](int q){return enc_adaptive_extended_target(count,6,8000,0,0,0,10,q);},[]{return enc_adaptive_extended(count,6,8000,0,0,0,10);},false},
        {"adaptive loudness",[](int q){return enc_adaptive_loudness_target(count,4,8000,0,0,0,1,q);},[]{return enc_adaptive_loudness(count,4,8000,0,0,0,1);},false},
        {"adaptive level",[](int q){return enc_adaptive_level_target(count,6,8000,0,0,0,1,-18,12,q);},[]{return enc_adaptive_level(count,6,8000,0,0,0,1,-18,12);},false},
        {"bitrate8",[](int q){return enc_bitrate_target(count,8,8000,0,0,q);},[]{return enc_bitrate(count,8,8000,0,0);},false},
        {"bitrate3",[](int q){return enc_bitrate_target(count,3,8000,0,0,q);},[]{return enc_bitrate(count,3,8000,0,0);},false},
        {"bitrate loudness",[](int q){return enc_bitrate_loudness_target(count,8,8000,0,q);},[]{return enc_bitrate_loudness(count,8,8000,0);},false},
        {"bitrate level",[](int q){return enc_bitrate_level_target(count,8,8000,0,-18,12,q);},[]{return enc_bitrate_level(count,8,8000,0,-18,12);},false},
        {"stream create",[](int q){return enc_stream_create_target(count,4,8000,0,1,0,-18,12,q);},[]{return enc_stream_create(count,4,8000,0,1,0,-18,12);},true},
        {"stream accuracy",[](int q){return enc_stream_create_accuracy_target(count,4,8000,0,1,0,-18,12,q);},[]{return enc_stream_create_accuracy(count,4,8000,0,1,0,-18,12);},true},
    };
    for(const auto& route:routes) {
        for(int invalid:{-1,2,256,std::numeric_limits<int>::min(),std::numeric_limits<int>::max()})
            require(route.explicitTarget(invalid)==-1,route.name);
        std::fill(enc_input(),enc_input()+count,int16_t(0));
        int before=route.legacy();std::vector<uint8_t> previous;
        if(before>0&&!route.streaming)previous.assign(enc_adaptive_output(),enc_adaptive_output()+before);
        std::fill(enc_input(),enc_input()+count,int16_t(0));
        int next=route.explicitTarget(1);require(next==before,"legacy/explicit PWM return codes differ");
        if(next>0&&!route.streaming)require(previous==std::vector<uint8_t>(enc_adaptive_output(),enc_adaptive_output()+next),"legacy/explicit PWM bytes differ");
        std::fill(enc_input(),enc_input()+count,int16_t(0));
        int native=route.explicitTarget(0);require(native>0||native==-6,"valid PCM option failed unexpectedly");
    }
    // Nonzero refinement calls, interspersed policies, and all actual rates.
    for(int rate:{8000,12000,16000}) {
        std::fill(enc_input(),enc_input()+count,int16_t(0));
        const int bytes=enc_accuracy(count,6,rate,1,0,-18,12);require(bytes>0,"legacy searched accuracy failed");
        const std::vector<uint8_t> original(enc_adaptive_output(),enc_adaptive_output()+bytes);
        require(enc_accuracy_target(count,6,rate,1,0,-18,12,0)>0,"PCM searched accuracy failed");
        require(enc_accuracy_target(count,6,rate,1,0,-18,12,1)==bytes,"PWM wrapper retained previous policy");
        require(original==std::vector<uint8_t>(enc_adaptive_output(),enc_adaptive_output()+bytes),"interleaved target changed default PWM bytes");
    }
    std::puts("PASS api: all explicit wrappers reject invalid targets; legacy/PWM bytes and call0/search/rate paths");
}

struct StreamOutput { std::vector<uint8_t> body[2];lpx::Pcm pcm[2]; };
void append(StreamOutput& output,const lpx::StreamingChunk& part) {
    output.body[0].insert(output.body[0].end(),part.controlBytes.begin(),part.controlBytes.end());
    output.body[1].insert(output.body[1].end(),part.candidateBytes.begin(),part.candidateBytes.end());
    output.pcm[0].insert(output.pcm[0].end(),part.controlPcm.begin(),part.controlPcm.end());
    output.pcm[1].insert(output.pcm[1].end(),part.candidatePcm.begin(),part.candidatePcm.end());
}
void verifyStreamBytes(lpx::StreamingEncoder& encoder,const StreamOutput& output) {
    require(encoder.hasCandidate(),"zero-input streaming fixture lost candidate");
    for(int kind=0;kind<2;++kind) {
        auto bytes=encoder.getHeader(kind!=0);bytes.insert(bytes.end(),output.body[kind].begin(),output.body[kind].end());
        Lpx4HybridCore decoder;require(decoder.beginWideV9(bytes.data(),bytes.size()),"stream bytes failed decoder begin");
        for(int16_t expected:output.pcm[kind]) { int16_t actual;require(decoder.nextS16(actual)&&actual==expected,"continuous stream PCM differs"); }
        int16_t tail;require(!decoder.nextS16(tail)&&!decoder.error()&&decoder.finished(),"continuous stream tail failed");
    }
}
void streaming() {
    const int count=lpx::kLpxStreamWindow+161;
    lpx::StreamingEncoder pcm(count,6,8000,0,1,false,false,pcmTarget);
    lpx::StreamingEncoder pwm(count,6,8000,0,1,false,false,pwmTarget);
    require(!pcm.status()&&!pwm.status(),"independent streaming owners failed");
    StreamOutput output[2];
    for(int at=0;at<count;at+=lpx::kLpxStreamWindow) {
        const int size=std::min(lpx::kLpxStreamWindow,count-at),ahead=at+size<count?48:0;
        const lpx::Pcm source(size,0),future(ahead,0);
        lpx::StreamingChunk part;
        require(pcm.process(source,future,part)>=0,"PCM continuation failed");append(output[0],part);
        require(pwm.process(source,future,part)>=0,"PWM continuation failed");append(output[1],part);
    }
    lpx::StreamingChunk part;
    require(pcm.finish(part)>=0,"PCM stream finish failed");append(output[0],part);
    require(pwm.finish(part)>=0,"PWM stream finish failed");append(output[1],part);
    verifyStreamBytes(pcm,output[0]);verifyStreamBytes(pwm,output[1]);
    // Public admission seam accepts externally verified PCM. Inject the same
    // deliberate crossing triple into both owners to isolate policy semantics;
    // these three payloads are NOT claimed as actual zero-input encode outputs.
    const lpx::Pcm injected[3]={lpx::Pcm(count,126),lpx::Pcm(count,110),lpx::Pcm(count,127)};
    for(int kind=0;kind<3;++kind)for(int at=0;at<count;at+=lpx::kLpxStreamWindow) {
        int size=std::min(lpx::kLpxStreamWindow,count-at);
        require(pcm.verifyPut(kind,at,injected[kind].data()+at,size)>=0,"PCM external verification failed");
        require(pwm.verifyPut(kind,at,injected[kind].data()+at,size)>=0,"PWM external verification failed");
    }
    // A separate entry point selecting PWM cannot alter either existing owner.
    require(enc_reserve(21),"interleaved API reserve failed");std::fill(enc_input(),enc_input()+21,int16_t(0));
    require(enc_accuracy_target(21,4,8000,0,0,-18,12,1)>0,"interleaved independent encode failed");
    require(pcm.admit()==1,"PCM session lost its policy before final admission");
    require(pwm.admit()==0,"PWM session admitted worse PWM after interleaving");
    std::puts("PASS stream: independent interleaved owners, continuation bytes, immutable final admission target");
}
}

int main(int argc,char** argv) {
    require(argc==2,"select metrics, cache, api, or stream");
    const std::string mode=argv[1];
    if(mode=="metrics")metrics();else if(mode=="cache")cache();else if(mode=="api")api();else if(mode=="stream")streaming();else return 2;
    return 0;
}
