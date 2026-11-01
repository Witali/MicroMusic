#include "avr25_math.h"
#if !LPX25_USE_ASM
extern "C" int32_t proto_mul(int16_t x,int16_t y){return (int32_t)x*y;}
extern "C" int32_t proto_shift12(int32_t value){return value>>12;}
extern "C" int32_t proto_shift14(int32_t value){return value>>14;}
#endif
