#pragma once
#include "LpxQuality.h"
#include "LpxLoudness.h"
#include "LpxProfileQuality.h"

namespace lpx {
struct AdaptiveReport {
    int candidates=0,stages=0,selected=0,cap=0,gainExponent=0,error=0;
    int stageOperator[4]={},localEvaluations[4]={},fullEvaluations[4]={};
    int expandedLocalEvaluations=0,expandedFullEvaluations=0,expandedAccepted=0;
    Measurement baseline,measurement;
    LoudnessReport loudness;
    ProfileQualityReport qualitySearch;
    JointQualityReport jointQuality;
};
// Whole-input controller. Original input is retained; no reset-file splitting.
// maxBytes=0 uses the original v5 control's actual complete size as the budget,
// matching the Python reference before lossless V9 repacking.
Stream adaptiveEncode(const Pcm& input,int profile,int rate,AdaptiveReport& report,
                      bool autoQuiet=false,int maxBytes=0,int calls=4,bool speech=true,
                      bool expandedSearch=false,int sizeAllowancePercent=0,bool normalize=false,
                      const Stream* prefix=nullptr);
bool verifyStream(const Stream& stream,const Pcm& expected);
// One whole-input gain decision shared by adaptive and bitrate presets.
Pcm prepareInputLevel(const Pcm& input,bool autoQuiet,int& gainExponent);
}
