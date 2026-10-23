/* Full-device bridges. Included after the legacy ABI definitions in avr.c. */
#include "attiny13a-registers.h"
static uint64_t full_generation;
static uint32_t full_reset_count;
static uint32_t full_audio_rate, full_audio_channels;
static uint64_t full_audio_start, full_audio_frame, full_audio_at;
static uint64_t full_audio_interval, full_audio_area[2];
/* Generated code uses f64 deadlines. In the opt-in physical clock profile,
 * expose a bounded offset from a host-call origin rather than an absolute
 * picosecond timestamp (which would lose precision after about 2.5 hours). */
static uint64_t full_time_origin;
static int full_ps;
static uint8_t full_audio_levels;
static int full_audio_active;
static void full_audio_collect(void);
static uint64_t full_time64(void){return full_ps?device_time_ps():device_base_half();}
static const void *full_pin_events(uint32_t *count){
 return full_ps?(const void *)device_pin_events_ps(count):(const void *)device_pin_events(count);
}
static uint64_t full_pin_time(const void *events,uint32_t n){
 return full_ps?((const device_pin_event_ps_t *)events)[n].time_ps:((const device_pin_event_t *)events)[n].base_half;
}
static uint8_t full_pin_levels(const void *events,uint32_t n){
 return full_ps?((const device_pin_event_ps_t *)events)[n].levels:((const device_pin_event_t *)events)[n].levels;
}

static void full_fault(void) { if(device_fault())ERROR=25; }
static void full_deadline(void) {
 uint64_t next=device_next_cpu_event();
 S(overflowAt)=next==UINT64_MAX?INFINITY:S(cyc)+(double)next;
 S(timer)=!!(IO(AT13_IO_TCCR0B)&(AT13_MASK_CS00|AT13_MASK_CS01|AT13_MASK_CS02)) && !(IO(AT13_IO_PRR)&AT13_MASK_PRTIM0);
 full_fault();
}
static void full_reset(void) {
 if(!device_init(data,rom,eeprom))ERROR=25;
 full_ps=device_physical_mode();full_time_origin=0;
 full_generation=device_flash_generation();full_reset_count=0;
 full_audio_rate=0;full_audio_active=0;S(fastIdle)=0;S(fastBlocks)=0;full_deadline();
}
static void full_clock(double n) {
 if(n<0||n>4294967295.0||floor(n*2)!=n*2){ERROR=25;return;}
 device_advance_half((uint64_t)(n*2));S(cyc)=(double)device_virtual_half()/2.0;full_deadline();
 if(full_audio_active)full_audio_collect();
 if(device_reset_requested()){full_interrupt();ERROR=26;}
}
static int full_write_io(int a,int v,int mask) {
 if(device_reset_requested())return 0;
 unsigned stalls=device_write(a,v,mask);
 if(a==AT13_IO_OCR0B && S(timer)){S(duty)=IO(a);S(writes)++;}
 if(a==AT13_IO_OCR0A && S(timer)){S(dutyLeft)=IO(a);S(leftWrites)++;}
 full_deadline();return (int)stalls;
}
static void full_interrupt(void) {
 uint8_t reset=device_reset_requested();
 if(reset){
  device_reset(reset);S(pc)=0;FLAGS=0;SP=AT13_MEMORY_RAMEND;S(irqDelay)=0;
  S(frameCount)=0;S(inIRQ)=0;S(irqStart)=0;full_reset_count++;full_deadline();return;
 }
 if(S(irqDelay)){S(irqDelay)--;return;}
 if(device_halted()||!(FLAGS&AT13_MASK_SREG_I))return;
 uint8_t vector=device_next_irq();if(!vector)return;
 if(S(frameCount)>=32){fail(E_PUSH);return;}
 int return_pc=(int)S(pc);double started=S(cyc);
 FLAGS&=~AT13_MASK_SREG_I;
 /* Digital-profile phases: SRAM writes at C2/C3, vector at C4. The data
  * sheet guarantees the four-cycle total, not these internal stack phases.
  * A reset at any barrier cancels later writes and frame bookkeeping. */
 full_clock(2);if(ERROR)return;push(return_pc&255);if(ERROR)return;
 full_clock(1);if(ERROR)return;push(return_pc>>8);if(ERROR)return;
 full_clock(1);if(ERROR)return;device_ack_irq(vector);S(pc)=vector;
 S(irqStart)=started;frames[(int)S(frameCount)++]=started;
 S(inIRQ)=1;S(irqCount)++;
}

