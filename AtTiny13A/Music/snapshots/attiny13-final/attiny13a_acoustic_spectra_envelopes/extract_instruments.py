#!/usr/bin/env python3
"""Extract measured spectra, envelopes and packed oscillator wavetable ROM.

Data source: short locally rendered notes from TimGM6mb.sf2 using FluidSynth.
These are sample-based instrument references, NOT raw University of Iowa recordings.
Input format: reference_INSTRUMENT_MIDI.wav in the path given by --input.
No dependency on soundfont at extraction time; optionally re-render references
using soundfont_reference.py and SOUNDFONT_PATH in the source project.

Outputs: harmonics.csv, envelopes.csv, waveform_tables.inc,
         envelope_tables.inc, tables.json, plots, wavetable_demo.wav.
"""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.optimize import minimize_scalar
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

SR_TARGET=37500
NOTES={'violin':[55,69,74], 'piano':[48,62,81], 'guitar':[43,62,69]}
STAGES=['attack','sustain']
N=16
ENVELOPE_MS=[5,15,35,70,120,200,350,500,600,665,710,800]
NOTE_OFF_MS=650
WIN={'violin':[(0.028,0.105),(0.220,0.520)],
     'piano':[(0.008,0.080),(0.220,0.460)],
     'guitar':[(0.012,0.090),(0.210,0.470)]}


def note_name(midi):
    return ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'][midi%12]+str(midi//12-1)

def load(path):
    sr,y=wavfile.read(path)
    if y.ndim==2:y=y.astype(np.float64).mean(axis=1)
    if y.dtype.kind in 'iu':y=y/float(np.iinfo(y.dtype).max)
    y=np.asarray(y,dtype=np.float64)
    y-=np.mean(y[:min(1024,len(y))])
    return sr,y

def measured_rms(sr,y,t,window=0.014):
    begin=max(0,round((t-window/2)*sr)); end=min(len(y),round((t+window/2)*sr))
    if end-begin<3:return 0.
    seg=y[begin:end]
    return float(np.sqrt(np.mean((seg-np.mean(seg))**2)))

def harmonic_amplitudes(sr,seg,freq,maxh=8):
    # Coherent projection with a Hann analysis window, robust to window size.
    time=np.arange(len(seg),dtype=np.float64)/sr
    seg=seg-np.mean(seg)
    w=np.hanning(len(seg)); weighted=seg*w
    amp=[]
    for k in range(1,maxh+1):
        # Sum spectral energy in a very small search range for detuned and
        # mildly inharmonic partials; avoid relying on a single FFT bin.
        fk=freq*k
        width=max(1.5,0.0035*fk)
        fs=fk+np.linspace(-width,width,5)
        z=np.exp((-2j*np.pi)*fs[:,None]*time[None,:])@weighted
        amp.append(2*float(np.max(np.abs(z)))/max(np.sum(w),1))
    return np.array(amp)

def estimate_frequency(sr,y,nominal):
    seg=y[round(.25*sr):round(.56*sr)]
    time=np.arange(len(seg),dtype=np.float64)/sr
    w=np.hanning(len(seg));weighted=(seg-seg.mean())*w
    # Evaluate fundamental and second harmonic: robust where the first
    # partial is not the strongest in a real instrument.
    def power(f):
        a=np.exp(-2j*np.pi*f*time)@weighted
        b=np.exp(-4j*np.pi*f*time)@weighted
        return abs(a)**2 + .25*abs(b)**2
    r=minimize_scalar(lambda f:-power(f),bounds=(nominal*.991,nominal*1.009),method='bounded',options={'xatol':.005})
    return float(r.x)

def relative_phase(sr,seg,freq,kmax=7):
    time=np.arange(len(seg))/sr
    seg=seg-seg.mean();w=np.hanning(len(seg))
    cs=np.array([np.sum(seg*w*np.exp(-2j*np.pi*freq*k*time)) for k in range(1,kmax+1)])
    # Relative harmonic phases survive arbitrary sample start times.
    phase=np.angle(cs);return phase-np.arange(1,kmax+1)*phase[0]

