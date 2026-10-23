#include <stdint.h>
extern void speex_avr_iir40(const int16_t *,const int16_t *,int16_t *,int32_t *);
int16_t iir_samples[40],iir_coef[10];
int32_t iir_state[15];
volatile uint8_t iir_command,iir_status,iir_zero;
int main(void)
{
   iir_status=1;
   for (;;) {
      while (!iir_command) {}
      speex_avr_iir40(iir_samples,iir_coef,iir_samples,iir_state);
      __asm__ ("mov %0,r1":"=r"(iir_zero));
      iir_command=0;
      iir_status=2;
   }
}
