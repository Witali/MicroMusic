/*
 * ATtiny13A — первоначальный пользовательский C-прототип (21.06.2016).
 * Реконструкция по исходному сообщению; форматирование и комментарии сокращены.
 * Служит ИСТОРИЧЕСКИМ исходником, не текущей рабочей прошивкой.
 */
#define F_CPU 9600000UL
#include <avr/io.h>
#include <util/delay.h>
#include <avr/pgmspace.h>
#include <avr/interrupt.h>
#define SAMPLE_RATE 40000
const char SIN_TABLE[] PROGMEM = {
  50, 54, 58, 63, 67, 71, 75, 78, 82, 85, 88, 90, 93, 95, 97, 98, 99, 99, 100,
  99, 99, 98, 97, 95, 93, 90, 88, 85, 82, 78, 75, 71, 67, 63, 58, 54,
  50, 46, 42, 37, 33, 29, 25, 22, 18, 15, 12, 10, 7, 5, 3, 2, 1, 1, 0,
  1, 1, 2, 3, 5, 7, 10, 12, 15, 18, 22, 25, 29, 33, 37, 42, 46
};
const char NOTE_FREQ[] PROGMEM = {
  131, 139, 148, 156, 165, 175, 185, 196, 207, 220, 233, 247
};
const char MELODY[] PROGMEM = {
  0xD2,
  0x11,0x51,0x81,0x51,0x62,0x51,0x31,0x82,0x62,0x13,
  0x51,0x81,0xC1,0xC1,0xD3,0x12,0xD2,0xC1,0xA1,0x83,
  0xB2,0xD3,0x22,0x51,0xD2,0xA3,0xA1,0x32,0x31
};
const int MELODY_LENGTH = 30;
char tempo = 80;
int main(void)
{
  DDRB |= (1 << DDB3) | (1 << DDB1);
  TCCR0A = (0 << COM0A1) | (0 << COM0A0) | (1 << COM0B1) | (0 << COM0B0) | (1 << WGM01) | (1 << WGM00);
  TCCR0B = (1 << CS00) | (1 << WGM02);
  OCR0A = 239;
  TIMSK0 = (1 << TOIE0);
  sei();
  OCR0B = 100;
  while (1) {
    for (int i=0, n=72; i<n; i++) {
      //_delay_ms(50);
      //OCR0B = pgm_read_byte(SIN_TABLE+i);
    }
  }
}
#define FP_SHIFT 6
ISR(TIM0_OVF_vect)
{
  static unsigned portion=0;
  static unsigned phase=0;
  static char next_note=0;
  static unsigned elapsed=0;
  static unsigned note_length=0;
  static char octave=1;
  if (elapsed > note_length) {
    char note_code=pgm_read_byte(MELODY+next_note);
    elapsed=0; phase=0;
    if (note_code>0x0f && note_code<0xD0) {
      int note_freq=pgm_read_byte(NOTE_FREQ+(note_code>>4)-1);
      note_length=(1<<(note_code&0x0F))*10000;
      portion=(72<<FP_SHIFT)/(SAMPLE_RATE/note_freq);
      portion<<=octave;
    } else if (note_code<0x10) {
      note_length=(1<<(note_code&0x0F))*10000;
      portion=0;
    } else if ((note_code&0xF0)==0xD0) {
      octave=note_code&0x0F;
      portion=0; note_length=0;
    }
    if (++next_note>MELODY_LENGTH) next_note=0;
  }
  OCR0B=pgm_read_byte(SIN_TABLE+(phase>>FP_SHIFT))+70;
  phase+=portion;
  if (phase>=(72<<FP_SHIFT)) phase-=(72<<FP_SHIFT);
  elapsed++;
  //PORTB ^= (1 << PORTB3);
  // Code to handle the event.
}
