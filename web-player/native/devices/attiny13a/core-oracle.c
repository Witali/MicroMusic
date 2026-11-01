/* Typed DWARF2 mailbox for the project-local Studio control fixture.
 * Firmware execution and initialization are entirely in core-oracle.S. */
#include <stdint.h>
#include <stddef.h>
#include <avr/io.h>
typedef struct {
    uint8_t magic[4], build[4], control[4], cases[ORACLE_CASE_COUNT][4];
} oracle_record_t;
volatile oracle_record_t oracle_record;
_Static_assert(offsetof(oracle_record_t, cases) == 12, "mailbox layout");
_Static_assert(sizeof(oracle_record_t) <= RAMEND - RAMSTART + 1 - 4,
               "reserve four stack bytes; interrupts must stay disabled");
