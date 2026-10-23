#include <stdint.h>
#include <avr/pgmspace.h>
#include "nb3_c_math.h"
#include "packed24.h"
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
static void innovation10_c(int16_t *out,const uint8_t *pitch,
                           const int8_t *shape,int32_t scale)
{
   const int16_t high=(int16_t)(scale>>12),low=(int16_t)(scale&4095);
   uint8_t i;
   for (i=0;i<10;i++) {
      int32_t adaptive=speex_nb3_read24(pitch+3*i);
      int32_t innovation=speex_nb3_shape_scale_c((int8_t)pgm_read_byte(shape+i),high,low);
      if (adaptive>2048000) adaptive=2048000;
      if (adaptive<-2048000) adaptive=-2048000;
      int32_t value=(int32_t)(((uint32_t)adaptive<<8)+(uint32_t)innovation+8192)>>14;
      if (value>32767) value=32767;
      if (value<-32767) value=-32767;
      out[i]=(int16_t)value;
   }
}
int main(void)
{
   iir_status=1;
   for (;;) {
      while (!iir_command) {}
      if (iir_command==1)
         speex_avr_iir40(iir_samples,iir_coef,iir_samples,iir_state);
      else if (iir_command==3)
         innovation10_c(iir_samples,innovation_pitch,
                        innovation_shapes+innovation_index,innovation_scale);
      else
         speex_avr_innovation10(iir_samples,innovation_pitch,
                               innovation_shapes+innovation_index,innovation_scale);
      __asm__ ("mov %0,r1":"=r"(iir_zero));
      iir_command=0;
      iir_status=2;
   }
}
