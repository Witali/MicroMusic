#pragma once
#include "LpxQuality.h"

namespace lpx {
struct AdaptiveReport {
    int candidates=0,stages=0,selected=0,cap=0,gainExponent=0,error=0;
    int stageOperator[4]={},localEvaluations[4]={},fullEvaluations[4]={};
    Measurement baseline,measurement;
};
// Whole-input controller. Original input is retained; no reset-file splitting.
// maxBytes=0 uses the original v5 control's actual complete size as the budget,
// matching the Python reference before lossless V9 repacking.
Stream adaptiveEncode(const Pcm& input,int profile,int rate,AdaptiveReport& report,
                      bool autoQuiet=false,int maxBytes=0,int calls=4,bool speech=true);
bool verifyStream(const Stream& stream,const Pcm& expected);
}
