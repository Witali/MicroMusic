"""Shared stdlib-only bindings, artifact checks and anonymous report schema."""
from __future__ import annotations
from array import array
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path.insert(0,str(HERE))
import build as builder

SAMPLES=160000
RATE=8000
LABELS={'baseline':'baseline','raw_candidate':'raw','selected_output':'selected'}
QUALITY_SCALARS=('pcm_sse','pwm_sse','clipped')
QUALITY_PAIRS=('stoi','voice','noise','fullband_error','fullband_temporal_error','pitch_within','pitch_collapsed','period','shape')
QUALITY_BOOLS=('stable','level_safe','spectrum_safe')
CHANGE_KEYS=('spectral_frames','spectral_indices','scales','lags','gains','pulse_positions','pulse_amplitudes','extras','pre','brightness')
BIT_KEYS=('header','spectral_repeat_flags','spectral_mode_tags','absolute_rice','delta_rice','scale','gain','lag','main_pulses',
          'extra_presence','extra_symbols','padding','spectral_total','repeated_frames','absolute_frames','delta_frames',
          'rice_escapes','zero_gain_blocks','active_extras','total')
GRID_KEYS=('odd_rank_residual_fields_all_frames','odd_rank_residual_fields_updated_frames','updated_frames','held_frames')
STAGE_KEYS=('enabled','eligible','attempted','search_calls','status','error','policy_budget_C','baseline_bytes_B0',
 'raw_bytes','selected_bytes','raw_valid','raw_changed','selected','search_candidates','search_selected','parameter_trials',
 'pulse_trials','selection_candidates','selection_accepted','selection_error','selection_octave_rejected','initial_objective','final_objective')


def sha(path):return builder.sha(path)
def digest(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return builder.encoded(value)
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path,value,immutable=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);data=encoded(value)
    if immutable and path.exists():
        if path.read_bytes()!=data:raise ValueError('Immutable record already exists with different content')
        return
    pending=path.with_name(path.name+'.'+uuid.uuid4().hex+'.partial');pending.write_bytes(data)
    try:
        if immutable:
            if os.name=='nt':os.rename(pending,path)
            else:os.link(pending,path)
        else:pending.replace(path)
    finally:pending.unlink(missing_ok=True)


def private(path):
    path=Path(path).resolve();path.relative_to((ROOT/'build').resolve())
    if path==(ROOT/'build').resolve():raise ValueError('Use a dedicated ignored output folder')
    return path


def checked(root,relative,expected):
    path=(Path(root)/relative).resolve();path.relative_to(Path(root).resolve())
    if sha(path)!=expected:raise ValueError('Bound file digest mismatch')
    return path


def finite(value):return type(value) in (int,float) and math.isfinite(value)