int avr_read_io(int a){int value=device_read(a);full_deadline();return value;}
int avr_write_io_masked(int a,int v,int mask){return full_write_io(a,v,mask);}
int avr_device_configure(int key,int value){return device_configure(key,value);}
int avr_device_configure_osccal_hz(int cal,int hz){return device_configure_osccal_hz(cal,hz);}
int avr_device_configure_power(int field,int value){return device_configure_power(field,value);}
int avr_device_ready(void){
 if(device_reset_requested())full_interrupt();full_fault();
 return !ERROR&&!device_halted()&&full_generation==device_flash_generation();
}
double avr_device_time(void){return (double)(full_time64()-full_time_origin);}
double avr_device_cpu_deadline(double at){
 if(full_ps){
  uint64_t deadline=full_time_origin+(uint64_t)at;
  return S(cyc)+(double)device_cpu_halves_until_ps(deadline)/2.0;
 }
 return S(cyc)+(at-(double)device_base_half())/(2.0*device_clkpr_divisor());
}
uint64_t avr_device_time64(void){return device_base_half();}
uint64_t avr_device_time_ps(void){return device_time_ps();}
uint64_t avr_device_rebase_time(void){full_time_origin=full_ps?device_time_ps():0;return full_time_origin;}
int avr_device_physical_mode(void){return device_physical_mode();}
int avr_device_oscillator_hz(void){return device_oscillator_hz();}
int avr_device_control(int command,int z,int value){
 int cycles=device_control(command,z,value);full_deadline();return cycles;
}
int avr_device_lpm(int z){int value=device_lpm(z);full_deadline();return value;}
int avr_device_wait(double deadline){
 uint64_t before=full_time64(),target=full_time_origin+(uint64_t)deadline;
 if(full_audio_active){
  uint64_t next=device_next_cpu_event();if(next>64)next=64;if(!next)next=1;
  uint64_t bounded=full_ps?device_cpu_half_deadline_ps(next*2):before+next*2*device_clkpr_divisor();
  if(target>bounded)target=bounded;
 }
 if(full_ps)device_wait_until_ps(target);else device_wait_until(target);
 S(cyc)=(double)device_virtual_half()/2.0;
 if(full_audio_active)full_audio_collect();
 full_deadline();full_interrupt();
 return full_time64()>before;
}
uint64_t avr_device_generation(void){return device_flash_generation();}
void avr_device_bind_generation(void){
 /* Wait-loop metadata is code-derived too: stale idle recognition could skip
  * newly programmed instructions even after the generated WASM was replaced. */
 for(int p=0;p<512;p++)decode(p);for(int p=0;p<512;p++)decode_idle(p);
 full_generation=device_flash_generation();device_take_dirty_pages();
}
int avr_device_fault(void){return device_fault();}
int avr_device_fault_detail(void){return device_fault_detail();}
int avr_device_inject_pins(uint64_t at,int mask,int levels){
 int accepted=device_inject_digital(at,mask,levels);
 if(device_reset_requested())full_interrupt();full_deadline();return accepted;
}
int avr_device_inject_analog(uint64_t at,int pin,int uv){
 int accepted=device_inject_analog(at,pin,uv);full_deadline();return accepted;
}
int avr_device_inject_pins_ps(uint64_t at,int mask,int levels){
 int accepted=device_inject_digital_ps(at,mask,levels);
 if(device_reset_requested())full_interrupt();full_deadline();return accepted;
}
int avr_device_inject_analog_ps(uint64_t at,int pin,int uv){
 int accepted=device_inject_analog_ps(at,pin,uv);full_deadline();return accepted;
}
int avr_device_inject_vcc_ps(uint64_t at,int uv){
 int accepted=device_inject_vcc_ps(at,uv);
 if(device_reset_requested())full_interrupt();full_deadline();return accepted;
}
int avr_device_power_enabled(void){return device_power_enabled();}
int avr_device_vcc_microvolts(void){return device_vcc_microvolts();}
uintptr_t avr_device_pin_buffer(void){uint32_t count;return (uintptr_t)device_pin_events(&count);}
int avr_device_pin_count(void){uint32_t count;device_pin_events(&count);return count;}
uintptr_t avr_device_pin_buffer_ps(void){uint32_t count;return (uintptr_t)device_pin_events_ps(&count);}
int avr_device_pin_count_ps(void){uint32_t count;device_pin_events_ps(&count);return count;}
void avr_device_pin_consume(int n){device_consume_pin_events(n);}
int avr_device_divisor(void){return device_clkpr_divisor();}
int avr_device_reset_count(void){return full_reset_count;}
int avr_device_halted(void){return device_halted();}
int avr_device_sleep_phase(void){return device_sleep_phase();}
int avr_device_starting(void){return device_starting();}
uint64_t avr_device_startup_deadline(void){return device_startup_deadline();}
uint64_t avr_device_startup_deadline_ps(void){return device_startup_deadline_ps();}
int avr_device_bod_disabled(void){return device_bod_disabled();}
int avr_device_bod_recovering(void){return device_bod_recovering();}
int avr_device_reset_held(void){return device_reset_held();}
uintptr_t avr_device_pins(void){return (uintptr_t)device_pin_state();}
uintptr_t avr_device_pins_ps(void){return (uintptr_t)device_pin_state_ps();}
int avr_device_pending(void){return device_pending_irqs();}
int avr_device_idle(double deadline){
 if(!avr_device_ready()||S(irqDelay)||device_pending_irqs())return 0;
 int p=(int)S(pc);if(p<0||p>=512)return 0;
 int kind=idle[p];if(!kind||(kind==2&&(FLAGS&64)))return 0;
 uint64_t distance=device_next_cpu_event();
 double budget=fmin(4294967294.0,deadline-S(cyc));
 if(distance!=UINT64_MAX)budget=fmin(budget,(double)distance-1);
 double period=kind==3?6:2,n=floor(budget/period)*period;if(n<=0)return 0;
 if(kind==3){
  int value=(data[src[p]]-data[src[(p+1)&511]])&imm[(p+2)&511],limit=imm[(p+3)&511];
  if(value<limit)return 0;
  data[dst[p]]=value;arithmetic(value,limit,0,1);
 }
 S(idleCycles)+=n;full_clock(n);return 1;
}

