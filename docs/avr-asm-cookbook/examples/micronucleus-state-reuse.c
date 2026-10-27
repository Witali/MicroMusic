/* SPDX-License-Identifier: GPL-2.0-or-later
 * Portable arithmetic reference for compact Micronucleus/V-USB state reuse.
 * Provenance: MicroNucleus commits 9b3918c05d09ed2977604267cf1b1c4e51476616
 * and 0cd03c728f63f7cabb701ea5e2503bf48ecd3027, ATtiny88 / AVR25.
 * The original loader contributors retain their GPL-2.0-or-later provenance.
 *
 * This standalone C reference performs no MMIO and selects no ASM backend.
 * It checks state/address/count arithmetic; actual instruction/IO tests live
 * with the cited source. It does not model watchdog, GPIO or USB timing.
 * Build: clang -std=c99 -Wall -Wextra -Werror micronucleus-state-reuse.c -o test
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#ifdef NDEBUG
#error Build this reference with assertions enabled
#endif

static uint8_t configuration_after(uint8_t previous, uint16_t value)
{
    assert(previous <= 1u);
    return value < 2u ? (uint8_t)value : previous;
}

static uint8_t configuration_reply_index(uint8_t configuration)
{
    assert(configuration <= 1u);
    return (uint8_t)(16u + configuration);
}

static uint16_t tagged_reply_pointer(uint16_t address, bool eeprom)
{
    assert(address < (eeprom ? 64u : 8192u));
    return (uint16_t)(address | (eeprom ? 0x8000u : 0u));
}

static void check_reply_state(void)
{
    const uint8_t descriptor_tail[] = {0, 0, 0, 1};  /* Bytes 14..17. */
    assert(descriptor_tail[0] == 0 && descriptor_tail[1] == 0);
    for (uint32_t value = 0; value <= UINT16_MAX; ++value) {
        for (uint8_t previous = 0; previous < 2u; ++previous) {
            uint8_t next = configuration_after(previous, (uint16_t)value);
            assert(next <= 1u);
            if (value >= 2u)
                assert(next == previous);
            else
                assert(next == value);
            assert(descriptor_tail[configuration_reply_index(next) - 14u] == next);
        }
        /* The shared cursor wraps as a complete 16-bit addition. */
        uint16_t cursor = (uint16_t)value;
        assert((uint16_t)(cursor + 8u) == (uint16_t)((value + 8u) & 0xffffu));
    }
    for (unsigned memory = 0; memory < 2u; ++memory) {
        bool eeprom = memory != 0;
        unsigned limit = eeprom ? 64u : 8192u;
        for (unsigned address = 0; address + 8u <= limit; address += 4u) {
            uint16_t pointer = tagged_reply_pointer((uint16_t)address, eeprom);
            assert(((pointer & 0x8000u) != 0) == eeprom);
            assert((pointer & 0x7fffu) == address);
            uint16_t after_packet = (uint16_t)(pointer + 8u);
            assert(((after_packet & 0x8000u) != 0) == eeprom);
            assert((after_packet & 0x7fffu) == address + 8u);
        }
    }
}

static void check_merged_clear_delay(void)
{
    uint8_t memory[0x300];
    memset(memory, 0xa5, sizeof(memory));
    uint16_t y = 0x12c;
    unsigned cleared = 0;
    uint32_t cycles = 2;  /* Initial SBI DDRD,D-; final CBI is not included. */
    do {
        uint16_t count = 27359;
        cycles += 2;  /* Two LDI instructions. */
        cycles += UINT32_C(4) * count - 1u;  /* SBIW 2; BRNE 2, final BRNE 1. */
        count = 0;
        assert(count == 0);
        memory[--y] = 0;
        ++cleared;
        cycles += 2u + 1u;  /* ST -Y then CPI YL. */
        cycles += (uint8_t)y != 0 ? 2u : 1u;
    } while ((uint8_t)y != 0);
    assert(cleared == 44u && y == 0x100u && cycles == 4815449u);
    for (unsigned address = 0; address < sizeof(memory); ++address)
        assert(memory[address] == (address >= 0x100u && address < 0x12cu ? 0 : 0xa5));
}

int main(void)
{
    check_reply_state();
    check_merged_clear_delay();
    puts("PASS portable configuration/tagged-pointer and merged clear/delay arithmetic");
    return 0;
}
