#ifndef MICROMUSIC_ATTINY13A_NVM_H
#define MICROMUSIC_ATTINY13A_NVM_H

#include <stdint.h>

/* Microchip DS40002307A, chapters 5, 16 and 17. Addresses are AVR I/O
 * addresses; add 0x20 for LD/ST data-space addresses. No host callbacks. */
enum {
 NVM_EECR=0x1c, NVM_EEDR=0x1d, NVM_EEARL=0x1e, NVM_SPMCSR=0x37,
 NVM_EERE=1, NVM_EEPE=2, NVM_EEMPE=4, NVM_EERIE=8,
 NVM_SELFPRGEN=1, NVM_PGERS=2, NVM_PGWRT=4, NVM_RFLB=8, NVM_CTPB=16,
 NVM_FLASH_BYTES=1024, NVM_EEPROM_BYTES=64, NVM_PAGE_BYTES=32
};

/* Programming uses the calibrated RC oscillator, not the CPU prescaler.
 * Supply explicit elapsed-time parameters. Table 5-1 gives EEPROM nominal
 * times, not bounds; Table 16-1 gives 3.7..4.5 ms per Flash operation. */
typedef struct {
 uint64_t eeprom_atomic_ns, eeprom_erase_ns, eeprom_write_ns;
 uint64_t flash_erase_ns, flash_write_ns;
} nvm_timing_t;

/* Choose one documented Flash bound explicitly; no universal SPM duration. */
nvm_timing_t nvm_datasheet_timing(int use_flash_maximum);

enum {
 NVM_FAULT_EEPROM_MODE=1u,
 NVM_FAULT_EEPROM_NOT_ERASED=2u,
 NVM_FAULT_BUFFER_RELOAD=4u,
 NVM_FAULT_FLASH_NOT_ERASED=8u,
 NVM_FAULT_PAGE_ALIGNMENT=16u,
 NVM_FAULT_FUSE_ADDRESS=32u,
 NVM_FAULT_TIME_REVERSED=64u
};
enum {
 NVM_SPM_IGNORED=0, NVM_SPM_BUFFER=1, NVM_SPM_ERASE=2,
 NVM_SPM_WRITE=3, NVM_SPM_CLEAR=4, NVM_SPM_UNDEFINED=-1
};

typedef struct {
 uint8_t *flash, *eeprom;
 nvm_timing_t timing;
 uint64_t cycle, now_ns, eempe_until, spm_until, rflb_until;
 uint64_t eeprom_until_ns, flash_until_ns, flash_generation;
 uint32_t flash_dirty_pages, faults;
 uint16_t buffer_loaded;
 uint16_t pending_page;
 uint8_t eecr, eedr, eearl, spmcsr;
 uint8_t eeprom_busy, eeprom_mode, pending_address, pending_data;
 uint8_t flash_busy, fuse_low, fuse_high, lock;
 uint8_t page_buffer[NVM_PAGE_BYTES], pending_buffer[NVM_PAGE_BYTES];
} attiny13a_nvm_t;

/* Bind caller-owned arrays without erasing them. Returns 0 for invalid timing
 * or pointers. Default chip fuses are FLB=0x6a, FHB=0xff, lock=0xff; a high
 * fuse with bit 4 cleared explicitly enables SPM. Lock bits constrain external
 * programmers, not firmware SPM/LPM, on this chip (Table 17-2). */
int nvm_init(attiny13a_nvm_t *n, uint8_t flash[NVM_FLASH_BYTES],
 uint8_t eeprom[NVM_EEPROM_BYTES], const nvm_timing_t *timing,
 uint8_t fuse_low, uint8_t fuse_high, uint8_t lock);

/* CPU cycles and elapsed ns must be monotonically nondecreasing. Timed
 * windows are half-open: write at t arms [t,t+4), fuse LPM [t,t+3).
 * Use the actual I/O write/instruction-effect edge consistently. Advance may
 * cross any number of cycles in O(1), including while the CPU sleeps. */
void nvm_advance(attiny13a_nvm_t *n, uint64_t cycle, uint64_t now_ns);
/* Reset register controls and temporary buffer; preserve arrays, generation,
 * dirty pages and any active programming operation at adequate VCC. */
void nvm_reset(attiny13a_nvm_t *n, uint64_t cycle, uint64_t now_ns);
int nvm_owns_io(uint8_t address);
uint8_t nvm_read_io(attiny13a_nvm_t *n, uint8_t address,
 uint64_t cycle, uint64_t now_ns);
/* mask=0xff for OUT/ST; mask=1<<bit for SBI/CBI with value holding the desired
 * bit. This avoids retriggering unrelated read/write strobes. Returns extra
 * CPU stall cycles: 4 for accepted EERE, 2 for accepted EEPE, otherwise 0.
 * Peripheral time must advance during those stalls. */
unsigned nvm_write_io(attiny13a_nvm_t *n, uint8_t address, uint8_t value,
 uint8_t mask, uint64_t cycle, uint64_t now_ns);
int nvm_spm(attiny13a_nvm_t *n, uint16_t z, uint16_t r1r0,
 uint64_t cycle, uint64_t now_ns);
/* Returns 1 and sets value for fuse/lock LPM, 0 for ordinary Flash LPM, or -1
 * for an unsupported fuse address (value=0xff; fault latched). The caller
 * still applies the documented LPM instruction cycles/register side effects. */
int nvm_lpm(attiny13a_nvm_t *n, uint16_t z, uint8_t *value,
 uint64_t cycle, uint64_t now_ns);

int nvm_ready_irq(const attiny13a_nvm_t *n);
int nvm_cpu_halted(const attiny13a_nvm_t *n);
/* UINT64_MAX means none. Cycle events expire protection windows; ns events
 * finish asynchronous programming, including when CPU/I/O clocks stop. */
uint64_t nvm_next_event_cycle(const attiny13a_nvm_t *n);
uint64_t nvm_next_event_ns(const attiny13a_nvm_t *n);
/* Returns and clears dirty page bits; generation remains monotonic. Every
 * completed erase/write increments generation even when bytes match.
 * A translated CPU MUST exit its block after starting SPM, remain halted
 * until completion, and invalidate/retranslate dirty Flash before resuming.
 * Clearing dirty bits alone never makes stale generated code safe. */
uint32_t nvm_take_dirty_pages(attiny13a_nvm_t *n);

#endif
