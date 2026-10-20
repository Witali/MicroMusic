"""Fit all eight EEPROM waves and compact FluidR3 envelope approximations."""
from pathlib import Path
import importlib.util
import copy
import json
import shutil
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'ATtiny13A/Music/variants/fluid-instruments'
spec = importlib.util.spec_from_file_location('violin_builder', ROOT / 'tools/build-fluid-violin.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
BASE = builder.BASE


def fit_waves(measurements):
    old = (BASE / 'eeprom.bin').read_bytes()
    names = list(json.loads((BASE / 'waveforms.json').read_text(encoding='utf-8')))
    waves, report = {}, {}
    strings=json.loads((OUT/'strings-comparison.json').read_text(encoding='utf-8'))['presets']['strings']['measurement']['notes']
    for i, name in enumerate(names):
        original = [v for b in old[i*8:i*8+8] for v in [(b&15)-8, (b>>4)-8]]
        profile = name.split('_')[0]
        stage = 'attack' if name.endswith('attack') else 'sustain'
        notes = []
        for note in measurements['instruments'][profile]['notes']:
            if '_low' in name and note['midi'] >= 62: continue
            if '_high' in name and note['midi'] < 62: continue
            notes.append(dict(midi=note['midi'], frames=[f for f in note['frames'] if f['stage']==stage]))
        raw_wave, raw_report=builder.fit(dict(notes=notes),[n['midi'] for n in notes],original)
        for note in notes:
            for frame in note['frames']:
                a=np.array(frame['amplitudes'][:7]);a/=np.linalg.norm(a)
                if profile=='violin':
                    neighbor=min(strings,key=lambda n:abs(n['midi']-note['midi']))
                    soft=np.median([np.array(f['amplitudes'][:7])/np.linalg.norm(f['amplitudes'][:7]) for f in neighbor['frames']],axis=0)
                    a=.6*a+.4*soft
                cutoff=3.2 if profile=='violin' else 4.0
                a/=np.sqrt(1+(np.arange(1,8)/cutoff)**4)
                frame['amplitudes'][:7]=(a/np.linalg.norm(a)).tolist()
        waves[name], report[name] = builder.fit(dict(notes=notes), [n['midi'] for n in notes], original, smoothness=.008)
        report[name]['rawFluidFitWave']=raw_wave
        report[name]['rawFluidTarget']=raw_report['targetHarmonics']
        report[name]['voicing']='Violin: 60% solo Violin / 40% Strings amplitudes, harmonic low-pass at H3.2. Piano/guitar: harmonic low-pass at H4. Quantization smoothness 0.008.'
        q=np.array(waves[name]); target_phase=-np.pi/2
        rotation=min(range(16),key=lambda k:abs(np.angle(np.exp(1j*(np.angle(np.fft.rfft(np.roll(q,k))[1])-target_phase)))))
        waves[name]=np.roll(q,rotation).tolist()
        report[name]['phaseRotationSteps']=rotation
        target_by_note = [np.mean([np.array(f['amplitudes'][:7])/np.linalg.norm(f['amplitudes'][:7]) for f in n['frames']],axis=0) for n in notes]
        report[name]['gridErrors'] = [dict(midi=n['midi'], before=float(np.linalg.norm(builder.spectrum(original)-t)),
                                         after=float(np.linalg.norm(builder.spectrum(waves[name])-t))) for n,t in zip(notes,target_by_note)]
        def upper_power(q):
            fft=abs(np.fft.fft(q));h=np.arange(1,16);p=(fft[h%16]*np.sinc(h/16))**2
            return float(p[3:].sum()/p.sum())
        report[name]['upperHarmonicPowerBefore']=upper_power(raw_wave)
        report[name]['upperHarmonicPowerAfter']=upper_power(waves[name])
        print(name, 'target distance', round(report[name]['originalSpectralDistance'],3), '->', round(report[name]['fittedSpectralDistance'],3))
    for profile in ['piano','guitar']:
        attack=np.array(waves[f'{profile}_attack'])
        for register in ['low','high']:
            sustain=np.array(waves[f'{profile}_{register}_sustain'])
            correlation=float(np.dot(attack,sustain)/(np.linalg.norm(attack)*np.linalg.norm(sustain)))
            report[f'{profile}_{register}_sustain']['attackCorrelation']=correlation
            assert correlation>0, f'{profile}: attack/sustain cancellation'
    return waves, report


def envelope(level, tick, mask, high, low):
    if not level: return 0
    if level < high: mask = mask*2+1
    if level < low: mask = mask*2+1
    return level - int(tick & mask == 0)


def fit_envelopes(measurements):
    targets = {}
    for profile, actual in [('piano',[49,52,54,55,59]), ('guitar',[44,47,49,50,54])]:
        data = measurements['instruments'][profile]
        times = np.array(data['envelopeTimesSeconds'])
        # Actual accompaniment notes get extra weight; keep coverage of the full grid.
        targets[profile] = (times, np.median([n['rms'] for n in data['notes'] for _ in range(4 if n['midi'] in actual else 1)],axis=0))
    tick_seconds = 512/37500
    best = None
    for high in range(6,15):
        for low in range(2,high):
            choices, total = {}, 0
            for profile in ['piano','guitar']:
                times,target = targets[profile]; selected = times < 3
                optimum = None
                for mask in [1,3,7,15]:
                    curves=[]
                    for phase in range(32):
                        values=[15]; level=15
                        for tick in range(1,round(3/tick_seconds)+2):
                            level=envelope(level,tick+phase,mask,high,low);values.append(level)
                        indices=np.minimum((times[selected]/tick_seconds).astype(int),len(values)-1)
                        curves.append(np.array(values)[indices]/15)
                    curve=np.mean(curves,axis=0)
                    error=float(np.mean((curve-target[selected])**2))
                    if optimum is None or error<optimum[0]: optimum=(error,mask)
                old_curves=[]
                for phase in range(32):
                    level=15; values=[15]
                    for tick in range(1,round(3/tick_seconds)+2):
                        if level and (level>=12 or (tick+phase)&(3 if profile=='piano' else 7)==0): level-=1
                        values.append(level)
                    old_curves.append(np.array(values)[indices]/15)
                old_error=float(np.mean((np.mean(old_curves,axis=0)-target[selected])**2))**.5
                total+=optimum[0]; choices[profile]=dict(mask=optimum[1],rmsError=optimum[0]**.5,originalRmsError=old_error)
            if best is None or total<best[0]: best=(total,high,low,choices)
    return dict(highThreshold=best[1],lowThreshold=best[2],instruments=best[3],
                method='Three piecewise linear rates: mask, 2*mask+1, 4*mask+3. Least squares over median measured 0..3 s RMS; actual score notes weighted fourfold; 32 starting tick phases.')


def firmware(waves, env):
    violin=ROOT/'ATtiny13A/Music/variants/fluid-violin'
    original=(violin/'synth.S').read_text(encoding='utf-8')
    old_vectors='''vectors:
  rjmp reset
  nop
  nop
  rjmp audio_irq
  nop
  nop
  nop
  nop
  nop
  nop'''
    new_vectors='''vectors:
  rjmp reset
envelope_return:
  clr r0
  ret
  rjmp audio_irq
envelope_gate:
  mov r17, r24
  and r17, r0
  brne envelope_gate_done
  dec r16
envelope_gate_done:
  rjmp .L198
  nop'''
    old_body='''  cpi r17, 12
  brcs .L188
  dec r16
  rjmp .L198
.L188:
  mov r17, r24
  and r17, r0
  brne .L198
  dec r16
  rjmp .L198
.L192:
  dec r16
  breq .L198
  dec r16
.L198:
  clr r0
  ret'''
    new_body=f'''  cpi r17, {env['highThreshold']}
  brcc envelope_decay
  lsl r0
  inc r0
.L188:
  cpi r17, {env['lowThreshold']}
  brcc envelope_decay
  lsl r0
  inc r0
envelope_decay:
  rjmp envelope_gate
.L192:
  dec r16
  breq .L198
  sbrc r0, 1
  dec r16
.L198:
  rjmp envelope_return'''
    assert original.count(old_vectors)==original.count(old_body)==1
    updated=original.replace(old_vectors,new_vectors).replace(old_body,new_body)
    for profile,reg,old_mask in [('piano',19,3),('guitar',20,7)]:
        before=f'  mov r16, r{reg}\n  ldi r17, {old_mask}'
        after=f'  mov r16, r{reg}\n  ldi r17, {env["instruments"][profile]["mask"]}'
        assert updated.count(before)==1; updated=updated.replace(before,after)
    percussion=json.loads((OUT/'percussion-measurements.json').read_text(encoding='utf-8'))
    previous=next(n for n in percussion['noiseCandidates'] if n['name']=='original')
    noise=next(n for n in percussion['noiseCandidates'] if n['hihatError']<previous['hihatError'] and n['snareError']<previous['snareError'])
    family,tap,direction=noise['name'].split('-');assert family=='split'
    kick=percussion['kickCandidates'][0];assert kick['name'].startswith('kick-')
    step=int(kick['name'].split('-')[1])
    old_kick='  ldi r17, 4\n  sub r17, r21\n  add r14, r17'
    new_kick=f'  ldi r17, {step}\n  nop\n  add r14, r17'
    old_noise='''  ldi r17, 29
  eor r14, r17
.L2a0:
  mov r17, r14
  lsl r17
  lsl r17
  eor r17, r14'''
    new_noise=f'''  ldi r17, {tap}
  eor r14, r17
.L2a0:
  mov r17, r14
  {'lsr' if direction=='right' else 'lsl'} r17
  sbrc r29, 0
  eor r17, r14'''
    old_hat='  cpi r21, 2\n  brcc write_pwm\n  rjmp .L298'
    new_hat='  nop\n  nop\n  rjmp .L298'
    for before,after in [(old_kick,new_kick),(old_noise,new_noise),(old_hat,new_hat)]:
        assert updated.count(before)==1;updated=updated.replace(before,after)
    updated=updated.replace('/* FluidR3: slow attack, continuous level/phase on legato, tapered release. */',
        '/* FluidR3 instruments: measured spectra and three-stage piano/guitar decay.\n * Only Timer0 overflow IRQ is enabled; unused vector slots hold envelope helpers. */')
    updated=updated.replace('blend attack to sustain over ~55 ms.', 'blend attack to sustain over ~110 ms (guitar) / ~220 ms (piano).')
    rom,patches=builder.assemble_changed_words(original,updated,(violin/'synth.bin').read_bytes(),('.L198',))
    assert len(rom)==1024
    ep=bytes((a[i]+8)|((a[i+1]+8)<<4) for a in waves.values() for i in range(0,16,2))
    assert len(ep)==64
    for filename,raw in [('synth.bin',rom),('eeprom.bin',ep)]: (OUT/filename).write_bytes(raw)
    for filename,raw in [('synth.hex',rom),('eeprom.hex',ep)]: (OUT/filename).write_text(builder.ihex(raw),encoding='utf-8',newline='\n')
    (OUT/'synth.S').write_text(updated,encoding='utf-8',newline='\n')
    for name in ['score.inc','score.json','config.inc']: shutil.copyfile(violin/name,OUT/name)
    html=(BASE/'player_template.html').read_text(encoding='utf-8').replace('/*AVR_CORE*/',(BASE/'avr_core.js').read_text(encoding='utf-8')).replace('/*FIRMWARE_HEX*/',builder.ihex(rom)).replace('/*EEPROM_HEX*/',builder.ihex(ep))
    html=html.replace('ATtiny13A — проигрыватель AVR-прошивки','ATtiny13A — тембры FluidR3')
    html=html.replace("hp.frequency.value=35;", "hp.frequency.value=35;hp.Q.value=20*Math.log10(.5);")
    html=html.replace("lp.frequency.value=9000;", "lp.frequency.value=4000;lp.Q.value=20*Math.log10(.5);")
    (OUT/'player.html').write_text(html,encoding='utf-8',newline='\n')
    report=dict(flashBytes=len(rom),eepromBytes=len(ep),flashSha256=builder.hash_bytes(rom),eepromSha256=builder.hash_bytes(ep),
                patchesFromViolin=patches,unchangedScore=True,envelopes=env,
                release='Piano: two levels per tick, guarded at zero. Guitar: one level per tick. Independent note-off unchanged.',
                percussion=dict(kick=kick,noise=noise,previousNoise=previous,hihat='Four decay stages (~110 ms) instead of two (~55 ms)'))
    (OUT/'build-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Firmware:',len(rom),'Flash,',len(ep),'EEPROM,',len(patches),'changed words')


if __name__ == '__main__':
    if '--firmware-only' in sys.argv:
        firmware(json.loads((OUT/'waveforms.json').read_text(encoding='utf-8')),json.loads((OUT/'fit-report.json').read_text(encoding='utf-8'))['envelopes'])
        sys.exit(0)
    measurements=json.loads((OUT/'measurements.json').read_text(encoding='utf-8'))
    waves, report=fit_waves(measurements)
    (OUT/'waveforms.json').write_text(json.dumps(waves,indent=2)+'\n',encoding='utf-8',newline='\n')
    env=fit_envelopes(measurements)
    (OUT/'fit-report.json').write_text(json.dumps(dict(waves=report,envelopes=env),indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Envelope fit:',json.dumps(env))
    firmware(waves,env)
