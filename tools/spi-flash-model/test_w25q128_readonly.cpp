// SPDX-License-Identifier: GPL-2.0-or-later
#include "w25q128_readonly.h"

#include <cstdio>
#include <cstdlib>
#include <vector>

#define CHECK(value) do { if (!(value)) { \
    std::fprintf(stderr, "SPI contract failed at line %d: %s\n", __LINE__, #value); \
    std::exit(1); } } while (0)

static uint8_t transfer(LpxW25q128 &device, uint8_t tx = 0xff)
{
    return lpx_w25q128_transfer8(&device, tx);
}

static void command(LpxW25q128 &device, uint8_t opcode)
{
    lpx_w25q128_select(&device, false);
    CHECK(transfer(device, opcode) == 0);
    lpx_w25q128_select(&device, true);
}

static uint8_t status(LpxW25q128 &device)
{
    lpx_w25q128_select(&device, false);
    CHECK(transfer(device, 0x05) == 0);
    uint8_t value = transfer(device);
    CHECK(transfer(device) == value);
    lpx_w25q128_select(&device, true);
    return value;
}

static void read_header(LpxW25q128 &device, uint8_t opcode, uint32_t address)
{
    lpx_w25q128_select(&device, false);
    CHECK(transfer(device, opcode) == 0);
    CHECK(transfer(device, static_cast<uint8_t>(address >> 16)) == 0);
    CHECK(transfer(device, static_cast<uint8_t>(address >> 8)) == 0);
    CHECK(transfer(device, static_cast<uint8_t>(address)) == 0);
}

