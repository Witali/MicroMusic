#include "nvm.h"
#include <string.h>

static attiny13a_nvm_t n;
static uint8_t flash[NVM_FLASH_BYTES], eeprom[NVM_EEPROM_BYTES];
#define CHECK(condition) do {if (!(condition)) return __LINE__;} while (0)
static void fresh(int spm) {
 nvm_timing_t timing=nvm_datasheet_timing(1);
 memset(flash,0xff,sizeof flash); memset(eeprom,0xff,sizeof eeprom);
 nvm_init(&n,flash,eeprom,&timing,0x6a,spm?0xef:0xff,0xff);
}
static unsigned write_at(uint8_t a, uint8_t v, uint64_t cyc, uint64_t ns) {
 return nvm_write_io(&n,a,v,255,cyc,ns);
}
static void arm(uint8_t cmd, uint64_t cyc, uint64_t ns) {
 write_at(NVM_SPMCSR,cmd,cyc,ns);
}
static unsigned ee_start(uint8_t mode, uint8_t address, uint8_t data,
 uint64_t cyc, uint64_t ns) {
 write_at(NVM_EEARL,address,cyc,ns); write_at(NVM_EEDR,data,cyc,ns);
 write_at(NVM_EECR,(uint8_t)(mode<<4)|NVM_EEMPE,cyc,ns);
 return nvm_write_io(&n,NVM_EECR,NVM_EEPE,NVM_EEPE,cyc+1,ns);
}

