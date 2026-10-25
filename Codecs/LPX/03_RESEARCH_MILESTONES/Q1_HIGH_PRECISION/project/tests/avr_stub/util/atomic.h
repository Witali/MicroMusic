#pragma once
#define ATOMIC_RESTORESTATE 1
// SYNTAX-ONLY STUB: does not disable interrupts. Never use for a real firmware build.
#define ATOMIC_BLOCK(how) for(uint8_t __atomic_done=1;__atomic_done;__atomic_done=0)
