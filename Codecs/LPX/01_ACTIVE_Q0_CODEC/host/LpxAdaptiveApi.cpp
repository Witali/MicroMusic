#include "LpxAdaptiveController.h"
#include "LpxEncoder.h"
#include "LpxSeed.h"
#include "LpxHostWorkspace.h"
#include "LpxBitrateProfiles.h"
#include <utility>

static std::vector<uint8_t> qualityOutput;
static lpx::AdaptiveReport qualityReport;
static int encodeAdaptive(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls,bool expanded,int allowance) {
    qualityOutput.clear();qualityReport=lpx::AdaptiveReport{};
    if(samples<1 || uint32_t(samples)>lpxSeedCapacity() || uint32_t(samples)>kLpxMaxSamples
        || (profile!=4 && profile!=6) || (rate!=8000 && rate!=12000 && rate!=16000)
        || (autoQuiet!=0 && autoQuiet!=1) || maxBytes<0 || (maxBytes>0 && maxBytes<22) || calls<0 || calls>4
        || allowance<0 || allowance>100)return -1;
    lpx::Pcm reference(enc_input(),enc_input()+samples);
    auto result=lpx::adaptiveEncode(reference,profile,rate,qualityReport,autoQuiet!=0,maxBytes,calls,true,expanded,allowance);
    if(qualityReport.error)return qualityReport.error;
    qualityOutput=lpx::packV9(result);return qualityOutput.size();
}
extern "C" {
int enc_adaptive(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls) {
    return encodeAdaptive(samples,profile,rate,autoQuiet,maxBytes,calls,false,0);
}
int enc_adaptive_extended(int samples,int profile,int rate,int autoQuiet,int maxBytes,int calls,int allowancePercent) {
    return encodeAdaptive(samples,profile,rate,autoQuiet,maxBytes,calls,true,allowancePercent);
}
// Bitrates are encoder budgets. The wire profile remains existing V9 P4/P6.
int enc_bitrate(int samples,int kbps,int rate,int autoQuiet,int calls) {
    qualityOutput.clear();qualityReport=lpx::AdaptiveReport{};
    if(samples<1 || uint32_t(samples)>lpxSeedCapacity() || uint32_t(samples)>kLpxMaxSamples
        || (kbps!=3 && kbps!=8) || rate!=8000 || (autoQuiet!=0 && autoQuiet!=1)
        || calls<0 || calls>4)return -1;
    const int cap=int(int64_t(samples)*kbps*1000/(8*rate));
    const int header=samples>64000?17:13;
    if(cap<header)return -6;
    lpx::Pcm reference(enc_input(),enc_input()+samples);
    lpx::Stream result;
    if(kbps==3) {
        reference=lpx::prepareInputLevel(reference,autoQuiet!=0,qualityReport.gainExponent);
        lpx::BitrateReport report;
        result=lpx::encodeThreeK(reference,cap,report);
        qualityReport.candidates=report.candidates;qualityReport.selected=report.selected;
        qualityReport.cap=cap;qualityReport.error=report.error;
    } else {
        // Existing operators budget their internal, complete 22-byte-header v5
        // representation. V9 removes at least 22-header bytes, never adds bits.
        result=lpx::adaptiveEncode(reference,6,rate,qualityReport,autoQuiet!=0,
            cap+22-header,calls,true,true,0);
    }
    if(qualityReport.error)return qualityReport.error;
    auto expected=lpx::render(result);
    if(!lpx::verifyStream(result,expected))return -3;
    auto output=lpx::packV9(result);
    if(output.size()>size_t(cap))return -6;
    qualityOutput=std::move(output);
    return qualityOutput.size();
}
uint8_t* enc_adaptive_output() { return qualityOutput.data(); }
int enc_adaptive_candidates() { return qualityReport.candidates; }
int enc_adaptive_stages() { return qualityReport.stages; }
int enc_adaptive_gain() { return qualityReport.gainExponent; }
}
