/* Device-owned edge-source integration; included by the ATtiny13A board.
 * No guessed period, opcode interpreter, allocator or host callback. */
static void gpio_external(void) {
 uint8_t mask=board.external_mask,levels=board.external_levels;
 if(board.clki_enabled){mask|=8;levels=(uint8_t)((levels&~8)|(attiny13a_clki_level(&board.clki_input)<<3));}
 system_gpio_external(&board.gpio,mask,levels,board.half);
}
int device_configure_clki(uint32_t field,uint32_t value) {
 if(board.initialized||field>2||value>1)return 0;
 clki_configuration[field]=(uint8_t)value;
 if(field==1)clki_initial_set=1;
 return 1;
}
static int clki_prepare(void) {
 if(!clki_initial_set||(board.config[DEVICE_CFG_FUSE_LOW]&3)||
    (board.config[DEVICE_CFG_WAKE_STARTUP_BASE_HALF]&1)){
  fail(DEVICE_FAULT_CONFIG,15);return 0;
 }
 uint32_t divisor=(board.config[DEVICE_CFG_FUSE_LOW]&16)?1:8;
 if(attiny13a_clki_init(&board.clki_input,board.clki_storage,CLKI_CAPACITY,0,clki_configuration[1])!=1||
    attiny13a_clki_clock_init(&board.clki_clock,clki_configuration[1],divisor)!=1){
  fail(DEVICE_FAULT_CLKI,2);return 0;
 }
 board.clki_aligned=board.clki_clock.output_level;
 board.clki_last_rise=board.clki_aligned?0:UINT64_MAX;
 board.clki_validation_enabled=clki_configuration[2];
 board.clki_min_edge_vcc=board.clki_min_period_vcc=board.clki_max_period_vcc=board.vcc_uv;
 if(attiny13a_clki_validation_init(&board.clki_validation,0,clki_configuration[1],0)){
  fail(DEVICE_FAULT_CLKI,6);return 0;
 }
 return 1;
}
uint8_t device_clki_enabled(void){return board.clki_enabled;}
uint8_t device_clki_validation_enabled(void){return board.clki_enabled&&board.clki_validation_enabled;}
static void clki_refill(void) {
 while(board.clki_periodic.remaining_edges&&attiny13a_clki_free(&board.clki_input)){
  attiny13a_clki_edge_t edge;
  if(attiny13a_clki_periodic_peek(&board.clki_periodic,&edge)!=1||
     attiny13a_clki_enqueue(&board.clki_input,&edge,1,edge.time_ps)!=1||
     attiny13a_clki_periodic_consume(&board.clki_periodic)!=1){fail(DEVICE_FAULT_CLKI,7);return;}
 }
 if(!board.clki_periodic.remaining_edges&&
    attiny13a_clki_horizon(&board.clki_input)<board.clki_declared_horizon&&
    attiny13a_clki_enqueue(&board.clki_input,NULL,0,board.clki_declared_horizon)!=1)
  fail(DEVICE_FAULT_CLKI,8);
}
int device_clki_enqueue(const attiny13a_clki_edge_t *edges,uint32_t count,uint64_t horizon) {
 if(!board.initialized||!board.clki_enabled||board.fault)return AT13_CLKI_BAD_ARGUMENT;
 if(board.clki_periodic.remaining_edges){
  if(count)return AT13_CLKI_BACKPRESSURE;
  if(horizon==UINT64_MAX||horizon<board.clki_declared_horizon)return AT13_CLKI_BAD_TIME;
  board.clki_declared_horizon=horizon;board.clki_status=0;deadline_invalidate(DEADLINE_INPUT);return 1;
 }
 int result=attiny13a_clki_enqueue(&board.clki_input,edges,count,horizon);
 if(result==1){board.clki_declared_horizon=horizon;deadline_invalidate(DEADLINE_INPUT);board.clki_status=0;}
 return result;
}
int device_clki_periodic_ps(uint64_t start,uint32_t initial,uint64_t high,uint64_t low,uint64_t count,uint64_t horizon){
 if(!board.initialized||!board.clki_enabled||board.fault||initial>1)return AT13_CLKI_BAD_ARGUMENT;
 if(board.clki_periodic.remaining_edges)return AT13_CLKI_BACKPRESSURE;
 if(start<board.clki_declared_horizon)return AT13_CLKI_BAD_TIME;
 uint8_t tail=attiny13a_clki_level(&board.clki_input)^(attiny13a_clki_count(&board.clki_input)&1);
 if(initial!=tail)return AT13_CLKI_BAD_LEVEL;
 attiny13a_clki_periodic_t next;
 if(attiny13a_clki_periodic_init(&next,start,(uint8_t)initial,high,low,count,horizon)!=1)return AT13_CLKI_BAD_ARGUMENT;
 board.clki_periodic=next;board.clki_declared_horizon=horizon;board.clki_status=0;
 deadline_invalidate(DEADLINE_INPUT);clki_refill();return board.fault?AT13_CLKI_BAD_ARGUMENT:1;
}
uint64_t device_clki_periodic_remaining(void){return board.clki_periodic.remaining_edges;}
uint64_t device_clki_horizon_ps(void){return board.clki_enabled?board.clki_declared_horizon:0;}
uint32_t device_clki_count(void){return board.clki_enabled?attiny13a_clki_count(&board.clki_input):0;}
uint32_t device_clki_free(void){return board.clki_enabled?attiny13a_clki_free(&board.clki_input):0;}
uint8_t device_clki_level(void){return board.clki_enabled?attiny13a_clki_level(&board.clki_input):0;}
uint8_t device_clki_status(void){return board.clki_status;}
uint8_t device_clki_aligned(void){return board.clki_aligned;}
uint64_t device_clki_startup_ck(void){return (uint64_t)board.clki_reset_ck+board.clki_wdt_reset_ck;}
static uint64_t clki_next_edge(void) {
 attiny13a_clki_edge_t edge;
 return attiny13a_clki_peek(&board.clki_input,&edge)==1?edge.time_ps:UINT64_MAX;
}
static int clki_fetch_ready(void) {
 return board.clki_aligned&&board.clki_clock.output_level&&board.clki_last_rise==board.base;
}
static void clki_reset_startup(uint8_t sources) {
 (void)sources;
 board.reset_until=0;board.clki_reset_ck=0;board.clki_reset_wait_until=0;
 if(!board.config[DEVICE_CFG_FUSE_STARTUP_PROFILE]||board.reset_held)return;
 unsigned sut=(board.config[DEVICE_CFG_FUSE_LOW]>>2)&3;
 uint32_t ticks=sut==2?8192:sut==1?512:0;
 board.clki_reset_wait_until=ticks?after_units(ticks,board.config[DEVICE_CFG_WATCHDOG_HZ],board.wdt_remainder):board.base;
 board.clki_reset_arm=board.clki_reset_wait_until;
 board.clki_reset_ck=20; /* 6 source CK plus14 CK, after the WDT timeout. */
}
static void clki_watchdog_reset(void) {
 board.clki_wdt_reset_ck=1;board.clki_wdt_arm=board.base;
 if(board.power_enabled){board.raw_other_reset|=POWER_RESET_WDRF;power_other_sources();}
 else {board.reset_held=1;board.reset_requested|=SYSTEM_WDRF;}
}
static void clki_wake(void) {
 if(board.sleep.phase==SYSTEM_SLEEP_ASLEEP){
  uint32_t recovery_ns=board.power_enabled?board.power_config[DEVICE_POWER_RECOVERY_NS]:board.config[DEVICE_CFG_BOD_RECOVERY_NS];
  uint64_t recovery=board.bod_disabled?(uint64_t)recovery_ns*1000:0;
  uint64_t source_ck=0;
  if(board.sleep.mode==SYSTEM_SLEEP_POWER_DOWN){
   source_ck=board.config[DEVICE_CFG_WAKE_STARTUP_BASE_HALF]/2;
   if(board.config[DEVICE_CFG_FUSE_STARTUP_PROFILE]&&source_ck<6)source_ck=6;
  }
  uint16_t pending=device_pending_irqs();
  uint8_t result=system_sleep_wake_clocked(&board.sleep,pending,pending,!(board.gpio.mcucr&3),
    source_ck,4,recovery,board.base);
  if(result&SYSTEM_SLEEP_INVALID_TIME)fail(DEVICE_FAULT_SLEEP,result);
  if(result&SYSTEM_SLEEP_WAKE_STARTED){
   if(board.power_enabled){power_reset_wake(&board.power,board.base);power_sync();}
   if(board.bod_disabled)board.bod_recovery_until=add(board.base,recovery);
   board.bod_disabled=0;
  }
 }
 clock_domains();
}
/* Already-recognized RESET and supply changes win a clock-edge tie. Ordinary
 * GPIO/analog changes remain after sampling. These preapplications are
 * idempotent when the shared input queue is consumed at the end of service. */