class Reader:
    def __init__(self,data,at):self.data=data;self.at=at
    def get(self,width):
        if self.at+width>len(self.data)*8:raise ValueError('Truncated packet')
        value=0
        for bit in range(width):value|=((self.data[self.at//8]>>(self.at%8))&1)<<bit;self.at+=1
        return value
    def rice(self,k,width):
        q=0
        while q<8 and not self.get(1):q+=1
        return self.get(width) if q==8 else (q<<k)|self.get(k)


def packet(data):
    if len(data)<17 or data[:2]!=b'L9' or not data[2]&64 or data[2]&63!=4:raise ValueError('Expected one P4 Long file')
    u=lambda at,width:int.from_bytes(data[at:at+width],'little')
    n=u(5,4);rate=u(3,2);pre=u(9,2);bright=u(11,2)
    if n!=SAMPLES or rate!=RATE or pre>16384 or bright>11469 or u(13,4)!=len(data)-17:
        raise ValueError('Long geometry or payload mismatch')
    bits={key:0 for key in BIT_KEYS};bits['header']=136;r=Reader(data,136);previous=None
    for frame in range((n+319)//320):
        bits['spectral_repeat_flags']+=1
        if r.get(1):
            bits['spectral_mode_tags']+=1;delta=r.get(1)
            if delta and previous is None:raise ValueError('Initial temporal spectrum')
            bits['delta_frames' if delta else 'absolute_frames']+=1;vector=[]
            for k in range(10):
                start=r.at;q=0
                while q<8 and not r.get(1):q+=1
                if q==8:z=r.get(5+delta);bits['rice_escapes']+=1
                else:z=(q<<(1-delta))|r.get(1-delta)
                bits['delta_rice' if delta else 'absolute_rice']+=r.at-start
                value=previous[k]+(z//2 if not z&1 else -(z//2)-1) if delta else (vector[-1]+1 if vector else 0)+z
                if not 0<=value<32 or vector and value<=vector[-1]:raise ValueError('Invalid wire spectrum')
                vector.append(value)
            previous=vector
        else:
            if previous is None:raise ValueError('Initial spectrum repeat')
            bits['repeated_frames']+=1
        for half in range(2):
            at=frame*320+half*160
            if at>=n:break
            r.get(5);bits['scale']+=5;gain=r.get(3);bits['gain']+=3
            if gain:r.get(7);bits['lag']+=7
            else:bits['zero_gain_blocks']+=1
            for group in range(4):
                if at+group*40>=n:break
                r.get(10);bits['main_pulses']+=10
                if data[2]&128:
                    bits['extra_presence']+=1
                    if r.get(1):
                        position=r.get(6);r.get(4)
                        if position>=40:raise ValueError('Invalid extra pulse position')
                        bits['extra_symbols']+=10;bits['active_extras']+=1
    bits['padding']=len(data)*8-r.at
    if not 0<=bits['padding']<=7:raise ValueError('Unexpected final packet padding')
    while r.at<len(data)*8:
        if r.get(1):raise ValueError('Nonzero final padding')
    bits['spectral_total']=sum(bits[k] for k in ('spectral_repeat_flags','spectral_mode_tags','absolute_rice','delta_rice'))
    bits['total']=len(data)*8
    if sum(bits[k] for k in ('header','spectral_repeat_flags','spectral_mode_tags','absolute_rice','delta_rice',
        'scale','gain','lag','main_pulses','extra_presence','extra_symbols','padding'))!=bits['total']:
        raise ValueError('Independent bit accounting mismatch')
    return dict(samples=n,rate=rate,pre=pre,bright=bright,header_bytes=17,payload_bytes=len(data)-17),bits


def model(path,header,accuracy):
    lines=Path(path).read_text(encoding='ascii').splitlines()
    if not lines or len(lines[0].split())!=6:raise ValueError('Wrong study host-model schema')
    values=[int(x) for x in ' '.join(lines).split()];n,profile,pre,bright,stored_accuracy,target=values[:6]
    frames=(n+319)//320;expected=6+frames*10+frames*2*3+frames*16*2+frames*8*2
    if (len(values)!=expected or n!=SAMPLES or profile!=4 or pre!=header['pre'] or bright!=header['bright']
            or stored_accuracy!=accuracy or stored_accuracy not in (3,4) or target!=1):raise ValueError('Host model/header/policy mismatch')
    at=6
    for _ in range(frames):
        row=values[at:at+10];at+=10
        if any(not 0<=v<32 for v in row) or any(a>=b for a,b in zip(row,row[1:])):raise ValueError('Invalid host spectrum')
    for _ in range(frames*2):
        scale,lag,gain=values[at:at+3];at+=3
        if not 0<=scale<32 or not 18<=lag<=145 or gain not in range(0,15,2):raise ValueError('Invalid host metadata')
    for _ in range(frames*16):
        pos,amp=values[at:at+2];at+=2
        if not 0<=pos<20 or (pos+3)%5==0 or amp not in (-8,8):raise ValueError('Invalid P4 innovation')
    for _ in range(frames*8):
        pos,amp=values[at:at+2];at+=2
        if not -8<=amp<=7 or amp and not 0<=pos<40:raise ValueError('Invalid host extra')


def pcm(path):
    data=Path(path).read_bytes()
    if len(data)!=SAMPLES*2:raise ValueError('Wrong complete PCM length')
    values=array('h');values.frombytes(data)
    if sys.byteorder!='little':values.byteswap()
    return values


def quality_copy(value):
    result={}
    for key in QUALITY_SCALARS:
        if not finite(value[key]) or value[key]<0:raise ValueError('Invalid waveform error/count')
        result[key]=value[key]
    for key in QUALITY_PAIRS:
        row=value[key]
        if not isinstance(row,list) or len(row)!=2 or any(x is not None and not finite(x) for x in row):
            raise ValueError('Invalid two-path diagnostic')
        result[key]=list(row)
    for key in QUALITY_BOOLS:
        if type(value[key]) is not bool:raise ValueError('Invalid safety diagnostic')
        result[key]=value[key]
    return result


def output_copy(value):
    keys=('bytes','header_bytes','long_header','declared_samples','declared_payload_bytes','host_accuracy',
          'produced_samples','native_model_exact','native_pcm_exact','native_pwm_exact','native_eof_exact')
    result={k:value[k] for k in keys}
    result['bits']={k:value['bits'][k] for k in BIT_KEYS}
    result['grid']={k:value['grid'][k] for k in GRID_KEYS};result['quality']=quality_copy(value['quality'])
    return result


def public_report(value):
    keys=('samples','rate','quality_target','active_paths','calls','global_error','policy_budget_C','baseline_byte_ceiling_B0',
          'baseline_component_seconds','baseline_component_cpu_seconds','optional_component_seconds','optional_component_cpu_seconds',
          'automatic_api_seconds','legacy_cap','legacy_selected','legacy_candidates','legacy_stages','baseline_optional_search_calls',
          'raw_available','raw_changed','selected_changed','research_retention_guard_raw','research_retention_guard_selected',
          'production_pitch_guard_raw','production_pitch_guard_selected','selector_replay_exact')
    result={k:value[k] for k in keys};result['stage']={k:value['stage'][k] for k in STAGE_KEYS}
    for label in LABELS:result[label]=output_copy(value[label])
    for label in ('raw_changes','selected_changes'):result[label]={k:value[label][k] for k in CHANGE_KEYS}
    return result


def check_artifacts(report,source,prefix):
    if (report['schema']!='lpx-audiobook-p3-components-v1' or report['model_schema']!='lpx-audiobook-host-model-v1'
            or report['samples']!=SAMPLES or report['rate']!=RATE or report['quality_target']!='pwm'
            or report['active_paths']!=['pcm','pwm'] or report['calls']!=4 or report['global_error']
            or report['baseline_optional_search_calls']!=0 or not report['selector_replay_exact']
            or report['automatic_api_seconds'] is not None):raise ValueError('Unexpected composed benchmark contract')
    for key in ('baseline_component_seconds','baseline_component_cpu_seconds','optional_component_seconds','optional_component_cpu_seconds'):
        if not finite(report[key]) or report[key]<0:raise ValueError('Invalid component timing')
    reference=pcm(source);reference_energy=sum(x*x for x in reference);outputs={};artifacts={}
    base_blob=Path(str(prefix)+'-baseline.lpx').read_bytes();B0=len(base_blob)
    if report['baseline_byte_ceiling_B0']!=B0 or report['stage']['baseline_bytes_B0']!=B0 or report['policy_budget_C']<B0:
        raise ValueError('Actual baseline ceiling differs from report')
    for label,suffix in LABELS.items():
        stem=Path(str(prefix)+'-'+suffix);blob=Path(str(stem)+'.lpx').read_bytes();header,bits=packet(blob);row=report[label]
        if (row['bytes']!=len(blob) or row['header_bytes']!=17 or not row['long_header']
                or row['declared_samples']!=SAMPLES or row['produced_samples']!=SAMPLES
                or row['declared_payload_bytes']!=header['payload_bytes'] or row['bits']!=bits
                or not all(row[k] is True for k in ('native_model_exact','native_pcm_exact','native_pwm_exact','native_eof_exact'))):
            raise ValueError('Output metadata/native/bit count mismatch')
        values=pcm(str(stem)+'.pcm');model(str(stem)+'.model',header,row['host_accuracy'])
        error=0;pwm_error=0;clips=0;pwm_rails=0
        for expected,actual in zip(reference,values):
            error+=(actual-expected)**2;clips+=actual<=-32768 or actual>=32767
            q14=(actual+1)//2;duty=max(0,min(255,128+((q14*130+8192)>>14)))
            pwm_error+=((duty-128)*256-expected)**2;pwm_rails+=duty in (0,255)
        if (row['quality']['pcm_sse']!=error or row['quality']['pwm_sse']!=pwm_error or row['quality']['clipped']!=clips):
            raise ValueError('Stored output error/count labels differ from actual PCM/PWM')
        quality_copy(row['quality'])
        outputs[label]=dict(reference_energy=reference_energy,pcm_sse=error,pwm_sse=pwm_error,
                           pcm_clipped=clips,pwm_rail_samples=pwm_rails)
        for extension in ('.lpx','.pcm','.model'):
            path=Path(str(stem)+extension);artifacts[path.name]=sha(path)
    raw=Path(str(prefix)+'-raw.lpx').read_bytes();selected=Path(str(prefix)+'-selected.lpx').read_bytes()
    if (report['raw_changed']!=(raw!=base_blob) or report['selected_changed']!=(selected!=base_blob)
            or len(selected)>B0 or report['stage']['selected_bytes']!=len(selected)
            or report['selected_output']['host_accuracy']!=(4 if selected!=base_blob else 3)
            or report['baseline']['host_accuracy']!=3):raise ValueError('Changed/selected/B0 policy labels differ')
    if not report['raw_available'] and raw!=base_blob:raise ValueError('Unavailable raw is not explicit baseline fallback')
    if report['raw_available'] and (len(raw)>B0 or report['raw_candidate']['host_accuracy']!=4):raise ValueError('Invalid raw proposal')
    if report['stage']['error'] and selected!=base_blob:raise ValueError('Failed optional stage displaced successful baseline')
    if not report['stage']['error'] and report['stage']['search_calls']!=1:raise ValueError('Wrong optional search count')
    return artifacts,outputs


def check_verification(value,report):
    if (value['schema']!='lpx-audiobook-p3-verify-v1' or value['model_schema']!='lpx-audiobook-host-model-v1'
            or value['passed'] is not True or value['no_encoding_or_search'] is not True
            or value['samples']!=SAMPLES or value['rate']!=RATE or value['quality_target']!='pwm'
            or not value['selector_replay_exact']):raise ValueError('Read-only native verification failed')
    for label,suffix in LABELS.items():
        if value[label]!=report[label]:raise ValueError('Replayed output metrics differ')
        meta=value['outputs'][suffix]
        if (meta['produced_samples']!=SAMPLES or meta['declared_samples']!=SAMPLES or meta['header_bytes']!=17
                or not all(meta[k] is True for k in ('native_pcm_exact','native_pwm_exact','native_eof_exact'))):
            raise ValueError('Read-only native EOF/count metadata differs')
    for key in ('raw_changed','selected_changed','selector_replay_exact','research_retention_guard_raw','research_retention_guard_selected',
                'production_pitch_guard_raw','production_pitch_guard_selected','raw_changes','selected_changes'):
        if value[key]!=report[key]:raise ValueError('Replayed selection/diagnostic labels differ')


def aggregate(rows,expected):
    valid=[r for r in rows if r['status']=='PASS'];complete=len(valid)==expected
    result=dict(expected_cases=expected,completed_cases=len(valid),failed_cases=sum(r['status']!='PASS' for r in rows),
        not_completed_cases=expected-len(rows),complete=complete,raw_available_cases=sum(r['report']['raw_available'] for r in valid),
        selected_changes=sum(r['report']['selected_changed'] for r in valid),
        optional_errors=sum(r['report']['stage']['error']!=0 for r in valid))
    variants={}
    for label in LABELS:
        paths=[]
        for path in (0,1):
            eligible=[r for r in valid if r['stoi_eligible'][path]]
            values=[r['report'][label]['quality']['stoi'][path] for r in eligible]
            missing=sum(not finite(v) for v in values)
            power=sum(r['waveform'][label]['reference_energy'] for r in valid)
            error=sum(r['waveform'][label]['pcm_sse' if path==0 else 'pwm_sse'] for r in valid)
            paths.append(dict(reference_energy=power,error_energy=error,
                summed_energy_ser_db=10*math.log10(power/error) if complete and power and error else None,
                baseline_eligible_stoi_cases=len(eligible),missing_eligible_stoi_cases=missing,
                baseline_unassessed_stoi_cases=len(valid)-len(eligible),
                mean_stoi=sum(values)/len(values) if complete and values and not missing else None))
        variants[label]=dict(bytes=sum(r['report'][label]['bytes'] for r in valid),paths=paths)
    result['outputs']=variants
    for key in ('baseline_component_seconds','baseline_component_cpu_seconds','optional_component_seconds','optional_component_cpu_seconds'):
        result[key]=sum(r['report'][key] for r in valid)
    result['case_subprocess_wall_seconds']=sum(r['subprocess_wall_seconds'] for r in valid)
    result['read_only_verification_wall_seconds']=sum(r['verification_wall_seconds'] for r in valid)
    return result
