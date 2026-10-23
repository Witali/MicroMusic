# MicroMusic DecoderOpt — public synthetic example

Optimized ATtiny13A MiniLPC-HQ3 decoder, 388 B including reset/vectors/ISR, 9.6 MHz, 7.5 kHz audio, PB1/OC0B PWM. A single new VBR LPC format. There is no old-format compatibility in the firmware.

The provided `speech.hq` is a synthetic signal written for this test (not taken from films). Run `python3 build.py` to create `firmware.hex` / `firmware.bin` with clang/llvm-objcopy, then use `node verify_synthetic.js` to execute the AVR machine code in the included cycle-counting emulator.

Registers `r11` and `r12` are exclusively reserved for the ISR. High pointer bytes XH/YH are initialized once and must remain zero in the code. No physical-board tests have been performed.
