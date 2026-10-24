"""Alternate verified COREOPT capacity evidence with deterministic DATAOPT.

This consumes actual assembler/three-engine reports; it does not invent code
savings or edit the frozen numerical oracles. New data still needs its own
assembled/emulated qualification after fitting.
"""
from collections import Counter
import hashlib
import importlib
import importlib.util
from itertools import zip_longest
import json
from pathlib import Path
import sys
import time

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))


def load_search(pole=False):
    name = 'q3_coordinate_search_'+str(bool(pole))
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name,ROOT/'tools/probe-q3-pulsebook.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        codec = importlib.import_module('q3_pulsebook_pole' if pole else 'q3_pulsebook')
        module.render,module.validate,module.SCHEMA = codec.render,codec.validate,codec.SCHEMA
    return sys.modules[name]


search = load_search(False)


def coordinate_actions(state):
    n = len(state.frames)
    groups = [
        [('table',row,col,delta) for row in range(4) for col in range(16) for delta in (-1,1)],
        [('table_pair',row,col,delta) for row in range(4) for col in range(16) for delta in (-1,1)],
        [('pitch',i,0,delta) for i in range(n) for delta in (-2,-1,1,2)],
        [('gain',i,0,delta) for i in range(n) for delta in (-1,1)],
        [('mode',i,0,mode) for i in range(n) for mode in range(4)],
        [('coefficient_run',i,k,delta) for i in range(n) for k in range(8) for delta in (-1,1)],
        [('coefficient_frame',i,k,delta) for i in range(n) for k in range(8) for delta in (-1,1)],
        [('boundary',i,0,delta) for i in range(n-1) for delta in (-64,64)],
    ]
    # Interleave classes so a bounded sweep does not spend its entire budget
    # on only the first parameter family or only the earliest book entries.
    return [action for row in zip_longest(*groups) for action in row if action is not None]


def apply_coordinate(state, action):
    kind,index,position,value = action
    f,d,b = state.frames.copy(),state.durations.copy(),state.book.copy()
    if kind in ('table','table_pair'):
        target = int(b[index,position])+value
        if not -7 <= target <= 7:
            return None
        b[index,position] = target
        if kind == 'table_pair':
            other = (position+1)%16
            target = int(b[index,other])-value
            if not -7 <= target <= 7:
                return None
            b[index,other] = target
    elif kind == 'pitch':
        target = int(f[index,0])+value
        if not 0 <= target <= 126:
            return None
        f[index,0] = target
    elif kind == 'gain':
        target = (int(f[index,1]) & 15)+value
        if not 0 <= target <= 15:
            return None
        f[index,1] = (int(f[index,1]) & 48)|target
    elif kind == 'mode':
        f[index,1] = (int(f[index,1]) & 15)|(value << 4)
    elif kind.startswith('coefficient'):
        column,shift = 2+position//2,(position%2)*4
        target = ((int(f[index,column]) >> shift) & 15)+value
        if not 0 <= target <= 15:
            return None
        first,last = index,index+1
        if kind == 'coefficient_run':
            half = 2 if column < 4 else 4
            reference = f[index,half:half+2].copy()
            while first and np.array_equal(f[first-1,half:half+2],reference):
                first -= 1
            while last < len(f) and np.array_equal(f[last,half:half+2],reference):
                last += 1
        mask = 255 ^ (15 << shift)
        f[first:last,column] = (f[first:last,column] & mask)|(target << shift)
    elif kind == 'boundary':
        a,c = int(d[index])+value,int(d[index+1])-value
        if not 64 <= a <= 256 or not 64 <= c <= 256:
            return None
        d[index],d[index+1] = a,c
    else:
        raise ValueError('Unknown deterministic coordinate action')
    if np.array_equal(f,state.frames) and np.array_equal(d,state.durations) and np.array_equal(b,state.book):
        return None
    return type(state)(f,d,b,state.nearest,state.tilt)


