/* Observe the actual linked production producer without AVR instrumentation.
 * Reuse the complete playback/metadata observer; only host stepping is wrapped.
 * Function entry/SP/RET and actual head publication define useful calls.
 * Foreground intervals include RET (4 AVR5 cycles), exclude caller CALL and
 * subtract complete RUNNING notification IRQ intervals plus measured RETI
 * steps (simavr1.6 lowers RUNNING before charging RETI). Endpoints are outside
 * IRQ context, so no partly overlapping IRQ is subtracted as a whole call.
 */
#define _POSIX_C_SOURCE 200809L
#include "sim_avr.h"
static int producer_step(avr_t *target);
#define avr_run producer_step
#define main playback_main
#include "sim_player.c"
#undef main
#undef avr_run

typedef struct {
    uint64_t count,total,maximum,ring[320],sum160,sum320,max160,max320;
    unsigned cursor;
} ProducerDurations;
static ProducerDurations work,wall;
static uint32_t producer_entry,producer_size,entry_sp,return_pc,entry_head_value;
static uint64_t begin_cycle,begin_irq_total,calls,preload_calls,playback_calls;
static uint64_t irq_return_cycles,begin_irq_return_cycles;
static uint64_t notification_cycles_in_calls,return_cycles_in_calls;
static uint64_t unpublished_calls,failed_calls,boundary_errors;
static uint64_t terminal_published_calls,terminal_unpublished_calls,first_producer_cycle;
static unsigned active,verify_return,entry_started,entry_eof;
static FILE *cycle_trace;

