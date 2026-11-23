#pragma once
#include <stdint.h>
#include <stddef.h>

// Browser resource limits, independent of the uint32 V9 Long wire fields.
static constexpr uint32_t kLpxMaxSamples = 32000000;
static constexpr uint32_t kLpxMaxFileBytes = 100 * 1024 * 1024;

#if defined(__wasm__) && !defined(LPX_ADAPTIVE_ENCODER)
extern "C" unsigned char __heap_base;
static void* reserveWorkspace(uint32_t bytes) {
    const uintptr_t base = (reinterpret_cast<uintptr_t>(&__heap_base) + 7) & ~uintptr_t(7);
    const uint32_t pages = static_cast<uint32_t>((base + bytes + 65535) / 65536);
    const size_t current = __builtin_wasm_memory_size(0);
    if (pages > current && __builtin_wasm_memory_grow(0, pages - current) == size_t(-1)) return nullptr;
    return reinterpret_cast<void*>(base);
}
#else
#include <stdlib.h>
static void* reserveWorkspace(uint32_t bytes) {
    static void* workspace = nullptr;
    static uint32_t capacity = 0;
    if (bytes > capacity) {
        void* grown = realloc(workspace, bytes);
        if (!grown) return nullptr;
        workspace = grown; capacity = bytes;
    }
    return workspace;
}
#endif
