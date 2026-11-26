#pragma once
#include "LpxQuality.h"
#include "LpxLoudness.h"
#include "LpxProfileQuality.h"

namespace lpx {
// Optional completed-P3 phase. Its counters and failure status never replace
// the preceding successful controller's legacy report fields.
struct CompactEnsembleReport {
    int enabled=0,eligible=0,attempted=0,searchCalls=0,status=0,error=0;
    int policyBudget=0,baselineBytes=0,rawBytes=0,selectedBytes=0,rawValid=0,rawChanged=0,selected=0;
    int searchCandidates=0,searchSelected=0;
    uint64_t parameterTrials=0,pulseTrials=0;
    ProfileQualityReport selection;
};
struct AdaptiveReport {
    int candidates=0,stages=0,selected=0,cap=0,gainExponent=0,error=0;
    SeedFitStatus originalSeedStatus=SeedFitStatus::Failure;
    int stageOperator[4]={},localEvaluations[4]={},fullEvaluations[4]={};
    int expandedLocalEvaluations=0,expandedFullEvaluations=0,expandedAccepted=0;
    Measurement baseline,measurement;
    LoudnessReport loudness;
    ProfileQualityReport qualitySearch;
    JointQualityReport jointQuality;
    CompactEnsembleReport compactEnsemble;
};
// Whole-input controller. Original input is retained; no reset-file splitting.
// maxBytes=0 uses the original v5 control's actual complete size as the budget,
// matching the Python reference before lossless V9 repacking.
Stream adaptiveEncode(const Pcm& input,int profile,int rate,AdaptiveReport& report,
                      bool autoQuiet=false,int maxBytes=0,int calls=4,bool speech=true,
                      bool expandedSearch=false,int sizeAllowancePercent=0,bool normalize=false,
                      const Stream* prefix=nullptr,const Stream* preparedSeed=nullptr,
                      CandidateEvaluation* evaluation=nullptr,QualityTarget target=QualityTarget::Pwm);
// preparedSeed is the unmodified fixed-pre/zeroScale=false/.97 fit for this
// exact reference and prefix. Input-level preparation must already be complete.
bool verifyStream(const Stream& stream,const Pcm& expected);
// One whole-input gain decision shared by adaptive and bitrate presets.
Pcm prepareInputLevel(const Pcm& input,bool autoQuiet,int& gainExponent);
}