def coordinate_sweep(objective,state,budget,max_evaluations=2000,*,branch='balanced'):
    """Return (greedy endpoint, non-dominated states, transparent pass report).

    Balanced accepts a strictly smaller existing target scalar. Spectrum/STOI
    branches accept a strict improvement of that coordinate; the other metric
    may worsen and is preserved explicitly in the Pareto archive. None adds an
    old baseline-quality floor. Hard arithmetic/layout guards remain mandatory.
    """
    if branch not in ('balanced','spectrum','stoi') or max_evaluations < 0 or budget < 1:
        raise ValueError('Invalid bounded coordinate-sweep configuration')
    state.score = objective.evaluate(state)
    if state.score is None or len(search.pack_stream(state.frames,state.durations)) > budget:
        raise ValueError('Coordinate starting state must pass actual core capacity and arithmetic guards')
    initial = dict(state.score)
    archive,accepted,evaluations,attempted,budget_rejections = [state],0,0,0,0
    evaluated_types,accepted_types,history = Counter(),Counter(),[]
    visited = set()
    for action in coordinate_actions(state):
        if evaluations >= max_evaluations:
            break
        attempted += 1
        candidate = apply_coordinate(state,action)
        if candidate is None:
            continue
        key = (candidate.frames.tobytes(),candidate.durations.tobytes(),candidate.book.tobytes())
        if key in visited:
            continue
        visited.add(key)
        size = len(search.pack_stream(candidate.frames,candidate.durations))
        if size > budget:
            budget_rejections += 1
            continue
        evaluations += 1
        evaluated_types[action[0]] += 1
        candidate.score = objective.evaluate(candidate)
        if candidate.score is None:
            continue
        archive = search.pareto_add(archive,candidate)
        if branch == 'balanced':
            better = objective.energy(candidate.score) < objective.energy(state.score)-1e-12
        elif branch == 'spectrum':
            better = candidate.score['spectrogram_loss'] < state.score['spectrogram_loss']-1e-12
        else:
            better = candidate.score['stoi'] > state.score['stoi']+1e-12
        if better:
            history.append(dict(evaluation=evaluations,action=list(action),before=dict(state.score),after=dict(candidate.score)))
            state = candidate
            accepted += 1
            accepted_types[action[0]] += 1
    report = dict(branch=branch,evaluations=evaluations,max_evaluations=max_evaluations,attempted=attempted,
        accepted=accepted,budget=budget,budget_rejections=budget_rejections,
        evaluated_parameter_classes=dict(evaluated_types),accepted_parameter_classes=dict(accepted_types),
        initial=initial,final=dict(state.score),pareto_points=len(archive),history=history,
        target_met=any(x.score.get('target_met',False) for x in archive),
        policy='Deterministic interleaved greedy coordinates; exact original objectives and hard guards; all tradeoffs remain explicit')
    return state,archive,report


def load_core_profile(path):
    path = Path(path)
    report = json.loads(path.read_text(encoding='utf-8'))
    if ('q3-pulsebook' not in report.get('schema','') or report.get('status') != 'verified'
            or not report.get('verification',{}).get('pass')
            or set(report['verification'].get('engines',[])) != {'reference','wasm','wasm-unoptimized'}):
        raise ValueError('COREOPT requires an actual successful three-engine assembler report')
    code,cap,eof,limit = (int(report[k]) for k in ('codeBytes','maximumStreamBytes','eofBytes','flashLimitBytes'))
    if (limit != 1024 or eof != 1 or code+cap+eof > limit or (code+cap+eof)%2
            or report.get('flashBytes',1025) > limit or report.get('eepromBytes') != 64):
        raise ValueError('COREOPT code/stream/EOF/EEPROM capacity is inconsistent')
    image = path.parent/'firmware.bin'
    if (not image.is_file() or len(image.read_bytes()) != report['flashBytes']
            or search.sha(image) != report.get('imageSha256')):
        raise ValueError('COREOPT compiled image/hash is missing or changed')
    rounding = report.get('productRounding','')
    if not (rounding == 'floor' or rounding.startswith('nearest')):
        raise ValueError('COREOPT report must identify the exact product rounding')
    return dict(code_bytes=code,stream_budget=cap,eof_bytes=eof,flash_limit=limit,eeprom_bytes=64,
        nearest=rounding.startswith('nearest'),pole='15/16' in report.get('reflectionZeroMapping',''),
        evidence_sha256=search.sha(path),image_sha256=report['imageSha256'],
        source_sha256_normalized_lf=report.get('normalizedSourceSha256',{}),
        verified_core=True,physical_hardware_tested=bool(report.get('hardwareTested')))


def memory(core,state):
    size = len(search.pack_stream(state.frames,state.durations))
    unpadded = core['code_bytes']+size+core['eof_bytes']
    return dict(code_bytes=core['code_bytes'],stream_bytes=size,eof_bytes=core['eof_bytes'],
        alignment_bytes=unpadded%2,flash_bytes=unpadded+unpadded%2,eeprom_bytes=64,
        unused_stream_bytes=core['stream_budget']-size)