def reconstruct_wave(amps,relative_phases,size=N):
    # Spectral partials measured from recorded sounds, normalized for ROM.
    # No made-up harmonic coefficients; the reference phase relation is
    # held constant across the attack/sustain pair to reduce clicks.
    phase=np.arange(size)/size
    arr=np.zeros(size)
    for k,(amp,p) in enumerate(zip(amps[:7],relative_phases),start=1):
        arr+=amp*np.cos(2*np.pi*k*phase+p)
    arr-=arr.mean()
    if np.max(np.abs(arr))>0:arr*=7.0/np.max(np.abs(arr))
    q=np.rint(arr).astype(int)
    # Enforce EXACT DC=0 even after 4-bit rounding. Deterministically
    # change one or more least-expensive sample quantizations.
    while int(q.sum())!=0:
        if q.sum()>0:
            options=np.where(q>-8)[0]; candidates=options[np.argsort((q[options]-1-arr[options])**2-(q[options]-arr[options])**2)]
            q[candidates[0]]-=1
        else:
            options=np.where(q<7)[0]; candidates=options[np.argsort((q[options]+1-arr[options])**2-(q[options]-arr[options])**2)]
            q[candidates[0]]+=1
    assert int(q.sum())==0 and q.min()>=-8 and q.max()<=7
    return q

def hex_bytes(values):
    assert len(values)%2==0
    return [(int(values[i])&15)|((int(values[i+1])&15)<<4) for i in range(0,len(values),2)]

def midi_hz(note):return 440*2**((note-69)/12)

def interp_envelope(times,values,t):
    times=np.asarray(times); values=np.asarray(values)
    return np.interp(t,times,values,left=values[0],right=0)

