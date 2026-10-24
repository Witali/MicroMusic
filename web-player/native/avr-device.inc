/* Full-device bridges. Included after the legacy ABI definitions in avr.c. */
#include "attiny13a-registers.h"
#include "devices/attiny13a/avr-profile.inc"
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
/* Optional instruction continuation ABI. The emitter owns architectural effects
 * and its locals/stage; native code owns bounded clock spans and IRQ entry. */
typedef struct {
 uint32_t active,exec_pc,next_pc,stage;
 uint64_t remaining_halves;
 int32_t locals[9];
 uint32_t padding;
 double temp;
 uint64_t retired;
} full_phase_context_t;
_Static_assert(sizeof(full_phase_context_t)==80,"CPU phase context ABI size");
_Static_assert(offsetof(full_phase_context_t,remaining_halves)==16,"CPU phase half offset");
_Static_assert(offsetof(full_phase_context_t,locals)==24,"CPU phase local offset");
_Static_assert(offsetof(full_phase_context_t,temp)==64,"CPU phase temp offset");
_Static_assert(offsetof(full_phase_context_t,retired)==72,"CPU phase retirement offset");
static full_phase_context_t full_phase;
static int full_phase_enabled,full_phase_initialized;
static uint64_t full_phase_limit=UINT64_MAX;
static uint8_t full_phase_vector;
static int full_phase_return_pc;
static double full_phase_irq_started;
static void full_phase_irq_resume(void);
static void full_phase_cancel(void) {
 uint64_t retired=full_phase.retired;
 full_phase=(full_phase_context_t){0};full_phase.retired=retired;
 full_phase_vector=0;
}
static uint64_t full_time64(void){return full_ps?device_time_ps():device_base_half();}
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
 full_phase=(full_phase_context_t){0};full_phase_vector=0;full_phase_limit=UINT64_MAX;
 full_phase_initialized=1;
 if(!device_init(data,rom,eeprom))ERROR=25;
 full_ps=device_physical_mode();full_time_origin=0;
 if(full_phase_enabled&&!full_ps)ERROR=25;
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
  if(full_phase_enabled)full_phase_cancel();
  device_reset(reset);S(pc)=0;FLAGS=0;set_sp(AT13_MEMORY_RAMEND);S(irqDelay)=0;
  S(frameCount)=0;S(inIRQ)=0;S(irqStart)=0;full_reset_count++;full_deadline();return;
 }
 if(full_phase_enabled){
  if(full_phase.active==1)return;
  if(full_phase.active==2){full_phase_irq_resume();return;}
 }
 if(S(irqDelay)){S(irqDelay)--;return;}
 if(device_halted()||!(FLAGS&AT13_MASK_SREG_I))return;
 uint8_t vector=device_next_irq();if(!vector)return;
 if(S(frameCount)>=32){fail(E_PUSH);return;}
 int return_pc=(int)S(pc);double started=S(cyc);
 FLAGS&=~AT13_MASK_SREG_I;
 if(full_phase_enabled){
  full_phase.active=2;full_phase.exec_pc=(uint32_t)return_pc;
  full_phase.next_pc=vector;full_phase.stage=0;full_phase.remaining_halves=0;
  full_phase_vector=vector;full_phase_return_pc=return_pc;full_phase_irq_started=started;
  full_phase_irq_resume();return;
 }
 /* Digital-profile phases: SRAM writes at C2/C3, vector at C4. The data
  * sheet guarantees the four-cycle total, not these internal stack phases.
  * A reset at any barrier cancels later writes and frame bookkeeping. */
 full_clock(2);if(ERROR)return;push(return_pc&255);if(ERROR)return;
 full_clock(1);if(ERROR)return;push(return_pc>>8);if(ERROR)return;
 full_clock(1);if(ERROR)return;device_ack_irq(vector);S(pc)=vector;
 S(irqStart)=started;frames[(int)S(frameCount)++]=started;
 S(inIRQ)=1;S(irqCount)++;
}

