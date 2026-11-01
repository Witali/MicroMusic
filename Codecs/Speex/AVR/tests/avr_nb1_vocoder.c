/* Isolated vector C/ASM primitive only; no C decoder execution. */
#include "nb1_vocoder.h"
int16_t voc_out[40],voc_context[14];
uint8_t voc_classes[40];
SpeexNb1Cursor voc_cursor;
volatile uint8_t voc_command,voc_status;
int main(void)
{
    voc_status=1;
    for(;;)if(voc_command==1||voc_command==2) {
        if(voc_command==1)speex_nb1_synthesize40_avr(voc_out,voc_classes,voc_context,&voc_cursor);
        else speex_nb1_synthesize40_c(voc_out,voc_classes,voc_context,&voc_cursor);
        voc_command=0;voc_status=2;
    }
}
