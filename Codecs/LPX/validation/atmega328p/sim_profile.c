/* Independent complete-firmware runner using the public simavr API.
 * API references: https://github.com/buserror/simavr (sim_elf.h, sim_avr.h,
 * avr_ioport.h). No simavr implementation source is copied here.
 * Build against simavr 1.6 + libelf; simulation is not a physical board test.
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "sim_avr.h"
#include "sim_elf.h"
#include "sim_io.h"
#include "avr_ioport.h"

static avr_t *cpu;
static uint32_t running_addr, valid_addr, pwm_addr_addr;
static uint32_t occupancy_addr, underruns_addr;
static uint64_t ticks, min_tick = UINT64_MAX, max_tick, previous_tick;
static FILE *valid_output;
static uint64_t durations[64000], decode_count;
static uint64_t trace_cycles[4096];
static uint32_t trace_underruns[4096], trace_queue[4096], trace_count;

static uint32_t symbol(elf_firmware_t *fw, const char *name) {
    for (uint32_t i = 0; i < fw->symbolcount; ++i)
        if (!strcmp(fw->symbol[i]->symbol, name)) return fw->symbol[i]->addr & 0xffff;
    fprintf(stderr, "Missing ELF symbol: %s\n", name);
    exit(2);
}
static uint32_t read_le(uint32_t address, unsigned n) {
    uint32_t result = 0;
    for (unsigned i = 0; i < n; ++i) result |= (uint32_t)cpu->data[address+i] << (8*i);
    return result;
}
static void tick(struct avr_irq_t *irq, uint32_t value, void *parameter) {
    (void)irq;(void)value;(void)parameter;
    if (!cpu->data[running_addr]) return;
    if (ticks) {
        uint64_t delta = cpu->cycle - previous_tick;
        if (delta < min_tick) min_tick = delta;
        if (delta > max_tick) max_tick = delta;
    }
    previous_tick = cpu->cycle;
    ++ticks;
    if ((ticks-1)%160==0 && trace_count<4096) {
        trace_cycles[trace_count]=cpu->cycle;
        trace_queue[trace_count]=read_le(occupancy_addr,2);
        trace_underruns[trace_count]=read_le(underruns_addr,4);
        ++trace_count;
    }
    if (cpu->data[valid_addr]) {
        uint16_t address = read_le(pwm_addr_addr, 2);
        fputc(cpu->data[address], valid_output);
    }
}

int main(int argc, char **argv) {
    if (argc != 4) {fprintf(stderr, "usage: sim_profile firmware.elf valid.pcm8 report.json\n");return 2;}
    elf_firmware_t firmware = {0};
    if (elf_read_firmware(argv[1], &firmware) < 0) return 3;
    firmware.frequency = 16000000;
    cpu = avr_make_mcu_by_name("atmega328p");
    if (!cpu || avr_init(cpu) < 0) return 4;
    avr_load_firmware(cpu, &firmware);
    cpu->frequency = 16000000;
    uint32_t ready = symbol(&firmware, "profile_ready");
    uint32_t done = symbol(&firmware, "profile_done");
    uint32_t active = symbol(&firmware, "profile_decode_active");
    uint32_t error = symbol(&firmware, "profile_error");
    uint32_t produced = symbol(&firmware, "profile_produced");
    uint32_t played = symbol(&firmware, "profile_played");
    uint32_t underruns = symbol(&firmware, "profile_underruns");
    uint32_t occupancy = symbol(&firmware, "profile_min_occupancy");
    occupancy_addr = symbol(&firmware, "profile_occupancy");
    underruns_addr = underruns;
    uint32_t spl_address = symbol(&firmware, "profile_spl_address");
    uint32_t sph_address = symbol(&firmware, "profile_sph_address");
    uint32_t bss_end = symbol(&firmware, "__bss_end");
    running_addr = symbol(&firmware, "profile_running");
    valid_addr = symbol(&firmware, "profile_output_valid");
    pwm_addr_addr = symbol(&firmware, "profile_pwm_address");
    valid_output = fopen(argv[2], "wb");
    if (!valid_output) return 5;
    avr_irq_register_notify(avr_io_getirq(cpu, AVR_IOCTL_IOPORT_GETIRQ('B'), IOPORT_IRQ_PIN0), tick, NULL);
    uint8_t previous_active = 0;
    uint64_t decode_start = 0, total_decode = 0, maximum_decode = 0;
    uint32_t minimum_sp = 0xffff;
    int state = cpu_Running;
    // 125 simulated seconds covers heavily under-running clips, with a hard stop.
    while (cpu->cycle < UINT64_C(2000000000) && !cpu->data[done] && state != cpu_Crashed && state != cpu_Done) {
        state = avr_run(cpu);
        if (!cpu->data[ready]) continue;
        uint16_t sp = cpu->data[read_le(spl_address, 2)] | ((uint16_t)cpu->data[read_le(sph_address, 2)] << 8);
        if (sp < minimum_sp) minimum_sp = sp;
        uint8_t now = cpu->data[active];
        if (now && !previous_active) decode_start = cpu->cycle;
        if (!now && previous_active && decode_count < 64000) {
            uint64_t duration = cpu->cycle - decode_start;
            durations[decode_count++] = duration;
            total_decode += duration;
            if (duration > maximum_decode) maximum_decode = duration;
        }
        previous_active = now;
    }
    fclose(valid_output);
    uint64_t max40=0, max80=0, max160=0;
    for (uint64_t end=0; end<decode_count; ++end) {
        uint64_t sum=0;
        for (unsigned width=1; width<=160 && width<=end+1; ++width) {
            sum += durations[end+1-width];
            if (width==40 && sum>max40) max40=sum;
            if (width==80 && sum>max80) max80=sum;
            if (width==160 && sum>max160) max160=sum;
        }
    }
    FILE *report=fopen(argv[3], "w");
    if (!report) return 6;
    fprintf(report, "{\"simulator\":\"simavr 1.6\",\"cpu_hz\":16000000,\"audio_hz\":8000,"
        "\"done\":%u,\"decoder_error\":%u,\"produced\":%u,\"played\":%u,\"underruns\":%u,"
        "\"timer_ticks\":%llu,\"tick_interval_min_cycles\":%llu,\"tick_interval_max_cycles\":%llu,"
        "\"min_queue_before_producer_eos\":%u,\"decode_calls\":%llu,\"decode_wall_cycles_total\":%llu,"
        "\"decode_wall_cycles_max\":%llu,\"decode_wall_cycles_max_40\":%llu,"
        "\"decode_wall_cycles_max_80\":%llu,\"decode_wall_cycles_max_160\":%llu,"
        "\"minimum_stack_pointer\":%u,\"bss_end\":%u,\"stack_margin_bytes\":%d,\"total_cycles\":%llu,\"occupancy_trace\":[",
        cpu->data[done],cpu->data[error],read_le(produced,4),read_le(played,4),read_le(underruns,4),
        (unsigned long long)ticks,(unsigned long long)(ticks>1?min_tick:0),(unsigned long long)max_tick,
        read_le(occupancy,2),(unsigned long long)decode_count,(unsigned long long)total_decode,
        (unsigned long long)maximum_decode,(unsigned long long)max40,(unsigned long long)max80,(unsigned long long)max160,
        minimum_sp,bss_end,(int)minimum_sp-(int)bss_end,(unsigned long long)cpu->cycle);
    for (uint32_t i=0;i<trace_count;++i)
        fprintf(report,"%s{\"cycle\":%llu,\"queued\":%u,\"underruns\":%u}",i?",":"",
            (unsigned long long)trace_cycles[i],trace_queue[i],trace_underruns[i]);
    fprintf(report,"]}\n");
    fclose(report);
    return cpu->data[done] && !cpu->data[error] && minimum_sp>bss_end ? 0 : 7;
}
