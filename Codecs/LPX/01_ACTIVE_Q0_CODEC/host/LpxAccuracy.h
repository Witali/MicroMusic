#pragma once
#include "LpxAdaptiveController.h"
namespace lpx{
struct AccuracyPolicy{int level=0,wireProfile=0,detailBitsPerFrame=0;bool corrections=false;};
AccuracyPolicy accuracyPolicy(int level);
int accuracyPacketBound(int samples,int level);
int accuracyBudget(int samples,int level,int originalBytes);
Stream encodeAccuracy(const Pcm& reference,int level,int rate,AdaptiveReport& report,
                      int calls=4,const Stream* prefix=nullptr);
}
