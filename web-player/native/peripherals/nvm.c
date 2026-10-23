#include "nvm.h"
#include <stddef.h>
#include <string.h>

static uint64_t earliest(uint64_t a, uint64_t b) { return a < b ? a : b; }
static uint64_t deadline(uint64_t at, uint64_t duration) {
 return duration > UINT64_MAX-at ? UINT64_MAX : at+duration;
}
static void clear_buffer(attiny13a_nvm_t *n) {
 memset(n->page_buffer, 0xff, sizeof n->page_buffer);
 n->buffer_loaded=0;
}
static void clear_command(attiny13a_nvm_t *n) {
 n->spmcsr=0; n->spm_until=0; n->rflb_until=0;
}
nvm_timing_t nvm_datasheet_timing(int use_flash_maximum) {
 uint64_t flash_ns=use_flash_maximum ? 4500000u : 3700000u;
 nvm_timing_t t={3400000u,1800000u,1800000u,flash_ns,flash_ns};
 return t;
}
int nvm_init(attiny13a_nvm_t *n, uint8_t *flash, uint8_t *eeprom,
 const nvm_timing_t *timing, uint8_t fl, uint8_t fh, uint8_t lock) {
 if (!n || !flash || !eeprom || !timing || !timing->eeprom_atomic_ns ||
     !timing->eeprom_erase_ns || !timing->eeprom_write_ns ||
     !timing->flash_erase_ns || !timing->flash_write_ns) return 0;
 memset(n,0,sizeof *n); n->flash=flash; n->eeprom=eeprom; n->timing=*timing;
 n->fuse_low=fl; n->fuse_high=fh|0xe0; n->lock=lock|0xfc;
 clear_buffer(n); return 1;
}
void nvm_advance(attiny13a_nvm_t *n, uint64_t cycle, uint64_t now_ns) {
 if (cycle<n->cycle || now_ns<n->now_ns) {
  n->faults|=NVM_FAULT_TIME_REVERSED; return;
 }
 n->cycle=cycle; n->now_ns=now_ns;
 if ((n->eecr&NVM_EEMPE) && cycle>=n->eempe_until)
  n->eecr&=(uint8_t)~NVM_EEMPE;
 if (!n->flash_busy && n->spmcsr &&
     cycle>=((n->spmcsr&NVM_RFLB)?n->rflb_until:n->spm_until)) clear_command(n);
 if (n->eeprom_busy && !(n->faults&NVM_FAULT_EEPROM_VOLTAGE_UNCERTAIN) && now_ns>=n->eeprom_until_ns) {
  if (n->eeprom_mode==1) n->eeprom[n->pending_address]=0xff;
  else n->eeprom[n->pending_address]=n->pending_data;
  n->eeprom_busy=0; n->eecr&=(uint8_t)~NVM_EEPE;
 }
 if (n->flash_busy && !(n->faults&NVM_FAULT_FLASH_VOLTAGE_UNCERTAIN) && now_ns>=n->flash_until_ns) {
  if (n->flash_busy==NVM_SPM_ERASE)
   memset(n->flash+n->pending_page,0xff,NVM_PAGE_BYTES);
  else {
   memcpy(n->flash+n->pending_page,n->pending_buffer,NVM_PAGE_BYTES);
   clear_buffer(n);
  }
  n->flash_dirty_pages|=(uint32_t)1<<(n->pending_page/32);
  n->flash_generation++; n->flash_busy=0; clear_command(n);
 }
}
void nvm_voltage_uncertain(attiny13a_nvm_t *n,uint32_t mask) {
 if(n->eeprom_busy) n->faults|=mask&NVM_FAULT_EEPROM_VOLTAGE_UNCERTAIN;
 if(n->flash_busy) n->faults|=mask&NVM_FAULT_FLASH_VOLTAGE_UNCERTAIN;
}
void nvm_reset(attiny13a_nvm_t *n, uint64_t cycle, uint64_t now_ns) {
 nvm_advance(n,cycle,now_ns);
 n->eecr=n->eeprom_busy ? (uint8_t)((n->eecr&0x30)|NVM_EEPE) : 0;
 n->eedr=0; n->eearl=n->eeprom_busy ? n->pending_address : 0;
 n->eempe_until=0; clear_buffer(n);
 if (!n->flash_busy) clear_command(n);
}
int nvm_owns_io(uint8_t address) {
 return address==NVM_EECR || address==NVM_EEDR || address==NVM_EEARL || address==NVM_SPMCSR;
}
uint8_t nvm_read_io(attiny13a_nvm_t *n, uint8_t a, uint64_t cyc, uint64_t ns) {
 nvm_advance(n,cyc,ns);
 switch (a) {
 case NVM_EECR:return n->eecr;
 case NVM_EEDR:return n->eedr;
 case NVM_EEARL:return n->eearl;
 case NVM_SPMCSR:return n->spmcsr;
 default:return 0;
 }
}
unsigned nvm_write_io(attiny13a_nvm_t *n, uint8_t a, uint8_t v,
 uint8_t mask, uint64_t cyc, uint64_t ns) {
 nvm_advance(n,cyc,ns);
 if(n->faults&(NVM_FAULT_EEPROM_VOLTAGE_UNCERTAIN|NVM_FAULT_FLASH_VOLTAGE_UNCERTAIN)) return 0;
 if (a==NVM_EEARL) {
  if (!n->eeprom_busy) n->eearl=((n->eearl&~mask)|(v&mask))&63;
  return 0;
 }
 if (a==NVM_EEDR) {n->eedr=(n->eedr&~mask)|(v&mask); return 0;}
 if (a==NVM_SPMCSR) {
  if (n->eeprom_busy || n->flash_busy) return 0;
  unsigned cmd=((n->spmcsr&~mask)|(v&mask))&31;
  if (cmd!=1 && cmd!=3 && cmd!=5 && cmd!=9 && cmd!=17) return 0;
  n->spmcsr=(uint8_t)cmd; n->spm_until=deadline(cyc,4); n->rflb_until=deadline(cyc,3);
  /* CTPB itself clears the temporary buffer (16.2, 16.9.1). */
  if (cmd&NVM_CTPB) clear_buffer(n);
  return 0;
 }
 if (a!=NVM_EECR) return 0;
 uint8_t old=n->eecr, merged=(old&~mask)|(v&mask), strobes=v&mask;
 n->eecr=(old&NVM_EEPE)|(merged&NVM_EERIE)|
  (n->eeprom_busy ? (old&0x30) : (merged&0x30));
 if (merged&NVM_EEMPE) {
  n->eecr|=NVM_EEMPE;
  if (strobes&NVM_EEMPE) n->eempe_until=deadline(cyc,4);
 }
 if (n->eeprom_busy || n->flash_busy) return 0;
 if ((strobes&NVM_EEPE) && (old&NVM_EEMPE)) {
  unsigned mode=(n->eecr>>4)&3;
  if (mode==3) {n->faults|=NVM_FAULT_EEPROM_MODE; return 0;}
  if (mode==2 && n->eeprom[n->eearl]!=0xff) {
   /* Datasheet calls the result lost: diagnose rather than fabricate data. */
   n->faults|=NVM_FAULT_EEPROM_NOT_ERASED; return 0;
  }
  n->eeprom_mode=(uint8_t)mode; n->pending_address=n->eearl; n->pending_data=n->eedr;
  n->eeprom_busy=1; n->eecr|=NVM_EEPE;
  n->eeprom_until_ns=deadline(ns,mode==0?n->timing.eeprom_atomic_ns:
   mode==1?n->timing.eeprom_erase_ns:n->timing.eeprom_write_ns);
  clear_buffer(n); clear_command(n);
  return 2;
 }
 if (strobes&NVM_EERE) {n->eedr=n->eeprom[n->eearl]; return 4;}
 return 0;
}
int nvm_spm(attiny13a_nvm_t *n, uint16_t z, uint16_t data,
 uint64_t cyc, uint64_t ns) {
 nvm_advance(n,cyc,ns);
 if(n->faults&(NVM_FAULT_EEPROM_VOLTAGE_UNCERTAIN|NVM_FAULT_FLASH_VOLTAGE_UNCERTAIN)) return NVM_SPM_UNDEFINED;
 if ((n->fuse_high&16) || n->eeprom_busy || n->flash_busy ||
     !(n->spmcsr&NVM_SELFPRGEN)) return NVM_SPM_IGNORED;
 unsigned cmd=n->spmcsr;
 if (cmd==17) {clear_buffer(n); clear_command(n); return NVM_SPM_CLEAR;}
 if (cmd==9) {clear_command(n); return NVM_SPM_IGNORED;}
 if (cmd==1) {
  unsigned offset=z&30, word=offset/2;
  clear_command(n);
  if (n->buffer_loaded & (1u<<word)) {
   n->faults|=NVM_FAULT_BUFFER_RELOAD; return NVM_SPM_UNDEFINED;
  }
  n->page_buffer[offset]=(uint8_t)data; n->page_buffer[offset+1]=(uint8_t)(data>>8);
  n->buffer_loaded|=(uint16_t)(1u<<word); return NVM_SPM_BUFFER;
 }
 unsigned page=z&0x3e0;
 if (cmd==5) {
  if (z&~0x3e0u) {
   n->faults|=NVM_FAULT_PAGE_ALIGNMENT; clear_command(n); return NVM_SPM_UNDEFINED;
  }
  for (unsigned i=0;i<NVM_PAGE_BYTES;i++) if (n->flash[page+i]!=0xff) {
   n->faults|=NVM_FAULT_FLASH_NOT_ERASED; clear_command(n); return NVM_SPM_UNDEFINED;
  }
  memcpy(n->pending_buffer,n->page_buffer,NVM_PAGE_BYTES);
 }
 n->pending_page=(uint16_t)page;
 n->flash_busy=cmd==3?NVM_SPM_ERASE:NVM_SPM_WRITE;
 n->flash_until_ns=deadline(ns,cmd==3?n->timing.flash_erase_ns:n->timing.flash_write_ns);
 return n->flash_busy;
}
int nvm_lpm(attiny13a_nvm_t *n, uint16_t z, uint8_t *value,
 uint64_t cyc, uint64_t ns) {
 nvm_advance(n,cyc,ns);
 /* Reading fuse/lock bytes is not an SPM instruction, so it does not require
  * the SELFPRGEN fuse. EEPROM programming does block this special LPM. */
 if (n->eeprom_busy || n->flash_busy || n->spmcsr!=9) return 0;
 clear_command(n);
 switch (z) {
 case 0:*value=n->fuse_low; return 1;
 case 1:*value=n->lock; return 1;
 case 3:*value=n->fuse_high; return 1;
 default:*value=0xff; n->faults|=NVM_FAULT_FUSE_ADDRESS; return -1;
 }
}
int nvm_ready_irq(const attiny13a_nvm_t *n) {
 return (n->eecr&NVM_EERIE) && !n->eeprom_busy && !n->flash_busy;
}
int nvm_cpu_halted(const attiny13a_nvm_t *n) {return !!n->flash_busy;}
uint64_t nvm_next_event_cycle(const attiny13a_nvm_t *n) {
 uint64_t at=(n->eecr&NVM_EEMPE)?n->eempe_until:UINT64_MAX;
 if (n->spmcsr && !n->flash_busy)
  at=earliest(at,(n->spmcsr&NVM_RFLB)?n->rflb_until:n->spm_until);
 return at;
}
uint64_t nvm_next_event_ns(const attiny13a_nvm_t *n) {
 return earliest(n->eeprom_busy&&!(n->faults&NVM_FAULT_EEPROM_VOLTAGE_UNCERTAIN)?n->eeprom_until_ns:UINT64_MAX,
  n->flash_busy&&!(n->faults&NVM_FAULT_FLASH_VOLTAGE_UNCERTAIN)?n->flash_until_ns:UINT64_MAX);
}
uint32_t nvm_take_dirty_pages(attiny13a_nvm_t *n) {
 uint32_t pages=n->flash_dirty_pages; n->flash_dirty_pages=0; return pages;
}
