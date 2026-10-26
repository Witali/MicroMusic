/* Compile this translation unit with explicit ASM disable. Keep the actual
 * production C filter and its original arithmetic macros, not a copied loop. */
#include "arch.h"
#define iir_mem16 speex_test_iir_mem16_c
#include "iir_direct.c.inc"
void speex_test_iir10_c(const int16_t *x,const int16_t *den,int16_t *out,int32_t *state)
{speex_test_iir_mem16_c(x,den,out,40,10,state,0);}
