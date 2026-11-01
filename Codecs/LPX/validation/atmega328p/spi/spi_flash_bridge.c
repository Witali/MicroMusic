/* GPL-3.0-or-later host harness against pinned simavr1.6 and read-only QEMU
 * protocol adapter. No encoded audio or firmware backend is part of this file.
 */
#include <inttypes.h>
#include <limits.h>
#include <string.h>
#include "sim_io.h"
#include "simavr_spi_clock.h"
#include "spi_flash_bridge.h"

static LpxSpiBridge *active;

static unsigned mask(avr_regbit_t bit){return (unsigned)bit.mask<<bit.bit;}
static void minimum(uint64_t *value,uint64_t sample){if(sample<*value)*value=sample;}
static void maximum(uint64_t *value,uint64_t sample){if(sample>*value)*value=sample;}

void lpx_simavr_spi_started(avr_t *cpu,avr_spi_t *port,uint8_t tx,uint16_t cycles){
    LpxSpiBridge *b=active;
    if(!b || b->cpu!=cpu || b->spi!=port)return;
    if(b->busy){++b->errors;return;}
    const LpxSpiHardware *h=&b->hw;
    const unsigned outputs=(1u<<h->cs_bit)|(1u<<h->mosi_bit)|(1u<<h->sck_bit);
    const unsigned control=h->spe|h->mstr;
    if((cpu->data[h->spcr]&(control|h->cpol|h->cpha|h->dord|h->spr0|h->spr1))!=control ||
       !(cpu->data[h->spsr]&h->spi2x) || (cpu->data[h->ddr]&outputs)!=outputs ||
       (cpu->data[h->ddr]&(1u<<h->miso_bit)) || (cpu->data[h->port]&(1u<<h->cs_bit)) ||
       !avr_regbit_get(cpu,port->spe) || !avr_regbit_get(cpu,port->mstr) || cycles!=16)
        ++b->errors;
    if(b->completed){
        uint64_t gap=cpu->cycle-b->last_completion;
        minimum(&b->min_gap,gap);maximum(&b->max_gap,gap);b->total_gaps+=gap;
    }
    b->busy=1;b->start_cycle=cpu->cycle;b->scheduled=cycles;b->tx=tx;
    ++b->started;b->clock_cycles+=cycles;
    if(cpu->sreg[S_I])++b->starts_with_interrupts_enabled;
}

static void byte_completed(struct avr_irq_t *irq,uint32_t value,void *context){
    (void)irq;
    LpxSpiBridge *b=context;
    if(!b->busy || b->tx!=(uint8_t)value){++b->errors;return;}
    uint64_t delay=b->cpu->cycle-b->start_cycle;
    /* Pinned v1.6 raw run services timers after the instruction, before IRQs.
     * _avr_push_addr/service add no cycles; AVR5 RET/RETI are four cycles.
     * The player rejects sleep, so four cycles conservatively bound dispatch
     * quantization. Scheduled hardware duration remains exactly sixteen.
     */
    if(delay<b->scheduled || delay>b->scheduled+4u)++b->errors;
    uint64_t lateness=delay>=b->scheduled?delay-b->scheduled:0;
    minimum(&b->min_delay,delay);maximum(&b->max_delay,delay);
    minimum(&b->min_lateness,lateness);maximum(&b->max_lateness,lateness);
    b->last_completion=b->cpu->cycle;b->busy=0;++b->completed;
    if(b->audio_irq_running && *b->audio_irq_running)++b->completions_during_audio_irq;
    uint8_t response=lpx_w25q128_transfer8(&b->flash,(uint8_t)value);
    avr_raise_irq(b->spi->io.irq+SPI_IRQ_INPUT,response);
}

static void cs_changed(struct avr_irq_t *irq,uint32_t value,void *context){
    (void)irq;
    LpxSpiBridge *b=context;
    bool high=(value&1)!=0;
    if(b->busy && high!=b->flash.cs_high)++b->errors;
    lpx_w25q128_select(&b->flash,high);
}

