/* Full-device bridges. Included after the legacy ABI definitions in avr.c. */
static uint64_t full_generation;
static uint32_t full_reset_count;
static uint32_t full_audio_rate, full_audio_channels;
static uint64_t full_audio_start, full_audio_frame, full_audio_at;
static uint64_t full_audio_interval, full_audio_area[2];
static uint8_t full_audio_levels;
static int full_audio_active;
static void full_audio_collect(void);

static void full_fault(void) { if(device_fault())ERROR=25; }
static void full_deadline(void) {
 uint64_t next=device_next_cpu_event();
 S(overflowAt)=next==UINT64_MAX?INFINITY:S(cyc)+(double)next;
 S(timer)=!!(IO(0x33)&7) && !(IO(0x25)&2);
 full_fault();
}
static void full_reset(void) {
 if(!device_init(data,rom,eeprom))ERROR=25;
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
 if(a==0x29 && S(timer)){S(duty)=IO(a);S(writes)++;}
 if(a==0x36 && S(timer)){S(dutyLeft)=IO(a);S(leftWrites)++;}
 full_deadline();return (int)stalls;
}
static void full_interrupt(void) {
 uint8_t reset=device_reset_requested();
 if(reset){
  device_reset(reset);S(pc)=0;FLAGS=0;SP=0x9f;S(irqDelay)=0;
  S(frameCount)=0;S(inIRQ)=0;S(irqStart)=0;full_reset_count++;full_deadline();return;
 }
 if(S(irqDelay)){S(irqDelay)--;return;}
 if(device_halted()||!(FLAGS&128))return;
 uint8_t vector=device_next_irq();if(!vector)return;
 if(S(frameCount)>=32){fail(E_PUSH);return;}
 int return_pc=(int)S(pc);double started=S(cyc);
 FLAGS&=127;
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
int avr_device_ready(void){
 if(device_reset_requested())full_interrupt();full_fault();
 return !ERROR&&!device_halted()&&full_generation==device_flash_generation();
}
double avr_device_time(void){return (double)device_base_half();}
double avr_device_cpu_deadline(double at){return S(cyc)+(at-(double)device_base_half())/(2.0*device_clkpr_divisor());}
uint64_t avr_device_time64(void){return device_base_half();}
int avr_device_control(int command,int z,int value){
 int cycles=device_control(command,z,value);full_deadline();return cycles;
}
int avr_device_lpm(int z){int value=device_lpm(z);full_deadline();return value;}
int avr_device_wait(double deadline){
 uint64_t before=device_base_half();
 if(full_audio_active){
  uint64_t next=device_next_cpu_event();if(next>64)next=64;if(!next)next=1;
  double bounded=(double)before+next*2.0*device_clkpr_divisor();
  if(deadline>bounded)deadline=bounded;
 }
 device_wait_until((uint64_t)deadline);S(cyc)=(double)device_virtual_half()/2.0;
 if(full_audio_active)full_audio_collect();
 full_deadline();full_interrupt();
 return device_base_half()>before;
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
int avr_device_inject_analog(uint64_t at,int pin,int uv){return device_inject_analog(at,pin,uv);}
uintptr_t avr_device_pin_buffer(void){uint32_t count;return (uintptr_t)device_pin_events(&count);}
int avr_device_pin_count(void){uint32_t count;device_pin_events(&count);return count;}
void avr_device_pin_consume(int n){device_consume_pin_events(n);}
int avr_device_divisor(void){return device_clkpr_divisor();}
int avr_device_reset_count(void){return full_reset_count;}
int avr_device_halted(void){return device_halted();}
int avr_device_sleep_phase(void){return device_sleep_phase();}
int avr_device_reset_held(void){return device_reset_held();}
uintptr_t avr_device_pins(void){return (uintptr_t)device_pin_state();}
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
 full_audio_start=full_audio_at=device_base_half();full_audio_frame=0;
 full_audio_interval=full_audio_at;full_audio_area[0]=full_audio_area[1]=0;
 full_audio_levels=0;full_audio_active=0;
 uint32_t count;const device_pin_event_t *events;
 while((events=device_pin_events(&count))&&count){
  uint32_t n=0;while(n<count&&events[n].base_half<=full_audio_at)full_audio_levels=events[n++].levels;
  device_consume_pin_events(n);if(n<count)break;
 }
}
double avr_device_audio_deadline(void){
 /* oscillatorHz is exported through board configuration; independent CLKPR. */
 extern uint32_t device_oscillator_hz(void);
 uint64_t ticks=2ull*device_oscillator_hz();
 uint64_t frame=full_audio_frame+1;
 return (double)(full_audio_start+(frame/full_audio_rate)*ticks+(frame%full_audio_rate)*ticks/full_audio_rate);
}
static void full_audio_collect(void){
 uint64_t end=(uint64_t)avr_device_audio_deadline();
 if(end>device_base_half())end=device_base_half();
 uint64_t at=full_audio_at;
 uint32_t count;const device_pin_event_t *events;
 while((events=device_pin_events(&count))&&count){
  uint32_t n=0;
  while(n<count&&events[n].base_half<=end){
   uint64_t time=events[n].base_half;if(time<at)time=at;
   for(int ch=0;ch<2;ch++)if(full_audio_levels&(1<<ch))full_audio_area[ch]+=time-at;
   at=time;full_audio_levels=events[n++].levels;
  }
  device_consume_pin_events(n);if(n<count)break;
 }
 for(int ch=0;ch<2;ch++)if(full_audio_levels&(1<<ch))full_audio_area[ch]+=end-at;
 full_audio_at=end;
}
void avr_device_audio_begin(void){full_audio_active=1;full_audio_collect();}
void avr_device_audio_end(void){full_audio_active=0;}
int avr_device_audio_sample(int index){
 uint64_t end=(uint64_t)avr_device_audio_deadline(),start=full_audio_interval;
 if(device_base_half()<end)return 0;
 full_audio_collect();
 if(end==start)return 0;
 for(unsigned ch=0;ch<full_audio_channels;ch++){
  unsigned pin=full_audio_channels==1?1:ch;
  raw[index*full_audio_channels+ch]=(float)(2.0*full_audio_area[pin]/(end-start)-1.0);
 }
 full_audio_interval=end;full_audio_frame++;full_audio_area[0]=full_audio_area[1]=0;return 1;
}
