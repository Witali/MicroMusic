#include <stdint.h>
typedef int16_t spx_word16_t;
typedef int32_t spx_word32_t;
#include "../patches/avr_fastmul.h"
spx_word32_t fastmul_test(spx_word16_t a, spx_word16_t b) {return MULT16_16(a,b);}
