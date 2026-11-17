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
#ifdef H_LPX_NATIVE_TARGET
static avr_t *native_cpu;
#define cpu (*native_cpu)
static uint8_t entry_registers[32],entry_flags[7];
static FILE *valid_out;
static unsigned expected_valid;
static uint64_t irq_r0_nonzero,irq_r1_nonzero;
#else
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
#endif
#ifndef H_LPX_SAMPLE_VECTOR
#define H_LPX_SAMPLE_VECTOR H_TIMER0_COMPA_vect_num
#define H_LPX_SAMPLE_CLOCK H_TCCR0A
#define H_LPX_SAMPLE_MASK H_TIMSK0
#define H_LPX_PWM_REGISTER H_OCR1AL
#endif
static unsigned head,tail,eof,error,stopped,queue,bss,decode_begin,decode_end;
static FILE *out;
static uint64_t ticks,writes,underruns,first,last,min_gap=UINT64_MAX,max_gap,irq_start,irq_total,irq_max;
static uint64_t event_last,event_min=UINT64_MAX,event_max,events;
static unsigned in_irq,irq_finishing,min_queue=H_LPX25_QUEUE,minimum_sp=H_RAMEND,sp_ready;
static uint64_t decode_start,decode_sum,decode_calls,decode_max,active_sum,active_calls;
static uint64_t decode_irq_start,decode_irq_sum,decode_cpu_sum,decode_cpu_max,active_cpu_sum;
static unsigned decoding,decode_active;
/* Foreground-only direct IN/LDS(head) to actual OUT/STS(head) publication.
 * All addresses come from ELF aliases; no firmware markers are added.
 * Each retry replaces the pending read, so full-queue waits are excluded.
 */
static uint64_t producer_start,producer_irq_start,producer_calls;
static uint64_t producer_sum,producer_irq_sum,producer_cpu_sum,producer_cpu_max;
static uint64_t producer_active_calls,producer_active_sum,producer_active_cpu_sum,producer_active_cpu_max;
static unsigned producer_open,producer_decoded,producer_active;
static uint64_t irq_clock(void){
 return irq_total+((in_irq||irq_finishing)?cpu.cycle-irq_start:0);
}
static unsigned head_access(uint32_t pc,unsigned store){
 if(pc+1>H_FLASHEND)return 0;
 const uint16_t op=cpu.flash[pc]|(uint16_t)cpu.flash[pc+1]<<8;
 /* Ordinary AVR IN/OUT has a six-bit I/O address, mapped at data+0x20. */
 if(head>=0x20 && head<0x60 && (op&0xf800)==(store?0xb800:0xb000))
  return ((op&15)|((op>>5)&0x30))+0x20==head;
 /* Direct SRAM fallback for a build that does not use a GPIOR alias. */
 if(pc+3<=H_FLASHEND && (op&0xfe0f)==(store?0x9200:0x9000))
  return (cpu.flash[pc+2]|(unsigned)cpu.flash[pc+3]<<8)==head;
 return 0;
}
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
#ifdef H_LPX_NATIVE_TARGET
  memcpy(entry_registers,cpu.data,32);
  irq_r0_nonzero+=entry_registers[0]!=0;
  irq_r1_nonzero+=entry_registers[1]!=0;
  for(unsigned i=0;i<7;i++)entry_flags[i]=cpu.sreg[i];
#endif
  // simavr1.6 avr_service_interrupts pushes PC/clears I but charges no
  // response cycles. Account the real AVRe four-cycle hardware entry here.
  // Existing cycle timers observe the advanced clock on the next avr_run.
  cpu.cycle+=4;
  unsigned h=cpu.data[head],t=cpu.data[tail];
  if(h>=H_LPX25_QUEUE || t>=H_LPX25_QUEUE){fprintf(stderr,"Invalid queue cursor\n");exit(3);}
  unsigned count=h>=t?h-t:H_LPX25_QUEUE+h-t;
#ifdef H_LPX_NATIVE_TARGET
  expected_valid=count!=0;
#endif
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
#ifdef H_LPX_NATIVE_TARGET
 if(expected_valid)fputc(value&255,valid_out);
