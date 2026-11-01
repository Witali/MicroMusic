/* Codec-independent blocking read-only SPI NOR reader for ATmega328P.
 * Register and pin definitions come exclusively from the AVR vendor header.
 * Mode 0, MSB first, F_CPU/2; 0x0b + 24-bit address + one dummy byte.
 */
#ifndef AVR_SPI_FLASH_READER_H
#define AVR_SPI_FLASH_READER_H
#include <stdint.h>
#include <stdbool.h>
#include <avr/io.h>
#if !defined(__AVR_ATmega328P__)
#error This pin mapping supports ATmega328P only
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct AvrSpiFlashReader {
    uint32_t remaining;
} AvrSpiFlashReader;

static inline uint8_t avr_spi_flash_transfer(uint8_t value) {
    SPDR=value;
    while (!(SPSR&_BV(SPIF))) {}
    return SPDR;
}

static inline void avr_spi_flash_close(AvrSpiFlashReader *reader) {
    PORTB|=_BV(PORTB2);
    reader->remaining=0;
}

static inline void avr_spi_flash_init(AvrSpiFlashReader *reader) {
    /* Set CS high before enabling its output driver. PB2 also remains SS out. */
    PORTB|=_BV(PORTB2);
    PORTB&=(uint8_t)~(_BV(PORTB3)|_BV(PORTB5));
    DDRB=(uint8_t)((DDRB|_BV(DDB2)|_BV(DDB3)|_BV(DDB5))&~_BV(DDB4));
    SPCR=_BV(SPE)|_BV(MSTR);
    SPSR=_BV(SPI2X);
    reader->remaining=0;
}

static inline bool avr_spi_flash_begin(AvrSpiFlashReader *reader,
                                        uint32_t address,uint32_t bytes) {
    avr_spi_flash_close(reader);
    if (!bytes || address>=UINT32_C(16777216) || bytes>UINT32_C(16777216)-address)
        return false;
    PORTB&=(uint8_t)~_BV(PORTB2);
    avr_spi_flash_transfer(0x0b);
    avr_spi_flash_transfer((uint8_t)(address>>16));
    avr_spi_flash_transfer((uint8_t)(address>>8));
    avr_spi_flash_transfer((uint8_t)address);
    avr_spi_flash_transfer(0xff); /* Exactly one dummy byte, value ignored. */
    reader->remaining=bytes;
    return true;
}

/* Callback-compatible bounds failure is -1. A wire returning 0xff is data;
 * this read-only protocol provides no CRC or automatic disconnected-bus test.
 * The consumer may finish before remaining reaches zero; close/next begin
 * discards that unread tail without transferring it.
 */
static inline int16_t avr_spi_flash_read(void *context) {
    AvrSpiFlashReader *reader=(AvrSpiFlashReader *)context;
    if (!reader->remaining) return -1;
    --reader->remaining;
    return avr_spi_flash_transfer(0xff);
}

#ifdef __cplusplus
}
#endif
#endif
