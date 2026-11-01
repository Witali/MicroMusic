/* Host-only byte/peripheral bridge. The AVR clocked module owns transfer time. */
#ifndef LPX_SPI_FLASH_BRIDGE_H
#define LPX_SPI_FLASH_BRIDGE_H
#include <stdint.h>
#include <stdio.h>
#include "avr_spi.h"
#include "avr_ioport.h"
#include "w25q128_readonly.h"

typedef struct LpxSpiHardware {
    uint32_t spdr,spcr,spsr,ddr,port,cs_bit,mosi_bit,miso_bit,sck_bit;
    uint32_t spe,mstr,cpol,cpha,dord,spi2x,spr0,spr1;
} LpxSpiHardware;

typedef struct LpxSpiBridge {
    avr_t *cpu;
    avr_spi_t *spi;
    LpxW25q128 flash;
    LpxSpiHardware hw;
    const unsigned *audio_irq_running;
    uint64_t started,completed,start_cycle,last_completion,clock_cycles;
    uint64_t min_delay,max_delay,min_lateness,max_lateness,min_gap,max_gap,total_gaps;
    uint64_t starts_with_interrupts_enabled,completions_during_audio_irq;
    uint16_t scheduled;
    uint8_t tx,busy;
    unsigned errors;
} LpxSpiBridge;

int lpx_spi_bridge_attach(LpxSpiBridge *bridge,avr_t *cpu,const uint8_t *image,size_t bytes,
                         const LpxSpiHardware *hardware,const unsigned *audio_irq_running);
int lpx_spi_bridge_valid(const LpxSpiBridge *bridge);
void lpx_spi_bridge_report(const LpxSpiBridge *bridge,FILE *report);
#endif
