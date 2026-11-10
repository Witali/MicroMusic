#include "wb_fold.h"
#include <avr/io.h>
#include <avr/interrupt.h>
#include <stdint.h>
struct {uint16_t before;int16_t values[40];uint16_t after;} unit_out;
struct {uint16_t before;uint8_t values[5];uint16_t after;} unit_codes;
volatile int32_t unit_scale,unit_gain;
volatile uint16_t unit_irqs;
volatile uint8_t unit_command,unit_status,unit_kind;
ISR(TIMER2_COMPA_vect){++unit_irqs;}
int main(void){
 TCCR2A=_BV(WGM21);TCCR2B=_BV(CS21);OCR2A=124;TIMSK2=_BV(OCIE2A);sei();
 unit_status=1;
 for(;;)if(unit_command){
  switch(unit_kind){
   case 0:speex_wb_excitation40_avr(unit_out.values,unit_codes.values,unit_scale,unit_gain);break;
   case 1:speex_wb_excitation40_c(unit_out.values,unit_codes.values,unit_scale,unit_gain);break;
   case 2:speex_wb_excitation8_40_avr(unit_out.values,unit_codes.values,unit_scale,unit_gain);break;
   case 3:speex_wb_excitation8_40_c(unit_out.values,unit_codes.values,unit_scale,unit_gain);break;
   case 4:speex_wb_excitation_nb2_40_avr(unit_out.values,unit_codes.values,unit_scale,unit_gain);break;
   case 5:speex_wb_excitation_low40_c(unit_out.values,unit_codes.values,unit_scale,unit_gain,2);break;
   case 6:speex_wb_excitation_nb8_40_avr(unit_out.values,unit_codes.values,unit_scale,unit_gain);break;
   default:speex_wb_excitation_low40_c(unit_out.values,unit_codes.values,unit_scale,unit_gain,8);break;
  }
  unit_command=0;unit_status=2;
 }
}