/* Physical pin box integration. A CPU instruction may extend beyond an audio
 * deadline; future pin events remain queued for the following sample. */
void avr_device_audio_config(int rate,int channels){
 full_audio_rate=rate;full_audio_channels=channels;
 full_audio_start=full_audio_at=full_time64();full_audio_frame=0;
 full_audio_interval=full_audio_at;full_audio_area[0]=full_audio_area[1]=0;
 full_audio_levels=full_ps?device_pin_state_ps()->levels:device_pin_state()->levels;
 full_audio_active=0;
 uint32_t count;const void *events;
 while((events=full_pin_events(&count))&&count){
  uint32_t n=0;while(n<count&&full_pin_time(events,n)<=full_audio_at){full_audio_levels=full_pin_levels(events,n);n++;}
  device_consume_pin_events(n);if(n<count)break;
 }
}
static uint64_t full_audio_deadline64(void){
 if(full_ps)return device_next_sample_ps(full_audio_start,full_audio_frame+1,full_audio_rate);
 /* oscillatorHz is exported through board configuration; independent CLKPR. */
 extern uint32_t device_oscillator_hz(void);
 uint64_t ticks=2ull*device_oscillator_hz();
 uint64_t frame=full_audio_frame+1;
 return full_audio_start+(frame/full_audio_rate)*ticks+(frame%full_audio_rate)*ticks/full_audio_rate;
}
double avr_device_audio_deadline(void){
 uint64_t end=full_audio_deadline64();
 /* A slow CPU instruction may already have crossed several sample deadlines. */
 return end>=full_time_origin?(double)(end-full_time_origin):-(double)(full_time_origin-end);
}
static void full_audio_collect(void){
 uint64_t end=full_audio_deadline64();
 if(end>full_time64())end=full_time64();
 uint64_t at=full_audio_at;
 uint32_t count;const void *events;
 while((events=full_pin_events(&count))&&count){
  uint32_t n=0;
  while(n<count&&full_pin_time(events,n)<=end){
   uint64_t time=full_pin_time(events,n);if(time<at)time=at;
   for(int ch=0;ch<2;ch++)if(full_audio_levels&(1<<ch))full_audio_area[ch]+=time-at;
   at=time;full_audio_levels=full_pin_levels(events,n);n++;
  }
  device_consume_pin_events(n);if(n<count)break;
 }
 for(int ch=0;ch<2;ch++)if(full_audio_levels&(1<<ch))full_audio_area[ch]+=end-at;
 full_audio_at=end;
}
void avr_device_audio_begin(void){full_audio_active=1;full_audio_collect();}
void avr_device_audio_end(void){full_audio_active=0;}
int avr_device_audio_sample(int index){
 uint64_t end=full_audio_deadline64(),start=full_audio_interval;
 if(full_time64()<end)return 0;
 full_audio_collect();
 if(end==start)return 0;
 for(unsigned ch=0;ch<full_audio_channels;ch++){
  unsigned pin=full_audio_channels==1?1:ch;
  raw[index*full_audio_channels+ch]=(float)(2.0*full_audio_area[pin]/(end-start)-1.0);
 }
 full_audio_interval=end;full_audio_frame++;full_audio_area[0]=full_audio_area[1]=0;return 1;
}
