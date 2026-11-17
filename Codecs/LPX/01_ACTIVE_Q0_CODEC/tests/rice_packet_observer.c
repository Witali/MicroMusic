/* Test adapter against simavr 1.6 public APIs; no simulator code copied. */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "sim_avr.h"
#include "sim_core.h"
#include "sim_elf.h"
#include "sim_interrupts.h"
enum { READY,PROFILE,K,WIDTH,LEFT,CACHE,BYTES,INITIAL_ERROR,VALUE,END_LEFT,END_CACHE,ERROR,END_BYTES,CURSOR,IRQS,CASE,FEED,HARDWARE,NSYM };
static const char *symbols[NSYM]={"ready","profile","k","width","left","cache","bytes","initial_error","value","end_left","end_cache","error","end_bytes","cursor","irqs","case","feed","hardware"};
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
static void invoke(Machine *m,unsigned serial,unsigned profile,unsigned k,unsigned width,unsigned left,unsigned cache,unsigned bytes,unsigned error,const uint8_t feed[2],unsigned result[6]){
 uint8_t *d=m->cpu->data;
 d[m->sym[PROFILE]]=profile;d[m->sym[K]]=k;d[m->sym[WIDTH]]=width;d[m->sym[LEFT]]=left;d[m->sym[CACHE]]=cache;d[m->sym[BYTES]]=bytes;d[m->sym[INITIAL_ERROR]]=error;
 memcpy(m->cpu->flash+m->sym[FEED],feed,2); /* Synthetic data object only. */
 for(unsigned i=0;i<sizeof callee/sizeof callee[0];i++)d[callee[i]]=(callee[i]*19+serial)&255;
 const unsigned stack=sp(m);const uint64_t start=m->cpu->cycle;
 _avr_push_addr(m->cpu,0);m->cpu->pc=m->sym[CASE];
 do{step(m);if(m->cpu->cycle-start>20000){fprintf(stderr,"Probe cycle bound\n");exit(3);}}while(m->cpu->pc || m->in_irq);
 if(sp(m)!=stack || d[1]){fprintf(stderr,"SP/r1 ABI mismatch\n");exit(3);}
 for(unsigned i=0;i<sizeof callee/sizeof callee[0];i++)if(d[callee[i]]!=((callee[i]*19+serial)&255)){fprintf(stderr,"Callee ABI mismatch\n");exit(3);}
 result[0]=d[m->sym[VALUE]];result[1]=d[m->sym[END_LEFT]];result[2]=d[m->sym[END_CACHE]];result[3]=d[m->sym[ERROR]];
 result[4]=word(d,m->sym[END_BYTES]);result[5]=word(d,m->sym[CURSOR]);
}
int main(int argc,char **argv){
 if(argc!=2)return 2;
 Machine machines[4]={0};const char *names[]={"old-asm","new-asm","old-c","new-c"};
 for(unsigned i=0;i<4;i++)initialize(machines+i,argv[1],names[i]);
 unsigned count=0,success=0,errors=0;
 const unsigned profiles[]={4,6,15};
 for(unsigned pi=0;pi<3;pi++)for(unsigned delta=0;delta<2;delta++){
  const unsigned profile=profiles[pi],bits=profile==4?5:6,k=bits-4-delta,width=bits+delta;
  for(unsigned high=0;high<=8;high++)for(unsigned value=0;value<(1u<<(high==8?width:k));value++){
   uint8_t bits[32]={0};unsigned length=high;
   if(high<8)bits[length++]=1;
   for(unsigned i=0;i<(high==8?width:k);i++)bits[length++]=(value>>i)&1;
   while(length<32){bits[length]=(length*13+value+high)&1;length++;}
   for(unsigned left=0;left<8;left++)for(unsigned bytes=0;bytes<=2;bytes++)for(unsigned initial=0;initial<2;initial++){
    unsigned cache=0;uint8_t feed[2]={0};
    for(unsigned i=0;i<left;i++)cache|=(unsigned)bits[i]<<i;
    for(unsigned i=0;i<16;i++)feed[i/8]|=bits[left+i]<<(i&7);
    unsigned reference[6]={0},c_reference[6]={0};
    for(unsigned machine=0;machine<4;machine++){
     unsigned result[6];invoke(machines+machine,count,profile,k,width,left,cache,bytes,initial?4:0,feed,result);
     if(!machine)memcpy(reference,result,sizeof result);
     else if(machine==1 && memcmp(reference,result,sizeof result)){fprintf(stderr,"ASM Rice trace mismatch at case%u\n",count);return 4;}
     else if(machine==2){
      memcpy(c_reference,result,sizeof result);
      if(!initial && memcmp(reference,result,sizeof result)){fprintf(stderr,"Clear-error C/ASM trace mismatch at case%u\n",count);return 4;}
     }else if(machine==3 && memcmp(c_reference,result,sizeof result)){fprintf(stderr,"C Rice trace mismatch at case%u\n",count);return 4;}
    }
    if(reference[3])errors++;else success++;
    count++;
   }
  }
 }
 char path[4096];snprintf(path,sizeof path,"%s/verification.json",argv[1]);FILE *out=fopen(path,"w");if(!out)return 2;
 fprintf(out,"{\"cases_per_backend\":%u,\"backends\":4,\"successful_traces\":%u,\"error_traces\":%u,\"all_payload_values\":true,\"cache_positions\":8,\"rom_bytes\":[0,1,2],\"initial_errors\":[0,4],\"paired_old_new_full_reader_state_exact\":true,\"cross_C_ASM_clear_error_state_exact\":true,\"existing_nonzero_error_private_state_difference_retained\":true,\"abi_preserved\":true,\"native_target\":\"atmega328p\",\"physical_board_measured\":false,\"irq_counts\":[",count,success,errors);
 for(unsigned i=0;i<4;i++){
  if(machines[i].irqs<100 || (machines[i].irqs&65535)!=word(machines[i].cpu->data,machines[i].sym[IRQS]))return 5;
  fprintf(out,"%s%llu",i?",":"",(unsigned long long)machines[i].irqs);avr_terminate(machines[i].cpu);
 }
 fprintf(out,"]}\n");fclose(out);printf("Rice native proof passed:%u cases/backend\n",count);return 0;
}