#endif
}
int main(int argc,char **argv){
 if(argc!=4){fprintf(stderr,"usage: sim_player player.elf output.pwm timing.json\n");return 2;}
 elf_firmware_t f={0};if(elf_read_firmware(argv[1],&f)<0 || f.flashsize>H_FLASHEND+1)return 2;
 head=symbol(&f,"lpx25_head");tail=symbol(&f,"lpx25_tail");eof=symbol(&f,"lpx25_eof");
 error=symbol(&f,"lpx25_error");stopped=symbol(&f,"lpx25_stopped");queue=symbol(&f,"lpx25_queue");bss=symbol(&f,"__bss_end");
 decode_begin=symbol(&f,"lpx25_decode_begin");decode_end=symbol(&f,"lpx25_decode_end");
 if(queue<H_RAMSTART || queue+H_LPX25_QUEUE>bss || bss>H_RAMEND+1)return 2;
#ifdef H_LPX_NATIVE_TARGET
 if(!(native_cpu=avr_make_mcu_by_name(H_LPX_NATIVE_TARGET)))return 2;
#endif
 if(avr_init(&cpu)<0)return 2;cpu.frequency=16000000;f.frequency=16000000;avr_load_firmware(&cpu,&f);
 cpu.run_cycle_limit=1;
 out=fopen(argv[2],"wb");if(!out)return 2;
#ifdef H_LPX_NATIVE_TARGET
 char *valid_name=malloc(strlen(argv[2])+7);if(!valid_name)return 2;
 sprintf(valid_name,"%s.valid",argv[2]);
 valid_out=fopen(valid_name,"wb");free(valid_name);if(!valid_out)return 2;
#endif
 avr_irq_t *audio=avr_get_interrupt_irq(&cpu,H_LPX_SAMPLE_VECTOR);
 avr_irq_register_notify(audio+AVR_INT_IRQ_PENDING,pending,NULL);
 avr_irq_register_notify(audio+AVR_INT_IRQ_RUNNING,running,NULL);
 avr_irq_register_notify(avr_iomem_getirq(&cpu,H_LPX_PWM_REGISTER,NULL,AVR_IOMEM_IRQ_ALL),pwm,NULL);
 uint64_t end=0;int state=cpu_Running;
 while(cpu.cycle<UINT64_C(1000000000) && state!=cpu_Crashed && state!=cpu_Done){
  const unsigned foreground_step=!in_irq;
  const unsigned before_head=cpu.data[head];
  const unsigned publishing=foreground_step && head_access(cpu.pc,1);
  if(foreground_step && head_access(cpu.pc,0)){
   producer_start=cpu.cycle;producer_irq_start=irq_clock();
   producer_open=1;producer_decoded=0;
   producer_active=cpu.data[H_LPX_SAMPLE_CLOCK]!=0;
  }
  if(cpu.pc==decode_begin && !decoding){
   if(!producer_open){fprintf(stderr,"Decode without a supported foreground head read\n");return 8;}
   producer_decoded=1;decode_start=cpu.cycle;decode_irq_start=irq_total;decoding=1;decode_active=cpu.data[H_LPX_SAMPLE_CLOCK]!=0;}
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
#ifdef H_LPX_NATIVE_TARGET
   for(unsigned i=0;i<32;i++){
    if(i!=H_LPX_IRQ_SAMPLE && i!=H_LPX_IRQ_SREG && cpu.data[i]!=entry_registers[i]){
     fprintf(stderr,"IRQ failed to preserve a CPU register\n");return 7;
    }
   }
   for(unsigned i=0;i<7;i++)if(cpu.sreg[i]!=entry_flags[i]){
    fprintf(stderr,"IRQ failed to preserve SREG\n");return 7;
   }
#endif
   uint64_t duration=cpu.cycle-irq_start;irq_total+=duration;if(duration>irq_max)irq_max=duration;
   irq_finishing=0;
  }
  if(publishing && cpu.data[head]!=before_head && producer_open && producer_decoded){
   const uint64_t elapsed=cpu.cycle-producer_start;
   const uint64_t interrupted=irq_clock()-producer_irq_start;
   if(interrupted>elapsed){fprintf(stderr,"Invalid producer IRQ accounting\n");return 8;}
   const uint64_t foreground=elapsed-interrupted;
   producer_calls++;producer_sum+=elapsed;producer_irq_sum+=interrupted;producer_cpu_sum+=foreground;
   if(foreground>producer_cpu_max)producer_cpu_max=foreground;
   if(producer_active){
    producer_active_calls++;producer_active_sum+=elapsed;producer_active_cpu_sum+=foreground;
    if(foreground>producer_active_cpu_max)producer_active_cpu_max=foreground;
   }
   producer_open=0;producer_decoded=0;
  }
  unsigned sp=cpu.data[H_SPL]|cpu.data[H_SPH]<<8;
  if(sp>=H_RAMSTART && sp<=H_RAMEND)sp_ready=1;
  if(sp_ready && sp<minimum_sp)minimum_sp=sp;
  if(minimum_sp<bss){fprintf(stderr,"Stack collision\n");return 4;}
  if(cpu.data[stopped] && !in_irq){if(!end)end=cpu.cycle;if(cpu.cycle-end>=12000)break;}
 }
