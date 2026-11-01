/* Isolated arithmetic primitive, not a C decoder execution/performance test. */
#include "lowrate_rng.h"
volatile uint32_t rng_input, rng_result;
volatile uint8_t rng_command, rng_status;
SPEEX_NB3_STAGE uint32_t rng_test_asm(uint32_t value)
{ return speex_low_rng_next(value); }
SPEEX_NB3_STAGE uint32_t rng_test_c(uint32_t value)
{ return speex_low_rng_next_c(value); }
int main(void)
{
    rng_status = 1;
    for (;;) {
        if (rng_command == 1 || rng_command == 2) {
            uint32_t value = rng_input;
            rng_result = rng_command == 1 ? rng_test_asm(value) : rng_test_c(value);
            rng_command = 0;
            rng_status = 2;
        }
    }
}