def run(input_dir,out_dir):
    out_dir.mkdir(exist_ok=True,parents=True)
    specs={};waves={};env={};metrics={};rows=[];envrows=[]
    for instr,notes in NOTES.items():
      for band,note in enumerate(notes):
        src=input_dir/f'reference_{instr}_{note}.wav'
        if not src.exists():raise FileNotFoundError(f'Missing {src}')
        sr,y=load(src)
        if len(y)/sr < .85:raise ValueError(f'Need at least 850ms of audio for {src}')
        nominal=midi_hz(note); f0=estimate_frequency(sr,y,nominal)
        peak=max(measured_rms(sr,y,t/1000) for t in np.arange(5,645,5))
        real_env=[measured_rms(sr,y,t/1000)/max(peak,1e-10) for t in ENVELOPE_MS]
        q_env=np.rint(np.clip(np.array(real_env)*15,0,15)).astype(int)
        # Measure attack rise, slow note decay, and release independently.
        on_times=np.arange(0.005,.61,.005)
        on_rms=np.array([measured_rms(sr,y,t) for t in on_times])/max(peak,1e-10)
        reach=on_times[np.where(on_rms>=.85)[0][0]] if np.any(on_rms>=.85) else float('nan')
        def tau_fit(begin,end,anchor):
            ts=np.arange(begin,end,.01);amps=np.array([measured_rms(sr,y,t)/max(peak,1e-10) for t in ts]); ok=amps>.007
            if sum(ok)<3:return None
            fit=np.polyfit(ts[ok]-anchor,np.log(amps[ok]),1)
            return int(round(-1000/fit[0])) if fit[0]<-.02 else None
        decay_tau=tau_fit(.15,.60,.15)
        release_tau=tau_fit(.66,.82,.65)
        metrics[(instr,band)]={'midi_note':note,'note':note_name(note),'frequency_nominal_hz':nominal,
           'frequency_measured_hz':f0,'source':src.name,'peak_rms':peak,
           'attack_to_85pct_ms':round(float(reach)*1000),
           'note_decay_tau_ms':decay_tau,'release_tau_ms':release_tau}
        env[(instr,band)]={'times_ms':ENVELOPE_MS,'normalized':[round(float(x),4) for x in real_env],
          'q4':q_env.tolist(),'bytes':hex_bytes(q_env)}
        for t,r,q in zip(ENVELOPE_MS,real_env,q_env):
            envrows.append(dict(instrument=instr,register=['low','mid','high'][band],midi_note=note,time_ms=t,
              reference_rms_relative=round(float(r),5),q4=int(q)))
        att=WIN[instr][0];early=y[round(att[0]*sr):round(att[1]*sr)]
        relph=relative_phase(sr,early,f0)
        for stage,(b,e) in zip(STAGES,WIN[instr]):
            segment=y[round(b*sr):round(e*sr)]
            a=harmonic_amplitudes(sr,segment,f0,8)
            relative=a/max(a[0],1e-12)
            q_wave=reconstruct_wave(a,relph)
            # normalized amplitudes from quantized 16-sample wave (1..7)
            fft=np.abs(np.fft.rfft(q_wave.astype(float)))[1:8]
            qrelative=fft/max(fft[0],1e-12)
            allowed=relative[:7]>0.02
            mae=float(np.mean(np.abs(20*np.log10(np.maximum(relative[:7][allowed],1e-5))-
                              20*np.log10(np.maximum(qrelative[allowed],1e-5))))) if np.any(allowed) else 0.
            specs[(instr,band,stage)]={'harmonics':[round(float(x),5) for x in relative.tolist()],
                 'rms_amplitudes':[round(float(x),7) for x in a.tolist()],
                 'quantized_relative_harmonics':[round(float(x),5) for x in qrelative.tolist()],
                 'spectral_error_db_unweighted_significant':round(mae,2)}
            waves[(instr,band,stage)]={'q4signed':q_wave.tolist(),
                  'bytes':hex_bytes(q_wave+8), 'dc_sum':int(q_wave.sum())}
            for n in range(1,9):
                rows.append(dict(instrument=instr,register=['low','mid','high'][band],midi_note=note,
                stage=stage,harmonic=n,reference_amplitude_rel_h1=round(float(relative[n-1]),6),
                reference_level_db=round(float(20*np.log10(max(relative[n-1],1e-8))),2),
                table_level_db=(round(float(20*np.log10(max(qrelative[n-1],1e-8))),2) if n<=7 else ''),
                observed_f0_hz=round(f0,3)))

    # The DDS phases restart at note-on. Choose one cyclic rotation for BOTH
    # spectral stages so their initial value is as close to zero as possible.
    # This avoids an arbitrary step from PWM=128 when a new note begins.
    # A rotation leaves the measured harmonic AMPLITUDES unchanged.
    phase_rotation={}
    for instr,notes in NOTES.items():
      for band in range(3):
        early=np.asarray(waves[(instr,band,'attack')]['q4signed'])
        late=np.asarray(waves[(instr,band,'sustain')]['q4signed'])
        scores=[]
        for k in range(N):
            da=int(early[(k+1)%N])-int(early[k])
            ds=int(late[(k+1)%N])-int(late[k])
            scores.append(2*abs(early[k])+2*abs(late[k])+0.5*max(0,-da)+0.5*max(0,-ds))
        k=int(np.argmin(scores));phase_rotation[f'{instr}.{band}']=k
        for stage in STAGES:
            q=np.roll(np.asarray(waves[(instr,band,stage)]['q4signed']),-k)
            waves[(instr,band,stage)]={'q4signed':q.tolist(),'bytes':hex_bytes(q+8), 'dc_sum':int(q.sum())}
    # Multi-register collection; stage alternation, low/mid/high, 8B each.
    order=[(ins,reg,stage) for ins in ('violin','piano','guitar') for reg in range(3) for stage in STAGES]
    packed=[b for key in order for b in waves[key]['bytes']]
    assert len(packed)==3*3*2*8==144
    env_order=[(ins,reg) for ins in ('violin','piano','guitar') for reg in range(3)]
    packed_env=[b for key in env_order for b in env[key]['bytes']]
    assert len(packed_env)==54
    text=['/* Generated from sample-based acoustic instrument recordings (TimGM6mb).',
          ' * Each waveform: 16 samples, two signed 4-bit PCM values per byte.',
          ' * Decode: signed = (nibble - 8). Each wave sums to exactly zero.',
          ' * Layout: violin, piano, guitar; low, mid, high; attack, sustain.',
          ' * All 18 waveforms require 144 bytes of ATtiny13A program FLASH.',
          ' */',' .section .text','instrument_waves:']
    for k in order:
        b=waves[k]['bytes']
        text.append(' /* %-6s %-4s %-7s */'%(k[0],('low','mid','high')[k[1]],k[2]))
        text.append(' .byte '+', '.join(f'0x{x:02x}' for x in b))
    (out_dir/'waveform_tables.inc').write_text('\n'.join(text)+'\n')
    e=['/* 12 time-grid points per recorded note, 4 bits per measured RMS value.',
       ' * Time points in milliseconds: '+','.join(map(str,ENVELOPE_MS)),
       ' * Note-off was at 650 ms; values after that model release.',
       ' * 9 envelopes x 6 bytes = 54 FLASH bytes. */',
       ' .section .text','instrument_envelopes:']
    for k in env_order:
        e.append(' /* %-6s %-4s */'%(k[0],('low','mid','high')[k[1]]))
        e.append(' .byte '+', '.join(f'0x{x:02x}' for x in env[k]['bytes']))
    (out_dir/'envelope_tables.inc').write_text('\n'.join(e)+'\n')
    with (out_dir/'harmonics.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    with (out_dir/'envelopes.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=envrows[0].keys());w.writeheader();w.writerows(envrows)
    db={'source':{'dataset':'TimGM6mb sample-based SoundFont notes rendered with FluidSynth',
                'provenance':'local attiny13-refined/reference_{instrument}_{note}.wav',
                'not_raw_field_recordings':True,
                'note_off_ms':NOTE_OFF_MS,'sample_rate_original':SR_TARGET},
        'format':{'wave_samples':16,'signed_pcm_bits':4,'wave_stride_bytes':8,
                  'two_spectral_stages':['attack','sustain'],
                  'registers':['low','mid','high'],
                  'wave_packed_size_bytes':len(packed),
                  'envelope_points_ms':ENVELOPE_MS,
                  'envelope_stride_bytes':6,'envelopes_packed_size_bytes':len(packed_env),
                  'total_table_size_bytes':len(packed)+len(packed_env),
                  'waveform_order':[f'{k[0]}.{k[1]}.{k[2]}' for k in order],
                  'phase_rotation':phase_rotation},
        'spectra':{f'{k[0]}.{k[1]}.{k[2]}':v for k,v in specs.items()},
        'waves':{f'{k[0]}.{k[1]}.{k[2]}':v for k,v in waves.items()},
        'envelopes':{f'{k[0]}.{k[1]}':v for k,v in env.items()},
        'envelope_metrics':{f'{k[0]}.{k[1]}':v for k,v in metrics.items()}}
    (out_dir/'tables.json').write_text(json.dumps(db,ensure_ascii=False,indent=2)+'\n')
    return db


