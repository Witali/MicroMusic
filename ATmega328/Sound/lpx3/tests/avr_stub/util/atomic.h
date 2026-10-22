#pragma once
// Syntax checking ONLY. Does not implement actual IRQ masking.
#define ATOMIC_RESTORESTATE 0
#define ATOMIC_BLOCK(value) for (uint8_t _atomic_once=1;_atomic_once;_atomic_once=0)
