/* Mailbox for independent ISA tests of the C/ASM arithmetic boundary. */
#include <stdint.h>
#include "avr_multiply.h"
#include "avr_shift.h"
#include "nb3_c_math.h"
extern int32_t speex_avr_mul16_32_q14(int16_t,int32_t);
extern int32_t speex_avr_lsp_mul_q14(int16_t,int32_t);
volatile int16_t math_a,math_b;
volatile int32_t math_value;
volatile int32_t math_result;
volatile uint8_t math_command,math_status,math_zero;
__attribute__((noinline,noclone)) int32_t math_multiply(int16_t a,int16_t b)
{
    return speex_avr_mul_s16_s16(a,b);
}
int main(void)
{
    math_status=1;
    for (;;) {
        while (!math_command) { }
        switch (math_command) {
        case 100: math_result=speex_avr_mul16_32_q14(math_a,math_value); break;
        case 101: math_result=speex_avr_lsp_mul_q14(math_a,math_value); break;
        case 102: math_result=speex_nb3_mul16_32_q14_c(math_a,math_value); break;
        case 13: math_result=speex_avr_asr13(math_value); break;
        case 14: math_result=speex_avr_asr14(math_value); break;
        case 15: math_result=speex_avr_asr15(math_value); break;
        case 114: math_result=speex_avr_asr14_word(math_value); break;
        case 115: math_result=speex_avr_asr15_word(math_value); break;
        default: math_result=math_multiply(math_a,math_b); break;
        }
        __asm__ ("mov %0,r1":"=r"(math_zero));
        math_command=0;
        math_status=2;
    }
}
