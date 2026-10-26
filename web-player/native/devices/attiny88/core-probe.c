/* Hardware acquisition fixture for common AVR instruction effects/totals.
 * No ATtiny88 physical peripheral model is implemented by this firmware.
 * Original Microchip iotn88.h is selected first by the builder's include path. */
#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/wdt.h>
#include <avr/eeprom.h>
#include <avr/pgmspace.h>
#include <util/delay_basic.h>
#include <stdint.h>
#include "probe-cases.generated.h"
#if !defined(__AVR_ATtiny88__) || F_CPU != 16000000UL
#error "This acquisition fixture requires ATtiny88 / 16 MHz"
#endif
volatile uint8_t probe_packet[64];

/* A bootloader handoff need not reset peripherals. avr-libc .init3 convention,
 * also used by the project's retained Micronucleus music application. */
void probe_early(void) __attribute__((naked,used,section(".init3")));
void probe_early(void){
    cli();MCUSR=0;wdt_reset();wdt_disable();CLKPR=_BV(CLKPCE);CLKPR=0;
    PRR=0;EIMSK=0;PCICR=0;TIMSK0=0;TIMSK1=0;
    TCCR0A=0;TCCR1B=0;TCCR1A=0;GTCCR=0;ADCSRA=0;EECR=0;
}
/* Only the assembly test stimulus calls this non-C-ABI callee. */
__asm__(".text\n.global probe_callee\nprobe_callee:\ninc r16\nret\n");

static uint16_t checksum(void){
    uint16_t crc=0xffff;
    for(uint8_t n=0;n<64;n++){
        if(n==14||n==15)continue;
        crc^=(uint16_t)probe_packet[n]<<8;
        for(uint8_t b=0;b<8;b++)crc=(uint16_t)((crc<<1)^((crc&0x8000)?0x1021:0));
    }
    return crc;
}
static void delay100(void){for(uint8_t n=0;n<10;n++)_delay_loop_2(40000);}
int main(void){
    TCCR1B=0;TCCR1A=0;TCNT1=0;
    TIFR1=_BV(TOV1)|_BV(OCF1A)|_BV(OCF1B)|_BV(ICF1);
    TCCR1B=_BV(CS10);
    uint8_t control[4];probe_control(control);
    probe_run_cases((uint8_t *)probe_packet+16);
    TCCR1B=0;
    probe_packet[0]='A';probe_packet[1]='V';probe_packet[2]='R';probe_packet[3]='1';
    probe_packet[4]=1;probe_packet[5]=PROBE_CASE_COUNT;probe_packet[6]=0;probe_packet[7]=0;
    for(uint8_t n=0;n<4;n++)probe_packet[8+n]=pgm_read_byte(probe_build_id+n);
    probe_packet[12]=control[2];probe_packet[13]=control[3];
    const uint16_t overhead=(uint16_t)control[2]|((uint16_t)control[3]<<8);
    for(uint8_t n=0;n<PROBE_CASE_COUNT;n++){
        const uint8_t at=16+n*4;
        uint16_t delta=(uint16_t)probe_packet[at+2]|((uint16_t)probe_packet[at+3]<<8);
        if(probe_packet[at]==pgm_read_byte(&probe_expected[n][0])&&
           probe_packet[at+1]==pgm_read_byte(&probe_expected[n][1])&&
           (uint16_t)(delta-overhead)==pgm_read_byte(&probe_expected[n][2]))probe_packet[6]++;
    }
    const uint16_t crc=checksum();probe_packet[14]=(uint8_t)crc;probe_packet[15]=(uint8_t)(crc>>8);
    probe_packet[7]=0xa5;
    /* Software validation stops here: the music-oriented Tiny88 profile does
     * not model EEPROM programming. The SRAM record is already complete. */
    __asm__ __volatile__(".global probe_measured\nprobe_measured:\n":::"memory");
    eeprom_update_byte((uint8_t *)7,0); /* Invalidate a previous completed run. */
    eeprom_update_block((const void *)probe_packet,(void *)0,7);
    eeprom_update_block((const void *)(probe_packet+8),(void *)8,56);
    eeprom_update_byte((uint8_t *)7,0xa5);eeprom_busy_wait();
    __asm__ __volatile__(".global probe_complete\nprobe_complete:\n":::"memory");
    /* MH-ET LIVE's status LED is D0/PD0. USB D1/PD1 and D2/PD2 are untouched. */
    DDRD|=_BV(DDD0);
    for(;;){
        uint8_t count=probe_packet[6]==PROBE_CASE_COUNT?1:3;
        do{PORTD|=_BV(PORTD0);delay100();PORTD&=(uint8_t)~_BV(PORTD0);delay100();}while(--count);
        for(uint8_t n=0;n<8;n++)delay100();
    }
}