#ifdef H_LPX_NATIVE_TARGET
 fclose(valid_out);
#endif
 fclose(out);FILE *report=fopen(argv[3],"w");if(!report)return 2;
 fprintf(report,"{\"samples\":%llu,\"ticks\":%llu,\"timer_events\":%llu,\"underruns\":%llu,\"min_queue\":%u,"
  "\"first_output_cycle\":%llu,\"last_output_cycle\":%llu,\"output_gap_min\":%llu,\"output_gap_max\":%llu,"
  "\"timer_event_gap_min\":%llu,\"timer_event_gap_max\":%llu,\"irq_mean\":%.6f,\"irq_max\":%llu,"
  "\"irq_entry_cycles\":4,\"irq_reti_complete\":true,"
  "\"decode_calls\":%llu,\"decode_mean\":%.6f,\"decode_active_irq_mean\":%.6f,\"decode_max\":%llu,"
  "\"decode_cycles\":%llu,\"decode_irq_cycles\":%llu,\"decode_cpu_cycles\":%llu,"
  "\"decode_cpu_mean\":%.6f,\"decode_active_cpu_mean\":%.6f,\"decode_cpu_max\":%llu,"
  "\"stack_bytes\":%u,\"stack_margin\":%u,\"eof\":%u,\"error\":%u,\"stopped\":%u,\"queue_empty\":%s,\"timer_stopped\":%s"
#ifdef H_LPX_NATIVE_TARGET
  ",\"irq_r0_nonzero\":%llu,\"irq_r1_nonzero\":%llu,\"irq_registers_preserved\":true"
#endif
  "",
  (unsigned long long)writes,(unsigned long long)ticks,(unsigned long long)events,(unsigned long long)underruns,min_queue,
  (unsigned long long)first,(unsigned long long)last,(unsigned long long)min_gap,(unsigned long long)max_gap,
  (unsigned long long)event_min,(unsigned long long)event_max,(double)irq_total/(ticks?ticks:1),(unsigned long long)irq_max,
  (unsigned long long)decode_calls,(double)decode_sum/(decode_calls?decode_calls:1),(double)active_sum/(active_calls?active_calls:1),(unsigned long long)decode_max,
  (unsigned long long)decode_sum,(unsigned long long)decode_irq_sum,(unsigned long long)decode_cpu_sum,
  (double)decode_cpu_sum/(decode_calls?decode_calls:1),(double)active_cpu_sum/(active_calls?active_calls:1),
  (unsigned long long)decode_cpu_max,
  H_RAMEND-minimum_sp,minimum_sp-bss,cpu.data[eof],cpu.data[error],cpu.data[stopped],
  cpu.data[head]==cpu.data[tail]?"true":"false",!cpu.data[H_LPX_SAMPLE_CLOCK]&&!cpu.data[H_LPX_SAMPLE_MASK]?"true":"false"
#ifdef H_LPX_NATIVE_TARGET
  ,(unsigned long long)irq_r0_nonzero,(unsigned long long)irq_r1_nonzero
#endif
  );
 fprintf(report,
  ",\"producer_accounting_kind\":\"foreground-direct-head-read-to-publish-v1\","
  "\"producer_calls\":%llu,\"producer_active_calls\":%llu,\"producer_unpublished_decode_calls\":%llu,"
  "\"producer_cycles\":%llu,\"producer_irq_cycles\":%llu,\"producer_cpu_cycles\":%llu,"
  "\"producer_mean\":%.6f,\"producer_cpu_mean\":%.6f,\"producer_cpu_max\":%llu,"
  "\"producer_active_irq_mean\":%.6f,\"producer_active_cpu_mean\":%.6f,\"producer_active_cpu_max\":%llu}\n",
  (unsigned long long)producer_calls,(unsigned long long)producer_active_calls,
  (unsigned long long)(decode_calls-producer_calls),
  (unsigned long long)producer_sum,(unsigned long long)producer_irq_sum,(unsigned long long)producer_cpu_sum,
  (double)producer_sum/(producer_calls?producer_calls:1),(double)producer_cpu_sum/(producer_calls?producer_calls:1),
  (unsigned long long)producer_cpu_max,
  (double)producer_active_sum/(producer_active_calls?producer_active_calls:1),
  (double)producer_active_cpu_sum/(producer_active_calls?producer_active_calls:1),(unsigned long long)producer_active_cpu_max);
 fclose(report);avr_terminate(&cpu);return end?0:5;
}
