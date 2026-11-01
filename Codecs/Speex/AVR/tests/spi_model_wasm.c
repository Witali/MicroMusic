/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only bridge to the shared QEMU-derived read-only SPI model.
 * This module is never linked into the Speex library or AVR firmware. */
#include "w25q128_readonly.h"

static uint8_t image[LPX_W25Q128_IMAGE_BYTES];
static LpxW25q128 device;

/* Freestanding WASM build: the model only needs this libc operation. */
void *memset(void *destination, int value, size_t bytes)
{
    uint8_t *out = (uint8_t *)destination;
    while (bytes--) *out++ = (uint8_t)value;
    return destination;
}

uint8_t *speex_spi_image(void) { return image; }
int speex_spi_init(void) { return lpx_w25q128_init(&device, image, sizeof(image)); }
void speex_spi_select(int high) { lpx_w25q128_select(&device, high != 0); }
uint32_t speex_spi_transfer(uint32_t value) { return lpx_w25q128_transfer8(&device, (uint8_t)value); }
uint64_t speex_spi_stat(uint32_t index)
{
    LpxW25q128Stats stats = lpx_w25q128_get_stats(&device);
    switch (index) {
    case 0: return stats.transfer_calls;
    case 1: return stats.selected_bytes;
    case 2: return stats.command_bytes;
    case 3: return stats.address_bytes;
    case 4: return stats.dummy_bytes;
    case 5: return stats.read_bytes;
    case 6: return stats.cs_assertions;
    case 7: return stats.cs_deassertions;
    case 8: return stats.unsupported_commands;
    case 9: return stats.resets;
    default: return UINT64_MAX;
    }
}
