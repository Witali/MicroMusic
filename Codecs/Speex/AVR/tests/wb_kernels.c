/* Independent AVR mailbox; both arithmetic backends remain linked for direct
 * comparison. Buffer gaps are guards; no heap or full-frame PCM storage. */
#include "wb_qmf.h"
#include "wb_fold.h"
#include "wb_iir.h"
#include <string.h>
uint8_t wb_unit_buffer[400];
int16_t wb_unit_den[8];
volatile int32_t wb_unit_gain;
volatile uint8_t wb_unit_command,wb_unit_kind,wb_unit_status,wb_unit_alias;
int main(void)
{
    wb_unit_status=1;
    for(;;) {
        if(wb_unit_command==2) {
            memset(wb_unit_buffer,165,sizeof(wb_unit_buffer));
            memset(wb_unit_buffer+332,0,64);
            wb_unit_command=0;wb_unit_status=1;
        }else if(wb_unit_command==1) {
            int16_t *in=(int16_t *)(wb_unit_buffer+4);
            int16_t *out=(int16_t *)(wb_unit_buffer+168);
            uint8_t *state=wb_unit_buffer+332;
            const int16_t *high=in+40;
            if(wb_unit_alias) {memcpy(out+40,high,80);high=out+40;}
            wb_unit_status=2;
            switch(wb_unit_kind) {
            case 0:speex_wb_qmf40_avr(in,high,out,state);break;
            case 1:speex_wb_qmf40_c(in,high,out,state);break;
            case 2:speex_wb_fold40_avr(in,wb_unit_gain);break;
            case 3:speex_wb_fold40_c(in,wb_unit_gain);break;
            case 4:speex_wb_iir40_avr(in,wb_unit_den,out,(int32_t *)state);break;
            case 5:speex_wb_iir40_c(in,wb_unit_den,out,(int32_t *)state);break;
            }
            wb_unit_command=0;wb_unit_status=3;
        }
    }
}
