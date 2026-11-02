/* Isolated vector arithmetic, never a C decoder. Command 5 checks selection. */
#include "nb1_vocoder.h"
#if !SPEEX_NB3_USE_AVR_ASM
/* Direct ASM reference controls remain available in this isolated fixture,
 * while command5 must select C through the ordinary library header. */
void speex_nb1_synthesize40_avr(int16_t *,const uint8_t *,const int16_t *,SpeexNb1Cursor *);
void speex_nb1_synthesize40_zero_avr(int16_t *,const uint8_t *,const int16_t *,SpeexNb1Cursor *);
#endif
int16_t voc_out[40],voc_context[14];
uint8_t voc_classes[40];
SpeexNb1Cursor voc_cursor;
volatile uint8_t voc_command,voc_status;
int main(void)
{
    voc_status=1;
    for(;;)if(voc_command) {
        if(voc_command==1)speex_nb1_synthesize40_avr(voc_out,voc_classes,voc_context,&voc_cursor);
        else if(voc_command==2)speex_nb1_synthesize40_c(voc_out,voc_classes,voc_context,&voc_cursor);
        else if(voc_command==3)speex_nb1_synthesize40_zero_avr(voc_out,voc_classes,voc_context,&voc_cursor);
        else if(voc_command==4)speex_nb1_synthesize40_zero_c(voc_out,voc_classes,voc_context,&voc_cursor);
        else speex_nb1_synthesize40_zero(voc_out,voc_classes,voc_context,&voc_cursor);
        voc_command=0;voc_status=2;
    }
}
