#include <stdint.h>
#include <avr/pgmspace.h>
extern void speex_avr_iir40(const int16_t *,const int16_t *,int16_t *,int32_t *);
extern void speex_avr_innovation10(int16_t *,const uint8_t *,const int8_t *,int32_t);
static const int8_t innovation_shapes[] PROGMEM={
#include "test-shapes.h"
};
uint8_t innovation_pitch[3*10];
volatile int32_t innovation_scale;
volatile uint8_t innovation_index;
int16_t iir_samples[40],iir_coef[10];
int32_t iir_state[15];
volatile uint8_t iir_command,iir_status,iir_zero;
int main(void)
{
   iir_status=1;
   for (;;) {
      while (!iir_command) {}
      if (iir_command==1)
         speex_avr_iir40(iir_samples,iir_coef,iir_samples,iir_state);
      else
         speex_avr_innovation10(iir_samples,innovation_pitch,
                               innovation_shapes+innovation_index,innovation_scale);
      __asm__ ("mov %0,r1":"=r"(iir_zero));
      iir_command=0;
      iir_status=2;
   }
}
