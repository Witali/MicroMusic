/* Include after fixed_generic.h and the fast multiply override. Only known
 * signed 32-bit fixed-point expressions are replaced; generic SHR/SHR16 keep
 * their original integer promotions and variable-shift semantics. */
#ifndef SPEEX_AVR_FIXED_H
#define SPEEX_AVR_FIXED_H
#include "avr_shift.h"
#ifdef __AVR__
#undef SHR32
#define SHR32(a,s) (__builtin_constant_p(s) && (s)==13 ? speex_avr_asr13(a) : \
                   __builtin_constant_p(s) && (s)==14 ? speex_avr_asr14(a) : \
                   __builtin_constant_p(s) && (s)==15 ? speex_avr_asr15(a) : ((a)>>(s)))
#undef MULT16_16_Q13
#undef MULT16_16_Q14
#undef MULT16_16_Q15
#undef MULT16_16_P13
#undef MULT16_16_P14
#undef MULT16_16_P15
#define MULT16_16_Q13(a,b) speex_avr_asr13(MULT16_16(a,b))
#define MULT16_16_Q14(a,b) speex_avr_asr14(MULT16_16(a,b))
#define MULT16_16_Q15(a,b) speex_avr_asr15(MULT16_16(a,b))
#define MULT16_16_P13(a,b) speex_avr_asr13(ADD32(4096,MULT16_16(a,b)))
#define MULT16_16_P14(a,b) speex_avr_asr14(ADD32(8192,MULT16_16(a,b)))
#define MULT16_16_P15(a,b) speex_avr_asr15(ADD32(16384,MULT16_16(a,b)))
#undef MULT16_32_Q14
#undef MULT16_32_Q15
#undef MULT16_32_P15
#define MULT16_32_Q14(a,b) ADD32(MULT16_16((a),speex_avr_asr14_word(b)),speex_avr_asr14(MULT16_16((a),((b)&0x3fff))))
#define MULT16_32_Q15(a,b) ADD32(MULT16_16((a),speex_avr_asr15_word(b)),speex_avr_asr15(MULT16_16((a),((b)&0x7fff))))
#define MULT16_32_P15(a,b) ADD32(MULT16_16((a),speex_avr_asr15_word(b)),speex_avr_asr15(ADD32(16384,MULT16_16((a),((b)&0x7fff)))))
#endif
#endif
