/* Host integer-promotion/selector check, independent untouched Xiph object. */
#include "nb3_lsp_angle.h"
#include <assert.h>
#include <stdio.h>
int16_t reference_lsp_angle(int16_t);
int main(void)
{
    for(int32_t x=-32768;x<=32767;x++) {
        int16_t expected=reference_lsp_angle((int16_t)x);
        assert(speex_nb3_lsp_angle_c((int16_t)x)==expected);
        assert(speex_nb3_lsp_angle((int16_t)x)==expected);
    }
    puts("PASS: 65536 signed16 angles; selected/explicit C match untouched Xiph");
}
