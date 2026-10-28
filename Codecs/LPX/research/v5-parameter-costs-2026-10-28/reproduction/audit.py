"""Independent cost audit using an indexed cursor and existing BitWriter; no new format."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import runpy
import sys
import time

ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))
import speech_compact as compact
from lpx4 import BitWriter
from speech_parameter_costs import METHODS
from speech_parameter_histograms import FIELDS,parameter_codes
from measure_speech_firmware import checked_output
from output_paths import protect_outputs

sha=lambda b:hashlib.sha256(b).hexdigest()
canonical=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def load(path):return json.loads(Path(path).read_text())


class IndexedCursor:
    def __init__(self,data):self.data=data;self.at=0
    def get(self,width):
        if width<0 or self.at+width>len(self.data)*8:raise ValueError('Indexed cursor outside payload')
        byte=self.at//8;offset=self.at%8;count=(offset+width+7)//8
        value=(int.from_bytes(self.data[byte:byte+count],'little')>>offset)&((1<<width)-1)
        self.at+=width;return value


def inspect(blob):
    values=compact.unpack(blob);n,profile,spectra,params,*_=values
    reader=IndexedCursor(blob[22:]);old=None;coded=[];markers=extras=0
    for fi,expected in enumerate(spectra):
        actual=compact.get_spectrum(reader,old,5 if profile==4 else 6)
        if actual!=expected:raise AssertionError('Independent indexed spectrum mismatch')
        old=actual
        for half in range(2):
            coded.append((reader.get(5),reader.get(7),reader.get(3)))
            for _ in range(4):
                reader.get(10 if profile==4 else 17)
                if blob[5]&128:
                    markers+=1
                    if reader.get(1):reader.get(10);extras+=10
    bits=reader.at;pad=(len(blob)-22)*8-bits
    if not 0<=pad<8 or reader.get(pad)!=0 or coded!=parameter_codes(params):raise AssertionError('Indexed parameter/padding mismatch')
    return {'values':values,'coded':coded,'payload':bits,'padding':pad,'markers':markers,'extras':extras}


def parameter_writer(coded,method):
    writer=BitWriter();escapes={name:0 for name,_ in FIELDS}
    for value,(_,width) in zip(coded[0],FIELDS):writer.put(value,width)
    for old,new in zip(coded,coded[1:]):
        for i,(_,width) in enumerate(FIELDS):
            value=new[i]
            if not method.mask&(1<<i):writer.put(value,width)
            elif method.kind=='repeat':
                changed=value!=old[i];writer.put(int(changed),1)
                if changed:writer.put(value,width)
            else:
                delta=value-old[i];z=2*delta if delta>=0 else -2*delta-1
                if z>>method.k<8:compact.putrice(writer,z,method.k,width+1)
                else:writer.put(0,8);writer.put(value,width);escapes[FIELDS[i][0]]+=1
    return writer.total,escapes


def audit(study,driver,output):
    study=checked_output(study);output=checked_output(output);started=time.perf_counter();self_hash=sha(Path(__file__).read_bytes())
    private=load(study/'results-private.json');summary=load(study/'summary.json');runtime=load(study/'source-runtime.json')
    rows=load(study/'rows.json')['rows'];hist=load(study/'histograms.json')['groups'];nomination=load(study/'nomination.json');lock=load(study/'nomination-lock-private.json')
    if private['status']!=summary['status'] or summary['status']!='complete' or len(rows)!=5980 or len(private['records'])!=460:
        raise ValueError('Expected complete460source-profile study')
    module=runpy.run_path(str(driver),run_name='parameter_study_audit');binding=module['source_binding']()
    if any(runtime[k]!=v for k,v in binding.items()) or private['source_binding_sha256']!=sha(canonical(binding)):
        raise ValueError('Current source/runtime differs from measured study')
    if runtime['measurement_driver_sha256']!=sha(Path(driver).read_bytes()):raise ValueError('Measured driver changed')
    for path,digest in {**private['input_manifests_sha256'],**private['stream_files_sha256']}.items():
        if sha(Path(path).read_bytes())!=digest:raise ValueError('Frozen input changed')
    if lock['heldout_or_nonspeech_costs_processed']!=0 or lock['nomination']!=nomination or module['nominate'](rows)!=nomination:
        raise AssertionError('Nomination differs from frozen tuning-only selection')
    lookup=defaultdict(list)
    for row in rows:lookup[row['id']].append(row)
    if len(lookup)!=460:raise AssertionError('Missing source/profile group')
    protect_outputs([Path(driver),Path(__file__),*[study/name for name in ('results-private.json','summary.json','rows.json','histograms.json','nomination.json','nomination-lock-private.json','source-runtime.json')]], [output/'audit.json'])
    cache={};hist_input=defaultdict(list);canonical_count=noncanonical_count=parameter_checks=segment_cost_checks=0
    family_counts=Counter();sources_by_id={}
    for ordinal,record in enumerate(private['records'],1):
        public=lookup[record['id']]
        if len(public)!=13 or {r['method']['selector'] for r in public}!=set(range(1,14)):raise AssertionError('Missing hypothetical method')
        header=public[0];family_counts[header['family']]+=1
        if record['family']!=header['family']:raise AssertionError('Source family changed')
        if ordinal<=80 and (header['family'] not in ('baseline-v2','expanded100') or header['split']!='tuning'):
            raise AssertionError('Heldout/robustness cost was processed before nomination lock')
        blobs=[];details=[]
        for entry in record['streams']:
            blob=Path(entry['path']).read_bytes();digest=sha(blob)
            if digest!=entry['sha256']:raise ValueError('Recorded source bytes changed')
            if digest not in cache:
                info=inspect(blob);cache[digest]=info
                normalized,meta=compact.pack(*info['values'][:7],extras=info['values'][7],force_extras=bool(blob[5]&128))
                if normalized==blob:
                    if meta['payload_bits']!=info['payload']:raise AssertionError('Actual source cursor differs from existing serializer')
                    canonical_count+=1
                else:noncanonical_count+=1
            blobs.append(blob);details.append(cache[digest])
        sources_by_id[record['id']]=blobs
        group=(header['family'],header['split'],header['cohort'],header['profile']);hist_input[group].extend(details)
        if sum(v['values'][0] for v in details)!=header['samples']:raise AssertionError('Complete source length changed')
        for row in public:
            method=METHODS[row['method']['selector']-1]
            if row['method']!=module['asdict'](method) or len(row['segment_costs'])!=len(blobs):raise AssertionError('Method/segment geometry changed')
            total=fallback=0;escape_counts=Counter()
            for blob,info,cost in zip(blobs,details,row['segment_costs']):
                params,escapes=parameter_writer(info['coded'],method);escape_counts.update(escapes);parameter_checks+=1
                payload=info['payload']-15*len(info['coded'])+params;pad=(-payload)%8;size=23+(payload+pad)//8
                expected={'current_file_bytes':len(blob),'current_payload_bits':info['payload'],'current_parameter_bits':15*len(info['coded']),
                    'current_padding_bits':info['padding'],'source_extras_flag':bool(blob[5]&128),'source_extra_marker_bits':info['markers'],
                    'source_extra_value_bits':info['extras'],'untouched_payload_bits':info['payload']-15*len(info['coded']),
                    'proposed_header_bytes':23,'additional_selector_bytes':1,'proposed_parameter_bits':params,'proposed_payload_bits':payload,
                    'proposed_padding_bits':pad,'proposed_file_bytes':size,'whole_stream_saved_bytes':len(blob)-size}
                if any(cost[k]!=v for k,v in expected.items()):raise AssertionError('Independent complete stored cost mismatch')
                total+=size;fallback+=max(0,len(blob)-size);segment_cost_checks+=1
            old=sum(map(len,blobs))
            if row['current_file_bytes']!=old or row['proposed_file_bytes']!=total or row['whole_stream_saved_bytes']!=old-total or row['fallback_data_only_upper_bound_bytes']!=fallback:
                raise AssertionError('Independent whole-chain size/upper-bound mismatch')
            if row['field_absolute_escapes']!=dict(escape_counts):raise AssertionError('Absolute escape census differs from actual writer')
        if ordinal%40==0:print(json.dumps({'audited_source_profiles':ordinal,'requested':460}),flush=True)
    if dict(family_counts)!={'baseline-v2':98,'expanded100':98,'non-speech-baseline-v1':264}:raise AssertionError('Incomplete robustness/main coverage')
    indexed_hist={(h['family'],h['split'],h['cohort'],h['profile']):h for h in hist}
    for group,details in hist_input.items():
        actual=indexed_hist[group];expected=actual['histogram']['groups'];unused=Counter()
        for label in ('stored','audible'):
            packets=first=transitions=repeats=0;absolute={f:Counter() for f,_ in FIELDS};deltas={f:Counter() for f,_ in FIELDS}
            for info in details:
                coded=info['coded'] if label=='stored' else info['coded'][:(info['values'][0]+159)//160]
                packets+=len(coded);first+=1;transitions+=len(coded)-1
                for packet in coded:
                    for i,(field,_) in enumerate(FIELDS):absolute[field][packet[i]]+=1
                for before,after in zip(coded,coded[1:]):
                    repeats+=int(before==after)
                    for i,(field,_) in enumerate(FIELDS):deltas[field][after[i]-before[i]]+=1
            value=expected[label]
            if any(value[k]!=v for k,v in {'packets':packets,'first_packets':first,'transitions':transitions,'tuple_repeats':repeats}.items()):raise AssertionError('Histogram packet history changed')
            for field,_ in FIELDS:
                if value['fields'][field]['absolute']!={str(k):v for k,v in sorted(absolute[field].items())} or value['fields'][field]['delta']!={str(k):v for k,v in sorted(deltas[field].items())}:
                    raise AssertionError('Full repeat/delta histogram mismatch')
                if value['fields'][field]['repeats']!=deltas[field][0]:raise AssertionError('Repeat count differs from actual parameter history')
        for info in details:
            coded=info['coded'];unused['stored_gain_zero_tuples']+=sum(g==0 for s,l,g in coded)
            unused['gain_zero_lag_changes']+=sum(b[2]==0 and b[1]!=a[1] for a,b in zip(coded,coded[1:]))
            unused['scale_code_alias_values_0_to_5_retained']+=sum(s<=5 for s,l,g in coded)
        if dict(unused)!=actual['unused_but_preserved']:raise AssertionError('Unused parameter preservation census changed')
    if module['source_binding']()!=binding or sha(Path(__file__).read_bytes())!=self_hash:raise ValueError('Source changed during cost audit')
    for path,digest in {**private['input_manifests_sha256'],**private['stream_files_sha256']}.items():
        if sha(Path(path).read_bytes())!=digest:raise ValueError('Input changed during audit')
    report={'schema':'lpx-v5-parameter-cost-independent-audit-v1','status':'passed','source_profiles':460,'methods':13,'whole_chain_cost_rows':5980,
        'unique_v5_streams':len(cache),'canonical_sources_checked_against_existing_writer':canonical_count,'noncanonical_sources_retained_without_repacking':noncanonical_count,
        'independent_parameter_writer_checks':parameter_checks,'independent_segment_cost_checks':segment_cost_checks,
        'actual_source_flag_markers_tails_and_per_segment_padding_verified':True,'stored_and_audible_histograms_independently_verified':True,
        'unused_lag_and_scale_aliases_retained':True,'tuning_nomination_locked_before_heldout':True,
        'new_format_or_decoder_implemented':False,'audio_quality_or_stoi_computed':False,'decoder_flash_measured':False,
        'audit_source_sha256':self_hash,'measurement_source_sha256':sha(Path(driver).read_bytes()),'seconds':time.perf_counter()-started}
    module['save'](output/'audit.json',report);print(json.dumps(report),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('study','driver','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();audit(args.study,args.driver,args.output)
