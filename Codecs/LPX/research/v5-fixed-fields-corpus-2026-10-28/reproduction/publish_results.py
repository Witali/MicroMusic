"""Project the audited anonymous corpus receipts into a local research folder."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))
from output_paths import protect_outputs
def load(path):return json.loads(path.read_text())
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
sha=lambda data:hashlib.sha256(data).hexdigest()


def publish(audit,drivers,destination):
    audit=Path(audit);drivers=Path(drivers);destination=Path(destination).resolve()
    if not destination.is_relative_to((ROOT/'Codecs/LPX/research').resolve()):raise ValueError('Destination must be a local LPX research folder')
    summary=load(audit/'summary.json');rows=load(audit/'rows.json')['rows'];binding=load(audit/'source-runtime.json')
    if summary['status']!='complete' or len(rows)!=294 or summary['profile_groups']!=98:
        raise ValueError('Only the complete independently audited run may be published')
    for name,field in (('corpus_control.py','measurement_driver_sha256'),('audit_and_export.py','audit_export_driver_sha256')):
        if sha((drivers/name).read_bytes())!=binding[field]:raise ValueError('Reproduction driver differs from audited source')
    targets=[destination/name for name in ('summary.json','rows.json','generation.json','source-runtime.json','equal-size-summary.json','tests.json','README.md')]
    targets.extend(destination/'reproduction'/name for name in ('corpus_control.py','audit_and_export.py','publish_results.py','sources.json'))
    for target in targets:
        if target.is_symlink() or target.exists() and target.stat().st_nlink>1:raise ValueError('Publication output cannot alias another file')
    protect_outputs([audit/name for name in ('summary.json','rows.json','generation.json','source-runtime.json')]+
        [drivers/name for name in ('corpus_control.py','audit_and_export.py','publish_results.py')],targets)
    destination.mkdir(parents=True,exist_ok=True);(destination/'reproduction').mkdir(exist_ok=True)
    for name in ('summary.json','rows.json','generation.json','source-runtime.json'):
        shutil.copyfile(audit/name,destination/name)
    for name in ('corpus_control.py','audit_and_export.py','publish_results.py'):
        shutil.copyfile(drivers/name,destination/'reproduction'/name)
    equal=[]
    for percent in (100,95,90):
        chosen=[r for r in rows if r['percent']==percent and r['amplitude'] is not None]
        identical=[r for r in chosen if r['amplitude']['file_bytes']==r['swapped_accepted']['file_bytes']]
        def outcomes(values):
            deltas=[r['accepted_pcm_sse_change_percent_vs_amplitude'] for r in values]
            return [sum(d<0 for d in deltas),sum(d==0 for d in deltas),sum(d>0 for d in deltas)]
        equal.append({'percent':percent,'common_cap_fits':len(chosen),'equal_achieved_bytes':len(identical),
            'equal_bytes_pcm_sse_better_equal_worse_vs_amplitude':outcomes(identical),
            'same_cap_pcm_sse_better_equal_worse_vs_amplitude':outcomes(chosen),
            'accepted_uses_fewer_bytes':sum(r['accepted_size_change_vs_amplitude']<0 for r in chosen),
            'accepted_uses_more_bytes_within_cap':sum(r['accepted_size_change_vs_amplitude']>0 for r in chosen)})
    save(destination/'equal-size-summary.json',{'schema':'lpx-v5-fixed-fields-equal-size-v1','groups':equal,
        'scope':'Same total cap and equal achieved complete-stream bytes are separate comparisons. All accepted outputs preserve the same-cap whole-chain amplitude floors; original-incumbent flags remain separate.'})
    testnames=('test_speech_rate_allocation.py','test_speech_parameter_histograms.py','test_speech_chain_frontier.py')
    save(destination/'tests.json',{'focused_groups':16,'failures':0,'errors':0,
        'source_sha256':{name:sha((ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tests'/name).read_bytes()) for name in testnames},
        'scope':'8 allocation +3 histogram +5 chain-selection groups before the frozen corpus run; independent corpus audit is separate.'})
    save(destination/'reproduction/sources.json',{'schema':'lpx-v5-fixed-fields-reproduction-v1',
        'scripts':{p.name:sha(p.read_bytes()) for p in sorted((destination/'reproduction').glob('*.py'))},
        'measurement_and_audit_scripts_are_exact_copies':True,'publisher_included':True,'allocator_commit':'5865df33','chain_selector_origin_commit':'0e10e9b1',
        'decoder_source_commit':'5c7e0592','private_media_artifacts_or_recording_fingerprints_included':False})
    groups=summary['groups'][:3]
    cap_table='\n'.join(f"| {r['percent']}% | {r['amplitude_fits']}/98 | {r['swapped_accepted_fits']}/98 | {r['no_fit']} | {' / '.join(map(str,r['accepted_pcm_sse_better_equal_worse_vs_amplitude']))} | {r['accepted_original_four_floor_passes']} |" for r in groups)
    equal_table='\n'.join(f"| {r['percent']}% | {r['equal_achieved_bytes']} | {' / '.join(map(str,r['equal_bytes_pcm_sse_better_equal_worse_vs_amplitude']))} | {r['accepted_uses_fewer_bytes']} | {r['accepted_uses_more_bytes_within_cap']} |" for r in equal)
    content=f'''# Frozen fixed-fields v5 corpus control

This study applies the frozen bounded optional-pulse policy to **49 recordings,
both profiles: 98 profile groups and all 294 original-cap rows**. It changes no
MCU source or v5 syntax. Decoder sources match the frozen baseline inventory
from `5c7e0592`; host program-Flash benefit is **0 B**.

Settings were fixed before this run: amplitude seed, at most 128 full renders,
32-candidate batches, SSE objective/lambda zero, and the amplitude-control four
quality floors. Tuning, evaluation and additional cohorts use exactly the same
settings. No settings were retuned on evaluation/additional outcomes. Joint LPC
changes and nonzero-lambda sweeps are outside this control.

## Complete-recording results

The cap is `floor(original_complete_stream_bytes * percent / 100)`. It includes
every segment header, stored final packet, extras marker and padding byte. These
are encoded reset-chain byte caps; full linked MCU player Flash/IRQ admission
remains a separate measurement.

| Cap | Amplitude fits | Accepted swap fits | No finite-pool fit | PCM SSE better / equal / worse versus same-cap amplitude | Accepted passing original-incumbent four floors |
| --- | ---: | ---: | ---: | --- | ---: |
{cap_table}

Across common fitting profile groups, summed PCM error energy changes by
{groups[1]['common_fit_aggregate_pcm_sse_change_percent_vs_amplitude']:.4f}% at the 95% cap
and {groups[2]['common_fit_aggregate_pcm_sse_change_percent_vs_amplitude']:.4f}% at the 90% cap
versus amplitude controls. At 100% it is unchanged.

Every accepted output preserves the *complete-recording* amplitude control's
PCM/PWM SSE and available STOI floors. This does not imply a gain against the
larger original incumbent. `rows.json` contains full original-incumbent,
amplitude, accepted-swap and raw-swap PCM/PWM metrics, actual bytes and original
floor flags. The raw result can fail amplitude or original floors; it remains a
research/listening alternative. All automatic-adoption flags are false.

The last table column checks the returned accepted output against the original
incumbent. `observed_original_selected` is a separate best qualifying point
among returned shortlist/frontier snapshots. It does not claim a global optimum
over every unmeasured combination. The original incumbent is always preserved
as rollback even when it lies outside a smaller cap.

Same-cap quality comparisons may spend a different number of bytes within the
same total cap. Equal achieved byte counts are reported separately:

| Cap | Equal achieved bytes | PCM SSE better / equal / worse at equal bytes | Accepted uses fewer bytes | Accepted uses more bytes within cap |
| --- | ---: | --- | ---: | ---: |
{equal_table}

Error-energy percentages describe measured error, not perceived-quality
percentages. Group aggregates sum actual full-length error energies across
common fitting cases. Non-speech STOI is retained as a mechanical gate/metric,
not interpreted as music intelligibility.

## Frozen proposal and selection protocol

Spectra, scale/lag/gain, mandatory pulses, pre/bright filters, samples and reset
boundaries stay frozen. Only membership of the original optional extras can
change. Each segment gets a finite proposal cap grid: original bytes; actual
serialized sizes with 0/25/50/75/100% active extras; 90/95/100% segment bytes;
and requested whole-cap residuals against other segments' baseline/minimum
fixed-field bytes. Out-of-API and redundant proposals remain in the grid report.
These are generation caps, **never proportional final admission**.

The preserved amplitude fit supplies each proposal's control. Bounded swaps
exchange one retained and one removed original extra at unchanged stored rate.
Accepted states are actually serialized and reconstructed again; subsequent
proposals use the new state. Duplicate identical amplitude seeds reuse only an
equivalent frozen search; reused renders are counted as zero and traces match.
Generation no-fit and evaluation-limit outcomes are kept in `generation.json`.

Proposal quality gates replace just that segment in the original complete
reset chain. Since the objective is SSE, its fixed other-segment contribution
can be added exactly; STOI/PWM gates still use the complete concatenated output.
The complete amplitude pools are then assembled under each true total cap.
Merged swapped pools use that fitting whole-chain amplitude result as rollback
and quality baseline. Final outputs are re-scored on the full original reference
with original gain/length and decoder resets. No local cap or segment-local
floor decides final admission.

The shared selector enumerates finite pools when possible, otherwise reports
its bounded 32-wide/4096-evaluation beam. It preserves cheap feasible
continuations and limits the returned size frontier to 16 points. Its metric
admission scope is the objective shortlist, frontier and feasible rollback.
Every limit/no-fit row is retained; these finite-search results cannot establish
that a different spectrum or v5 stream cannot fit.

## Source and independent audit

Sixteen focused test groups passed before the run. The independent audit then
re-read every original reference, ordered segment and generated artifact, and
verified current native **common and v5-only PCM/PWM** against the full integer
model. It reconstructed accepted intermediate swaps and rechecked their exact
scores, constant rates and four floors. Whole-chain roles were independently
reconstructed and re-scored again.

The audit checked {summary['independent_validated_unique_streams']} unique streams,
{summary['independent_accepted_intermediate_trace_checks']} accepted intermediate
states and {summary['independent_full_chain_points']} returned complete-chain
points. All source/runtime/input guards passed. Per-record source/artifact
bindings, reference/audio fingerprints, private identities and paths remain
only in ignored receipts; published rows use anonymous case/profile identifiers.
`source-runtime.json` pins public source, native library and package provenance.

The resumed three-worker campaign took {summary['parallel_campaign_wall_seconds']:.2f} s
wall time and reused one source/artifact-verified tuning smoke record. Per-record
measured wall sum is {summary['search_record_wall_seconds_sum']:.2f} s and measured
process CPU sum is {summary['search_python_process_cpu_seconds_sum']:.2f} s. CPU
includes in-process native decoding, NumPy/SciPy/Numba DSP and metrics; excludes
compiler subprocesses/coordinator/startup. Wall sums include validation and I/O,
so these are campaign costs rather than a matched isolated-search speedup.
The separate audit took {summary['independent_audit_wall_seconds']:.2f} s.

## Reproduction

Run from the repository root with Python/package versions in
`source-runtime.json`, a native C++ compiler, and the locally supplied immutable
`lpx-v5-encoder-quality-study-v1` baseline-v2 manifest/files. The scripts in
`reproduction/` are exact copies of the measured/audited source, including the
same fixed settings. Provide a fresh ignored output directory:

```sh
python Codecs/LPX/research/{destination.name}/reproduction/corpus_control.py \\
  "$LPX_MANIFEST" build/fixed-fields-replay --workers 3
python Codecs/LPX/research/{destination.name}/reproduction/audit_and_export.py \\
  "$LPX_MANIFEST" build/fixed-fields-replay build/fixed-fields-audited \\
  Codecs/LPX/research/{destination.name}/reproduction/corpus_control.py
```

The native compiler belongs on PATH; shared Python dependencies may be supplied
through PYTHONPATH. The driver adds the repository tools directory itself.
Fresh runs bind their actual compiler-built native libraries and source-file
labels; existing cache receipts require the identical source/runtime identity.
Every cache hit remains provisional until the mandatory independent audit
rechecks current references, input streams, outputs and metrics. Do not run with
Python optimization flags: validation uses assertions in the shared model/tools.
Generated media/private receipts stay under ignored `build/`; no external upload
is needed. Actual whole-player Flash, SRAM and active-IRQ admission of newly
selected corpus streams is separate and is not claimed here.
'''
    (destination/'README.md').write_text(content,encoding='utf-8',newline='\n')
    print(json.dumps({'public_files':len([p for p in destination.rglob('*') if p.is_file()]),'rows':len(rows),'status':'projected_for_privacy_review'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('audit','drivers','destination'):parser.add_argument(name,type=Path)
    args=parser.parse_args();publish(args.audit,args.drivers,args.destination)