int lpx_spi_bridge_attach(LpxSpiBridge *b,avr_t *cpu,const uint8_t *image,size_t bytes,
                         const LpxSpiHardware *h,const unsigned *audio_irq_running){
    if(active || !b || !cpu || !h || h->cs_bit>7 || h->mosi_bit>7 || h->miso_bit>7 || h->sck_bit>7)
        return 0;
    memset(b,0,sizeof(*b));b->cpu=cpu;b->hw=*h;b->audio_irq_running=audio_irq_running;
    b->min_delay=b->min_lateness=b->min_gap=UINT64_MAX;
    if(!lpx_w25q128_init(&b->flash,image,bytes))return 0;
    avr_ioport_t *gpio=NULL;
    for(avr_io_t *io=cpu->io_port;io;io=io->next){
        if(io->kind && !strcmp(io->kind,"spi")){
            avr_spi_t *candidate=(avr_spi_t *)io;
            if(candidate->r_spdr==h->spdr)b->spi=candidate;
        }
        if(io->kind && !strcmp(io->kind,"port")){
            avr_ioport_t *candidate=(avr_ioport_t *)io;
            if(candidate->r_port==h->port && candidate->r_ddr==h->ddr)gpio=candidate;
        }
    }
    avr_spi_t *p=b->spi;
    if(!p || !gpio || p->r_spcr!=h->spcr || p->r_spsr!=h->spsr ||
       p->spe.reg!=h->spcr || mask(p->spe)!=h->spe || p->mstr.reg!=h->spcr || mask(p->mstr)!=h->mstr ||
       p->spr[0].reg!=h->spcr || mask(p->spr[0])!=h->spr0 || p->spr[1].reg!=h->spcr || mask(p->spr[1])!=h->spr1 ||
       p->spr[2].reg!=h->spsr || mask(p->spr[2])!=h->spi2x || !lpx_simavr_spi_clock_install(cpu,p))return 0;
    avr_irq_t *cs=avr_io_getirq(cpu,AVR_IOCTL_IOPORT_GETIRQ(gpio->name),(int)h->cs_bit);
    if(!cs)return 0;
    active=b;
    avr_irq_register_notify(cs,cs_changed,b);
    avr_irq_register_notify(p->io.irq+SPI_IRQ_OUTPUT,byte_completed,b);
    /* External CS pull-up keeps an unconfigured reset input deselected. */
    avr_ioport_external_t pull={.name=(unsigned)gpio->name,.mask=1u<<h->cs_bit,.value=1u<<h->cs_bit};
    if(avr_ioctl(cpu,AVR_IOCTL_IOPORT_SET_EXTERNAL(gpio->name),&pull)!=0)return 0;
    avr_raise_irq(cs,1);
    return 1;
}

int lpx_spi_bridge_valid(const LpxSpiBridge *b){
    LpxW25q128Stats stats=lpx_w25q128_get_stats(&b->flash);
    return b->errors==0 && !b->busy && b->started==b->completed && b->started>0 &&
        stats.transfer_calls==b->completed && stats.selected_bytes==b->completed &&
        stats.unsupported_commands==0 && b->flash.cs_high && b->clock_cycles==16*b->completed;
}

void lpx_spi_bridge_report(const LpxSpiBridge *b,FILE *file){
    LpxW25q128Stats s=lpx_w25q128_get_stats(&b->flash);
    fprintf(file,"{\"cpu_hz\":16000000,\"configured_sck_hz\":8000000,\"scheduled_byte_cycles\":16,"
        "\"bytes_started\":%" PRIu64 ",\"bytes_completed\":%" PRIu64 ",\"clock_cycles_total\":%" PRIu64 ","
        "\"completion_delay_min_cycles\":%" PRIu64 ",\"completion_delay_max_cycles\":%" PRIu64 ","
        "\"dispatch_lateness_min_cycles\":%" PRIu64 ",\"dispatch_lateness_max_cycles\":%" PRIu64 ","
        "\"software_gap_min_cycles\":%" PRIu64 ",\"software_gap_max_cycles\":%" PRIu64 ",\"software_gap_total_cycles\":%" PRIu64 ","
        "\"starts_with_interrupts_enabled\":%" PRIu64 ",\"completions_during_audio_irq\":%" PRIu64 ","
        "\"command_bytes\":%" PRIu64 ",\"address_bytes\":%" PRIu64 ",\"dummy_bytes\":%" PRIu64 ",\"payload_bytes\":%" PRIu64 ","
        "\"cs_assertions\":%" PRIu64 ",\"cs_deassertions\":%" PRIu64 ",\"unsupported_commands\":%" PRIu64 ","
        "\"cs_high_at_stop\":%s,\"bridge_errors\":%u}",
        b->started,b->completed,b->clock_cycles,b->completed?b->min_delay:0,b->max_delay,
        b->completed?b->min_lateness:0,b->max_lateness,b->completed>1?b->min_gap:0,b->max_gap,b->total_gaps,
        b->starts_with_interrupts_enabled,b->completions_during_audio_irq,s.command_bytes,s.address_bytes,s.dummy_bytes,s.read_bytes,
        s.cs_assertions,s.cs_deassertions,s.unsupported_commands,b->flash.cs_high?"true":"false",b->errors);
}