int avr_device_phase_enable(int enabled){
 if(full_phase_initialized||(enabled!=0&&enabled!=1))return 0;
 full_phase_enabled=enabled;return 1;
}
uintptr_t avr_device_phase_layout(int item){
 switch(item){
 case 0:return (uintptr_t)&full_phase;case 1:return sizeof full_phase;
 case 2:return (uintptr_t)&full_phase.active;case 3:return (uintptr_t)&full_phase.exec_pc;
 case 4:return (uintptr_t)&full_phase.next_pc;case 5:return (uintptr_t)&full_phase.stage;
 case 6:return (uintptr_t)&full_phase.remaining_halves;case 7:return (uintptr_t)&full_phase.locals;
 case 8:return (uintptr_t)&full_phase.temp;case 9:return (uintptr_t)&full_phase.retired;
 default:return 0;
 }
}
int avr_device_phase_active(void){return full_phase_enabled?(int)full_phase.active:0;}
void avr_device_phase_deadline(double relative){
 if(!full_phase_enabled)return;
 if(relative==INFINITY){full_phase_limit=UINT64_MAX;return;}
 if(!isfinite(relative)||relative<0||relative>9007199254740991.0||floor(relative)!=relative||
    (uint64_t)relative>=UINT64_MAX-full_time_origin){ERROR=25;return;}
 full_phase_limit=full_time_origin+(uint64_t)relative;
}
int avr_device_phase_clock(double cycles){
 if(!full_phase_enabled||!full_ps||full_phase.active<1||full_phase.active>2||
    !isfinite(cycles)||cycles<0||cycles>4294967295.0||floor(cycles*2)!=cycles*2){ERROR=25;return -1;}
 if(device_reset_requested()){full_interrupt();return -1;}
 if(ERROR||device_fault()){full_fault();return -1;}
 if(!full_phase.remaining_halves)full_phase.remaining_halves=(uint64_t)(cycles*2);
 if(full_phase.remaining_halves&&full_phase_limit<=device_time_ps())return 0;
 for(;;){
  uint64_t requested=full_phase.remaining_halves;
  uint64_t consumed=0;
  int result;
  if(full_audio_active){
   /* Deferred short spans must not consume a long barrier's ring headroom. */
   if(requested>128)full_audio_collect();
   result=device_advance_half_until_ps_buffered(full_phase.remaining_halves,full_phase_limit,&consumed);
  }else result=device_advance_half_until_ps(full_phase.remaining_halves,full_phase_limit,&consumed);
  full_phase.remaining_halves-=consumed;
  S(cyc)=(double)device_virtual_half()/2.0;full_deadline();
  if(full_audio_active&&(requested>128||result==2||device_pin_buffer_ready()))full_audio_collect();
  if(device_reset_requested()){full_interrupt();return -1;}
  if(result<0||ERROR)return -1;
  /* One CPU cycle can require512 source transitions. Drain inside this one
   * clock barrier without replaying its instruction effect or asking JS. */
  if(result==2)continue;
  return !full_phase.remaining_halves&&result==1;
 }
}
static void full_phase_irq_resume(void){
 while(full_phase.active==2&&!ERROR){
  if(full_phase.stage>2){ERROR=25;return;}
  int complete=avr_device_phase_clock(full_phase.stage?1:2);
  if(complete!=1)return;
  if(full_phase.stage==0){push(full_phase_return_pc&255);if(ERROR)return;full_phase.stage=1;}
  else if(full_phase.stage==1){push(full_phase_return_pc>>8);if(ERROR)return;full_phase.stage=2;}
  else {
   device_ack_irq(full_phase_vector);S(pc)=full_phase_vector;
   S(irqStart)=full_phase_irq_started;frames[(int)S(frameCount)++]=full_phase_irq_started;
   S(inIRQ)=1;S(irqCount)++;
   full_phase.active=0;full_phase.stage=0;full_phase.remaining_halves=0;full_phase_vector=0;
   full_deadline();return;
  }
 }
}
void avr_device_phase_retire(void){
 if(!full_phase_enabled||full_phase.active!=1||full_phase.remaining_halves||ERROR){ERROR=25;return;}
 if(full_phase.retired==UINT64_MAX){ERROR=25;return;}
 full_phase.retired++;full_phase.active=0;full_phase.stage=0;
 full_interrupt();
}

