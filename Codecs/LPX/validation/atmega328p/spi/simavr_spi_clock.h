/* Host-only explicit installation for the pinned simavr1.6 SPI module patch. */
#ifndef LPX_SIMAVR_SPI_CLOCK_H
#define LPX_SIMAVR_SPI_CLOCK_H
#include "avr_spi.h"
/* Returns 1 once for a matching existing module, otherwise 0. */
int lpx_simavr_spi_clock_install(avr_t *avr,avr_spi_t *port);
/* Supplied by the observer or test; called at each SPDR write before scheduling. */
void lpx_simavr_spi_started(avr_t *avr,avr_spi_t *port,uint8_t tx,uint16_t cycles);
#endif