def run_cycles(reference_path,models,core_reports,output,*,max_evaluations=2000,branch='balanced',previous_reports=()):
    output = Path(output)
    reference,sr = sf.read(reference_path,dtype='float64')
    if sr != 7500 or reference.ndim != 1:
        raise ValueError('Expected unchanged mono7500Hz original reference')
    previous = {}
    for path in previous_reports:
        profile = load_core_profile(path)
        previous[profile['pole'],profile['nearest']] = profile
    paths,cycles = list(map(Path,models)),[]
    for number,path in enumerate(core_reports,1):
        core = load_core_profile(path)
        module = load_search(core['pole'])
        objective = module.Objective(reference,rounded_budget=core['stream_budget'],floor_budget=core['stream_budget'])
        eligible,seed_report = [],[]
        for model_path in paths:
            model = json.loads(model_path.read_text(encoding='utf-8'))
            nearest = bool(model.get('nearest',model['schema'] == 'hq4-q3-rounded-v1'))
            if nearest != core['nearest']:
                continue
            f,d = np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16)
            # A nibble0 from the separate pole format must never be silently
            # interpreted by the ordinary Q3 decoder.
            if not core['pole'] and (np.any((f[:,2:] & 15) == 0) or np.any((f[:,2:] >> 4) == 0)):
                continue
            f,reuse = module.fit_budget(f,d,core['stream_budget'])
            state = module.State(f,d,np.asarray(model.get('pulsebook',module.legacy_tables()),np.int8),nearest,int(model.get('tilt_shift',1)))
            state.score = objective.evaluate(state)
            seed_report.append(dict(model_sha256=search.sha(model_path),coefficient_reuse=reuse,score=state.score))
            if state.score is not None:
                eligible.append(state)
        if not eligible:
            raise ValueError('No matching clean seed under the verified core profile')
        initial = min(eligible,key=lambda s:objective.energy(s.score))
        folder = output/f'cycle-{number:02d}'
        module.export_state(folder/'before',initial,objective,search.sha(reference_path))
        before_memory = memory(core,initial)
        old = previous.get((core['pole'],core['nearest']))
        started = time.perf_counter()
        final,archive,polish = coordinate_sweep(objective,initial,core['stream_budget'],max_evaluations,branch=branch)
        module.export_state(folder/'after',final,objective,search.sha(reference_path),final_metrics=True)
        for index,state in enumerate(sorted(archive,key=lambda s:s.score['stoi'])):
            module.export_state(folder/'pareto'/f'{index:02d}',state,objective,search.sha(reference_path))
        cycle = dict(cycle=number,coreopt=dict(profile=core,previous_profile=old,
            measured_bytes_freed=old['code_bytes']-core['code_bytes'] if old else None,
            before_memory=memory(old,initial) if old else None,after_memory=before_memory,
            quality_unchanged_by_core=True),dataopt=dict(**polish,before_memory=before_memory,after_memory=memory(core,final)),
            seed_screen=seed_report,elapsed_seconds=time.perf_counter()-started,
            final_candidate_avr_qualified=False,target_met=polish['target_met'])
        search.save(folder/'cycle.json',cycle)
        cycles.append(cycle)
        ordered = sorted(archive,key=lambda s:s.score['stoi'])
        selected = {max(range(len(ordered)),key=lambda i:ordered[i].score['stoi']),
            min(range(len(ordered)),key=lambda i:ordered[i].score['spectrogram_loss']),
            min(range(len(ordered)),key=lambda i:objective.energy(ordered[i].score))}
        paths += [folder/'after/model.json']+[folder/'pareto'/f'{i:02d}'/'model.json' for i in sorted(selected)]
        previous[core['pole'],core['nearest']] = core
        print(json.dumps(dict(cycle=number,code_bytes=core['code_bytes'],capacity=core['stream_budget'],
            final=polish['final'],target_met=polish['target_met'])),flush=True)
    report = dict(schema='q3-core-data-cycles-v1',reference_sha256=search.sha(reference_path),
        targets=dict(stoi=.9,spectrogram_loss=.344975554),cycles=cycles,target_met=any(c['target_met'] for c in cycles),
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for p in (Path(__file__),ROOT/'tools/probe-q3-pulsebook.py',CODEC/'q3_pulsebook.py',CODEC/'q3_pulsebook_pole.py')},
        policy='Each COREOPT is verified compiled-image capacity evidence, then bounded deterministic DATAOPT; fitted candidate needs separate AVR qualification')
    search.save(output/'report.json',report)
    return report


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--model',required=True,action='append',type=Path)
    p.add_argument('--core-report',required=True,action='append',type=Path)
    p.add_argument('--previous-core-report',action='append',type=Path,default=[])
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--max-evaluations',type=int,default=2000)
    p.add_argument('--branch',choices=('balanced','spectrum','stoi'),default='balanced')
    a = p.parse_args()
    run_cycles(a.reference,a.model,a.core_report,a.output,max_evaluations=a.max_evaluations,
        branch=a.branch,previous_reports=a.previous_core_report)


if __name__ == '__main__':
    main()