static void clki_reset_inputs(void) {
 for(uint32_t n=0;n<board.input_count;n++){
  input_t *event=&board.inputs[(board.input_head+n)%INPUT_CAPACITY];
  if(event->at!=board.base)break;
  if(!event->type&&(board.config[DEVICE_CFG_FUSE_HIGH]&AT13_FUSE_HIGH_RSTDISBL_MASK)){
   board.external_mask=(uint8_t)((board.external_mask&~32)|(event->mask&32));
   board.external_levels=(uint8_t)((board.external_levels&~32)|(event->value&32));
   external_reset_sync();
  }else if(event->type==1&&event->pin==5&&board.reset_input_enabled){
   board.analog_mask|=32;board.analog_uv[5]=event->voltage;
   reset_input_voltage();external_reset_sync();
  }else if(event->type==2){
   board.vcc_uv=event->voltage;supply_guard();reset_input_voltage();
   board.raw_other_reset=(uint8_t)((board.raw_other_reset&POWER_RESET_WDRF)|
    (external_reset_asserted()?POWER_RESET_EXTRF:0));
   power_reset_set_inputs(&board.power,board.base,board.vcc_uv,board.raw_other_reset);power_sync();
   if(!analog_reference(&board.analog,(uint32_t)board.vcc_uv,board.config[DEVICE_CFG_BANDGAP_UV],board.half))
    fail(DEVICE_FAULT_ANALOG,15);
  }
 }
}
static void clki_source_rise(void) {
 if(board.clki_wdt_reset_ck&&board.base>board.clki_wdt_arm){
  --board.clki_wdt_reset_ck;
  if(board.power_enabled){board.raw_other_reset&=(uint8_t)~POWER_RESET_WDRF;power_other_sources();}
  else {
   uint8_t held=(uint8_t)external_reset_asserted();board.reset_held=held;
   if(!held)reset_startup(SYSTEM_WDRF);
  }
 }
 if(board.clki_reset_ck&&board.base>board.clki_reset_arm&&board.base>=board.clki_reset_wait_until)
  --board.clki_reset_ck;
}
static void clki_service(uint64_t previous_half) {
 board.clki_edge=0;
 clki_reset_inputs();service_async();wake();
 int held=board.reset_held||reset_starting()||board.reset_requested;
 if(board.clki_validation_enabled){
  if(board.vcc_uv<board.clki_min_edge_vcc)board.clki_min_edge_vcc=board.vcc_uv;
  if(board.vcc_uv<board.clki_min_period_vcc)board.clki_min_period_vcc=board.vcc_uv;
  if(board.vcc_uv>board.clki_max_period_vcc)board.clki_max_period_vcc=board.vcc_uv;
  uint32_t reason=attiny13a_clki_validation_set_reset(&board.clki_validation,board.base,held);
  if(reason){fail(DEVICE_FAULT_CLKI,0x100|reason);return;}
 }
 int running=(board.domains&SYSTEM_CLOCK_MAIN)!=0;
 attiny13a_clki_edge_t edge;
 if(attiny13a_clki_peek(&board.clki_input,&edge)==1&&edge.time_ps==board.base){
  if(attiny13a_clki_consume(&board.clki_input,NULL)!=1){fail(DEVICE_FAULT_CLKI,3);return;}
  clki_refill();
  /* PB3 is the same physical pad seen by GPIO, ADC3 and pin capture. */
  gpio_external();capture_pins();pin_voltages();
  if(board.clki_validation_enabled){
   /* Qualify completed spans against their worst observed supply tier. This
    * is conservative for a changing VCC, not analog threshold reconstruction. */
   int32_t vcc=board.clki_min_edge_vcc<board.clki_min_period_vcc?board.clki_min_edge_vcc:board.clki_min_period_vcc;
   if(board.clki_max_period_vcc>5500000)vcc=board.clki_max_period_vcc;
   if(!board.clki_validation.have_edge)vcc=board.vcc_uv;
   uint32_t reason=attiny13a_clki_validation_edge(&board.clki_validation,board.base,edge.level,vcc,held);
   board.clki_min_edge_vcc=board.vcc_uv;
   if(edge.level||!board.clki_validation.have_rise){
    board.clki_min_period_vcc=board.clki_max_period_vcc=board.vcc_uv;
   }
   if(reason){fail(DEVICE_FAULT_CLKI,0x100|reason);return;}
  }
  if(edge.level)clki_source_rise();
  uint8_t sleep=system_sleep_clock_edge(&board.sleep,edge.level,0,board.base);
  if(sleep&SYSTEM_SLEEP_INVALID_TIME)fail(DEVICE_FAULT_SLEEP,sleep);
  uint8_t level=0;
  int result=attiny13a_clki_clock_edge(&board.clki_clock,edge.level,running,&level);
  if(result<0){fail(DEVICE_FAULT_CLKI,4);return;}
  if(result==1){
   if(board.clki_aligned)board.half=add(board.half,1);
   else if(level)board.clki_aligned=1;
   if(board.clki_aligned){
    board.clki_edge=level?2:1;
    if(level)board.clki_last_rise=board.base;
   }
  }
  board.divisor=board.clki_clock.divisor;
  board.pending_divisor=board.clki_clock.pending_divisor;
 }
 service_clocks(previous_half);
 uint8_t sleep=system_sleep_clock_edge(&board.sleep,0,board.clki_edge==2,board.base);
 if(sleep&SYSTEM_SLEEP_INVALID_TIME)fail(DEVICE_FAULT_SLEEP,sleep);
 /* Protected CPU-cycle windows expire on delivered phases too. Independent
  * counters were already advanced above; this second update charges no time. */
 if(nvm_active())nvm_advance(&board.nvm,cpu_cycle(),board.ns);
 uint8_t wdt=system_watchdog_advance(&board.watchdog,cpu_cycle(),board.wdt_ticks);
 if(wdt&(SYSTEM_WDT_RESERVED|SYSTEM_WDT_TIME_REVERSED))fail(DEVICE_FAULT_WATCHDOG,wdt);
 service_end();
 if(attiny13a_clki_hold_until(&board.clki_input,board.base)!=1)fail(DEVICE_FAULT_CLKI,5);
}
static int clki_advance(uint64_t wanted,uint64_t wall,uint64_t *consumed,uint32_t pin_limit) {
 uint64_t before=board.half,target=add(before,wanted);
 uint64_t horizon=device_clki_horizon_ps(),limit=minimum(wall,horizon);
 board.clki_status=0;
 if(board.fault||board.reset_requested)return -1;
 if(!wanted){advance_to(board.base);return board.fault||board.reset_requested?-1:1;}
 if(board.reset_held||reset_starting()||power_recovering())return 0;
 while(board.half<target&&board.base<limit&&!board.fault&&!board.reset_requested&&
       !pin_buffer_ready(pin_limit)){
  uint64_t previous=board.base;
  advance_to(minimum(next_event(),limit));
  if(previous==board.base&&!board.fault&&!board.reset_requested){fail(DEVICE_FAULT_TIME,13);break;}
 }
 *consumed=board.half-before;
 if(*consumed>wanted){fail(DEVICE_FAULT_TIME,14);return -1;}
 if(board.fault||board.reset_requested)return -1;
 if(*consumed==wanted)return 1;
 if(pin_buffer_ready(pin_limit))return 2;
 board.clki_status=limit<wall&&board.base==limit?2:1;
 return 0;
}
