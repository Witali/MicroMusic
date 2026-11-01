/*
 * ST M25P80 emulator. Emulate all SPI flash devices based on the m25p80 command
 * set. Known devices table current as of Jun/2012 and taken from linux.
 * See drivers/mtd/devices/m25p80.c.
 *
 * Copyright (C) 2011 Edgar E. Iglesias <edgar.iglesias@gmail.com>
 * Copyright (C) 2012 Peter A. G. Crosthwaite <peter.crosthwaite@petalogix.com>
 * Copyright (C) 2012 PetaLogix
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; either version 2 or
 * (at your option) a later version of the License.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program; if not, see <http://www.gnu.org/licenses/>.
 */

/* SPDX-License-Identifier: GPL-2.0-or-later
 * Project adaptation: read-only W25Q128 protocol subset extracted from QEMU
 * m25p80.c, pinned and preserved under third_party/qemu-m25p80/. This is not
 * the complete QEMU device. See README.md for exact supported behavior.
 */
#include "w25q128_readonly.h"

#include <string.h>

enum {
    STATE_IDLE, STATE_ADDRESS, STATE_DUMMY, STATE_READ,
    STATE_JEDEC, STATE_STATUS, STATE_STATUS2, STATE_CONFIG, STATE_UNSUPPORTED
};

static void reset_memory(LpxW25q128 *s)
{
    s->address = 0;
    s->state = STATE_IDLE;
    s->command = 0;
    s->address_left = 0;
    s->response_pos = 0;
    s->write_enable = false;
    s->reset_enable = false;
}

bool lpx_w25q128_init(LpxW25q128 *s, const uint8_t *image, size_t image_bytes)
{
    if (!s) {
        return false;
    }
    memset(s, 0, sizeof(*s));
    s->cs_high = true;
    if (!image || image_bytes != LPX_W25Q128_IMAGE_BYTES) {
        return false;
    }
    s->image = image;
    reset_memory(s);
    return true;
}

void lpx_w25q128_select(LpxW25q128 *s, bool cs_high)
{
    if (!s || !s->image || s->cs_high == cs_high) {
        return;
    }
    s->cs_high = cs_high;
    if (cs_high) {
        ++s->stats.cs_deassertions;
        s->state = STATE_IDLE;
        s->command = 0;
        s->address_left = 0;
        s->response_pos = 0;
    } else {
        ++s->stats.cs_assertions;
    }
}

void lpx_w25q128_reset(LpxW25q128 *s)
{
    if (!s || !s->image) {
        return;
    }
    reset_memory(s);
    ++s->stats.resets;
}

static void decode_new_command(LpxW25q128 *s, uint8_t tx)
{
    ++s->stats.command_bytes;
    s->command = tx;
    if (tx != 0x99) {
        s->reset_enable = false;
    }
    switch (tx) {
    case 0x03: /* READ: 24-bit address, no dummy clocks. */
    case 0x0b: /* FAST_READ with QEMU byte-dummy-cycles=true. */
        s->address = 0;
        s->address_left = 3;
        s->state = STATE_ADDRESS;
        break;
    case 0x9f:
        s->response_pos = 0;
        s->state = STATE_JEDEC;
        break;
    case 0x05:
        s->state = STATE_STATUS;
        break;
    case 0x35:
        s->state = STATE_STATUS2;
        break;
    case 0x15:
        s->state = STATE_CONFIG;
        break;
    case 0x06:
        s->write_enable = true;
        break;
    case 0x04:
        s->write_enable = false;
        break;
    case 0x66:
        s->reset_enable = true;
        break;
    case 0x99:
        if (s->reset_enable) {
            lpx_w25q128_reset(s);
        }
        break;
    default:
        ++s->stats.unsupported_commands;
        s->stats.last_unsupported_command = tx;
        s->state = STATE_UNSUPPORTED;
        break;
    }
}

uint8_t lpx_w25q128_transfer8(LpxW25q128 *s, uint8_t tx)
{
    static const uint8_t id[6] = {0xef, 0x40, 0x18, 0, 0, 0};
    if (!s) {
        return 0xff;
    }
    ++s->stats.transfer_calls;
    if (!s->image || s->cs_high) {
        return 0xff;
    }
    ++s->stats.selected_bytes;
    switch (s->state) {
    case STATE_IDLE:
        decode_new_command(s, tx);
        break;
    case STATE_ADDRESS:
        ++s->stats.address_bytes;
        s->address = ((s->address << 8) | tx) & (LPX_W25Q128_IMAGE_BYTES - 1);
        if (!--s->address_left) {
            s->state = s->command == 0x0b ? STATE_DUMMY : STATE_READ;
        }
        break;
    case STATE_DUMMY:
        ++s->stats.dummy_bytes;
        s->state = STATE_READ;
        break;
    case STATE_READ: {
        uint8_t value = s->image[s->address];
        s->address = (s->address + 1) & (LPX_W25Q128_IMAGE_BYTES - 1);
        ++s->stats.read_bytes;
        return value;
    }
    case STATE_JEDEC: {
        uint8_t value = id[s->response_pos++];
        if (s->response_pos == sizeof(id)) {
            s->state = STATE_IDLE;
        }
        return value;
    }
    case STATE_STATUS:
        return s->write_enable ? 2 : 0;
    case STATE_STATUS2:
        return 0;
    case STATE_CONFIG:
        s->state = STATE_IDLE;
        return 0;
    case STATE_UNSUPPORTED:
        return 0;
    }
    /* QEMU returns zero while accepting command/address/dummy bytes. */
    return 0;
}

LpxW25q128Stats lpx_w25q128_get_stats(const LpxW25q128 *s)
{
    LpxW25q128Stats result;
    memset(&result, 0, sizeof(result));
    if (s) {
        result = s->stats;
    }
    return result;
}
