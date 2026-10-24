# Speex NB8 AVR: separate fast decoder and compact interrupt code.
# Full GCC/avr-libc toolchain required for firmware.elf / firmware.hex.
HOSTCC ?= gcc
AVRCC ?= avr-gcc
AVROBJCOPY ?= avr-objcopy
AVRSIZE ?= avr-size
MCU ?= atmega328p
F_CPU ?= 16000000UL
COMMON = -mmcu=$(MCU) -DF_CPU=$(F_CPU) -std=gnu99 -Wall -Wextra -ffunction-sections -fdata-sections -fstack-usage
# Hot DSP is optimized for execution speed; player/ISR optimized for size.
DECFLAGS ?= -O3
OTHERFLAGS ?= -Os
OBJECTS = speex_nb8.o lpc_fast.o speex_tables.o cos_table.o sample_data.o avr_player.o

.PHONY: all host avr clean llvm-objects llvm-trace
all: host
host: host_decode
host_decode: host_decode.c speex_nb8.c speex_nb8.h speex_tables.c cos_table.c
	$(HOSTCC) -O2 -std=c99 -Wall -Wextra host_decode.c speex_nb8.c speex_tables.c cos_table.c -o $@

avr: firmware.hex
firmware.elf: $(OBJECTS)
	$(AVRCC) -mmcu=$(MCU) -Wl,--gc-sections -o $@ $(OBJECTS)
	$(AVRSIZE) -C --mcu=$(MCU) $@
firmware.hex: firmware.elf
	$(AVROBJCOPY) -O ihex -R .eeprom $< $@

speex_nb8.o: speex_nb8.c speex_nb8.h
	$(AVRCC) $(COMMON) $(DECFLAGS) -c $< -o $@
lpc_fast.o: lpc_fast.S
	$(AVRCC) -mmcu=$(MCU) -c $< -o $@
%.o: %.c speex_nb8.h
	$(AVRCC) $(COMMON) $(OTHERFLAGS) -c $< -o $@

llvm-objects:
	clang -target avr -mmcu=$(MCU) -ffreestanding -Itest_shims -O3 -c speex_nb8.c -o llvm_decoder.o
	clang -target avr -mmcu=$(MCU) -c lpc_fast.S -o llvm_lpc.o
	clang -target avr -mmcu=$(MCU) -ffreestanding -Itest_shims -Os -c avr_player.c -o llvm_player.o
llvm-trace:
	python3 build_llvm_trace.py
clean:
	rm -f *.o *.su host_decode firmware.elf firmware.hex asm_O3_noinline_merged.s

# CBR Speex WB 9.8k: extracted NB 8k embedded layer only, output PWM 16k
# interpolation, with no highband synthesis.
OBJECTS16 = speex_nb8.o lpc_fast.o speex_tables.o cos_table.o sample_data_16k.o avr_player_16k.o
.PHONY: avr16k
avr16k: firmware16.hex
firmware16.elf: $(OBJECTS16)
	$(AVRCC) -mmcu=$(MCU) -Wl,--gc-sections -o $@ $(OBJECTS16)
	$(AVRSIZE) -C --mcu=$(MCU) $@
firmware16.hex: firmware16.elf
	$(AVROBJCOPY) -O ihex -R .eeprom $< $@
