/* Original project probe using the public simavr 1.6 API. No simavr source is
 * copied. The linked simavr library is GPL-3.0-or-later. Tiny Timer1 and CPU
 * memory geometry come from the compiler-selected official device header. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sim_avr.h"
#include "sim_elf.h"
#include "sim_interrupts.h"
#include "avr_timer.h"
#include "hardware.h"

#ifndef GAIN_NATIVE_MCU
#define BIT(r,b) {.reg=H_##r,.bit=H_##b,.mask=1}
static avr_timer_t timer1={.name='1',.r_tcnt=H_TCNT1L,.r_tcnth=H_TCNT1H,
 .wgm_op={[0]=AVR_TIMER_WGM_NORMAL16()},
 .cs={BIT(TCCR1B,CS10),BIT(TCCR1B,CS11),BIT(TCCR1B,CS12)},
 .cs_div={[1]=0,[2]=3,[3]=6,[4]=8,[5]=10},
 .overflow={.vector=H_TIMER1_OVF_vect_num,.enable=BIT(TIMSK1,TOIE1),.raised=BIT(TIFR1,TOV1)}};
static void init(avr_t* cpu){avr_timer_init(cpu,&timer1);}
static avr_t tiny={.mmcu="attiny88-lpx-gain-probe",.ioend=H_RAMSTART-1,.ramend=H_RAMEND,
 .flashend=H_FLASHEND,.e2end=H_E2END,.vector_size=2,.init=init};
#endif

static uint32_t symbol(const elf_firmware_t* fw,const char* name){
 for(uint32_t i=0;i<fw->symbolcount;++i)
  if(!strcmp(fw->symbol[i]->symbol,name))return fw->symbol[i]->addr&65535;
 fprintf(stderr,"Missing probe symbol %s\n",name);exit(2);
}
static uint32_t read32(const avr_t* cpu,uint32_t address){
 uint32_t result=0;for(unsigned i=0;i<4;++i)result|=(uint32_t)cpu->data[address+i]<<(8*i);return result;
}
static void running(struct avr_irq_t* irq,uint32_t value,void* context){
 (void)irq;if(value)((avr_t*)context)->cycle+=4;
}
int main(int argc,char** argv){
 if(argc!=2)return 2;
 elf_firmware_t fw={0};if(elf_read_firmware(argv[1],&fw)<0)return 2;
#ifdef GAIN_NATIVE_MCU
 avr_t* cpu=avr_make_mcu_by_name(GAIN_NATIVE_MCU);
#else
 avr_t* cpu=&tiny;
#endif
 if(!cpu||avr_init(cpu)<0)return 2;
 cpu->frequency=16000000;fw.frequency=16000000;avr_load_firmware(cpu,&fw);
 avr_irq_t* irq=avr_get_interrupt_irq(cpu,H_TIMER1_OVF_vect_num);
 avr_irq_register_notify(irq+AVR_INT_IRQ_RUNNING,running,cpu);
 const uint32_t done=symbol(&fw,"math_done"),error=symbol(&fw,"math_error"),zero=symbol(&fw,"math_zero_error");
 const uint32_t cases=symbol(&fw,"math_cases"),irqs=symbol(&fw,"math_irqs"),backend=symbol(&fw,"math_backend");
 int state=cpu_Running;
 while(cpu->cycle<UINT64_C(3000000000)&&!cpu->data[done]&&state!=cpu_Crashed&&state!=cpu_Done)
  state=avr_run(cpu);
 printf("{\"done\":%u,\"error\":%u,\"zero_error\":%u,\"cases\":%u,\"irqs\":%u,\"backend\":%u,\"irq_entry_cycles\":4,\"cycles\":%llu}\n",
  cpu->data[done],cpu->data[error],cpu->data[zero],read32(cpu,cases),read32(cpu,irqs),cpu->data[backend],
  (unsigned long long)cpu->cycle);
 const int failed=!cpu->data[done]||cpu->data[error]||cpu->data[zero]||read32(cpu,cases)!=32768||!read32(cpu,irqs);
 avr_terminate(cpu);return failed;
}
