#pragma once
// Included only by LPX4_FLOAT_SYNTHESIS=1. No fixed/AVR helper depends on it.
#include <stdint.h>
#include <cmath>
static const double lpx4FloatPi=3.141592653589793238462643383279502884;
static inline double lpx4FloatClamp(double x,double lo,double hi){return x<lo?lo:(x>hi?hi:x);}
static inline void lpx4FloatFactor(double* p,uint8_t& degree,double c){
    // Convolve with 1+c*z^-1+z^-2, preserving fractional coefficients.
    for(int j=degree+2;j>=0;--j){
        const double same=j<=degree?p[j]:0.0;
        const double one=j>=1 && j-1<=degree?p[j-1]:0.0;
        const double two=j>=2 && j-2<=degree?p[j-2]:0.0;
        p[j]=same+c*one+two;
    }
    degree+=2;
}
// Final output quantization only: nearest integer, ties toward positive.
static inline int16_t lpx4FloatQuantize(double x,int16_t lo,int16_t hi){
    return static_cast<int16_t>(lpx4FloatClamp(std::floor(x+0.5),lo,hi));
}
static inline uint8_t lpx4FloatPwm(double b,uint8_t gain,bool rounded){
    const double offset=b*gain/16384.0;
    const double duty=128.0+(rounded?std::floor(offset+0.5):std::trunc(offset));
    return static_cast<uint8_t>(lpx4FloatClamp(duty,0.0,255.0));
}
