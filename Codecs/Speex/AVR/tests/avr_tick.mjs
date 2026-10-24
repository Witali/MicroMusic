// AVR8js 0.21.1 tick() accepts IRQ immediately after SREG.I rises and charges
// only two entry cycles. Model the ATmega328P's next-instruction guarantee
// and four-cycle minimum entry without changing instruction execution/timers.
// https://avrdudes.github.io/avr-libc/avr-libc-user-manual/FAQ.html
// Section: Why are interrupts re-enabled in the middle of writing the stack pointer?
// Microchip ATmega328P datasheet: Reset and Interrupt Handling / Response Time.
export function tickAvr(cpu, previouslyEnabled) {
  const defer = !previouslyEnabled && cpu.interruptsEnabled;
  if (defer) cpu.data[0x5f] &= 0x7f;
  const pc = cpu.pc;
  cpu.tick(); // Clock events and pending flags still advance during deferral.
  if (defer) cpu.data[0x5f] |= 0x80;
  if (cpu.pc !== pc) cpu.cycles += 2; // avr8js already charged two of four.
}
