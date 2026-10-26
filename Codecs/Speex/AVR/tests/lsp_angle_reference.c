/* Independent untouched Xiph 1.2.1 math_approx.h/fixed_generic.h oracle.
 * Compile this object without LTO and without project arithmetic overrides. */
#include <stdint.h>
#include "arch.h"
#include "math_approx.h"
int16_t reference_lsp_angle(int16_t x){return SHL16(spx_cos(x),2);}
