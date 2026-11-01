"""Read-only strongest-seed selection and closed target-admission links."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path

PHASE = {'speech-default':0,'speech-screen':1,'nonspeech-default':0}
ARM = {'single-path':0,'trajectory':1}
VALUE_KEYS = ('metrics','voice','pwm_voice','noise','pwm_noise','domain_scores','score',
    'clipped_samples','voice_components','pwm_voice_components')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def normalize(path):
    return os.path.normcase(os.path.abspath(str(path)))


class Inputs:
    def __init__(self):self.pins={}
    def read(self,path,digest=None):
        path=Path(path).resolve();raw=path.read_bytes();actual=sha(raw)
        if digest is not None and digest!=actual or str(path) in self.pins and self.pins[str(path)]!=actual:
            raise ValueError('An immutable baseline/proof input changed')
        self.pins[str(path)]=actual
        return raw
    def json(self,path,digest=None):return json.loads(self.read(path,digest))
    def stream(self,meta):
        raw=self.read(meta['path'],meta['stream_sha256'])
        if len(raw)!=meta['file_bytes']:raise ValueError('Actual stream cost differs')
        return raw
    def verify(self):
        if any(sha(Path(p).read_bytes())!=d for p,d in self.pins.items()):
            raise ValueError('A baseline, target or proof changed during preparation')


def chain_key(parts):
    return tuple((p['stream_sha256'],p['file_bytes'],p['samples'],p['profile']) for p in parts)


def rank(candidate):
    value=candidate['value']
    return (value['score'],value['stream_bytes'],PHASE[candidate['phase']],
        0 if candidate['kind']=='canonical' else 1,ARM.get(candidate.get('arm'),-1),
        candidate.get('tier',0),candidate.get('job_id',-1),candidate['id'])


def strongest(candidates):
    if not candidates or len({c['context'] for c in candidates})!=1:
        raise ValueError('Only one exact source/profile/level context may compete')
    if any(not c['value']['automatic_quality_eligible'] or not math.isfinite(c['value']['score']) for c in candidates):
        raise ValueError('An ineligible/nonfinite candidate entered baseline ranking')
    return min(candidates,key=rank)


def successful_row(row,n):
    if not row.get('passed') or row.get('flash_bytes',32769)>32768 or not row.get('verification',{}).get('passed'):
        return False
    report=row['report']
    return (all(report[name]==n for name in ('produced','played','timer_ticks','timer_events'))
        and all(report[name]==0 for name in ('underruns','decoder_error','observer_errors','observer_exit_code','queued_at_stop'))
        and all(report[name]==1 for name in ('eof','stopped','timer_started'))
        and report['stack_margin_all_bytes']>0)


def admission_registry(inputs,rom_handoff,rom_proof,spi_handoff,spi_proof):
    registry=defaultdict(list)
    raw=inputs.read(rom_handoff);handoff=json.loads(raw);proof=inputs.json(rom_proof)
    if proof['status']!='complete' or proof['handoff_sha256']!=sha(raw) or len(proof['rows'])!=374:
        raise ValueError('The closed matched-search ROM campaign is incomplete')
    indexed={(r['chain'],r['extra_irq_cycles']):r for r in proof['rows']}
    for item in handoff['chains']:
        entry=item['entry']
        rows=[indexed[item['id'],irq] for irq in (0,100)]
        if all(successful_row(row,entry['samples']) for row in rows):
            hashes=[p['stream_sha256'] for p in entry['segments']]
            if any(row['stream_sha256']!=hashes or not row['physical_pwm_exact']
                    or not row['verification']['cost']['complete_image']
                    or not row['verification']['cost']['embedded_streams_exact'] for row in rows):
                raise ValueError('An admitted ROM row lost exact-byte evidence')
            registry[chain_key(entry['segments'])].append(dict(kind='ROM',chain_id=item['id'],
                handoff_path=str(Path(rom_handoff).resolve()),proof_path=str(Path(rom_proof).resolve()),irqs=[0,100]))
    raw=inputs.read(spi_handoff);handoff=json.loads(raw);proof=inputs.json(spi_proof)
    if proof['status']!='complete' or proof['handoff_sha256']!=sha(raw) or len(proof['rows'])!=28:
        raise ValueError('The closed 28-row external-SPI campaign is incomplete')
    case_path=Path(handoff['cases_path'])
    expected={normalize(p):d for p,d in handoff['input_files_sha256'].items()}.get(normalize(case_path))
    if expected is None:raise ValueError('SPI cases are not bound by their campaign')
    cases=inputs.json(case_path,expected)
    for chain in cases['chains']:
        rows=[r for r in proof['rows'] if r['chain_id']==chain['id'] and r['storage']=='spi' and r['assembly']]
        if len(rows)==2 and {r['extra_irq_cycles'] for r in rows}=={0,100} and all(successful_row(r,chain['samples']) for r in rows):
            if any(not r['verification']['cost']['complete_image'] or not r['verification']['cost']['external_streams_exact']
                    or r['verification']['expected_pwm_sha256']!=chain['expected_pwm_sha256'] for r in rows):
                raise ValueError('An admitted SPI row lost complete external-data evidence')
            registry[chain_key(chain['segments'])].append(dict(kind='SPI',chain_id=chain['id'],
                cases_path=str(case_path),handoff_path=str(Path(spi_handoff).resolve()),proof_path=str(Path(spi_proof).resolve()),irqs=[0,100]))
    return dict(registry)


def load_current(inputs,study,registry):
    export=study/'export-v1';closed=inputs.json(export/'binding-private.json')
    hashes={normalize(p):d for p,d in closed['inputs_sha256'].items()}
    def bound(path):
        digest=hashes.get(normalize(path))
        if digest is None:raise ValueError('An authoritative producer receipt is not closed')
        return inputs.json(path,digest)
    summary=inputs.json(export/'summary.json')
    if summary['status']!='PASS' or summary['arm_records']!=248 or summary['helper_calls']!=312 or summary['cap_views']!=744:
        raise ValueError('The complete admitted matched-CPU study is required')
    old=bound(study/'baselines-v1/binding-private.json')
    bases={b['id']:b for b in old['baselines']}
    if len(bases)!=104:raise ValueError('The 104 canonical contexts changed')
    options={}
    for identifier,base in bases.items():
        options[identifier]=[dict(kind='canonical',context=(base['nonspeech'],base['source_ordinal'],base['profile'],base['mode']),
            phase=base['source_phase'],id=base['canonical_whole_candidate_id'],value=base['canonical_whole_value'],
            segments=base['segments'],source_result_path=base['source_result_path'])]
    all_rows=[]
    for shard in (0,1):
        folder=study/('replay-v1-shard-%d'%shard)
        attempt=bound(folder/'attempt-private.json');receipt=bound(folder/'summary.json')
        rows=bound(folder/'results-private.json')
        if (attempt['status']!='complete' or receipt['status']!='PASS' or receipt['new_initial_fits']
                or attempt['forbidden_fit_or_build_attempts'] or any(e['status']!='complete' for e in attempt['helper_calls'])):
            raise ValueError('A matched-CPU worker is not complete')
        for row in rows:
            base=bases[row['baseline_id']]
            identifier=next(d['selected_id'] for d in row['decisions'] if d['percent']==100)
            if identifier is None:raise ValueError('A prior current100 selection is missing')
            value=row['whole_rows'][identifier];decision=next(d for d in row['decisions'] if d['percent']==100)
            if not value['automatic_quality_eligible'] or value['stream_bytes']>decision['cap']:
                raise ValueError('A matched-CPU100 winner is not admitted numerically')
            parts=row['whole_chains'][identifier]['segments']
            candidate=dict(kind='matched-cpu',context=(not row['speech'],row['source_ordinal'],row['profile'],row['mode']),
                phase=row['phase'],arm=row['arm'],tier=row['cpu_seconds_per_reset'],job_id=row['id'],id=identifier,
                value=value,segments=parts,source_result_path=str(folder/'arms'/('job-%03d'%row['id'])/'result-private.json'))
            # The canonical member is retained regardless of whether this old
            # campaign needed to schedule its unchanged playback explicitly.
            is_canonical=chain_key(parts)==chain_key(base['segments'])
            if not is_canonical and chain_key(parts) not in registry:
                raise ValueError('A matched-CPU100 winner has no exact positive target admission')
            options[base['id']].append(candidate)
        all_rows.extend(rows)
    if len(all_rows)!=248 or len({r['id'] for r in all_rows})!=248:
        raise ValueError('The complete prior arm population differs')
    result=[]
    for identifier,base in bases.items():
        winner=strongest(options[identifier]);parts=winner['segments']
        # Reopen the winning leaf, but do not reread unused raw candidate pools.
        bound(Path(winner['source_result_path']))
        position=0
        for index,part in enumerate(parts):
            blob=inputs.stream(part)
            if (part['index']!=index or part['start']!=position or part['profile']!=base['profile']
                    or len(blob)<22 or blob[:4]!=b'L4HY' or blob[4]!=5 or blob[5]&127!=base['profile']
                    or int.from_bytes(blob[8:12],'little')!=part['samples']
                    or len(blob)!=22+int.from_bytes(blob[20:22],'little')):
                raise ValueError('The strongest actual ordered v5 bytes/geometry differ')
            position+=part['samples']
        actual=sum(p['file_bytes'] for p in parts)
        if position!=base['samples'] or actual!=winner['value']['stream_bytes']:
            raise ValueError('The common strongest whole length/byte cost differs')
        result.append(dict(**{k:v for k,v in base.items() if k not in ('segments','stream_bytes','canonical_whole_value','source_phase','source_result_path','canonical_whole_candidate_id')},
            segments=parts,stream_bytes=actual,source_choice={k:v for k,v in winner.items() if k not in ('segments','value','context')},
            stored_expected_whole_value=winner['value'],canonical_rollback_segments=base['segments'],
            canonical_rollback_bytes=base['stream_bytes'],target_admission_links=registry.get(chain_key(parts),[]),
            fresh_whole_metric_check_pending=True))
    return result


def pilot_ids(bases):
    sources={}
    for b in bases:
        if b['profile']==4:sources[(b['nonspeech'],b['source_ordinal'])]=b
    eligible=sorted([b for b in sources.values() if not b['nonspeech'] and b['split']=='tuning'
        and b['mode']=='preserve' and len(b['segments'])==1 and b['samples']>=8000],key=lambda b:(b['samples'],b['source_ordinal']))
    quiet=sorted([b for b in sources.values() if not b['nonspeech'] and b['mode']=='auto-quiet'],key=lambda b:b['source_ordinal'])
    multi=sorted([b for b in sources.values() if not b['nonspeech'] and len(b['segments'])>1],key=lambda b:(-len(b['segments']),-b['samples'],b['source_ordinal']))
    ns=sorted([b for b in sources.values() if b['nonspeech']],key=lambda b:(b['samples'],b['source_ordinal']))
    selected=[eligible[0],eligible[len(eligible)//2],quiet[0],multi[0],*ns[:2]]
    contexts={(b['nonspeech'],b['source_ordinal']) for b in selected}
    if len(contexts)!=6:raise ValueError('Pilot metadata strata overlap unexpectedly')
    return [b['id'] for b in bases if (b['nonspeech'],b['source_ordinal']) in contexts]
