/* Original project observer/model binding against simavr 1.6 public API.
 * No simavr implementation is copied. Linked simavr is GPL-3.0-or-later.
 * This bounded ATtiny88 model binds CPU memory, Port B, Timer0 CTC and
 * Timer1 fast PWM to a separately compiled, pinned vendor device header.
 * Unused peripherals (USB, EEPROM, ADC, SPI, watchdog) are not modeled here.
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "sim_avr.h"
#include "sim_elf.h"
#include "sim_io.h"
#include "sim_interrupts.h"
#include "avr_timer.h"
#include "avr_ioport.h"
#include "hardware.h"
#define BIT(r,b) { .reg=H_##r, .bit=H_##b, .mask=1 }
#define VECTOR(v,r,b,f,fb) { .vector=H_##v, .enable=BIT(r,b), .raised=BIT(f,fb) }
static avr_ioport_t port={.name='B',.r_port=H_PORTB,.r_ddr=H_DDRB,.r_pin=H_PINB};
static avr_timer_t t0={.name='0',.r_tcnt=H_TCNT0,
 .wgm={BIT(TCCR0A,CTC0)},.wgm_op={[0]=AVR_TIMER_WGM_NORMAL8(),[1]=AVR_TIMER_WGM_CTC()},
 .cs={BIT(TCCR0A,CS00),BIT(TCCR0A,CS01),BIT(TCCR0A,CS02)},
 .cs_div={[1]=0,[2]=3,[3]=6,[4]=8,[5]=10},
 .comp={[AVR_TIMER_COMPA]={.r_ocr=H_OCR0A,
  .interrupt=VECTOR(TIMER0_COMPA_vect_num,TIMSK0,OCIE0A,TIFR0,OCF0A)}},
 .overflow=VECTOR(TIMER0_OVF_vect_num,TIMSK0,TOIE0,TIFR0,TOV0)};
static avr_timer_t t1={.name='1',.r_tcnt=H_TCNT1L,.r_tcnth=H_TCNT1H,.r_icr=H_ICR1L,.r_icrh=H_ICR1H,
 .wgm={BIT(TCCR1A,WGM10),BIT(TCCR1A,WGM11),BIT(TCCR1B,WGM12),BIT(TCCR1B,WGM13)},
 .wgm_op={[0]=AVR_TIMER_WGM_NORMAL16(),[5]=AVR_TIMER_WGM_FASTPWM8()},
 .cs={BIT(TCCR1B,CS10),BIT(TCCR1B,CS11),BIT(TCCR1B,CS12)},
 .cs_div={[1]=0,[2]=3,[3]=6,[4]=8,[5]=10},
 .comp={[AVR_TIMER_COMPA]={.r_ocr=H_OCR1AL,.r_ocrh=H_OCR1AH,
  .interrupt=VECTOR(TIMER1_COMPA_vect_num,TIMSK1,OCIE1A,TIFR1,OCF1A),
  .com={.reg=H_TCCR1A,.bit=H_COM1A0,.mask=3},.com_pin=BIT(PORTB,PB1)}},
 .overflow=VECTOR(TIMER1_OVF_vect_num,TIMSK1,TOIE1,TIFR1,TOV1)};
static void init(avr_t *a){avr_ioport_init(a,&port);avr_timer_init(a,&t0);avr_timer_init(a,&t1);}
static avr_t cpu={.mmcu="attiny88-lpx-timers",.ioend=H_RAMSTART-1,.ramend=H_RAMEND,
 .flashend=H_FLASHEND,.e2end=H_E2END,.vector_size=2,.init=init};
static unsigned head,tail,eof,error,stopped,queue,bss,decode_begin,decode_end;
static FILE *out;
static uint64_t ticks,writes,underruns,first,last,min_gap=UINT64_MAX,max_gap,irq_start,irq_total,irq_max;
static uint64_t event_last,event_min=UINT64_MAX,event_max,events;
static unsigned in_irq,irq_finishing,min_queue=H_LPX25_QUEUE,minimum_sp=H_RAMEND,sp_ready;
static uint64_t decode_start,decode_sum,decode_calls,decode_max,active_sum,active_calls;
static uint64_t decode_irq_start,decode_irq_sum,decode_cpu_sum,decode_cpu_max,active_cpu_sum;
static unsigned decoding,decode_active;
static uint8_t expected;
static unsigned symbol(elf_firmware_t *f,const char *name){
 for(unsigned i=0;i<f->symbolcount;i++)if(!strcmp(f->symbol[i]->symbol,name))return f->symbol[i]->addr&65535;
 fprintf(stderr,"Missing symbol %s\n",name);exit(2);
}
static void pending(struct avr_irq_t *irq,uint32_t value,void *p){
 (void)irq;(void)p;if(!value)return;
 if(events++){uint64_t gap=cpu.cycle-event_last;if(gap<event_min)event_min=gap;if(gap>event_max)event_max=gap;}
 event_last=cpu.cycle;
}
static void running(struct avr_irq_t *irq,uint32_t value,void *p){
 (void)irq;(void)p;
 if(value){
  in_irq=1;ticks++;irq_start=cpu.cycle;
  // simavr1.6 avr_service_interrupts pushes PC/clears I but charges no
  // response cycles. Account the real AVRe four-cycle hardware entry here.
  // Existing cycle timers observe the advanced clock on the next avr_run.
  cpu.cycle+=4;
  unsigned h=cpu.data[head],t=cpu.data[tail];
  if(h>=H_LPX25_QUEUE || t>=H_LPX25_QUEUE){fprintf(stderr,"Invalid queue cursor\n");exit(3);}
  unsigned count=h>=t?h-t:H_LPX25_QUEUE+h-t;
  if(!cpu.data[eof] && count<min_queue)min_queue=count;
  if(!count)underruns++;
  expected=count?cpu.data[queue+cpu.data[tail]]:128;
 }else{
  // RUNNING falls at the beginning of RETI, before its four cycles retire.
  // Complete the duration in the outer loop after avr_run returns.
  irq_finishing=1;in_irq=0;
 }
}
static void pwm(struct avr_irq_t *irq,uint32_t value,void *p){
 (void)irq;(void)p;if(!in_irq)return;
 if((value&255)!=expected){fprintf(stderr,"Queue/PWM mismatch\n");exit(3);}
 if(writes++){uint64_t gap=cpu.cycle-last;if(gap<min_gap)min_gap=gap;if(gap>max_gap)max_gap=gap;}else first=cpu.cycle;
 last=cpu.cycle;fputc(value&255,out);
}
int main(int argc,char **argv){
 if(argc!=4){fprintf(stderr,"usage: sim_player player.elf output.pwm timing.json\n");return 2;}
 elf_firmware_t f={0};if(elf_read_firmware(argv[1],&f)<0 || f.flashsize>H_FLASHEND+1)return 2;
 head=symbol(&f,"lpx25_head");tail=symbol(&f,"lpx25_tail");eof=symbol(&f,"lpx25_eof");
 error=symbol(&f,"lpx25_error");stopped=symbol(&f,"lpx25_stopped");queue=symbol(&f,"lpx25_queue");bss=symbol(&f,"__bss_end");
 decode_begin=symbol(&f,"lpx25_decode_begin");decode_end=symbol(&f,"lpx25_decode_end");
 if(queue<H_RAMSTART || queue+H_LPX25_QUEUE>bss || bss>H_RAMEND+1)return 2;
 if(avr_init(&cpu)<0)return 2;cpu.frequency=16000000;f.frequency=16000000;avr_load_firmware(&cpu,&f);
 cpu.run_cycle_limit=1;
 out=fopen(argv[2],"wb");if(!out)return 2;
 avr_irq_t *audio=avr_get_interrupt_irq(&cpu,H_TIMER0_COMPA_vect_num);
 avr_irq_register_notify(audio+AVR_INT_IRQ_PENDING,pending,NULL);
 avr_irq_register_notify(audio+AVR_INT_IRQ_RUNNING,running,NULL);
 avr_irq_register_notify(avr_iomem_getirq(&cpu,H_OCR1AL,NULL,AVR_IOMEM_IRQ_ALL),pwm,NULL);
 uint64_t end=0;int state=cpu_Running;
 while(cpu.cycle<UINT64_C(1000000000) && state!=cpu_Crashed && state!=cpu_Done){
  if(cpu.pc==decode_begin && !decoding){decode_start=cpu.cycle;decode_irq_start=irq_total;decoding=1;decode_active=cpu.data[H_TCCR0A]!=0;}
  if(cpu.pc==decode_end && decoding){
   uint64_t elapsed=cpu.cycle-decode_start,interrupted=irq_total-decode_irq_start;
   if(interrupted>elapsed){fprintf(stderr,"Invalid decode IRQ accounting\n");return 6;}
   const uint64_t foreground=elapsed-interrupted;
   decode_sum+=elapsed;decode_calls++;decode_irq_sum+=interrupted;decode_cpu_sum+=foreground;
   if(foreground>decode_cpu_max)decode_cpu_max=foreground;
   if(elapsed>decode_max)decode_max=elapsed;
   if(decode_active){active_sum+=elapsed;active_cpu_sum+=foreground;active_calls++;}decoding=0;
  }
  state=avr_run(&cpu);
  if(irq_finishing){
   uint64_t duration=cpu.cycle-irq_start;irq_total+=duration;if(duration>irq_max)irq_max=duration;
   irq_finishing=0;
  }
  unsigned sp=cpu.data[H_SPL]|cpu.data[H_SPH]<<8;
  if(sp>=H_RAMSTART && sp<=H_RAMEND)sp_ready=1;
  if(sp_ready && sp<minimum_sp)minimum_sp=sp;
  if(minimum_sp<bss){fprintf(stderr,"Stack collision\n");return 4;}
  if(cpu.data[stopped] && !in_irq){if(!end)end=cpu.cycle;if(cpu.cycle-end>=12000)break;}
 }
 fclose(out);FILE *report=fopen(argv[3],"w");if(!report)return 2;
 fprintf(report,"{\"samples\":%llu,\"ticks\":%llu,\"timer_events\":%llu,\"underruns\":%llu,\"min_queue\":%u,"
  "\"first_output_cycle\":%llu,\"last_output_cycle\":%llu,\"output_gap_min\":%llu,\"output_gap_max\":%llu,"
  "\"timer_event_gap_min\":%llu,\"timer_event_gap_max\":%llu,\"irq_mean\":%.6f,\"irq_max\":%llu,"
  "\"irq_entry_cycles\":4,\"irq_reti_complete\":true,"
  "\"decode_calls\":%llu,\"decode_mean\":%.6f,\"decode_active_irq_mean\":%.6f,\"decode_max\":%llu,"
  "\"decode_cycles\":%llu,\"decode_irq_cycles\":%llu,\"decode_cpu_cycles\":%llu,"
  "\"decode_cpu_mean\":%.6f,\"decode_active_cpu_mean\":%.6f,\"decode_cpu_max\":%llu,"
  "\"stack_bytes\":%u,\"stack_margin\":%u,\"eof\":%u,\"error\":%u,\"stopped\":%u,\"queue_empty\":%s,\"timer_stopped\":%s}\n",
  (unsigned long long)writes,(unsigned long long)ticks,(unsigned long long)events,(unsigned long long)underruns,min_queue,
  (unsigned long long)first,(unsigned long long)last,(unsigned long long)min_gap,(unsigned long long)max_gap,
  (unsigned long long)event_min,(unsigned long long)event_max,(double)irq_total/(ticks?ticks:1),(unsigned long long)irq_max,
  (unsigned long long)decode_calls,(double)decode_sum/(decode_calls?decode_calls:1),(double)active_sum/(active_calls?active_calls:1),(unsigned long long)decode_max,
  (unsigned long long)decode_sum,(unsigned long long)decode_irq_sum,(unsigned long long)decode_cpu_sum,
  (double)decode_cpu_sum/(decode_calls?decode_calls:1),(double)active_cpu_sum/(active_calls?active_calls:1),
  (unsigned long long)decode_cpu_max,
  H_RAMEND-minimum_sp,minimum_sp-bss,cpu.data[eof],cpu.data[error],cpu.data[stopped],
  cpu.data[head]==cpu.data[tail]?"true":"false",!cpu.data[H_TCCR0A]&&!cpu.data[H_TIMSK0]?"true":"false");
 fclose(report);avr_terminate(&cpu);return end?0:5;
}
