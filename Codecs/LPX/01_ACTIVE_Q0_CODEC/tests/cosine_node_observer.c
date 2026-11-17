/* Test adapter against simavr 1.6 public APIs; no simulator code copied. */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "sim_avr.h"
#include "sim_core.h"
#include "sim_elf.h"
#include "sim_interrupts.h"
enum { READY,NODE,VALUE,IRQS,CASE,HARDWARE,NSYM };
static const char *symbols[NSYM]={"ready","node","value","irqs","case","hardware"};
typedef struct {
 avr_t *cpu;elf_firmware_t elf;unsigned sym[NSYM],spl,sph;
 uint64_t irqs;unsigned in_irq,finishing;uint8_t saved[32],flags[7];
} Machine;
static unsigned symbol(elf_firmware_t *f,const char *name){
 char full[64];snprintf(full,sizeof full,"probe_%s",name);
 for(unsigned i=0;i<f->symbolcount;i++)if(!strcmp(f->symbol[i]->symbol,full))return f->symbol[i]->addr&65535;
 fprintf(stderr,"Missing fixture symbol\n");exit(2);
}
static unsigned word(const uint8_t *data,unsigned at){return data[at]|(unsigned)data[at+1]<<8;}
static unsigned sp(Machine *m){return m->cpu->data[m->spl]|(unsigned)m->cpu->data[m->sph]<<8;}
static void running(struct avr_irq_t *irq,uint32_t value,void *parameter){
 (void)irq;Machine *m=parameter;
 if(value){
  m->in_irq=1;m->irqs++;memcpy(m->saved,m->cpu->data,32);
  for(unsigned i=0;i<7;i++)m->flags[i]=m->cpu->sreg[i];
  m->cpu->cycle+=4;
 }else{m->in_irq=0;m->finishing=1;}
}
static void step(Machine *m){
 if(avr_run(m->cpu)==cpu_Crashed){fprintf(stderr,"Probe CPU crashed\n");exit(3);}
 if(m->finishing){
  if(memcmp(m->saved,m->cpu->data,32)){fprintf(stderr,"IRQ register context mismatch\n");exit(3);}
  for(unsigned i=0;i<7;i++)if(m->flags[i]!=m->cpu->sreg[i]){fprintf(stderr,"IRQ SREG mismatch\n");exit(3);}
  m->finishing=0;
 }
}
static void initialize(Machine *m,const char *folder,const char *name){
 char path[4096];snprintf(path,sizeof path,"%s/%s.elf",folder,name);
 if(elf_read_firmware(path,&m->elf)<0 || !(m->cpu=avr_make_mcu_by_name("atmega328p")) || avr_init(m->cpu)<0)exit(2);
 m->cpu->frequency=16000000;m->elf.frequency=16000000;avr_load_firmware(m->cpu,&m->elf);m->cpu->run_cycle_limit=1;
 for(unsigned i=0;i<NSYM;i++)m->sym[i]=symbol(&m->elf,symbols[i]);
 const unsigned hw=m->sym[HARDWARE];m->spl=word(m->cpu->flash,hw);m->sph=word(m->cpu->flash,hw+2);
 avr_irq_t *irq=avr_get_interrupt_irq(m->cpu,word(m->cpu->flash,hw+4));
 avr_irq_register_notify(irq+AVR_INT_IRQ_RUNNING,running,m);
 while(!m->cpu->data[m->sym[READY]]){step(m);if(m->cpu->cycle>100000)exit(3);}
}
static const unsigned callee[]={2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29};

static unsigned invoke(Machine *m,unsigned serial,unsigned node){
 uint8_t *d=m->cpu->data;d[m->sym[NODE]]=node;
 for(unsigned i=0;i<sizeof callee/sizeof callee[0];i++)d[callee[i]]=(callee[i]*19+serial)&255;
 const unsigned stack=sp(m);const uint64_t start=m->cpu->cycle;
 _avr_push_addr(m->cpu,0);m->cpu->pc=m->sym[CASE];
 do{step(m);if(m->cpu->cycle-start>20000)exit(3);}while(m->cpu->pc||m->in_irq);
 if(sp(m)!=stack||d[1])exit(3);
 for(unsigned i=0;i<sizeof callee/sizeof callee[0];i++)if(d[callee[i]]!=((callee[i]*19+serial)&255))exit(3);
 return word(d,m->sym[VALUE]);
}
int main(int argc,char **argv){
 if(argc!=2)return 2;
 Machine machines[4]={0};const char *names[]={"old-asm","new-asm","old-c","new-c"};
 for(unsigned i=0;i<4;i++)initialize(machines+i,argv[1],names[i]);
 unsigned count=0;
 for(unsigned repeat=0;repeat<16;repeat++)for(unsigned node=1;node<128;node++){
  const unsigned reference=invoke(machines,count,node);
  for(unsigned i=1;i<4;i++)if(invoke(machines+i,count,node)!=reference){fprintf(stderr,"Cosine node mismatch\n");return 4;}
  count++;
 }
 char path[4096];snprintf(path,sizeof path,"%s/verification.json",argv[1]);FILE *out=fopen(path,"w");if(!out)return 2;
 fprintf(out,"{\"cases_per_backend\":%u,\"backends\":4,\"minimum_node\":1,\"maximum_node\":127,\"repeats\":16,\"all_reachable_nodes_exact\":true,\"C_and_ASM_exact\":true,\"abi_preserved\":true,\"native_target\":\"atmega328p\",\"physical_board_measured\":false,\"irq_counts\":[",count);
 for(unsigned i=0;i<4;i++){
  if(machines[i].irqs<100 || (machines[i].irqs&65535)!=word(machines[i].cpu->data,machines[i].sym[IRQS]))return 5;
  fprintf(out,"%s%llu",i?",":"",(unsigned long long)machines[i].irqs);avr_terminate(machines[i].cpu);
 }
 fprintf(out,"]}\n");fclose(out);printf("Cosine native proof passed: %u cases/backend\n",count);return 0;
}
