/* MicroMusic - PIC16F1503 XC8 port, reference implementation.
 * Source material: https://github.com/Witali/MicroMusic (rhythmic variant).
 * FOSC 16 MHz HFINTOSC, instruction rate 4 MIPS.
 * Timer2 PR2=63 prescaler 1:1 => PWM3 62,500 Hz, effective 8-bit resolution.
 * Timer2 interrupt postscaler 1:4 => output update 15,625 Hz.
 * Three pitched voices and one percussion voice; per-voice note-off.
 * Score repetitions and measured harmonic waveforms inherited from MicroMusic.
 * This release is unverified on silicon; compile and benchmark with MPLAB XC8.
 */
#include <xc.h>
#include <stdint.h>
#include "music_data.h"

/* XC8 device packs name this SFR PWM3CON or PWM3CON0 depending on DFP. */
#if !defined(PWM3CON) && defined(PWM3CON0)
#define PWM3CON PWM3CON0
#endif

#pragma config FOSC = INTOSC
#pragma config WDTE = OFF
#pragma config PWRTE = ON
#pragma config MCLRE = ON
#pragma config CP = OFF
#pragma config BOREN = ON
#pragma config CLKOUTEN = OFF
#pragma config WRT = OFF
#pragma config STVREN = ON
#pragma config BORV = LO
#pragma config LPBOR = OFF
#pragma config LVP = OFF

#define F_OSC 16000000UL
#define SAMPLES_PER_SECOND 15625UL
#define BUFFER_SIZE 16u
#define BUFFER_MASK 15u
#define V_RELEASE 0u
#define V_ATTACK 1u
#define V_HOLD 2u

/* 3 * 9 = 27 bytes; 16-byte queue, RAM total below 128 B excluding compiler temporaries.
 * The fixed-point phase runs freely during note-off (no audible phase reset).
 */
typedef struct {
    uint16_t phase;
    uint16_t step;
    uint8_t env;
    uint8_t stage;
    uint8_t age;
    uint8_t decay;
    uint8_t frame;
} voice_t;
static voice_t voice[3];
static volatile uint8_t queue[BUFFER_SIZE];
static volatile uint8_t read_index, write_index;
static volatile uint8_t last_duty = 128;
static volatile uint8_t underruns;
static uint8_t drum_env, drum_mode, beat_index;
static uint16_t drum_lfsr = 0xACE1u, drum_phase;
static uint8_t music_divider, envelope_ticks, remaining_grid, section_index, score_offset;
static uint16_t grid_phase;

/* Tone profiles: attack age, envelope rates and register select are deliberately
 * shared across all voices; selecting instruments adds data, not DSP instructions.
 */
static void note_start(uint8_t n, uint16_t step) {
    voice_t *v = &voice[n];
    v->step = step;
    /* Retain phase on retrigger for smooth legato and avoid destructive clicks. */
    v->age = 0; v->decay = 0; v->frame = 0; v->stage = V_ATTACK;
    v->env = n == 0 ? 1u : 15u;
}
static void note_release(uint8_t n) {
    if (voice[n].env) voice[n].stage = V_RELEASE;
}
static void drums_trigger(uint8_t mode) {
    drum_mode = mode; drum_env = 15;
    if (mode == 0) drum_phase = 0; /* rising phase + falling pitch for kick */
}

/* Update only at 244.140625 Hz, and never in the timer ISR. */
static void envelope_tick(void) {
    uint8_t i;
    ++envelope_ticks;
    for (i=0; i<3; ++i) {
        voice_t *v = &voice[i];
        if (!v->env) continue;
        if (v->age < 255) ++v->age;
        if (v->frame < 3) {
            uint8_t period = i==1 ? 6u : 4u;
            if (i==0) period=20u;
            if (v->age >= (uint8_t)((v->frame+1u)*period)) ++v->frame;
        }
        if (v->stage == V_RELEASE) {
            if (++v->decay >= 2) { v->decay=0; --v->env; }
        } else if (i==0) {
            /* Bowed violin: slow bow attack, stable body after reaching sustain. */
            if (v->stage==V_ATTACK && (++v->decay & 3u)==0) {
                if (v->env < 14) ++v->env;
                else v->stage=V_HOLD;
            }
        } else {
            /* Piano: softer long tail at low notes; guitar: faster pluck decay. */
            uint8_t high = (v->step >= 1500u);
            uint8_t period = i==1 ? (high ? 9u:17u) : (high ? 7u:12u);
            if (++v->decay >= period) {
                v->decay=0;
                if (v->env) --v->env;
                v->stage=V_HOLD;
            }
        }
    }
    if (drum_env) {
        uint8_t rate = drum_mode==2 ? 3u : 1u;
        if ((envelope_ticks % rate)==0) --drum_env;
    }
}

/* Packed events: E0..EF chord, F0..FE selective note-off, FF section end,
 * below E0 note index in bits7:3 and duration index in bits2:0.
 * A 15-position playlist references original unique sections byte-for-byte.
 */
static void advance_event(void) {
    uint8_t guard=0;
    while (guard++ < 32u) {
        uint8_t e;
        if (score_offset >= MM_SCORE_LEN) { score_offset=0; section_index=0; }
        e=mm_score[score_offset++];
        if (e == 0xff) {
            ++section_index;
            if (section_index >= MM_PLAYLIST_LEN) section_index=0;
            score_offset=mm_playlist[section_index];
            continue;
        }
        if (e >= 0xf0) {
            if(e & 1) note_release(0);
            if(e & 2) note_release(1);
            if(e & 4) note_release(2);
            if(e & 8) drum_env=0;
            continue;
        }
        if(e >= 0xe0) {
            uint8_t j=e & 0x0f;
            if (j<5) {
                note_start(1, mm_chords_key[j]);
                note_start(2, mm_chords_pluck[j]);
            }
            continue;
        }
        {
            uint8_t idx = (uint8_t)(e>>3);
            uint8_t duration=e & 7u;
            remaining_grid = duration < 7 ? mm_durations[duration] : 1u;
            if (idx==13) note_release(0);
            else if (idx<13) note_start(0,mm_note_steps[idx]);
            return;   /* index 14 is HOLD: no change in oscillator phase. */
        }
    }
    remaining_grid=1; /* guard against corrupted Flash event streams */
}

