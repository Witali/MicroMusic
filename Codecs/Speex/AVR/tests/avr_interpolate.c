/* C-only quarter-step mailbox; oracle is the untouched vendored lsp.c. */
#include <stdint.h>
#include "nb3_interpolate.h"
#include "lsp.h"

int16_t quarter_old[12], quarter_next[12], quarter_raw[12];
int16_t quarter_delta[12], quarter_out[12], quarter_expected[12];
volatile uint8_t quarter_command, quarter_status, quarter_sub;

int main(void)
{
    unsigned i;
    quarter_status=1;
    for (;;) {
        while (!quarter_command) {}
        if (quarter_command==1) {
            for (i=1;i<=10;i++) {
                quarter_raw[i]=quarter_old[i];
                quarter_delta[i]=(quarter_next[i]>>2)-(quarter_old[i]>>2);
            }
            quarter_sub=0;
        } else {
            lsp_interpolate(quarter_old+1,quarter_next+1,quarter_expected+1,
                            10,quarter_sub,4,16);
            speex_nb3_interpolate(quarter_raw+1,quarter_delta+1,quarter_out+1);
            quarter_sub++;
        }
        quarter_command=0;
        quarter_status=2;
    }
}
