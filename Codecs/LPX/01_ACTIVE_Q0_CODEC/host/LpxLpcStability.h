#pragma once
#include <stdint.h>
#include <float.h>

// Schur step-down for A(z) = 1 + sum(a[i] * z^(-i-1)), where a[] is the
// decoder's actual signed Q12 predictor. Ordered LSFs alone do not guarantee
// that rounded coefficients or linear coefficient interpolation remain stable.
//
// This checks one frozen polynomial, not arbitrary switching between filters.
// Callers must check every interpolated vector and validate rendered output.
// The tiny reflection margin rejects the numerically ambiguous unit boundary;
// it is not a prescribed pole-radius or audible bandwidth adjustment.
inline bool lpxStableLpc(const int16_t* coefficients) {
    if(!coefficients)return false;
    constexpr double margin=1e-9;
    double current[10],previous[10];
    for(int i=0;i<10;++i)current[i]=coefficients[i]/4096.0;
    for(int order=10;order>0;--order) {
        const double reflection=current[order-1];
        // Comparisons reject NaN/infinity without C++ runtime dependencies.
        if(!(reflection>-(1.0-margin) && reflection<1.0-margin))return false;
        if(order==1)return true;
        const double denominator=1.0-reflection*reflection;
        if(!(denominator>margin && denominator<=DBL_MAX))return false;
        for(int i=0;i<order-1;++i) {
            previous[i]=(current[i]-reflection*current[order-i-2])/denominator;
            if(!(previous[i]>=-DBL_MAX && previous[i]<=DBL_MAX))return false;
        }
        for(int i=0;i<order-1;++i)current[i]=previous[i];
    }
    return false;
}
