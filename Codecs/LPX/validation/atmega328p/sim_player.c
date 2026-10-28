/* External observer for the standalone player; no diagnostic AVR globals.
 * Original project code against public simavr1.6 API (GPL-3.0-or-later library).
 * References: github.com/buserror/simavr/tree/v1.6/simavr/sim
 * sim_interrupts.h RUNNING notifications and sim_io.h ALL register notifications.
 * Hardware addresses/vector come from a separately compiled vendor-header object.
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <ctype.h>
#include <fcntl.h>
#include <unistd.h>
#include <libelf.h>
#include <gelf.h>
#include "avr_timer.h"
#include "avr_ioport.h"
#include "sim_avr.h"
#include "sim_elf.h"
#include "sim_io.h"
#include "sim_interrupts.h"
enum {PWM,SPL_ADDR,SPH_ADDR,TCCR1B_ADDR,TIMSK1_ADDR,OCR1AL_ADDR,OCR1AH_ADDR,
      TCCR2A_ADDR,TCCR2B_ADDR,DDRD_ADDR,TIMER_VECTOR,RUN_BITS,MASK_BITS,PWM_BITS,
      PWM_CLOCK,OUTPUT_BIT,QUEUE_SIZE,PREFILL,INDEX_BYTES,TIMER_TOP,
      HEAD_ADDR,TAIL_ADDR,EOF_ADDR,ERROR_ADDR,STOP_ADDR,QUEUE_ADDR,BSS_END,META_COUNT};
static avr_t *cpu;
static uint32_t m[META_COUNT];
static FILE *output;
static uint64_t ticks,played,produced,underruns,pending_ticks;
static uint64_t previous_tick,min_tick=UINT64_MAX,max_tick,first_tick;
static uint64_t previous_event,min_event=UINT64_MAX,max_event;
static uint64_t irq_start,irq_total,irq_max,output_first,output_last;
static uint64_t previous_output,min_output=UINT64_MAX,max_output;
static uint32_t minimum_sp=UINT32_MAX,minimum_sp_play=UINT32_MAX,min_queue=UINT32_MAX;
static uint32_t old_head,entry_tail,entry_head,expected_sample,irq_writes;
static unsigned in_irq,started,valid,observer_errors,sp_ready;
static int read_metadata(const char *path){
    FILE *file=fopen(path,"rb");if(!file)return 0;
    char text[1024];size_t bytes=fread(text,1,sizeof(text)-1,file);
    int extra=fgetc(file);fclose(file);
    if(extra!=EOF || !bytes || memchr(text,0,bytes))return 0;
    text[bytes]=0;char *at=text;
    for(unsigned i=0;i<META_COUNT;i++){
        while(isspace((unsigned char)*at))++at;
        if(!isdigit((unsigned char)*at))return 0;
        errno=0;char *end;unsigned long long value=strtoull(at,&end,10);
        if(errno || end==at || value>UINT32_MAX)return 0;
        m[i]=(uint32_t)value;at=end;
    }
    while(isspace((unsigned char)*at))++at;
    return !*at;
}
static int symbol_name(const char *name,const char *base){
    size_t n=strlen(base);return !strncmp(name,base,n) && (!name[n] || name[n]=='.');
}
static int elf_state_matches(const char *path){
    const char *names[]={"lpx_player_head","lpx_player_tail","lpx_player_eof",
        "lpx_player_error","lpx_player_stopped","lpx_player_queue","__bss_end"};
    unsigned fields[]={HEAD_ADDR,TAIL_ADDR,EOF_ADDR,ERROR_ADDR,STOP_ADDR,QUEUE_ADDR,BSS_END};
    unsigned sizes[]={m[INDEX_BYTES],m[INDEX_BYTES],1,1,1,m[QUEUE_SIZE],0},found[7]={0};
    if(elf_version(EV_CURRENT)==EV_NONE)return 0;
    int fd=open(path,O_RDONLY);if(fd<0)return 0;
    Elf *elf=elf_begin(fd,ELF_C_READ,NULL);if(!elf){close(fd);return 0;}
    int valid=1;Elf_Scn *section=NULL;
    while((section=elf_nextscn(elf,section))){
        GElf_Shdr header;if(!gelf_getshdr(section,&header)){valid=0;break;}
        if(header.sh_type!=SHT_SYMTAB)continue;
        if(!header.sh_entsize || header.sh_size/header.sh_entsize>INT_MAX){valid=0;break;}
        Elf_Data *data=elf_getdata(section,NULL);if(!data){valid=0;break;}
        for(size_t i=0;i<header.sh_size/header.sh_entsize;i++){
            GElf_Sym sym;if(!gelf_getsym(data,(int)i,&sym)){valid=0;break;}
            const char *name=elf_strptr(elf,header.sh_link,sym.st_name);if(!name){valid=0;break;}
            if(!strncmp(name,"profile_",8) || !strcmp(name,"lpx_player_hardware"))valid=0;
            for(unsigned j=0;j<7;j++)if(symbol_name(name,names[j])){
                ++found[j];if(sym.st_value!=UINT32_C(0x800000)+m[fields[j]] || sym.st_size!=sizes[j])valid=0;
            }
        }
    }
    for(unsigned j=0;j<7;j++)if(found[j]!=1)valid=0;
    elf_end(elf);close(fd);return valid;
}
static int metadata_valid(const char *elf){
    if((m[QUEUE_SIZE]!=128 && m[QUEUE_SIZE]!=256 && m[QUEUE_SIZE]!=512) ||
       m[INDEX_BYTES]!=(m[QUEUE_SIZE]>256?2:1) || !m[PREFILL] || m[PREFILL]>=m[QUEUE_SIZE] ||
       m[TIMER_TOP]+1!=cpu->frequency/8000 || !m[TIMER_VECTOR] || m[TIMER_VECTOR]>255)return 0;
    uint32_t low=(uint32_t)cpu->ioend+1,high=(uint32_t)cpu->ramend+1;
    unsigned states[]={HEAD_ADDR,TAIL_ADDR,EOF_ADDR,ERROR_ADDR,STOP_ADDR,QUEUE_ADDR};
    unsigned sizes[]={m[INDEX_BYTES],m[INDEX_BYTES],1,1,1,m[QUEUE_SIZE]};
    if(m[BSS_END]<low || m[BSS_END]>high)return 0;
    for(unsigned i=0;i<6;i++){
        uint32_t begin=m[states[i]];
        if(begin<low || begin>high-sizes[i] || begin+sizes[i]>m[BSS_END])return 0;
        for(unsigned j=0;j<i;j++)if(begin<m[states[j]]+sizes[j] && m[states[j]]<begin+sizes[i])return 0;
    }
    unsigned io_fields[]={PWM,SPL_ADDR,SPH_ADDR,TCCR1B_ADDR,TIMSK1_ADDR,OCR1AL_ADDR,OCR1AH_ADDR,TCCR2A_ADDR,TCCR2B_ADDR,DDRD_ADDR};
    for(unsigned i=0;i<10;i++){
        if(m[io_fields[i]]<AVR_IO_TO_DATA(0) || m[io_fields[i]]>cpu->ioend)return 0;
        for(unsigned j=0;j<i;j++)if(m[io_fields[i]]==m[io_fields[j]])return 0;
    }
    if(m[SPL_ADDR]!=R_SPL || m[SPH_ADDR]!=R_SPH)return 0;
    avr_timer_t *one=NULL,*two=NULL;avr_ioport_t *port=NULL;
    for(avr_io_t *io=cpu->io_port;io;io=io->next){
        if(io->irq_ioctl_get==AVR_IOCTL_TIMER_GETIRQ('1'))one=(avr_timer_t*)io;
        if(io->irq_ioctl_get==AVR_IOCTL_TIMER_GETIRQ('2'))two=(avr_timer_t*)io;
        if(io->irq_ioctl_get==AVR_IOCTL_IOPORT_GETIRQ('D'))port=(avr_ioport_t*)io;
    }
    if(!one || !two || !port)return 0;
    avr_timer_comp_t *a=&one->comp[AVR_TIMER_COMPA],*b=&two->comp[AVR_TIMER_COMPB];
    if(m[TIMER_VECTOR]!=a->interrupt.vector || m[TIMSK1_ADDR]!=a->interrupt.enable.reg ||
       m[MASK_BITS]!=(1u<<a->interrupt.enable.bit) || m[OCR1AL_ADDR]!=a->r_ocr || m[OCR1AH_ADDR]!=a->r_ocrh ||
       m[TCCR1B_ADDR]!=one->cs[0].reg || m[RUN_BITS]!=((1u<<one->cs[0].bit)|(1u<<one->wgm[2].bit)) ||
       m[PWM]!=b->r_ocr || m[TCCR2A_ADDR]!=b->com.reg || m[TCCR2B_ADDR]!=two->cs[0].reg ||
       m[PWM_BITS]!=((1u<<two->wgm[0].bit)|(1u<<two->wgm[1].bit)|(2u<<b->com.bit)) ||
       m[PWM_CLOCK]!=(1u<<two->cs[0].bit) || m[DDRD_ADDR]!=port->r_ddr ||
       b->com_pin.reg!=port->r_port || m[OUTPUT_BIT]!=(1u<<b->com_pin.bit))return 0;
    return elf_state_matches(elf);
}
static uint32_t read_le(uint32_t address,unsigned bytes){
    uint32_t result=0;for(unsigned i=0;i<bytes;i++)result|=(uint32_t)cpu->data[address+i]<<(8*i);return result;
}
static uint32_t index_at(unsigned field){return read_le(m[field],m[INDEX_BYTES]);}
static void track_head(void){
    if(!started)return;
    uint32_t head=index_at(HEAD_ADDR);
    if(head>=m[QUEUE_SIZE]){++observer_errors;return;}
    uint32_t change=(head-old_head)&(m[QUEUE_SIZE]-1);
    if(change>1)++observer_errors;
    produced+=change;old_head=head;
}
static void timer_event(struct avr_irq_t *irq,uint32_t value,void *param){
    (void)irq;(void)param;if(!value)return;
    if(pending_ticks){uint64_t d=cpu->cycle-previous_event;if(d<min_event)min_event=d;if(d>max_event)max_event=d;}
    previous_event=cpu->cycle;++pending_ticks;
}
static void pwm_write(struct avr_irq_t *irq,uint32_t value,void *param){
    (void)irq;(void)param;if(!in_irq)return;
    ++irq_writes;
    if(ticks>1){uint64_t d=cpu->cycle-previous_output;if(d<min_output)min_output=d;if(d>max_output)max_output=d;}
    if(ticks==1)output_first=cpu->cycle;
    output_last=previous_output=cpu->cycle;
    if(valid){if((value&255)!=expected_sample)++observer_errors;fputc(value&255,output);++played;}
    else{if((value&255)!=128)++observer_errors;++underruns;}
}
static void audio_irq(struct avr_irq_t *irq,uint32_t value,void *param){
    (void)irq;(void)param;
    if(value){
        if(in_irq || !started)++observer_errors;
        track_head();in_irq=1;irq_start=cpu->cycle;irq_writes=0;
        if(ticks){uint64_t d=cpu->cycle-previous_tick;if(d<min_tick)min_tick=d;if(d>max_tick)max_tick=d;}
        else first_tick=cpu->cycle;
        previous_tick=cpu->cycle;++ticks;
        entry_head=index_at(HEAD_ADDR);entry_tail=index_at(TAIL_ADDR);
        if(entry_tail>=m[QUEUE_SIZE] || entry_head>=m[QUEUE_SIZE]){
            ++observer_errors;valid=0;expected_sample=128;return;
        }
        uint32_t available=(entry_head-entry_tail)&(m[QUEUE_SIZE]-1);
        if(!cpu->data[m[EOF_ADDR]] && available<min_queue)min_queue=available;
        valid=available!=0;expected_sample=valid?cpu->data[m[QUEUE_ADDR]+entry_tail]:128;
    }else{
        if(!in_irq || irq_writes!=1)++observer_errors;
        uint32_t tail=index_at(TAIL_ADDR),expected=(entry_tail+(valid?1:0))&(m[QUEUE_SIZE]-1);
        if(tail!=expected || index_at(HEAD_ADDR)!=entry_head)++observer_errors;
        uint64_t duration=cpu->cycle-irq_start;irq_total+=duration;if(duration>irq_max)irq_max=duration;
        in_irq=0;
    }
}
int main(int argc,char **argv){
    if(argc!=5){fprintf(stderr,"usage: sim_player player.elf valid.pcm8 report.json observer.txt\n");return 2;}
    if(!read_metadata(argv[4]))return 2;
    elf_firmware_t firmware={0};if(elf_read_firmware(argv[1],&firmware)<0)return 3;
    firmware.frequency=16000000;cpu=avr_make_mcu_by_name("atmega328p");
    if(!cpu || avr_init(cpu)<0)return 4;
    cpu->frequency=16000000;
    if(!metadata_valid(argv[1])){fprintf(stderr,"Invalid observer metadata/ELF/device contract\n");return 2;}
    avr_load_firmware(cpu,&firmware);
    output=fopen(argv[2],"wb");if(!output)return 5;
    avr_irq_t *audio=avr_get_interrupt_irq(cpu,m[TIMER_VECTOR]);if(!audio)return 4;
    avr_irq_register_notify(audio+AVR_INT_IRQ_PENDING,timer_event,NULL);
    avr_irq_register_notify(audio+AVR_INT_IRQ_RUNNING,audio_irq,NULL);
    avr_irq_register_notify(avr_iomem_getirq(cpu,m[PWM],NULL,AVR_IOMEM_IRQ_ALL),pwm_write,NULL);
    int state=cpu_Running;uint64_t stopped_at=0;
    while(cpu->cycle<UINT64_C(2000000000) && state!=cpu_Crashed && state!=cpu_Done){
        state=avr_run(cpu);
        uint32_t sp=cpu->data[m[SPL_ADDR]]|((uint32_t)cpu->data[m[SPH_ADDR]]<<8);
        if(sp>=(uint32_t)cpu->ioend+1 && sp<=cpu->ramend)sp_ready=1;
        if(sp_ready && sp<minimum_sp)minimum_sp=sp;
        if(!started && cpu->data[m[TCCR1B_ADDR]]==m[RUN_BITS] &&
           (cpu->data[m[TIMSK1_ADDR]]&m[MASK_BITS])){
            started=1;old_head=index_at(HEAD_ADDR);produced=old_head;min_queue=old_head;
            if(old_head>m[PREFILL] || !old_head || cpu->data[m[TCCR2A_ADDR]]!=m[PWM_BITS] ||
               cpu->data[m[TCCR2B_ADDR]]!=m[PWM_CLOCK] ||
               !(cpu->data[m[DDRD_ADDR]]&m[OUTPUT_BIT]) ||
               read_le(m[OCR1AL_ADDR],2)!=m[TIMER_TOP])++observer_errors;
        }
        if(started && (cpu->sreg[S_I] || in_irq))track_head();
        if(started && sp<minimum_sp_play)minimum_sp_play=sp;
        if(cpu->data[m[STOP_ADDR]] && !in_irq){
            if(!stopped_at)stopped_at=cpu->cycle;
            if(cpu->cycle-stopped_at>=4000)break;
        }
    }
    fclose(output);
    if(state==cpu_Crashed || state==cpu_Done)++observer_errors;
    uint32_t queued=(index_at(HEAD_ADDR)-index_at(TAIL_ADDR))&(m[QUEUE_SIZE]-1);
    if(!started){produced=index_at(HEAD_ADDR);min_queue=queued;}
    if(produced!=played+queued)++observer_errors;
    if(cpu->data[m[STOP_ADDR]] && (cpu->data[m[TCCR1B_ADDR]] || cpu->data[m[TIMSK1_ADDR]]))++observer_errors;
    if(ticks!=pending_ticks)++observer_errors;
    if(ticks>1){
        int64_t drift=(int64_t)(output_last-output_first)-(int64_t)((ticks-1)*2000);
        if(drift < -64 || drift>64 || min_output<1936 || max_output>2064 || min_event<1996 || max_event>2004)++observer_errors;
    }
    FILE *report=fopen(argv[3],"w");if(!report)return 6;
    fprintf(report,"{\"simulator\":\"simavr1.6\",\"cpu_hz\":16000000,\"audio_hz\":8000,"
      "\"stopped\":%u,\"eof\":%u,\"decoder_error\":%u,\"observer_errors\":%u,"
      "\"timer_started\":%u,\"timer_ticks\":%llu,\"timer_events\":%llu,\"produced\":%llu,\"played\":%llu,\"underruns\":%llu,\"queued_at_stop\":%u,"
      "\"tick_interval_min_cycles\":%llu,\"tick_interval_max_cycles\":%llu,\"pwm_interval_min_cycles\":%llu,\"pwm_interval_max_cycles\":%llu,"
      "\"irq_cycles_total\":%llu,\"irq_cycles_max\":%llu,\"min_queue_before_producer_eof\":%u,"
      "\"minimum_stack_pointer_all\":%u,\"minimum_stack_pointer_playback\":%u,\"bss_end\":%u,\"stack_margin_all_bytes\":%d,\"stack_margin_playback_bytes\":%d,\"total_cycles\":%llu}\n",
      cpu->data[m[STOP_ADDR]],cpu->data[m[EOF_ADDR]],cpu->data[m[ERROR_ADDR]],observer_errors,
      started,(unsigned long long)ticks,(unsigned long long)pending_ticks,(unsigned long long)produced,(unsigned long long)played,(unsigned long long)underruns,queued,
      (unsigned long long)(ticks>1?min_tick:0),(unsigned long long)max_tick,(unsigned long long)(ticks>1?min_output:0),(unsigned long long)max_output,
      (unsigned long long)irq_total,(unsigned long long)irq_max,min_queue,
      minimum_sp,started?minimum_sp_play:0,m[BSS_END],(int)minimum_sp-(int)m[BSS_END],started?(int)minimum_sp_play-(int)m[BSS_END]:0,(unsigned long long)cpu->cycle);
    fclose(report);
    return cpu->data[m[STOP_ADDR]] && observer_errors==0 && minimum_sp>m[BSS_END]?0:7;
}
