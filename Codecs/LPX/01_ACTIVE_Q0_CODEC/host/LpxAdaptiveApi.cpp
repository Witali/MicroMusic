#include "LpxAdaptiveController.h"
#include "LpxEncoder.h"
#include "LpxSeed.h"
#include "LpxHostWorkspace.h"

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
uint8_t* enc_adaptive_output() { return qualityOutput.data(); }
int enc_adaptive_candidates() { return qualityReport.candidates; }
int enc_adaptive_stages() { return qualityReport.stages; }
int enc_adaptive_gain() { return qualityReport.gainExponent; }
int enc_loudness_status() { return qualityReport.loudness.status; }
int enc_loudness_limited() { return qualityReport.loudness.limited; }
double enc_loudness_input() { return qualityReport.loudness.input; }
double enc_loudness_prepared() { return qualityReport.loudness.prepared; }
double enc_loudness_decoded() { return qualityReport.loudness.decoded; }
double enc_loudness_gain_db() { return qualityReport.loudness.gainDb; }
}