int nvm_test_eeprom_windows(void) {
 fresh(0);
 CHECK(nvm_owns_io(NVM_EECR) && nvm_owns_io(NVM_SPMCSR) && !nvm_owns_io(0));
 CHECK(write_at(NVM_EECR,NVM_EEPE,10,0)==0 && !n.eeprom_busy);
 CHECK(write_at(NVM_EECR,NVM_EEMPE|NVM_EEPE,10,0)==0 && !n.eeprom_busy);
 CHECK(nvm_next_event_cycle(&n)==14);
 CHECK(nvm_read_io(&n,NVM_EECR,13,0)&NVM_EEMPE);
 CHECK(nvm_write_io(&n,NVM_EECR,NVM_EEPE,NVM_EEPE,13,0)==2);
 CHECK(n.eeprom_busy && (n.eecr&NVM_EEPE));
 fresh(0);
 write_at(NVM_EECR,NVM_EEMPE,10,0);
 CHECK(nvm_write_io(&n,NVM_EECR,NVM_EEPE,NVM_EEPE,14,0)==0);
 CHECK(!n.eeprom_busy && !(n.eecr&NVM_EEMPE));
 CHECK(nvm_next_event_cycle(&n)==UINT64_MAX);
 write_at(NVM_EECR,NVM_EEMPE,20,0);
 write_at(NVM_EECR,0,21,0);
 CHECK(nvm_write_io(&n,NVM_EECR,NVM_EEPE,NVM_EEPE,22,0)==0);
 CHECK(n.faults==0);
 return 0;
}
int nvm_test_eeprom_atomic(void) {
 fresh(0); eeprom[63]=0x33;
 CHECK(write_at(NVM_EEARL,255,0,0)==0 && n.eearl==63);
 CHECK(ee_start(0,63,0xa5,0,1000)==2);
 CHECK(nvm_next_event_ns(&n)==3401000);
 CHECK(eeprom[63]==0x33);
 CHECK(write_at(NVM_EECR,0,2,1001)==0 && (n.eecr&NVM_EEPE));
 write_at(NVM_EEARL,0,2,1001); CHECK(n.eearl==63);
 write_at(NVM_EEDR,0x55,2,1001); CHECK(n.eedr==0x55);
 write_at(NVM_EECR,0x30|NVM_EERE,2,1001);
 CHECK((n.eecr&0x30)==0 && n.eedr==0x55);
 nvm_advance(&n,1000000,3400999);
 CHECK(n.eeprom_busy && eeprom[63]==0x33);
 nvm_advance(&n,1000000,3401000);
 CHECK(!n.eeprom_busy && !(n.eecr&NVM_EEPE) && eeprom[63]==0xa5);
 CHECK(write_at(NVM_EECR,NVM_EERE,1000000,3401000)==4 && n.eedr==0xa5);
 CHECK(!(n.eecr&NVM_EERE) && nvm_next_event_ns(&n)==UINT64_MAX && n.faults==0);
 return 0;
}
int nvm_test_eeprom_modes_irq_reset(void) {
 fresh(1); eeprom[7]=0;
 CHECK(ee_start(1,7,0x12,0,0)==2);
 CHECK(nvm_next_event_ns(&n)==1800000);
 nvm_write_io(&n,NVM_EECR,NVM_EERIE,NVM_EERIE,2,0);
 CHECK(!nvm_ready_irq(&n));
 nvm_reset(&n,3,100);
 CHECK(n.eeprom_busy && (n.eecr&0x30)==0x10 && !(n.eecr&NVM_EERIE));
 nvm_advance(&n,4,1800000); CHECK(eeprom[7]==0xff && !n.eeprom_busy);
 CHECK(ee_start(2,7,0x96,5,1800000)==2);
 nvm_write_io(&n,NVM_EECR,NVM_EERIE,NVM_EERIE,7,1800000);
 nvm_advance(&n,8,3600000);
 CHECK(eeprom[7]==0x96 && nvm_ready_irq(&n));
 /* Ready is a level: accepting its interrupt must not clear a hidden flag. */
 CHECK(nvm_ready_irq(&n));
 nvm_write_io(&n,NVM_EECR,0,NVM_EERIE,8,3600000);
 CHECK(!nvm_ready_irq(&n));
 CHECK(ee_start(3,7,0xff,9,3600000)==0 && (n.faults&NVM_FAULT_EEPROM_MODE));
 CHECK(ee_start(2,7,0xff,11,3600000)==0 && (n.faults&NVM_FAULT_EEPROM_NOT_ERASED));
 CHECK(eeprom[7]==0x96);
 nvm_reset(&n,13,3600000); CHECK(n.eecr==0);
 return 0;
}
int nvm_test_bit_strobes(void) {
 fresh(0); eeprom[0]=0x87;
 write_at(NVM_EEDR,0xff,0,0);
 write_at(NVM_EECR,NVM_EEMPE,0,0);
 CHECK(nvm_write_io(&n,NVM_EECR,NVM_EERIE,NVM_EERIE,1,0)==0);
 CHECK(n.eempe_until==4 && nvm_ready_irq(&n));
 CHECK(nvm_write_io(&n,NVM_EECR,NVM_EEPE,NVM_EEPE,2,0)==2);
 CHECK(!nvm_ready_irq(&n));
 CHECK(nvm_write_io(&n,NVM_EECR,0,NVM_EERIE,3,0)==0 && n.eeprom_busy);
 CHECK(!(n.eecr&NVM_EERIE));
 nvm_advance(&n,10,3400000);
 CHECK(nvm_write_io(&n,NVM_EECR,NVM_EERE,NVM_EERE,10,3400000)==4);
 CHECK(n.eedr==0xff && !n.eeprom_busy);
 CHECK(n.faults==0);
 return 0;
}
int nvm_test_flash_command_windows(void) {
 fresh(1);
 arm(1,10,0); CHECK(nvm_next_event_cycle(&n)==14);
 CHECK(nvm_spm(&n,1,0x3456,13,0)==NVM_SPM_BUFFER);
 CHECK(n.page_buffer[0]==0x56 && n.page_buffer[1]==0x34 && n.spmcsr==0);
 arm(1,20,0); CHECK(nvm_spm(&n,2,0x9876,24,0)==NVM_SPM_IGNORED);
 CHECK(n.page_buffer[2]==0xff && n.spmcsr==0);
 arm(1,30,0); CHECK(nvm_spm(&n,0,0xabcd,31,0)==NVM_SPM_UNDEFINED);
 CHECK(n.faults&NVM_FAULT_BUFFER_RELOAD);
 arm(17,40,0); CHECK(n.buffer_loaded==0 && n.page_buffer[0]==0xff);
 CHECK(nvm_spm(&n,0,0,41,0)==NVM_SPM_CLEAR);
 /* Every other control combination is explicitly ineffective. */
 for (unsigned cmd=0;cmd<32;cmd++) {
  fresh(1); arm((uint8_t)cmd,0,0);
  CHECK(n.spmcsr==((cmd==1||cmd==3||cmd==5||cmd==9||cmd==17)?cmd:0));
 }
 return 0;
}
int nvm_test_flash_erase_write(void) {
 fresh(1); flash[992]=0; flash[1023]=0;
 arm(1,0,0); CHECK(nvm_spm(&n,30,0x1234,1,0)==NVM_SPM_BUFFER);
 arm(1,2,0); CHECK(nvm_spm(&n,0,0xabcd,3,0)==NVM_SPM_BUFFER);
 arm(3,4,0); CHECK(nvm_spm(&n,1023,0,5,200)==NVM_SPM_ERASE);
 CHECK(nvm_cpu_halted(&n) && nvm_next_event_ns(&n)==4500200);
 CHECK(n.spmcsr==3 && n.flash_generation==0 && n.buffer_loaded==0x8001);
 arm(5,6,200); CHECK(n.spmcsr==3);
 nvm_advance(&n,100000000,4500199); CHECK(flash[992]==0 && n.flash_generation==0);
 nvm_advance(&n,100000000,4500200);
 CHECK(flash[992]==0xff && flash[1023]==0xff && !nvm_cpu_halted(&n));
 CHECK(n.flash_generation==1 && nvm_take_dirty_pages(&n)==0x80000000u);
 CHECK(nvm_take_dirty_pages(&n)==0 && n.buffer_loaded==0x8001);
 arm(5,100000000,4500200);
 CHECK(nvm_spm(&n,992,0,100000001,4500200)==NVM_SPM_WRITE);
 CHECK(nvm_cpu_halted(&n) && flash[992]==0xff);
 nvm_advance(&n,100000001,9000200);
 CHECK(flash[992]==0xcd && flash[993]==0xab && flash[1022]==0x34 && flash[1023]==0x12);
 CHECK(flash[0]==0xff && flash[991]==0xff && n.flash_generation==2);
 CHECK(n.flash_dirty_pages==0x80000000u && n.buffer_loaded==0 && n.spmcsr==0 && n.faults==0);
 return 0;
}
int nvm_test_flash_fuses_lpm(void) {
 uint8_t value=0;
 fresh(0); arm(1,0,0);
 CHECK(nvm_spm(&n,0,0x1234,1,0)==NVM_SPM_IGNORED && n.buffer_loaded==0);
 /* Unprogrammed SELFPRGEN disables SPM, not fuse-reading LPM. */
 arm(9,2,0); CHECK(nvm_lpm(&n,0,&value,4,0)==1 && value==0x6a && n.spmcsr==0);
 arm(9,5,0); CHECK(nvm_lpm(&n,3,&value,7,0)==1 && value==0xff);
 arm(9,8,0); CHECK(nvm_lpm(&n,1,&value,10,0)==1 && value==0xff);
 arm(9,11,0); CHECK(nvm_lpm(&n,0,&value,14,0)==0 && n.spmcsr==0);
 arm(9,15,0); CHECK(nvm_lpm(&n,2,&value,16,0)==-1 && value==0xff);
 CHECK(n.faults&NVM_FAULT_FUSE_ADDRESS);
 /* This chip's lock protection is for external programming interfaces. */
 fresh(1); n.lock=0xfc; arm(1,0,0);
 CHECK(nvm_spm(&n,0,0x1234,1,0)==NVM_SPM_BUFFER);
 arm(9,2,0); CHECK(nvm_lpm(&n,1,&value,3,0)==1 && value==0xfc);
 return 0;
}
int nvm_test_eeprom_flash_interlock(void) {
 uint8_t value=0;
 fresh(1); arm(1,0,0); CHECK(nvm_spm(&n,0,0x1234,1,0)==NVM_SPM_BUFFER);
 CHECK(ee_start(0,0,0xa5,2,0)==2);
 CHECK(n.buffer_loaded==0 && n.page_buffer[0]==0xff);
 arm(3,4,0); CHECK(n.spmcsr==0 && nvm_spm(&n,0,0,5,0)==NVM_SPM_IGNORED);
 arm(9,6,0); CHECK(nvm_lpm(&n,0,&value,7,0)==0);
 nvm_advance(&n,8,3400000);
 arm(3,9,3400000); CHECK(nvm_spm(&n,0,0,10,3400000)==NVM_SPM_ERASE);
 CHECK(ee_start(0,1,0x33,11,3400000)==0 && !n.eeprom_busy);
 nvm_advance(&n,13,7900000);
 CHECK(eeprom[0]==0xa5 && eeprom[1]==0xff && n.faults==0);
 return 0;
}
int nvm_test_flash_reset_faults(void) {
 fresh(1); arm(1,0,0); CHECK(nvm_spm(&n,0,0x1234,1,0)==NVM_SPM_BUFFER);
 arm(5,2,0); CHECK(nvm_spm(&n,0,0,3,0)==NVM_SPM_WRITE);
 nvm_reset(&n,4,10);
 CHECK(nvm_cpu_halted(&n) && n.buffer_loaded==0);
 nvm_advance(&n,4,4500000);
 CHECK(flash[0]==0x34 && flash[1]==0x12 && n.flash_generation==1);
 arm(5,5,4500000); CHECK(nvm_spm(&n,0,0,6,4500000)==NVM_SPM_UNDEFINED);
 CHECK(n.faults&NVM_FAULT_FLASH_NOT_ERASED);
 arm(5,7,4500000); CHECK(nvm_spm(&n,33,0,8,4500000)==NVM_SPM_UNDEFINED);
 CHECK(n.faults&NVM_FAULT_PAGE_ALIGNMENT);
 nvm_advance(&n,7,4500000); CHECK(n.faults&NVM_FAULT_TIME_REVERSED);
 CHECK(n.cycle==8 && n.now_ns==4500000);
 return 0;
}
int nvm_test_clock_domains_timing(void) {
 fresh(1);
 nvm_timing_t minimum=nvm_datasheet_timing(0), maximum=nvm_datasheet_timing(1);
 CHECK(minimum.flash_write_ns==3700000 && maximum.flash_erase_ns==4500000);
 CHECK(minimum.eeprom_atomic_ns==3400000 && maximum.eeprom_write_ns==1800000);
 CHECK(ee_start(0,0,0x12,0,0)==2);
 /* CPU clock can stop, while the calibrated RC programming clock runs. */
 nvm_advance(&n,1,3399999); CHECK(n.eeprom_busy);
 nvm_advance(&n,1,3400000); CHECK(!n.eeprom_busy && eeprom[0]==0x12);
 nvm_advance(&n,((uint64_t)1<<40),3400000);
 write_at(NVM_EECR,NVM_EEMPE,((uint64_t)1<<40),3400000);
 CHECK(nvm_next_event_cycle(&n)==((uint64_t)1<<40)+4);
 CHECK(nvm_write_io(&n,NVM_EECR,NVM_EEPE,NVM_EEPE,((uint64_t)1<<40)+3,3400000)==2);
 CHECK(nvm_next_event_ns(&n)==6800000);
 CHECK(n.faults==0);
 return 0;
}
