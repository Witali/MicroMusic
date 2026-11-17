#include <stdint.h>
#include <avr/io.h>
#include <avr/interrupt.h>
#include "Lpx4Math.h"
extern "C" {
volatile uint8_t math_done,math_error,math_zero_error;
volatile uint32_t math_cases,math_irqs;
volatile const uint8_t math_backend=LPX4_USE_AVR_NOMUL_ASM;
}
ISR(TIMER1_OVF_vect){++math_irqs;}
static uint32_t state=0xc470ba15;
static uint32_t random32(){state^=state<<13;state^=state>>17;state^=state<<5;return state;}
__attribute__((noinline)) static int32_t product(int16_t a,int16_t b){return (int32_t)a*b;}
static int16_t aa[10],original[10],history[11];
template<bool q4,bool spare,bool keep,bool bounded>
__attribute__((noinline)) static void one(int32_t excitation){
 int32_t expected=excitation;
 for(uint8_t i=0;i<10;i++){history[i]=original[i];expected-=product(aa[i],original[i])>>12;}
 history[10]=12345;int16_t* base=0;
 const int32_t actual=lpx4SynthesisQ12<q4,spare,keep,bounded>(q4?excitation*16:excitation,aa,history,&base);
 uint8_t z;__asm__ volatile("mov %0,r1":"=r"(z):"r"(actual):"memory");
 if(z)math_zero_error=1;
 if(actual!=expected*(keep?16:1))math_error=1;
 if(base!=history || history[0]!=original[0])math_error=2;
 for(uint8_t i=1;i<10;i++)if(history[i]!=original[i-1])math_error=3;
 if(history[10]!=(spare?original[9]:12345))math_error=4;
 ++math_cases;
}
__attribute__((noinline)) static void all(int32_t e,bool bounded){
 one<false,false,false,false>(e);one<false,false,true,false>(e);
 one<false,true,false,false>(e);one<false,true,true,false>(e);
 one<true,false,false,false>(e);one<true,false,true,false>(e);
 one<true,true,false,false>(e);one<true,true,true,false>(e);
 if(bounded)one<true,true,true,true>(e);
}
int main(){
 TIMSK1=_BV(TOIE1);TCCR1B=_BV(CS10);sei();
 static const int16_t bounds[]={-32768,-32767,-32766,-4096,-2049,-2048,-1793,-1792,-1537,-1536,-257,-256,-255,-17,-16,-1,0,1,15,16,255,256,1535,1536,1791,1792,2047,2048,32766,32767};
 for(uint8_t a=0;a<30;a++)for(uint8_t h=0;h<30;h++){
  bool bounded=true;
  for(uint8_t i=0;i<10;i++){
   aa[i]=bounds[(a+i)%30];original[i]=bounds[(h+i*3)%30];
   if(aa[i]==-32768)bounded=false;
  }
  all((int32_t)((a+h)&1?524288:-524288),bounded);
 }
 for(uint16_t k=0;k<4096;k++){
  bool bounded=true;
  for(uint8_t i=0;i<10;i++){
   aa[i]=(int16_t)random32();original[i]=(int16_t)random32();
   if(aa[i]==-32768)bounded=false;
   if((k&15)==0)original[i]=0;
   if((k&15)==1)original[i]=(i&1)?32767:-32767;
  }
  all((int32_t)(random32()%1048577)-524288,bounded);
 }
 math_done=1;cli();for(;;){}
}
