#pragma once
#include <stdint.h>

namespace lpx {
enum class BudgetKind { V5Control, CompleteV9, AccuracyAllocation };
struct EncodingPolicy {
    int accuracyLevel=0, targetBitrate=0, wireProfile=0;
    BudgetKind budgetKind=BudgetKind::V5Control;
    bool corrections=false;
    bool valid() const { return wireProfile!=0; }
    bool supports(int rate,int allowance) const {
        return valid() && (rate==8000 || rate==12000 || rate==16000)
            && allowance>=0 && allowance<=100
            && (!accuracyLevel || !allowance)
            && (!targetBitrate || (rate==8000 && !allowance));
    }
};
// Compatibility profiles are resolved once at the boundary. Precision and
// strict kbps budgets remain distinct even when their numeric names coincide.
inline EncodingPolicy encodingPolicy(int selected,bool accuracy) {
    EncodingPolicy p;
    if(selected!=3 && selected!=4 && selected!=6 && selected!=8)return p;
    p.wireProfile=selected<=4?4:6;
    if(accuracy) {
        p.accuracyLevel=selected;p.corrections=true;
        p.budgetKind=BudgetKind::AccuracyAllocation;
    } else if(selected==3 || selected==8) {
        p.targetBitrate=selected*1000;p.budgetKind=BudgetKind::CompleteV9;
    }
    return p;
}
inline int v9HeaderBytes(uint32_t samples) { return samples>64000?17:13; }
inline uint64_t bitrateBudget(uint32_t samples,int bitsPerSecond,int rate) {
    return uint64_t(samples)*bitsPerSecond/(8*rate);
}
}
