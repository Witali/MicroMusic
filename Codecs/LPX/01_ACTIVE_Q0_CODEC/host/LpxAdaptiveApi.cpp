#include "LpxAdaptiveController.h"
#include "LpxEncoder.h"
#include "LpxSeed.h"
#include "LpxHostWorkspace.h"
#include "LpxBitrateProfiles.h"
#include <utility>

static std::vector<uint8_t> qualityOutput;
static lpx::AdaptiveReport qualityReport;
static int encodeAdaptive(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls,bool expanded,int allowance,bool normalize=false) {
    qualityOutput.clear();qualityReport=lpx::AdaptiveReport{};
    if(samples<1 || uint32_t(samples)>lpxSeedCapacity() || uint32_t(samples)>kLpxMaxSamples
        || (profile!=4 && profile!=6) || (rate!=8000 && rate!=12000 && rate!=16000)
        || (autoQuiet!=0 && autoQuiet!=1) || maxBytes<0 || (maxBytes>0 && maxBytes<22) || calls<0 || calls>4
        || allowance<0 || allowance>100)return -1;
    lpx::Pcm reference(enc_input(),enc_input()+samples);
    auto result=lpx::adaptiveEncode(reference,profile,rate,qualityReport,autoQuiet!=0,maxBytes,calls,true,expanded,allowance,normalize);
    if(qualityReport.error)return qualityReport.error;
    qualityOutput=lpx::packV9(result);return qualityOutput.size();
}
extern "C" {
int enc_normalize_loudness(int samples,int rate) {
    qualityReport=lpx::AdaptiveReport{};
    if(samples<1 || uint32_t(samples)>lpxSeedCapacity() || (rate!=8000 && rate!=12000 && rate!=16000))return -1;
    lpx::Pcm pcm(enc_input(),enc_input()+samples);
    qualityReport.loudness=lpx::normalizeLoudness(pcm,rate);
    for(int i=0;i<samples;++i)enc_input()[i]=pcm[i];
    return qualityReport.loudness.status;
}
int enc_adaptive_loudness(int samples,int profile,int rate,int maxBytes,int calls,int allowancePercent,int expanded) {
    if(expanded!=0 && expanded!=1)return -1;
    return encodeAdaptive(samples,profile,rate,0,maxBytes,calls,expanded!=0,allowancePercent,true);
}
int enc_adaptive(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls) {
    return encodeAdaptive(samples,profile,rate,autoQuiet,maxBytes,calls,false,0);
}
int enc_adaptive_extended(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls,int allowancePercent) {
    return encodeAdaptive(samples,profile,rate,autoQuiet,maxBytes,calls,true,allowancePercent);
}
// Bitrates are encoder budgets. The wire profile remains existing V9 P4/P6.
static int encodeBitrate(int samples,int kbps,int rate,int autoQuiet,int calls,bool normalize,int reserveBytes=0) {
    qualityOutput.clear();qualityReport=lpx::AdaptiveReport{};
    if(samples<1 || uint32_t(samples)>lpxSeedCapacity() || uint32_t(samples)>kLpxMaxSamples
        || (kbps!=3 && kbps!=8) || rate!=8000 || (autoQuiet!=0 && autoQuiet!=1)
        || calls<0 || calls>4)return -1;
    const int cap=int(int64_t(samples)*kbps*1000/(8*rate))-reserveBytes;
    const int header=samples>64000?17:13;
    if(cap<header)return -6;
    lpx::Pcm reference(enc_input(),enc_input()+samples);
    lpx::LoudnessReport loudness;
    if(normalize)loudness=lpx::normalizeLoudness(reference,rate);
    lpx::Stream result;
    if(kbps==3) {
        reference=lpx::prepareInputLevel(reference,autoQuiet!=0,qualityReport.gainExponent);
        lpx::BitrateReport report;
        result=lpx::encodeThreeK(reference,cap,report);
        qualityReport.candidates=report.candidates;qualityReport.selected=report.selected;
        qualityReport.cap=cap;qualityReport.error=report.error;
#if LPX_ENCODER_QUALITY_SEARCH
        if(!qualityReport.error) {
            result=lpx::refineProfileQuality(result,reference,cap,true,qualityReport.qualitySearch,true);
            qualityReport.error=qualityReport.qualitySearch.error;
        }
#endif
    } else {
        // Existing operators budget their internal, complete 22-byte-header v5
        // representation. V9 removes at least 22-header bytes, never adds bits.
        result=lpx::adaptiveEncode(reference,6,rate,qualityReport,autoQuiet!=0,
            cap+22-header,calls,true,true,0);
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
int enc_bitrate(int samples,int kbps,int rate,int autoQuiet,int calls) {
    return encodeBitrate(samples,kbps,rate,autoQuiet,calls,false);
}
int enc_bitrate_loudness(int samples,int kbps,int rate,int calls) {
    return encodeBitrate(samples,kbps,rate,0,calls,true);
}
int enc_adaptive_file_gain(int samples,int profile,int rate,int maxBytes,int calls,int allowancePercent,int expanded,int targetLufs,int maxGainDb) {
    if(targetLufs<-30 || targetLufs>-9 || maxGainDb<0 || maxGainDb>24 || (expanded!=0 && expanded!=1))return -1;
    int size=encodeAdaptive(samples,profile,rate,0,maxBytes,calls,expanded!=0,allowancePercent);
    if(size<0)return size;
    if(!lpx::normalizeFileGain(qualityOutput,targetLufs,maxGainDb,qualityReport.loudness))return -3;
    return qualityOutput.size();
}
int enc_bitrate_file_gain(int samples,int kbps,int rate,int calls,int targetLufs,int maxGainDb) {
    if(targetLufs<-30 || targetLufs>-9 || maxGainDb<0 || maxGainDb>24)return -1;
    int size=encodeBitrate(samples,kbps,rate,0,calls,false,2);
    if(size<0)return size;
    if(!lpx::normalizeFileGain(qualityOutput,targetLufs,maxGainDb,qualityReport.loudness))return -3;
    if(qualityOutput.size()>size_t(int64_t(samples)*kbps*1000/(8*rate)))return -6;
    return qualityOutput.size();
}
uint8_t* enc_adaptive_output() { return qualityOutput.data(); }
int enc_adaptive_candidates() { return qualityReport.candidates; }
int enc_adaptive_stages() { return qualityReport.stages; }
int enc_adaptive_gain() { return qualityReport.gainExponent; }
int enc_loudness_status() { return qualityReport.loudness.status; }
int enc_loudness_limited() { return qualityReport.loudness.limited; }
int enc_loudness_gain_limited() { return qualityReport.loudness.gainLimited; }
int enc_loudness_gain_q12() { return qualityReport.loudness.gainQ12; }
double enc_loudness_input() { return qualityReport.loudness.input; }
double enc_loudness_prepared() { return qualityReport.loudness.prepared; }
double enc_loudness_decoded() { return qualityReport.loudness.decoded; }
double enc_loudness_gain_db() { return qualityReport.loudness.gainDb; }
}
