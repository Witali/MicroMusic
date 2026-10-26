#include "attiny88-wave-reader.h"

/* A deterministic fixture shared by the selectable C and ASM implementations.
 * The validation script executes both real AVR images and checks all bytes. */
static const uint8_t bank[64] PROGMEM = {
    0, 19, 38, 57, 76, 95, 114, 133, 152, 171, 190, 209, 228, 247, 10, 29,
    48, 67, 86, 105, 124, 143, 162, 181, 200, 219, 238, 1, 20, 39, 58, 77,
    96, 115, 134, 153, 172, 191, 210, 229, 248, 11, 30, 49, 68, 87, 106, 125,
    144, 163, 182, 201, 220, 239, 2, 21, 40, 59, 78, 97, 116, 135, 154, 173
};
volatile uint8_t observed[64];
volatile uint8_t complete;

__attribute__((noinline,used)) uint8_t read_sample(uint8_t index)
{
    return micromusic_wave_byte(bank, index);
}