def graphs_and_wav(data,out):
    fig,axes=plt.subplots(3,3,figsize=(15,10),layout='constrained')
    for ir,ins in enumerate(('violin','piano','guitar')):
      for ic in range(3):
        ax=axes[ir,ic]
        for stage,color in [('attack','#e28d32'),('sustain','#1964ad')]:
          sp=data['spectra'][f'{ins}.{ic}.{stage}']
          ax.plot(range(1,9),20*np.log10(np.maximum(sp['harmonics'],1e-4)),color=color,
                  label=stage,marker='o',ms=3)
        ax.set_title(f'{ins} {data["envelope_metrics"][f"{ins}.{ic}"]["note"]}')
        ax.set_ylim(-65,22);ax.set_xticks(range(1,9));ax.grid(alpha=.25)
        if ir==2:ax.set_xlabel('Harmonic')
        if ic==0:ax.set_ylabel('dB relative to H1')
    axes[0,0].legend(loc='lower left')
    fig.suptitle('Measured acoustic-sample harmonics: attack and sustain (TimGM6mb)',fontsize=14)
    fig.savefig(out/'measured_spectra.png',dpi=140)
    plt.close(fig)

    fig,axes=plt.subplots(1,3,figsize=(15,4.2),layout='constrained')
    for ic,ins in enumerate(('violin','piano','guitar')):
      ax=axes[ic]
      for reg,c in enumerate(('#426baf','#da8640','#449466')):
        en=data['envelopes'][f'{ins}.{reg}']
        t=np.asarray(en['times_ms']);p=np.asarray(en['normalized'])
        ax.plot(t,p,'-o',color=c,label=data['envelope_metrics'][f'{ins}.{reg}']['note'],ms=4)
      ax.axvline(650,color='gray',ls='--',lw=1,label='Note off (650 ms)')
      ax.set_title(ins);ax.set_xlim(0,850);ax.set_ylim(0,1.06);ax.grid(alpha=.25)
      ax.set_xlabel('Time (ms)')
      if ic==0:ax.set_ylabel('RMS relative to note peak')
      ax.legend(loc='upper right')
    fig.suptitle('Measured amplitude envelopes, including release',fontsize=14)
    fig.savefig(out/'measured_envelopes.png',dpi=145)
    plt.close(fig)

    fig,axes=plt.subplots(3,3,figsize=(14,9),layout='constrained')
    for ir,ins in enumerate(('violin','piano','guitar')):
      for reg in range(3):
        ax=axes[ir,reg]
        for stage,c in [('attack','#df8328'),('sustain','#245fba')]:
          q=data['waves'][f'{ins}.{reg}.{stage}']['q4signed']
          ax.step(range(16),q,where='mid',label=stage,color=c)
        ax.set_xlim(0,15);ax.set_ylim(-9,9);ax.grid(alpha=.22)
        ax.set_title(f'{ins} {data["envelope_metrics"][f"{ins}.{reg}"]["note"]}')
        if ir==2:ax.set_xlabel('Phase sample')
        if reg==0:ax.set_ylabel('Signed 4-bit value')
    axes[0,0].legend(loc='lower left')
    fig.suptitle('ROM 16-step, 4-bit, zero-DC wavetable shapes',fontsize=14)
    fig.savefig(out/'packed_waveforms.png',dpi=135)
    plt.close(fig)

    # Offline sound preview of 9 independent notes (one per register), built
    # ONLY from these quantized 16-sample waves and quantized envelopes.
    # Linear table interpolation is deliberately enabled for this preview
    # so it is NOT a verified cycle-accurate ATtiny13A firmware output.
    chunks=[]
    sr=SR_TARGET
    for ins in ('violin','piano','guitar'):
      for reg in range(3):
        info=data['envelope_metrics'][f'{ins}.{reg}']
        f=info['frequency_nominal_hz']
        t=np.arange(int(.94*sr))/sr
        phase=np.mod(t*f,1)*16
        ix=np.floor(phase).astype(int);frac=phase-ix
        wave=[]
        for stage in STAGES:
            q=np.asarray(data['waves'][f'{ins}.{reg}.{stage}']['q4signed'],float)
            wave.append(q[ix]*(1-frac)+q[(ix+1)%16]*frac)
        blend=np.clip((t-.025)/.110,0,1)
        sound=(1-blend)*wave[0]+blend*wave[1]
        ev=data['envelopes'][f'{ins}.{reg}']
        rms=np.interp(t*1000,ev['times_ms'],np.array(ev['q4'],float)/15,left=0,right=0)
        output=sound*rms/9.5
        chunks.append(output)
        chunks.append(np.zeros(int(.16*sr)))
    audio=np.concatenate(chunks)
    wavfile.write(out/'packed_table_demo.wav',sr,np.int16(np.clip(audio*.80,-1,1)*32767))


def main():
    pa=argparse.ArgumentParser(description=__doc__)
    pa.add_argument('--input',type=Path,default=Path(__file__).parents[1]/'attiny13-refined')
    pa.add_argument('--output',type=Path,default=Path(__file__).parent)
    a=pa.parse_args();data=run(a.input,a.output); graphs_and_wav(data,a.output)
    print('Reference:',data['source']['dataset'])
    print('Bytes:',data['format']['wave_packed_size_bytes'],'wavetable +',data['format']['envelopes_packed_size_bytes'],'envelopes =',data['format']['total_table_size_bytes'])
    for name,m in data['envelope_metrics'].items():
        print(f'{name:12} {m["note"]:>3} attack-85% {m["attack_to_85pct_ms"]:3}ms '
              f'note decay tau {str(m["note_decay_tau_ms"]):>5}ms release tau {str(m["release_tau_ms"]):>5}ms')
    assert all(sum(d['q4signed'])==0 for d in data['waves'].values())
    print('PASSED all wavetable DC=0 checks.')

if __name__=='__main__':main()
