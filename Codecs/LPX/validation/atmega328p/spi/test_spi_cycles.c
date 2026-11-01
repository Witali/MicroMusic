/* Isolated host test of all eight real SPR/SPI2X divisors and protocol timing.
 * No firmware shortcut is used by the player observer: this small test drives
 * the same registered SPDR handlers directly, then runs actual AVR NOP cycles.
 */
#include <assert.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "avr_spi.h"
#include "sim_avr.h"
#include "sim_io.h"
#include "w25q128_readonly.h"
#include "simavr_spi_clock.h"

static avr_t *cpu;
static avr_spi_t *spi;
static LpxW25q128 flash;
static uint64_t start_cycle,scheduled_cycles,completion_cycle;
static unsigned starts,completed,tx_count;

void lpx_simavr_spi_started(avr_t *avr,avr_spi_t *port,uint8_t tx,uint16_t cycles){
    (void)tx;
    assert(avr==cpu && port==spi && starts==completed);
    start_cycle=avr->cycle;scheduled_cycles=cycles;++starts;
}

static void completed_byte(struct avr_irq_t *irq,uint32_t value,void *param){
    (void)irq;(void)param;
    assert(starts==completed+1);
    completion_cycle=cpu->cycle;
    assert(completion_cycle-start_cycle==scheduled_cycles);
    ++completed;++tx_count;
    avr_raise_irq(spi->io.irq+SPI_IRQ_INPUT,lpx_w25q128_transfer8(&flash,(uint8_t)value));
}

static uint8_t transfer(uint8_t value,uint16_t expected){
    unsigned io=AVR_DATA_TO_IO(spi->r_spdr);
    assert(cpu->io[io].w.c && cpu->io[io].r.c);
    cpu->io[io].w.c(cpu,spi->r_spdr,value,cpu->io[io].w.param);
    if(scheduled_cycles!=expected || avr_regbit_get(cpu,spi->spi.raised))
        fprintf(stderr,"timing mismatch expected=%u scheduled=%" PRIu64 " starts=%u complete=%u flag=%u setting=%u\n",
            expected,scheduled_cycles,starts,completed,avr_regbit_get(cpu,spi->spi.raised),avr_regbit_get_array(cpu,spi->spr,3));
    assert(scheduled_cycles==expected && !avr_regbit_get(cpu,spi->spi.raised));
    while(cpu->cycle<start_cycle+expected){
        assert(completed<starts && !avr_regbit_get(cpu,spi->spi.raised));
        assert(avr_run(cpu)==cpu_Running);
    }
    /* Event dispatch is performed at the due instruction boundary. */
    if(completed<starts)assert(avr_run(cpu)==cpu_Running);
    assert(completed==starts && avr_regbit_get(cpu,spi->spi.raised));
    uint8_t result=cpu->io[io].r.c(cpu,spi->r_spdr,cpu->io[io].r.param);
    assert(!avr_regbit_get(cpu,spi->spi.raised));
    return result;
}

int main(void){
    uint8_t *image=malloc(LPX_W25Q128_IMAGE_BYTES);assert(image);
    memset(image,0xff,LPX_W25Q128_IMAGE_BYTES);
    image[UINT32_C(0x010203)]=0x5a;
    assert(lpx_w25q128_init(&flash,image,LPX_W25Q128_IMAGE_BYTES));
    cpu=avr_make_mcu_by_name("atmega328p");assert(cpu && avr_init(cpu)==0);
    cpu->frequency=16000000;
    memset(cpu->flash,0,(size_t)cpu->flashend+1); /* actual one-cycle NOPs */
    for(avr_io_t *io=cpu->io_port;io;io=io->next)
        if(io->kind && !strcmp(io->kind,"spi"))spi=(avr_spi_t *)io;
    assert(spi);
    assert(lpx_simavr_spi_clock_install(cpu,spi)==1);
    avr_irq_register_notify(spi->io.irq+SPI_IRQ_OUTPUT,completed_byte,NULL);
    avr_regbit_set(cpu,spi->spe);avr_regbit_set(cpu,spi->mstr);
    const uint16_t cycles[8]={32,128,512,1024,16,64,256,512};
    for(unsigned setting=0;setting<8;setting++){
        for(unsigned bit=0;bit<3;bit++)
            avr_regbit_setto(cpu,spi->spr[bit],(uint8_t)((setting>>bit)&1));
        lpx_w25q128_select(&flash,false);
        assert(transfer(0x0b,cycles[setting])==0);
        assert(transfer(0x01,cycles[setting])==0);
        assert(transfer(0x02,cycles[setting])==0);
        assert(transfer(0x03,cycles[setting])==0);
        assert(transfer(0xa5,cycles[setting])==0); /* one complete dummy byte */
        assert(transfer(0xff,cycles[setting])==0x5a);
        lpx_w25q128_select(&flash,true);
        printf("{\"setting\":%u,\"byte_cycles\":%u,\"passed\":true}\n",setting,cycles[setting]);
    }
    LpxW25q128Stats stats=lpx_w25q128_get_stats(&flash);
    assert(tx_count==48 && starts==completed && stats.read_bytes==8 && stats.dummy_bytes==8
           && stats.address_bytes==24 && stats.unsupported_commands==0);
    printf("{\"status\":\"PASS\",\"divisors\":8,\"actual_completed_bytes\":%u,\"fast_byte_cycles\":16}\n",tx_count);
    avr_terminate(cpu);free(image);return 0;
}
