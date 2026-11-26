#include "LpxAdaptiveController.h"
#include "LpxEncoder.h"
#include "LpxSeed.h"
#include "LpxHostWorkspace.h"
#include "LpxBitrateProfiles.h"
#include "LpxAccuracy.h"
#include "LpxEncodingPolicy.h"
#include <utility>

static std::vector<uint8_t> qualityOutput;
static lpx::AdaptiveReport qualityReport;
static int encodeAdaptive(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls,bool expanded,int allowance,bool normalize=false,int target=-18,int maxGain=-1,lpx::QualityTarget qualityTarget=lpx::QualityTarget::Pwm) {
    qualityOutput.clear();qualityReport=lpx::AdaptiveReport{};
    if(samples<1 || uint32_t(samples)>lpxSeedCapacity() || uint32_t(samples)>kLpxMaxSamples
        || (profile!=4 && profile!=6) || (rate!=8000 && rate!=12000 && rate!=16000)
        || (autoQuiet!=0 && autoQuiet!=1) || maxBytes<0 || (maxBytes>0 && maxBytes<22) || calls<0 || calls>4
        || allowance<0 || allowance>100)return -1;
    lpx::Pcm reference(enc_input(),enc_input()+samples);
    lpx::LoudnessReport level;
    if(normalize && maxGain>=0)level=lpx::normalizeLoudness(reference,rate,target,maxGain);
    auto result=lpx::adaptiveEncode(reference,profile,rate,qualityReport,autoQuiet!=0,maxBytes,calls,true,expanded,allowance,normalize && maxGain<0,nullptr,nullptr,nullptr,qualityTarget);
    if(qualityReport.error)return qualityReport.error;
    if(normalize && maxGain>=0) { qualityReport.loudness=level;qualityReport.loudness.decoded=lpx::integratedLoudness(lpx::render(result),rate); }
    qualityOutput=lpx::packV9(result);return qualityOutput.size();
}
static bool validQualityTarget(int target) { return target==0 || target==1; }
extern "C" {
int enc_accuracy_target(int samples,int level,int rate,int calls,int normalize,int target,int maximum,int qualityTarget){
    qualityOutput.clear();qualityReport=lpx::AdaptiveReport{};
    if(!validQualityTarget(qualityTarget)||samples<1||uint32_t(samples)>lpxSeedCapacity()||uint32_t(samples)>kLpxMaxSamples||(normalize!=0&&normalize!=1)||target<-30||target>-9||maximum<0||maximum>24)return -1;
    lpx::Pcm reference(enc_input(),enc_input()+samples);lpx::LoudnessReport loudness;
    if(normalize)loudness=lpx::normalizeLoudness(reference,rate,target,maximum);
    const auto selected=lpx::encodeAccuracy(reference,level,rate,qualityReport,calls,nullptr,lpx::QualityTarget(qualityTarget));
    if(qualityReport.error)return qualityReport.error;
    if(normalize){qualityReport.loudness=loudness;qualityReport.loudness.decoded=lpx::integratedLoudness(lpx::render(selected),rate);}
    qualityOutput=lpx::packV9(selected);return qualityOutput.size();
}
int enc_normalize_loudness(int samples,int rate) {
    qualityReport=lpx::AdaptiveReport{};
    if(samples<1 || uint32_t(samples)>lpxSeedCapacity() || (rate!=8000 && rate!=12000 && rate!=16000))return -1;
    lpx::Pcm pcm(enc_input(),enc_input()+samples);
    qualityReport.loudness=lpx::normalizeLoudness(pcm,rate);
    for(int i=0;i<samples;++i)enc_input()[i]=pcm[i];
    return qualityReport.loudness.status;
}
int enc_normalize_level(int samples,int rate,int target,int maxGain) {
    qualityReport=lpx::AdaptiveReport{};
    if(samples<1 || uint32_t(samples)>lpxSeedCapacity() || (rate!=8000 && rate!=12000 && rate!=16000)
        || target<-30 || target>-9 || maxGain<0 || maxGain>24)return -1;
    lpx::Pcm pcm(enc_input(),enc_input()+samples);
    qualityReport.loudness=lpx::normalizeLoudness(pcm,rate,target,maxGain);
    for(int i=0;i<samples;++i)enc_input()[i]=pcm[i];
    return qualityReport.loudness.status;
}
int enc_accuracy(int samples,int level,int rate,int calls,int normalize,int target,int maximum){return enc_accuracy_target(samples,level,rate,calls,normalize,target,maximum,1);}
int enc_adaptive_loudness_target(int samples,int profile,int rate,int maxBytes,int calls,int allowancePercent,int expanded,int qualityTarget) {
    if(!validQualityTarget(qualityTarget))return -1;
    if(expanded!=0 && expanded!=1)return -1;
    return encodeAdaptive(samples,profile,rate,0,maxBytes,calls,expanded!=0,allowancePercent,true,-18,-1,lpx::QualityTarget(qualityTarget));
}
int enc_adaptive_loudness(int samples,int profile,int rate,int maxBytes,int calls,int allowancePercent,int expanded) { return enc_adaptive_loudness_target(samples,profile,rate,maxBytes,calls,allowancePercent,expanded,1); }
int enc_adaptive_target(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls,int qualityTarget) {
    if(!validQualityTarget(qualityTarget))return -1;
    return encodeAdaptive(samples,profile,rate,autoQuiet,maxBytes,calls,false,0,false,-18,-1,lpx::QualityTarget(qualityTarget));
}
int enc_adaptive(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls) { return enc_adaptive_target(samples,profile,rate,autoQuiet,maxBytes,calls,1); }
int enc_adaptive_extended_target(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls,int allowancePercent,int qualityTarget) {
    if(!validQualityTarget(qualityTarget))return -1;
    return encodeAdaptive(samples,profile,rate,autoQuiet,maxBytes,calls,true,allowancePercent,false,-18,-1,lpx::QualityTarget(qualityTarget));
}
int enc_adaptive_extended(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls,int allowancePercent) { return enc_adaptive_extended_target(samples,profile,rate,autoQuiet,maxBytes,calls,allowancePercent,1); }
// Bitrates are encoder budgets. The wire profile remains existing V9 P4/P6.
static int encodeBitrate(int samples,int kbps,int rate,int autoQuiet,int calls,bool normalize,int target=-18,int maxGain=-1,lpx::QualityTarget qualityTarget=lpx::QualityTarget::Pwm) {
    qualityOutput.clear();qualityReport=lpx::AdaptiveReport{};
    if(samples<1 || uint32_t(samples)>lpxSeedCapacity() || uint32_t(samples)>kLpxMaxSamples
        || (kbps!=3 && kbps!=8) || rate!=8000 || (autoQuiet!=0 && autoQuiet!=1)
        || calls<0 || calls>4)return -1;
    const auto policy=lpx::encodingPolicy(kbps,false);
    const int cap=int(lpx::bitrateBudget(samples,policy.targetBitrate,rate));
    const int header=lpx::v9HeaderBytes(samples);
    if(cap<header)return -6;
    lpx::Pcm reference(enc_input(),enc_input()+samples);
    lpx::LoudnessReport loudness;
    if(normalize)loudness=maxGain<0?lpx::normalizeLoudness(reference,rate):lpx::normalizeLoudness(reference,rate,target,maxGain);
    lpx::Stream result;
    if(kbps==3) {
        reference=lpx::prepareInputLevel(reference,autoQuiet!=0,qualityReport.gainExponent);
        lpx::BitrateReport report;
        result=lpx::encodeThreeK(reference,cap,report,.97,nullptr,nullptr,qualityTarget);
        qualityReport.candidates=report.candidates;qualityReport.selected=report.selected;
        qualityReport.cap=cap;qualityReport.error=report.error;
#if LPX_ENCODER_QUALITY_SEARCH
        if(!qualityReport.error) {
            result=lpx::refineProfileQuality(result,reference,cap,true,qualityReport.qualitySearch,true);
            qualityReport.error=qualityReport.qualitySearch.error;
#if LPX_ENCODER_JOINT_REFINEMENT
            if(!qualityReport.error) {
                result=lpx::refineJointQuality(result,reference,cap,true,qualityReport.jointQuality,true);
                qualityReport.error=qualityReport.jointQuality.selection.error;
            }
#endif
        }
#endif
    } else {
        // Existing operators budget their internal, complete 22-byte-header v5
        // representation. V9 removes at least 22-header bytes, never adds bits.
        result=lpx::adaptiveEncode(reference,6,rate,qualityReport,autoQuiet!=0,
            cap+22-header,calls,true,true,0,false,nullptr,nullptr,nullptr,qualityTarget);
    }
    if(qualityReport.error)return qualityReport.error;
    auto expected=lpx::render(result);
    if(normalize) { qualityReport.loudness=loudness;qualityReport.loudness.decoded=lpx::integratedLoudness(expected,rate); }
    if(!lpx::verifyStream(result,expected))return -3;
    auto output=lpx::packV9(result);
    if(output.size()>size_t(cap))return -6;
    qualityOutput=std::move(output);
    return qualityOutput.size();
}
int enc_bitrate_target(int samples,int kbps,int rate,int autoQuiet,int calls,int qualityTarget) {
    if(!validQualityTarget(qualityTarget))return -1;
    return encodeBitrate(samples,kbps,rate,autoQuiet,calls,false,-18,-1,lpx::QualityTarget(qualityTarget));
}
int enc_bitrate(int samples,int kbps,int rate,int autoQuiet,int calls) { return enc_bitrate_target(samples,kbps,rate,autoQuiet,calls,1); }
int enc_bitrate_loudness_target(int samples,int kbps,int rate,int calls,int qualityTarget) {
    if(!validQualityTarget(qualityTarget))return -1;
    return encodeBitrate(samples,kbps,rate,0,calls,true,-18,-1,lpx::QualityTarget(qualityTarget));
}
int enc_bitrate_loudness(int samples,int kbps,int rate,int calls) { return enc_bitrate_loudness_target(samples,kbps,rate,calls,1); }
int enc_adaptive_level_target(int samples,int profile,int rate,int maxBytes,int calls,int allowancePercent,int expanded,int targetLufs,int maxGainDb,int qualityTarget) {
    if(!validQualityTarget(qualityTarget))return -1;
    if(targetLufs<-30 || targetLufs>-9 || maxGainDb<0 || maxGainDb>24 || (expanded!=0 && expanded!=1))return -1;
    return encodeAdaptive(samples,profile,rate,0,maxBytes,calls,expanded!=0,allowancePercent,true,targetLufs,maxGainDb,lpx::QualityTarget(qualityTarget));
}
int enc_adaptive_level(int samples,int profile,int rate,int maxBytes,int calls,int allowancePercent,int expanded,int targetLufs,int maxGainDb) { return enc_adaptive_level_target(samples,profile,rate,maxBytes,calls,allowancePercent,expanded,targetLufs,maxGainDb,1); }
int enc_bitrate_level_target(int samples,int kbps,int rate,int calls,int targetLufs,int maxGainDb,int qualityTarget) {
    if(!validQualityTarget(qualityTarget))return -1;
    if(targetLufs<-30 || targetLufs>-9 || maxGainDb<0 || maxGainDb>24)return -1;
    return encodeBitrate(samples,kbps,rate,0,calls,true,targetLufs,maxGainDb,lpx::QualityTarget(qualityTarget));
}
int enc_bitrate_level(int samples,int kbps,int rate,int calls,int targetLufs,int maxGainDb) { return enc_bitrate_level_target(samples,kbps,rate,calls,targetLufs,maxGainDb,1); }
uint8_t* enc_adaptive_output() { return qualityOutput.data(); }
int enc_adaptive_candidates() { return qualityReport.candidates; }
int enc_adaptive_stages() { return qualityReport.stages; }
int enc_adaptive_gain() { return qualityReport.gainExponent; }
int enc_loudness_status() { return qualityReport.loudness.status; }
int enc_loudness_limited() { return qualityReport.loudness.limited; }
int enc_loudness_gain_limited() { return qualityReport.loudness.gainLimited; }
double enc_loudness_input() { return qualityReport.loudness.input; }
double enc_loudness_prepared() { return qualityReport.loudness.prepared; }
double enc_loudness_decoded() { return qualityReport.loudness.decoded; }
double enc_loudness_gain_db() { return qualityReport.loudness.gainDb; }
}