int main()
{
    std::vector<uint8_t> image(LPX_W25Q128_IMAGE_BYTES);
    for (uint32_t i = 0; i < image.size(); ++i) {
        image[i] = static_cast<uint8_t>(i * 17u + (i >> 8) * 31u + (i >> 16) * 47u + 19u);
    }
    LpxW25q128 device;
    unsigned contracts = 0;

    // Initialization rejects short/oversized/null images and remains safe.
    CHECK(!lpx_w25q128_init(nullptr, image.data(), image.size()));
    for (size_t n : {size_t(0), image.size() - 1, image.size() + 1}) {
        CHECK(!lpx_w25q128_init(&device, image.data(), n));
        lpx_w25q128_select(&device, false);
        CHECK(transfer(device, 0x03) == 0xff);
    }
    CHECK(!lpx_w25q128_init(&device, nullptr, image.size()));
    CHECK(lpx_w25q128_transfer8(nullptr, 0) == 0xff);
    CHECK(lpx_w25q128_get_stats(nullptr).transfer_calls == 0);
    ++contracts;

    // Deselected bytes cannot enter a command or consume image data.
    CHECK(lpx_w25q128_init(&device, image.data(), image.size()));
    CHECK(transfer(device, 0x9f) == 0xff);
    CHECK(lpx_w25q128_get_stats(&device).selected_bytes == 0);
    CHECK(lpx_w25q128_get_stats(&device).command_bytes == 0);
    ++contracts;

    // Ordinary READ starts only after all three address bytes.
    CHECK(lpx_w25q128_init(&device, image.data(), image.size()));
    read_header(device, 0x03, 0x123456);
    CHECK(lpx_w25q128_get_stats(&device).read_bytes == 0);
    for (uint32_t i = 0; i < 257; ++i) CHECK(transfer(device) == image[0x123456 + i]);
    lpx_w25q128_select(&device, true);
    LpxW25q128Stats stats = lpx_w25q128_get_stats(&device);
    CHECK(stats.command_bytes == 1 && stats.address_bytes == 3 && stats.dummy_bytes == 0);
    CHECK(stats.read_bytes == 257 && stats.selected_bytes == 261);
    ++contracts;

    // FAST_READ requires exactly one dummy byte (eight clocks), not zero/eight bytes.
    CHECK(lpx_w25q128_init(&device, image.data(), image.size()));
    read_header(device, 0x0b, 0x876543);
    CHECK(image[0x876543] != 0);
    CHECK(transfer(device, 0x99) == 0); // Dummy cannot act as reset or data.
    stats = lpx_w25q128_get_stats(&device);
    CHECK(stats.dummy_bytes == 1 && stats.read_bytes == 0 && stats.resets == 0);
    CHECK(transfer(device, 0x03) == image[0x876543]);
    CHECK(transfer(device, 0x9f) == image[0x876544]); // MOSI opcodes remain read clocks.
    CHECK(lpx_w25q128_get_stats(&device).selected_bytes == 7);
    lpx_w25q128_select(&device, true);
    ++contracts;

    // Sequential reads wrap at 24 bits, including the last physical byte.
    CHECK(lpx_w25q128_init(&device, image.data(), image.size()));
    read_header(device, 0x03, 0xffffe0);
    for (uint32_t i = 0; i < 96; ++i) CHECK(transfer(device) == image[(0xffffe0 + i) & 0xffffff]);
    lpx_w25q128_select(&device, true);
    ++contracts;

    // CS rising aborts partial addresses; the next transaction starts at opcode.
    CHECK(lpx_w25q128_init(&device, image.data(), image.size()));
    lpx_w25q128_select(&device, false);
    CHECK(transfer(device, 0x0b) == 0);
    CHECK(transfer(device, 0x12) == 0);
    lpx_w25q128_select(&device, true);
    read_header(device, 0x03, 0x010203);
    CHECK(transfer(device) == image[0x010203]);
    lpx_w25q128_select(&device, true);
    ++contracts;

    // CS also discards an outstanding dummy phase, while repeated levels are inert.
    CHECK(lpx_w25q128_init(&device, image.data(), image.size()));
    read_header(device, 0x0b, 0x010203);
    lpx_w25q128_select(&device, true);
    lpx_w25q128_select(&device, true);
    read_header(device, 0x03, 7);
    lpx_w25q128_select(&device, false);
    CHECK(transfer(device) == image[7]);
    CHECK(transfer(device) == image[8]);
    lpx_w25q128_select(&device, true);
    stats = lpx_w25q128_get_stats(&device);
    CHECK(stats.cs_assertions == 2 && stats.cs_deassertions == 2 && stats.dummy_bytes == 0);
    ++contracts;

    // QEMU exposes six JEDEC bytes then returns to command decoding under CS low.
    CHECK(lpx_w25q128_init(&device, image.data(), image.size()));
    lpx_w25q128_select(&device, false);
    CHECK(transfer(device, 0x9f) == 0);
    for (uint8_t value : {0xef, 0x40, 0x18, 0, 0, 0}) CHECK(transfer(device) == value);
    CHECK(transfer(device, 0x06) == 0);
    lpx_w25q128_select(&device, true);
    CHECK(status(device) == 2);
    command(device, 0x04);
    CHECK(status(device) == 0);
    ++contracts;

    // Read-only status never becomes busy; SR2 loops, 0x15 is one config byte.
    CHECK(lpx_w25q128_init(&device, image.data(), image.size()));
    lpx_w25q128_select(&device, false);
    CHECK(transfer(device, 0x35) == 0);
    for (unsigned i = 0; i < 20; ++i) CHECK(transfer(device) == 0);
    lpx_w25q128_select(&device, true);
    lpx_w25q128_select(&device, false);
    CHECK(transfer(device, 0x15) == 0 && transfer(device) == 0);
    CHECK(transfer(device, 0x06) == 0);
    lpx_w25q128_select(&device, true);
    CHECK(status(device) == 2);
    ++contracts;

    // RESET without enable is inert; a command between 66/99 cancels enable.
    command(device, 0x99);
    CHECK(status(device) == 2);
    command(device, 0x66);
    CHECK(status(device) == 2);
    command(device, 0x99);
    CHECK(status(device) == 2);
    CHECK(lpx_w25q128_get_stats(&device).resets == 0);
    command(device, 0x66);
    command(device, 0x99);
    CHECK(status(device) == 0 && lpx_w25q128_get_stats(&device).resets == 1);
    ++contracts;

    // Explicit device reset keeps the physical CS line and counters/image.
    command(device, 0x06);
    read_header(device, 0x03, 0x123456);
    CHECK(transfer(device) == image[0x123456]);
    uint64_t read_before_reset = lpx_w25q128_get_stats(&device).read_bytes;
    lpx_w25q128_reset(&device);
    CHECK(transfer(device, 0x9f) == 0 && transfer(device) == 0xef);
    lpx_w25q128_select(&device, true);
    CHECK(status(device) == 0);
    CHECK(lpx_w25q128_get_stats(&device).read_bytes == read_before_reset);
    ++contracts;

    // Unsupported program/erase/status writes consume a transaction, never data.
    CHECK(lpx_w25q128_init(&device, image.data(), image.size()));
    const std::vector<uint8_t> before = image;
    for (uint8_t opcode : {0x02, 0x20, 0xc7, 0x01}) {
        command(device, 0x06);
        lpx_w25q128_select(&device, false);
        CHECK(transfer(device, opcode) == 0);
        for (unsigned i = 0; i < 512; ++i) CHECK(transfer(device, static_cast<uint8_t>(i)) == 0);
        lpx_w25q128_select(&device, true);
    }
    CHECK(image == before);
    stats = lpx_w25q128_get_stats(&device);
    CHECK(stats.unsupported_commands == 4 && stats.last_unsupported_command == 0x01);
    CHECK(stats.read_bytes == 0);
    read_header(device, 0x03, 0);
    CHECK(transfer(device) == image[0]);
    lpx_w25q128_select(&device, true);
    ++contracts;

    // Large payload crosses pages and 64 KiB while every byte uses the SPI machine.
    CHECK(lpx_w25q128_init(&device, image.data(), image.size()));
    read_header(device, 0x0b, 0x00ff80);
    CHECK(transfer(device) == 0);
    for (uint32_t i = 0; i < 131073; ++i) CHECK(transfer(device) == image[0x00ff80 + i]);
    lpx_w25q128_select(&device, true);
    stats = lpx_w25q128_get_stats(&device);
    CHECK(stats.read_bytes == 131073 && stats.selected_bytes == 131078);
    CHECK(stats.command_bytes == 1 && stats.address_bytes == 3 && stats.dummy_bytes == 1);
    CHECK(stats.unsupported_commands == 0);
    ++contracts;

    std::printf("PASS: %u SPI flash protocol contracts\n", contracts);
}