int avr_read_io(int a){int value=device_read(a);full_deadline();return value;}
int avr_write_io_masked(int a,int v,int mask){return full_write_io(a,v,mask);}
int avr_device_configure(int key,int value){return device_configure(key,value);}
int avr_device_configure_osccal_hz(int cal,int hz){return device_configure_osccal_hz(cal,hz);}
int avr_device_configure_power(int field,int value){return device_configure_power(field,value);}
int avr_device_configure_reset_input(int field,int value){return device_configure_reset_input(field,value);}
int avr_device_configure_clki(int field,int value){return device_configure_clki(field,value);}
static attiny13a_clki_edge_t full_clki_batch[512];
int avr_device_clki_enabled(void){return device_clki_enabled();}
int avr_device_clki_validation_enabled(void){return device_clki_validation_enabled();}
int avr_device_clki_periodic_ps(uint64_t start,int initial,uint64_t high,uint64_t low,uint64_t count,uint64_t horizon){
 if(initial<0||initial>1)return AT13_CLKI_BAD_ARGUMENT;
 int result=device_clki_periodic_ps(start,(uint32_t)initial,high,low,count,horizon);full_deadline();return result;
}
uint64_t avr_device_clki_periodic_remaining(void){return device_clki_periodic_remaining();}
uintptr_t avr_device_clki_buffer(void){return (uintptr_t)full_clki_batch;}
int avr_device_clki_capacity(void){return 512;}
int avr_device_clki_commit(int count,uint64_t horizon){
 if(count<0||count>512)return AT13_CLKI_BAD_ARGUMENT;
 int result=device_clki_enqueue(full_clki_batch,(uint32_t)count,horizon);full_deadline();return result;
}
uint64_t avr_device_clki_horizon_ps(void){return device_clki_horizon_ps();}
int avr_device_clki_count(void){return device_clki_count();}
int avr_device_clki_free(void){return device_clki_free();}
int avr_device_clki_level(void){return device_clki_level();}
int avr_device_clki_status(void){return device_clki_status();}
int avr_device_clki_aligned(void){return device_clki_aligned();}
uint64_t avr_device_clki_startup_ck(void){return device_clki_startup_ck();}
int avr_device_reset_input_enabled(void){return device_reset_input_enabled();}
int avr_device_reset_input_asserted(void){return device_reset_input_asserted();}
uint64_t avr_device_reset_input_deadline_ps(void){return device_reset_input_deadline_ps();}
int avr_device_ready(void){
 if(device_reset_requested())full_interrupt();
 if(full_phase_enabled){
  if(full_phase.active==2)full_phase_irq_resume();
  full_fault();if(ERROR||full_phase.active==2)return 0;
  if(full_phase.active==1)return 1;
 }
 full_fault();
 return !ERROR&&!device_halted()&&full_generation==device_flash_generation();
}
double avr_device_time(void){return (double)(full_time64()-full_time_origin);}
double avr_device_cpu_deadline(double at){
 if(full_ps){
  /* An unbounded CPU block must still fit the finite physical timeline.
   * Keep the reserved UINT64_MAX sentinel outside that budget. The emitter
   * compares integer spans strictly below the rounded-up half-cycle bound. */
  uint64_t deadline=at==INFINITY?UINT64_MAX-1:full_time_origin+(uint64_t)at;
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
 if(full_phase_enabled&&full_phase.active==2){
  uint64_t saved=full_phase_limit;if(target<full_phase_limit)full_phase_limit=target;
  full_phase_irq_resume();full_phase_limit=saved;return full_time64()>before;
 }
 if(full_audio_active){
  uint64_t next=device_next_cpu_event();if(next>64)next=64;if(!next)next=1;
  uint64_t bounded=full_ps?device_cpu_half_deadline_ps(next*2):before+next*2*device_clkpr_divisor();
  if(target>bounded)target=bounded;
 }
 if(full_ps){
  if(full_audio_active)device_wait_until_ps_buffered(target);
  else device_wait_until_ps(target);
 }else device_wait_until(target);
 S(cyc)=(double)device_virtual_half()/2.0;
 if(full_audio_active&&(!full_phase_enabled||device_pin_buffer_ready()))full_audio_collect();
 full_deadline();
 if(!full_phase_enabled||full_phase.active!=1||device_reset_requested())full_interrupt();
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
 int accepted=device_inject_analog_ps(at,pin,uv);
 if(device_reset_requested())full_interrupt();full_deadline();return accepted;
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
int avr_device_pin_trace_config(int mask,int retain){return device_configure_pin_trace((uint32_t)mask,(uint32_t)retain);}
int avr_device_pin_trace_configuration(void){return (int)device_pin_trace_configuration();}
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
 if(full_phase_enabled)return 0;
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
 if(rate<8000||rate>192000||(channels!=1&&channels!=2)){ERROR=25;return;}
 if(!device_configure_audio_pins(channels==1?2:3)){ERROR=25;return;}
 full_audio_rate=rate;full_audio_channels=channels;
 full_audio_start=full_audio_at=full_time64();full_audio_frame=0;
 full_audio_interval=full_audio_at;full_audio_area[0]=full_audio_area[1]=0;
 /* A new stream starts at the live pins. Host history is a separate observer;
  * retaining it must never replay old levels into this initial baseline. */
 device_discard_audio_trace(full_audio_at);
 full_audio_levels=full_ps?device_pin_state_ps()->levels:device_pin_state()->levels;
 full_audio_active=0;
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
 while((events=device_audio_pin_events(&count))&&count){
  uint32_t n=0;
  while(n<count&&full_pin_time(events,n)<=end){
   uint64_t time=full_pin_time(events,n);if(time<at)time=at;
   for(int ch=0;ch<2;ch++)if(full_audio_levels&(1<<ch))full_audio_area[ch]+=time-at;
   at=time;full_audio_levels=full_pin_levels(events,n);n++;
  }
  device_consume_audio_pin_events(n);if(n<count)break;
 }
 for(int ch=0;ch<2;ch++)if(full_audio_levels&(1<<ch))full_audio_area[ch]+=end-at;
 full_audio_at=end;
 device_discard_audio_trace(end);
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