static int push_duration(ProducerDurations *state,uint64_t value){
    if(state->count==UINT64_MAX || value>UINT64_MAX-state->total)return 0;
    state->total+=value;if(value>state->maximum)state->maximum=value;
    state->sum160+=value;state->sum320+=value;
    if(state->count>=160)state->sum160-=state->ring[(state->cursor+160)%320];
    if(state->count>=320)state->sum320-=state->ring[state->cursor];
    if(state->count+1>=160 && state->sum160>state->max160)state->max160=state->sum160;
    if(state->count+1>=320 && state->sum320>state->max320)state->max320=state->sum320;
    state->ring[state->cursor]=value;state->cursor=(state->cursor+1)%320;++state->count;return 1;
}
static uint32_t stack_pointer(avr_t *target){
    return target->data[m[SPL_ADDR]]|((uint32_t)target->data[m[SPH_ADDR]]<<8);
}
static uint32_t stacked_return(avr_t *target,uint32_t sp){
    /* AVR5 pushes low PC byte first while SP descends; stored PC is words. */
    return (((uint32_t)target->data[sp+1]<<8)|target->data[sp+2])*2;
}
static int producer_step(avr_t *target){
    const uint32_t sp=stack_pointer(target),pc=target->pc;
    const uint64_t before_cycle=target->cycle;
    const unsigned reti=in_irq && pc+1<=target->flashend && target->flash[pc]==0x18 && target->flash[pc+1]==0x95;
    if(verify_return && !in_irq){
        if(pc!=return_pc || sp!=entry_sp+2)++boundary_errors;
        verify_return=0;
    }
    if(!active && !in_irq && pc==producer_entry){
        if(sp<m[BSS_END] || sp+2>target->ramend)++boundary_errors;
        else{
            active=1;entry_sp=sp;return_pc=stacked_return(target,sp);
            if(return_pc>=target->flashend || (return_pc&1))++boundary_errors;
            entry_head_value=index_at(HEAD_ADDR);begin_cycle=target->cycle;
            begin_irq_total=irq_total;begin_irq_return_cycles=irq_return_cycles;
            entry_started=started;entry_eof=target->data[m[EOF_ADDR]];
            if(!calls)first_producer_cycle=begin_cycle;
            ++calls;
        }
    }
    if(active && !in_irq && pc+1<=target->flashend &&
       target->flash[pc]==0x08 && target->flash[pc+1]==0x95 && sp==entry_sp){
        if(stacked_return(target,sp)!=return_pc)++boundary_errors;
        const uint32_t delta=(index_at(HEAD_ADDR)-entry_head_value)&(m[QUEUE_SIZE]-1);
        const uint64_t elapsed=target->cycle+4-begin_cycle;
        const uint64_t notifications=irq_total-begin_irq_total,returns=irq_return_cycles-begin_irq_return_cycles;
        const uint64_t interrupts=notifications+returns;
        if(interrupts>elapsed || delta>1)++boundary_errors;
        else if(delta==1){
            if(!push_duration(&wall,elapsed) || !push_duration(&work,elapsed-interrupts))++boundary_errors;
            if(cycle_trace && fprintf(cycle_trace,"%llu,%llu,%llu,%u\n",(unsigned long long)work.count,
                    (unsigned long long)elapsed,(unsigned long long)interrupts,entry_started)<0)++boundary_errors;
            if(entry_started)++playback_calls;else ++preload_calls;
            notification_cycles_in_calls+=notifications;return_cycles_in_calls+=returns;
            if(!entry_eof && target->data[m[EOF_ADDR]])++terminal_published_calls;
        }else if(target->data[m[ERROR_ADDR]])++failed_calls;
        else{++unpublished_calls;if(target->data[m[EOF_ADDR]])++terminal_unpublished_calls;}
        active=0;verify_return=1;
    }
    const int result=avr_run(target);
    if(reti){
        if(in_irq)++boundary_errors;
        irq_return_cycles+=target->cycle-before_cycle;
    }
    return result;
}
static int locate_producer(const char *path){
    if(elf_version(EV_CURRENT)==EV_NONE)return 0;
    int fd=open(path,O_RDONLY);if(fd<0)return 0;
    Elf *elf=elf_begin(fd,ELF_C_READ,NULL);if(!elf){close(fd);return 0;}
    unsigned found=0;Elf_Scn *section=NULL;
    while((section=elf_nextscn(elf,section))){
        GElf_Shdr header;if(!gelf_getshdr(section,&header)){found=2;break;}
        if(header.sh_type!=SHT_SYMTAB)continue;
        Elf_Data *data=elf_getdata(section,NULL);
        if(!data || !header.sh_entsize || header.sh_size/header.sh_entsize>INT_MAX){found=2;break;}
        for(size_t i=0;i<header.sh_size/header.sh_entsize;i++){
            GElf_Sym sym;if(!gelf_getsym(data,(int)i,&sym)){found=2;break;}
            const char *name=elf_strptr(elf,header.sh_link,sym.st_name);
            if(name && !strncmp(name,"_ZL7produce",11) && GELF_ST_TYPE(sym.st_info)==STT_FUNC){
                ++found;producer_entry=sym.st_value;producer_size=sym.st_size;
            }
        }
    }
    elf_end(elf);close(fd);
    return found==1 && producer_size>=2 && producer_entry+producer_size<=32768;
}
int main(int argc,char **argv){
    if(argc!=5 || !locate_producer(argv[1]))return 2;
    const size_t trace_length=strlen(argv[3])+sizeof(".producer-cycles.csv");
    char *trace_path=malloc(trace_length);if(!trace_path)return 6;
    snprintf(trace_path,trace_length,"%s.producer-cycles.csv",argv[3]);
    int trace_descriptor=open(trace_path,O_WRONLY|O_CREAT|O_EXCL,0600);free(trace_path);if(trace_descriptor<0)return 6;
    cycle_trace=fdopen(trace_descriptor,"w");if(!cycle_trace){close(trace_descriptor);return 6;}
    int result=playback_main(argc,argv);
    if(fclose(cycle_trace))++boundary_errors;
    cycle_trace=NULL;
    if(active || verify_return || work.count!=produced || work.count!=played || failed_calls)++boundary_errors;
    const size_t length=strlen(argv[3])+sizeof(".producer.json");
    char *path=malloc(length);if(!path)return 6;
    snprintf(path,length,"%s.producer.json",argv[3]);
    int descriptor=open(path,O_WRONLY|O_CREAT|O_EXCL,0600);free(path);if(descriptor<0)return 6;
    FILE *report=fdopen(descriptor,"w");if(!report){close(descriptor);return 6;}
    fprintf(report,"{\"schema\":\"lpx-production-producer-v2\",\"passed\":%s,"
      "\"producer_entry\":%u,\"producer_size\":%u,\"calls\":%llu,\"published_calls\":%llu,"
      "\"preload_calls\":%llu,\"playback_calls\":%llu,\"unpublished_calls\":%llu,\"failed_calls\":%llu,\"boundary_errors\":%llu,"
      "\"terminal_published_calls\":%llu,\"terminal_unpublished_calls\":%llu,\"cycles_before_first_producer_entry\":%llu,"
      "\"irq_notification_cycles_inside_calls\":%llu,\"irq_return_cycles_inside_calls\":%llu,"
      "\"producer_work_cycles_total\":%llu,\"producer_work_cycles_max\":%llu,\"producer_work_cycles_max160\":%llu,\"producer_work_cycles_max320\":%llu,"
      "\"producer_wall_cycles_total\":%llu,\"producer_wall_cycles_max160\":%llu,\"producer_wall_cycles_max320\":%llu,"
      "\"scope\":\"Actual production producer body plus RET4, caller CALL excluded; complete live IRQ notification intervals plus measured RETI steps subtracted; endpoints outside IRQ; queue/EOF publication included; polling/failure calls excluded\"}\n",
      result==0 && !boundary_errors?"true":"false",producer_entry,producer_size,
      (unsigned long long)calls,(unsigned long long)work.count,(unsigned long long)preload_calls,(unsigned long long)playback_calls,
      (unsigned long long)unpublished_calls,(unsigned long long)failed_calls,(unsigned long long)boundary_errors,
      (unsigned long long)terminal_published_calls,(unsigned long long)terminal_unpublished_calls,(unsigned long long)first_producer_cycle,
      (unsigned long long)notification_cycles_in_calls,(unsigned long long)return_cycles_in_calls,
      (unsigned long long)work.total,(unsigned long long)work.maximum,(unsigned long long)work.max160,(unsigned long long)work.max320,
      (unsigned long long)wall.total,(unsigned long long)wall.max160,(unsigned long long)wall.max320);
    fclose(report);return result || boundary_errors?7:0;
}