static void step_grid(void) {
    if ((beat_index & 1u)==0) {
        if (beat_index==0) drums_trigger(0);
        else if (beat_index==4) drums_trigger(1);
        else drums_trigger(2);
    }
    beat_index = (beat_index+1u)&7u;
    if(remaining_grid && --remaining_grid == 0) advance_event();
}

/* One Timer2 interrupt per FOUR PWM periods. The PWM carrier remains 62.5 kHz.
 * ISR writes both 10-bit duty registers: DCH=value>>2, DCL=(value&3)<<6.
 */
void __interrupt() interrupt_isr(void) {
    if (PIR1bits.TMR2IF) {
        PIR1bits.TMR2IF=0;
        if (read_index != write_index) {
            uint8_t v=queue[read_index];
            read_index=(read_index+1u)&BUFFER_MASK;
            PWM3DCH = v >> 2;
            PWM3DCL = (uint8_t)((v & 3u) << 6);
            last_duty=v;
        } else {
            ++underruns;
        }
    }
}

/* LFSR noise and decaying drum: no waveform samples are needed for percussion. */
static int8_t percussion_sample(void) {
    uint8_t old, n;
    if (drum_env==0) return 0;
    old=(uint8_t)drum_lfsr;
    drum_lfsr=(uint16_t)((drum_lfsr>>1)^((drum_lfsr & 1u)?0xB400u:0u));
    n=(uint8_t)drum_lfsr;
    if(drum_mode==0) {
        int8_t tone;
        drum_phase += (uint16_t)(180u + (uint16_t)drum_env*42u);
        tone=(int8_t)((drum_phase>>11)&31u)-16;
        return (int8_t)(((int16_t)tone*drum_env)>>4);
    }
    if(drum_mode==1) {
        int8_t raw=(int8_t)((n&31u)-16);
        int8_t body=(int8_t)((drum_phase>>11)&15u)-8;
        drum_phase+=300;
        return (int8_t)((((int16_t)raw+body)*drum_env)>>5);
    }
    return (int8_t)((((int16_t)((n ^ old)&31u)-16)*drum_env)>>5);
}

static int8_t wavetable(uint8_t instrument, const voice_t *v) {
    uint8_t idx=(uint8_t)(v->phase>>12);
    uint8_t high=v->step >= (instrument==0 ? 1450u : 1500u);
    if(instrument==0) return mm_violin[(high<<4)|idx];
    if(instrument==1) return mm_piano[(high<<6)|(v->frame<<4)|idx];
    return mm_guitar[(high<<6)|(v->frame<<4)|idx];
}
static uint8_t generate_sample(void) {
    int16_t mix=128;
    uint8_t i;
    if (++music_divider==64u) {
        uint16_t previous=grid_phase;
        music_divider=0;
        envelope_tick();
        grid_phase=(uint16_t)(grid_phase+MM_GRID_INC);
        if (grid_phase<previous) step_grid();
    }
    for(i=0;i<3;++i) {
        voice[i].phase=(uint16_t)(voice[i].phase+voice[i].step);
        if (voice[i].env) {
            int8_t s=wavetable(i,&voice[i]);
            mix+=((int16_t)s*voice[i].env)/4;
        }
    }
    mix+=percussion_sample();
    if (mix<0) return 0;
    if (mix>255) return 255;
    return (uint8_t)mix;
}

static void initialize_hardware(void) {
    OSCCON=0x7A;             /* IRCF=1111 -> 16MHz, SCS=10 -> internal */
    ANSELA &= (uint8_t)~0x04u;
    TRISA  |= 0x04u;        /* temporarily disable PWM pin output */
    PWM3CON=0x00;
    PR2=63;
    TMR2=0;
    PWM3DCH=32;
    PWM3DCL=0;
    PIR1bits.TMR2IF=0;
    T2CON=0x1C;            /* 1:4 postscale (IRQ); 1:1 prescale; on */
    PWM3CON=0x80;         /* turn on PWM generator */
    while (!PIR1bits.TMR2IF) { }
    PIR1bits.TMR2IF=0;
    TRISA &= (uint8_t)~0x04u;
    PWM3CON=0xC0;         /* enable RA2 driver */
    PIE1bits.TMR2IE=1;
    INTCONbits.PEIE=1;
    INTCONbits.GIE=1;
}

void main(void) {
    uint8_t i;
    read_index=write_index=underruns=0;
    music_divider=envelope_ticks=remaining_grid=section_index=score_offset=0;
    grid_phase=0;
    drum_env=beat_index=0;
    for(i=0;i<3;i++) {
        voice[i].phase=voice[i].step=0;
        voice[i].env=voice[i].stage=voice[i].age=voice[i].decay=voice[i].frame=0;
    }
    advance_event();
    initialize_hardware();
    for(;;) {
        uint8_t next=(write_index+1u)&BUFFER_MASK;
        if(next!=read_index) {
            uint8_t v=generate_sample();
            queue[write_index]=v;
            write_index=next;  /* only publish after sample data was written */
        }
    }
}
