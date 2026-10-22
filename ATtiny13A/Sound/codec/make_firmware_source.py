"""Transform the tested LPC-8 AVR lattice into interpolated, variable-length keyframes."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=(ROOT/'baseline_tinylpc.S').read_text()
p=BASE.replace('.set VOICE_ADDR,0x0300','.set VOICE_ADDR,0x0342\n.set K_ACTIVE, 0x80\n.set K_TARGET, 0x88')
# Gain smoothing and spectral smooth update every 4 PCM samples; F0 continues gentle correction at each 8 samples.
p=p.replace('active_frame:\n /* Small interpolated F0 glides', '''active_frame:
 /* Linear-in-quantized-domain ramp: all eight lattice reflection
  * coefficients and amplitude approach new keyframe targets by 1 step
  * every 4 samples (0.53 ms). No full-frame discontinuities.
  */
 mov r16,r10
 andi r16,3
 brne skip_smoothing
 rcall smooth_coeffs
 lds r16,GAIN_TARGET
 cp r5,r16
 breq skip_smoothing
 brlt gain_up
 dec r5
 rjmp skip_smoothing
gain_up:
 inc r5
skip_smoothing:
 /* Small interpolated F0 glides''')
# Add ~32 bytes subroutine before read_frame.
p=p.replace('read_frame:\n', '''smooth_coeffs:
 /* Active coefficients at 0x80..0x87, targets at 0x88..0x8f.
  * SRAM 0x90..0x9f stays free for the hardware stack.
  * Difference of +/-1 per 4 samples => <=14 steps to a new formant.
  */
 ldi r28,K_ACTIVE
 clr r29
 ldi r26,K_TARGET
 clr r27
 ldi r25,8
smooth_loop:
 ld r16,Y
 ld r23,X
 cp r16,r23
 breq smooth_next
 brlt smooth_up
 dec r16
 rjmp smooth_store
smooth_up:
 inc r16
smooth_store:
 st Y,r16
smooth_next:
 inc r28
 inc r26
 dec r25
 brne smooth_loop
 ret

read_frame:
''')
# Only full frame updates coefficient targets, short frame updates pitch/energy.
start=p.index('read_frame:\n')
end=p.index('\n/* ISR runs ',start)
p=p[:start]+'''read_frame:
 mov r23,r4  /* previous pitch for short F0 glide */
 /* A silence run stays silent; first command already reset filter states. */
 lds r16,RLE_LEFT
 tst r16
 breq fetch_frame
 dec r16
 sts RLE_LEFT,r16
 ret
fetch_frame:
 lpm r4,Z+
 mov r16,r4
 cpi r16,0xff
 brne check_silence
 ldi r30,lo8(VOICE_ADDR)
 ldi r31,hi8(VOICE_ADDR)
 lpm r4,Z+
check_silence:
 mov r16,r4
 cpi r16,0xe0
 brlo normal_frame
 subi r16,0xe1
 sts RLE_LEFT,r16
 rjmp silent_frame
normal_frame:
 /* Bits 0..5: pitch, bit7: only gain/F0 update (keep spectrum).
  * In a full frame 4 packed bytes update the eight lattice targets.
  */
 mov r27,r4
 mov r16,r4
 andi r16,0x3f
 mov r4,r16
 sts PITCH_TARGET,r4
 mov r16,r4
 sub r16,r23
 subi r16,252
 cpi r16,9
 brsh have_pitch
 mov r4,r23
have_pitch:
 lpm r16,Z+
 mov r24,r16
 andi r16,15
 sts GAIN_TARGET,r16
 tst r16
 breq clear_lattice_states
 sbrc r27,7
 ret
 mov r16,r24
 swap r16
 andi r16,15
 subi r16,8
 sts K_TARGET+0,r16
 lpm r16,Z+
 mov r24,r16
 andi r16,15
 subi r16,8
 sts K_TARGET+1,r16
 mov r16,r24
 swap r16
 andi r16,15
 subi r16,8
 sts K_TARGET+2,r16
 lpm r16,Z+
 mov r24,r16
 andi r16,15
 subi r16,8
 sts K_TARGET+3,r16
 mov r16,r24
 swap r16
 andi r16,15
 subi r16,8
 sts K_TARGET+4,r16
 lpm r16,Z+
 mov r24,r16
 andi r16,15
 subi r16,8
 sts K_TARGET+5,r16
 mov r16,r24
 swap r16
 andi r16,15
 subi r16,8
 sts K_TARGET+6,r16
 lpm r16,Z+
 andi r16,15
 subi r16,8
 sts K_TARGET+7,r16
 ret
silent_frame:
 clr r4
 sts PITCH_TARGET,r4
 clr r5
 sts GAIN_TARGET,r5
clear_lattice_states:
 clr r14
 clr r15
 clr r11
 clr r17
 clr r18
 clr r12
 clr r13
 sts STATE7,r13
 ret
''' + p[end:]
# Swap coefficient sources from r0/r1/r6/7/8/9/ram to 8 current SRAM slots.
# Note: explicit mov r23,rN used for MAC; r23 read only from SRAM for K.
p=p.replace('lds r23,COEFF_K7','lds r23,K_ACTIVE+7').replace('lds r23,COEFF_K6','lds r23,K_ACTIVE+6')
for i,reg in enumerate(['r6','r7','r8','r9','r0','r1']):
 p=p.replace('mov r23,'+reg+'\n',f'lds r23,K_ACTIVE+{i}\n')
# initialize SRAM K targets & active arrays with zeros, for deterministic startup
p=p.replace(' clr r10                  /* Frame sample count modulo 256. */', ''' clr r10                  /* Frame sample count modulo 256. */
 ldi r28,K_ACTIVE
 clr r29
 ldi r25,16
clr_coeffs:
 st Y+,r10
 dec r25
 brne clr_coeffs''')
# Don't leave r28 nonzero when reset goes on, it's reinitialized before access.
(ROOT/'tinylpc.S').write_text(p)
print('generated', len(p),'asm bytes')
