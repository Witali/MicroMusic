/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef LPX_W25Q128_READONLY_H
#define LPX_W25Q128_READONLY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LPX_W25Q128_IMAGE_BYTES UINT32_C(16777216)

typedef struct LpxW25q128Stats {
    uint64_t transfer_calls;
    uint64_t selected_bytes;
    uint64_t command_bytes;
    uint64_t address_bytes;
    uint64_t dummy_bytes;
    uint64_t read_bytes;
    uint64_t cs_assertions;
    uint64_t cs_deassertions;
    uint64_t unsupported_commands;
    uint64_t resets;
    uint8_t last_unsupported_command;
} LpxW25q128Stats;

/* Caller-owned storage; fields are private implementation state, not a read API. */
typedef struct LpxW25q128 {
    const uint8_t *image;
    uint32_t address;
    uint8_t state;
    uint8_t command;
    uint8_t address_left;
    uint8_t response_pos;
    bool cs_high;
    bool write_enable;
    bool reset_enable;
    LpxW25q128Stats stats;
} LpxW25q128;

/* Image must contain exactly 16 MiB and outlive the device; never modified here.
 * Failure leaves a supplied device safely unbound. Initial CS is high.
 */
bool lpx_w25q128_init(LpxW25q128 *device, const uint8_t *image, size_t image_bytes);

/* Electrical CS pin: false selects, true deselects. Repeated levels are inert. */
void lpx_w25q128_select(LpxW25q128 *device, bool cs_high);

/* One completed 8-clock single-wire SPI byte. Deselected/unbound returns 0xff.
 * This function has no cycle/time shortcut; the bridge owns clock timing.
 */
uint8_t lpx_w25q128_transfer8(LpxW25q128 *device, uint8_t tx);

/* Reset protocol/latches, preserving the external CS level, image and counters. */
void lpx_w25q128_reset(LpxW25q128 *device);
LpxW25q128Stats lpx_w25q128_get_stats(const LpxW25q128 *device);

#ifdef __cplusplus
}
#endif
#endif
