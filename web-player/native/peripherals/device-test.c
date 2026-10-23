#include "device.h"
#include <string.h>

#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)
static uint8_t data[160], flash[1024], eeprom[64];
static int fresh(void) {
 static const uint32_t defaults[]={0,1000000,128000,5000000,1100000,0x7a,0xff,0xff,27,0,0,0,0,0,1};
 for (unsigned i=1;i<15;i++) if (!device_configure(i,defaults[i])) return 0;
 memset(data,0,sizeof data); memset(flash,255,sizeof flash); memset(eeprom,255,sizeof eeprom);
 return device_init(data,flash,eeprom);
}
static int bus(void) {
 CHECK(fresh());
 CHECK(device_base_half()==0 && device_virtual_half()==0 && device_clkpr_divisor()==1);
 CHECK(device_oscillator_hz()==1000000 && device_read(0x34)==1);
 CHECK(!device_read(0x2a));
 device_write(0x3f,0x95,255); device_write(0x3d,0x9f,255);
 CHECK(device_read(0x3f)==0x95 && data[0x5d]==0x9f);
 device_write(0x18,0x0a,255); device_write(0x16,1,1);
 CHECK(device_read(0x18)==0x0b);
 device_write(0x16,0,2); CHECK(device_read(0x18)==0x0b);
 device_write(0x16,2,2); CHECK(device_read(0x18)==9);
 device_write(0x17,255,255); CHECK(device_read(0x17)==63);
 CHECK(!device_fault());
 return 0;
}
static int pwm_pins(void) {
 CHECK(fresh());
 device_write(0x17,1,255); device_write(0x36,2,255);
 device_write(0x2f,0x40,255); device_write(0x33,1,255);
 device_clear_pin_events();
 CHECK(device_next_cpu_event()==1); /* OCR0B's default zero still sets its flag. */
 device_advance(2); CHECK(device_read(0x32)==2 && !(device_read(0x38)&4));
 device_advance(1); CHECK(device_read(0x32)==3 && (device_read(0x38)&4));
 uint32_t count=0; const device_pin_event_t *events=device_pin_events(&count);
 CHECK(count==1 && events[0].base_half==6 && (events[0].levels&1) && (events[0].driven&1));
 device_consume_pin_events(count); CHECK(!device_pin_events(&count) && !count);
 device_write(0x38,4,4); CHECK(!(device_read(0x38)&4));
 CHECK(!device_fault());
 return 0;
}
static int external_t0(void) {
 CHECK(fresh());
 device_write(0x33,7,255);
 CHECK(device_inject_digital(1,4,4));
 device_advance(3); CHECK(device_read(0x32)==0);
 device_advance(1); CHECK(device_base_half()==8 && device_read(0x32)==1);
 CHECK(device_inject_digital(9,4,0));
 device_advance(4); CHECK(device_read(0x32)==1); /* Falling edge ignored. */
 device_write(0x33,6,255);
 CHECK(device_inject_digital(17,4,4)); CHECK(device_inject_digital(25,4,0));
 device_advance(8); CHECK(device_read(0x32)==2);
 CHECK(!device_fault());
 return 0;
}
static int interrupts(void) {
 CHECK(fresh());
 device_write(0x36,1,255); device_write(0x29,2,255);
 device_write(0x39,14,255); device_write(0x33,1,255);
 device_advance(3);
 CHECK(device_pending_irqs()==((1u<<6)|(1u<<7)) && device_next_irq()==6);
 device_ack_irq(6); CHECK(device_next_irq()==7 && (device_read(0x38)&8));
 device_write(0x1c,8,255); CHECK(device_next_irq()==4);
 device_ack_irq(4); CHECK(device_next_irq()==4); /* EEPROM-ready is a level. */
 device_write(0x3b,0x40,255); CHECK(device_next_irq()==1); /* INT0 low level. */
 device_ack_irq(1); CHECK(device_next_irq()==1);
 device_write(0x3b,0,255); device_write(0x1c,0,255); device_ack_irq(7);
 device_advance(253); CHECK(device_next_irq()==3);
 device_ack_irq(3); CHECK(!(device_pending_irqs()&(1u<<3)));
 CHECK(!device_fault());
 return 0;
}
static int adc(void) {
 CHECK(fresh());
 CHECK(device_inject_analog(0,5,1000000));
 device_write(0x06,0xc8,255);
 device_advance(51); CHECK(!(device_read(0x06)&16));
 device_advance(1); CHECK(device_read(0x06)&16);
 CHECK(device_pending_irqs()&(1u<<9));
 CHECK(device_read(4)==204 && device_read(5)==0);
 CHECK(data[32+4]==204 && !device_fault());
 /* Directed ADCSRA-specific RMW policy: its old ADIF participates in SBI. */
 device_write(6,1,1); CHECK(!(device_read(6)&16));
 device_write(6,0xc8,255); device_advance(28);
 CHECK(device_read(6)&16); device_ack_irq(9); CHECK(!(device_read(6)&16));
 CHECK(!device_fault());
 return 0;
}
static int adc_trigger(void) {
 CHECK(fresh());
 device_write(3,3,255); /* ADTS=Timer compare A, without TIMSK enable. */
 device_write(6,0xa8,255); device_write(0x36,1,255); device_write(0x33,1,255);
 device_advance(1); CHECK(!(device_read(6)&64));
 device_advance(1); CHECK(device_read(6)&64);
 device_advance(54); CHECK(device_read(6)&16);
 CHECK(device_next_irq()==9);
 CHECK(fresh());
 device_write(3,1,255); device_write(6,0xa8,255);
 CHECK(device_inject_analog(1,0,3000000));
 device_advance(3); CHECK(device_read(8)&16); CHECK(device_read(6)&64);
 CHECK(fresh());
 device_write(3,6,255); device_write(6,0xa8,255);
 device_write(0x15,1,255); CHECK(device_inject_digital(1,1,1));
 device_advance(4); CHECK(device_read(0x3a)&32); CHECK(device_read(6)&64);
 CHECK(fresh());
 device_write(3,2,255); device_write(6,0xa8,255);
 CHECK(device_read(6)&64); /* Live low INT0 request, independent of GIMSK. */
 CHECK(fresh());
 device_write(3,4,255); device_write(6,0xa8,255);
 device_write(0x32,254,255); device_write(0x33,1,255);
 device_advance(1); CHECK(!(device_read(6)&64));
 device_advance(1); CHECK(device_read(6)&64); /* Timer overflow source. */
 CHECK(fresh());
 device_write(3,5,255); device_write(6,0xa8,255);
 device_write(0x29,1,255); device_write(0x33,1,255);
 device_advance(2); CHECK(device_read(6)&64); /* Compare B source. */
 CHECK(!device_fault());
 return 0;
}
static int idle_sleep(void) {
 CHECK(fresh());
 device_write(0x39,2,255); device_write(0x33,1,255);
 device_write(0x35,32,255); device_advance(1); device_control(1,0,0);
 CHECK(device_halted());
 uint64_t elapsed=device_wait_until(1000);
 CHECK(elapsed==259 && device_base_half()==520 && !device_halted());
 CHECK(device_next_irq()==3 && device_read(0x32)==4);
 CHECK(!device_fault());
 return 0;
}
static int watchdog_powerdown(void) {
 CHECK(fresh());
 device_write(0x21,0x40,255); device_write(0x33,1,255);
 device_write(0x35,0x30,255); device_advance(1); device_control(1,0,0);
 CHECK(device_halted() && !device_reset_requested());
 device_wait_until(31999); CHECK(device_base_half()==31999 && device_halted());
 CHECK(device_read(0x32)==1); /* clkI/O was frozen throughout sleep. */
 device_wait_until(40000);
 CHECK(device_base_half()==32008 && !device_halted());
 CHECK(device_next_irq()==8 && device_read(0x32)==5);
 CHECK(!device_fault());
 return 0;
}
static int clock_division(void) {
 CHECK(fresh());
 device_write(0x26,128,255); device_advance(2); device_write(0x26,128,255);
 device_advance(2); CHECK(!(device_read(0x26)&128));
 device_write(0x26,3,255); CHECK(device_clkpr_divisor()==1);
 device_write(0x26,128,255); device_advance(1); device_write(0x26,3,255);
 CHECK(device_clkpr_divisor()==1 && device_base_half()==10 && device_next_cpu_event()==1);
 device_advance(1); CHECK(device_clkpr_divisor()==8 && device_base_half()==12 && device_virtual_half()==12);
 device_advance(1); CHECK(device_base_half()==28 && device_virtual_half()==14);
 CHECK(fresh()); device_write(0x26,128,255); device_write(0x26,3,255);
 device_write(0x21,0x40,255); device_advance(1999); CHECK(!device_pending_irqs());
 device_advance(2); CHECK(device_base_half()==32002 && device_next_irq()==8);
 CHECK(!device_fault());
 CHECK(device_configure(5,0x6a)); CHECK(device_init(data,flash,eeprom));
 CHECK(device_clkpr_divisor()==8);
 return 0;
}
static int eeprom_programming(void) {
 CHECK(fresh());
 device_write(0x1e,3,255); device_write(0x1d,0x42,255);
 device_write(0x1c,4,4); device_advance(1);
 CHECK(device_write(0x1c,2,2)==2); device_advance(2);
 device_write(0x26,128,255); device_write(0x26,3,255);
 CHECK(eeprom[3]==255);
 device_advance(400); CHECK(device_base_half()==6392 && eeprom[3]==255);
 device_advance(25); CHECK(device_base_half()==6792 && eeprom[3]==255);
 device_advance(1); CHECK(device_base_half()==6808 && eeprom[3]==0x42);
 device_write(0x1c,8,255); CHECK(device_next_irq()==4);
 CHECK(device_write(0x1c,1,1)==4 && device_read(0x1d)==0x42);
 CHECK(!device_fault());
 return 0;
}
static int flash_programming(void) {
 CHECK(fresh()); CHECK(device_configure(6,0xef)); CHECK(device_configure(13,2));
 CHECK(device_init(data,flash,eeprom));
 device_write(0x37,1,255); CHECK(device_control(2,0,0x1234)==2);
 device_advance(2); device_write(0x37,5,255); CHECK(device_control(2,0,0)==0);
 CHECK(device_halted() && device_flash_generation()==0);
 device_wait_until(9003); CHECK(device_halted() && flash[0]==255);
 device_wait_until(10000); CHECK(!device_halted() && device_base_half()==9004);
 CHECK(flash[0]==0x34 && flash[1]==0x12 && device_flash_generation()==1);
 CHECK(device_take_dirty_pages()==1 && device_take_dirty_pages()==0);
 device_write(0x37,9,255); CHECK(device_lpm(0)==0x7a);
 CHECK(!device_fault());
 return 0;
}
static int watchdog_reset(void) {
 CHECK(fresh());
 data[96]=77; eeprom[3]=19; device_write(0x21,8,255);
 device_advance(15999); device_advance(2);
 CHECK(device_base_half()==32000 && device_virtual_half()==32000);
 CHECK(device_reset_requested()==8 && device_halted());
 device_reset(device_reset_requested());
 CHECK(!device_reset_requested() && device_base_half()==32000 && device_read(0x34)==9);
 CHECK(device_read(0x21)&8); CHECK(data[96]==77 && eeprom[3]==19 && device_read(0x32)==0);
 device_write(0x34,0,255); device_write(0x21,0x18,255); device_write(0x21,0,255);
 CHECK(!device_read(0x21)); CHECK(!device_fault());
 return 0;
}
static int diagnostics(void) {
 CHECK(fresh());
 device_write(0x17,1,255); device_clear_pin_events();
 for (unsigned i=0;i<1030;i++) {
  device_write(0x18,(uint8_t)(i&1),1); device_advance(1);
 }
 CHECK(device_fault()==DEVICE_FAULT_OUTPUT_OVERFLOW && device_dropped_pin_events()>0);
 CHECK(fresh());
 CHECK(device_inject_digital(100,1,1));
 CHECK(!device_inject_digital(99,1,0) && device_fault()==DEVICE_FAULT_TIME);
 CHECK(fresh());
 device_control(2,0,0); CHECK(device_fault()==DEVICE_FAULT_SPM_TIMING);
 return 0;
}
static int external_reset_line(void) {
 CHECK(fresh());
 data[96]=71;
 device_write(0x17,1,255); device_write(0x18,1,255);
 CHECK(device_inject_digital(5,32,0));
 CHECK(device_inject_digital(17,32,32));
 device_advance(10);
 CHECK(device_base_half()==5 && device_virtual_half()==5);
 CHECK(device_reset_requested()==2 && device_reset_held() && device_halted());
 device_reset(device_reset_requested());
 CHECK(!device_reset_requested() && device_reset_held() && device_halted());
 CHECK(device_read(0x34)==3 && !device_read(0x17) && !device_read(0x18));
 CHECK(data[96]==71 && device_next_cpu_event()==0);
 device_write(0x18,1,255); CHECK(!device_read(0x18));
 device_advance(3); CHECK(device_base_half()==5);
 device_wait_until(16); CHECK(device_base_half()==16 && device_reset_held() && device_halted());
 device_wait_until(100);
 CHECK(device_base_half()==17 && !device_reset_held() && !device_halted());
 CHECK(!device_reset_requested() && device_read(0x34)==3);
 device_advance(1); CHECK(device_base_half()==19);
 /* Returning the externally driven pin to high-impedance also releases it. */
 CHECK(device_inject_digital(19,32,0)); CHECK(device_reset_requested()==2);
 device_reset(2);
 CHECK(device_inject_digital(23,0,0));
 device_wait_until(30); CHECK(device_base_half()==23 && !device_halted());
 CHECK(!device_fault());
 return 0;
}
static int external_reset_preserves_nvm(void) {
 CHECK(fresh());
 device_write(0x1e,4,255); device_write(0x1d,0x5a,255);
 device_write(0x1c,4,4); device_advance(1);
 CHECK(device_write(0x1c,2,2)==2);
 CHECK(device_inject_digital(3,32,0)); CHECK(device_inject_digital(8000,32,32));
 device_advance(2); CHECK(device_base_half()==3 && device_reset_requested()==2);
 device_reset(2); CHECK(eeprom[4]==255);
 device_wait_until(6801); CHECK(eeprom[4]==255 && device_reset_held());
 device_wait_until(6802); CHECK(eeprom[4]==0x5a && device_reset_held());
 device_wait_until(9000); CHECK(device_base_half()==8000 && !device_halted());
 CHECK(!device_fault());
 /* A fuse-forced watchdog does not accumulate timeouts while RESET is held. */
 CHECK(fresh()); CHECK(device_configure(5,0x5a)); CHECK(device_init(data,flash,eeprom));
 CHECK(device_inject_digital(0,32,0)); device_reset(2);
 CHECK(device_inject_digital(100000,32,32));
 device_wait_until(100000);
 CHECK(!device_reset_requested() && !device_reset_held() && device_read(0x34)==3);
 device_advance(16000); CHECK(device_reset_requested()==8 && device_base_half()==132000);
 return 0;
}
static int reset_disabled_pb5(void) {
 CHECK(fresh()); CHECK(device_configure(6,0xfe)); CHECK(device_init(data,flash,eeprom));
 CHECK(device_inject_digital(1,32,0));
 CHECK(device_inject_analog(1,5,2500000));
 device_advance(1);
 CHECK(!device_reset_requested() && !device_reset_held() && !device_halted());
 device_write(0x06,0xc0,255); device_advance(52);
 CHECK(device_read(4)==0 && device_read(5)==2); /* ADC0/PB5=512. */
 device_write(0x17,32,255); device_write(0x18,32,255);
 device_advance(3); CHECK(device_read(0x16)&32);
 CHECK(!device_reset_requested() && !device_reset_held() && !device_fault());
 return 0;
}
int device_test_case(unsigned index) {
 switch(index) {
 case 0:return bus(); case 1:return pwm_pins(); case 2:return external_t0();
 case 3:return interrupts(); case 4:return adc(); case 5:return adc_trigger();
 case 6:return idle_sleep(); case 7:return watchdog_powerdown(); case 8:return clock_division();
 case 9:return eeprom_programming(); case 10:return flash_programming();
 case 11:return watchdog_reset(); case 12:return diagnostics();
 case 13:return external_reset_line(); case 14:return external_reset_preserves_nvm();
 case 15:return reset_disabled_pb5(); default:return -1;
 }
}
