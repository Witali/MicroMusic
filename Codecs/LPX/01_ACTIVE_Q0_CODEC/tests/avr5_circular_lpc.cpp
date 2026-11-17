#include <avr/interrupt.h>
#include <avr/io.h>
#include <stddef.h>
#include <stdint.h>
#include "Lpx4Math.h"

extern "C" {
volatile uint8_t math_done, math_error, math_zero_error;
volatile uint8_t math_backend = LPX4_USE_AVR_ASM;
volatile uint32_t math_cases, math_irqs;
}

ISR(TIMER1_OVF_vect) {
    ++math_irqs;
}

struct Ring {
    uint8_t pos;
    uint8_t before;
    int16_t samples[10];
    uint8_t after;
};

static uint32_t rng = 6982331;

static uint16_t randomWord() {
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    return (uint16_t)rng;
}

static uint8_t slot(uint8_t pos) {
    return pos >= 10 ? pos - 10 : pos;
}

static int16_t reference(int32_t excitation, const int16_t* a, int16_t* h) {
    int32_t sum = excitation / 16;
    for (int8_t tap = 9; tap >= 0; --tap) {
        const int32_t product = (int32_t)a[tap] * h[tap];
        const int32_t term = product >= 0 ? product / 4096 : -((-product + 4095) / 4096);
        sum -= term;
        if (tap < 9) h[tap+1] = h[tap];
    }
    h[0] = sum < -32767 ? -32767 : sum > 32767 ? 32767 : (int16_t)sum;
    return h[0];
}

static bool check(Ring& ring, int16_t* linear, const int16_t* a, int32_t excitation) {
    const uint8_t position = ring.pos;
    const int16_t actual = lpx4SynthesisCircularQ12<offsetof(Ring,samples)>(excitation, a, &ring.pos);
    uint8_t zero;
    __asm__ volatile("mov %0,__zero_reg__" : "=r"(zero));
    if (zero) math_zero_error = 1;
    const int16_t expected = reference(excitation, a, linear);
    if (actual != expected || ring.pos != position || ring.before != 113 || ring.after != 79) return false;
    if (++ring.pos == 20) ring.pos = 0;
    uint8_t oldest = slot(ring.pos);
    for (int8_t tap = 9; tap >= 0; --tap) {
        if (ring.samples[oldest] != linear[tap]) return false;
        if (++oldest == 10) oldest = 0;
    }
    ++math_cases;
    return true;
}

int main() {
    TIMSK1 = _BV(TOIE1);
    TCCR1B = _BV(CS10);
    sei();
    Ring ring;
    int16_t linear[10], a[10];
    for (uint8_t start = 0; start < 20; ++start) {
        for (uint8_t scenario = 0; scenario < 48; ++scenario) {
            ring.pos = start;
            ring.before = 113;
            ring.after = 79;
            uint8_t oldest = slot(start);
            for (int8_t tap = 9; tap >= 0; --tap) {
                linear[tap] = (int16_t)randomWord();
                ring.samples[oldest] = linear[tap];
                if (++oldest == 10) oldest = 0;
            }
            for (uint8_t sample = 0; sample < 43; ++sample) {
                int32_t excitation;
                if (scenario == 0) {
                    for (uint8_t tap = 0; tap < 10; ++tap) a[tap] = 0;
                    const int32_t values[] = {-32769,-32768,-32767,0,32766,32767,32768,-524288,524287};
                    excitation = values[sample % 9] * 16;
                } else {
                    for (uint8_t tap = 0; tap < 10; ++tap) a[tap] = (int16_t)randomWord();
                    excitation = ((int32_t)((uint16_t)randomWord()) - 32768) * 256;
                }
                if (!check(ring,linear,a,excitation)) {
                    math_error = 1;
                    math_done = 1;
                    for (;;) {}
                }
            }
        }
    }
    math_done = 1;
    for (;;) {}
}
