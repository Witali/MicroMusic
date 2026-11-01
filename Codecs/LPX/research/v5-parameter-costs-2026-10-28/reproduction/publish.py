"""Publish only anonymous numeric parameter-cost preparation, after its independent audit."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import sys

ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))
from output_paths import protect_outputs
sha=lambda b:hashlib.sha256(b).hexdigest()
def load(path):return json.loads(path.read_text())
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
def number(value):return f'{value:g}' if isinstance(value,(int,float)) else str(value)


def publish(study,audit,drivers,destination):
    study=Path(study);audit=Path(audit);drivers=Path(drivers);destination=Path(destination).resolve()
    if not destination.is_relative_to((ROOT/'Codecs/LPX/research').resolve()):raise ValueError('Expected local LPX research destination')
    summary=load(study/'summary.json');rows=load(study/'rows.json')['rows'];check=load(audit/'audit.json');binding=load(study/'source-runtime.json')
    if summary['status']!='complete' or check['status']!='passed' or len(rows)!=5980:raise ValueError('Expected complete audited study')
    if sha((drivers/'study.py').read_bytes())!=binding['measurement_driver_sha256'] or sha((drivers/'audit.py').read_bytes())!=check['audit_source_sha256']:
        raise ValueError('Reproduction sources changed after measurement/audit')
    names=('summary.json','histograms.json','nomination.json','source-runtime.json','audit.json','byte-budget-context.json','tests.json','chain-costs.csv','segment-costs.csv','README.md')
    targets=[destination/n for n in names]+[destination/'reproduction'/n for n in ('study.py','audit.py','publish.py','sources.json')]
    for target in targets:
        if target.is_symlink() or target.exists() and target.stat().st_nlink>1:raise ValueError('Publication output aliases another file')
    protect_outputs([study/n for n in ('summary.json','rows.json','histograms.json','nomination.json','source-runtime.json')]+[audit/'audit.json']+[drivers/n for n in ('study.py','audit.py','publish.py')],targets)
    destination.mkdir(parents=True,exist_ok=True);(destination/'reproduction').mkdir(exist_ok=True)
    for name in ('summary.json','histograms.json','nomination.json','source-runtime.json'):shutil.copyfile(study/name,destination/name)
    shutil.copyfile(audit/'audit.json',destination/'audit.json')
    for name in ('study.py','audit.py','publish.py'):shutil.copyfile(drivers/name,destination/'reproduction'/name)
    chain_fields=['id','case','family','domain','profile','split','cohort','samples','method','selector','kind','mask','k','segments',
        'current_file_bytes','proposed_file_bytes','whole_stream_saved_bytes','added_decoder_flash_data_upper_bound_bytes',
        'fallback_data_only_upper_bound_bytes','all_segment_sizes_within_rom_api','scale_absolute_escapes','lag_absolute_escapes','gain_code_absolute_escapes',
        'format_implemented','decoder_flash_measured']
    prefixes=['id','case','family','profile','split','cohort','method','selector','segment']
    segment_fields=prefixes+[key for key in rows[0]['segment_costs'][0] if key not in prefixes]
    chains=[];segments=[]
    for row in rows:
        item={key:row[key] for key in chain_fields if key in row}
        item.update(method=row['method']['name'],**{key:row['method'][key] for key in ('selector','kind','mask','k')})
        item.update({field+'_absolute_escapes':row['field_absolute_escapes'][field] for field in ('scale','lag','gain_code')})
        chains.append(item)
        for i,part in enumerate(row['segment_costs']):
            segments.append({**{key:row[key] for key in prefixes if key in row},'method':row['method']['name'],
                'selector':row['method']['selector'],'segment':i,**part})
    for name,fields,data in (('chain-costs.csv',chain_fields,chains),('segment-costs.csv',segment_fields,segments)):
        with (destination/name).open('w',encoding='utf-8',newline='') as file:
            writer=csv.DictWriter(file,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(data)
    # Per-image upper bounds, not the unusable sum of a benchmark corpus.
    context=[]
    nominees=[summary['nomination'][k]['method']['name'] for k in ('minimal_repeat','higher_complexity_rice') if summary['nomination'][k]]
    for family in sorted({r['family'] for r in rows}):
        for split in sorted({r['split'] for r in rows if r['family']==family}):
            for method in nominees:
                chosen=[r for r in rows if r['family']==family and r['split']==split and r['method']['name']==method]
                small=[r for r in chosen if r['current_file_bytes']<=32768]
                savings=[r['whole_stream_saved_bytes'] for r in small]
                context.append({'family':family,'split':split,'method':method,'records':len(chosen),
                    'original_data_alone_over32768':len(chosen)-len(small),'original_data_alone_within32768':len(small),
                    'data_within32768_saved_bytes_min_median_max':None if not small else [min(savings),statistics.median(savings),max(savings)],
                    'scope':'Data alone is only an optimistic eligibility filter. Program, directories, tables and layout still have to fit; this is not firmware admission.'})
    save(destination/'byte-budget-context.json',{'schema':'lpx-hypothetical-parameter-byte-budget-context-v1','groups':context,
        'scope':'Five non-speech profile groups exceed 32 KiB before adding any program. Their large full-recording savings are not a usable whole-image ATmega328P budget. No actual added Flash allowance is guaranteed.'})
    tests=('test_speech_parameter_costs.py','test_speech_parameter_histograms.py')
    save(destination/'tests.json',{'focused_groups':9,'failures':0,'errors':0,
        'source_sha256':{name:sha((ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tests'/name).read_bytes()) for name in tests},
        'coverage':'Actual payload/flags, forced-empty extras partial tails, legal zero-amplitude markers, thirteen syntax lengths versus existing writer, unused lag, per-segment initial/header/padding, stale inspections. No new decoder was tested.'})
    save(destination/'reproduction/sources.json',{'schema':'lpx-parameter-cost-reproduction-v1','counter_commit':'1e5b49b9',
        'scripts':{p.name:sha(p.read_bytes()) for p in sorted((destination/'reproduction').glob('*.py'))},
        'exact_measured_and_audited_source_copies':True,'csv_projection':'Lossless scalar projection of 5,980 chain costs and 9,490 segment costs; no private raw JSON or media copied.'})
    repeat=summary['nomination']['minimal_repeat'];rice=summary['nomination']['higher_complexity_rice']
    table=[]
    for family in ('baseline-v2','expanded100','non-speech-baseline-v1'):
        for split in ('tuning','evaluation','additional','non_speech'):
            points=[p for p in summary['family_split_totals'] if p['family']==family and p['split']==split and p['method']['name'] in nominees]
            if not points:continue
            by={p['method']['name']:p for p in points}
            a=by[repeat['method']['name']];b=by[rice['method']['name']]
            table.append(f"| {family} / {split} | {a['records']} | {' / '.join(map(number,a['saved_bytes_min_median_max']))} | {' / '.join(map(number,b['saved_bytes_min_median_max']))} |")
    cost_table='\n'.join(table)
    content=f'''# Exact parameter-cost preparation: no new format

Thirteen predeclared parameter sketches were measured on the original
baseline-v2 and selected expanded100 streams for all 49 main recordings/both
profiles, plus all 132 frozen non-speech records/both profiles. This is **460
source/profile groups, 5,980 whole-chain costs and 9,490 segment costs**.
Baseline and expanded views share recordings; the separate robustness corpus
is not claimed to be statistically independent of the main regression set.

No new encoder/decoder format, MCU change, audio output or quality metric was
implemented/computed. These are exact *hypothetical stored byte costs under
explicit assumptions*. They identify parameter-preserving opportunities;
actual future parameter reconstruction, PCM/PWM equality and firmware savings
remain to be implemented and verified separately.

## Frozen tuning-only nomination

The simplest nominated syntax is **{repeat['method']['name']}**, scale only:
keep the first tuple absolute, then one scale-repeat flag per later tuple,
reading five absolute scale bits only on change. Lag/gain remain fully absolute.
Among repeat candidates with positive aggregate tuning savings in both source
families, the rule prefers fewer selected fields, then the strongest worst-source
fractional saving. It does not use held-out or robustness costs.

The separately retained higher-complexity point is
**{rice['method']['name']}**: Rice k=1 for scale and gain-code deltas, lag still
absolute. Eight-zero escape carries a complete absolute field. It needs exact
previous scale-code state or a separately proved representation; derived
`blockStep_` cannot recover aliases. No code-size benefit is assumed.

Both nominations locked after the 80 tuning source/profile groups and before
the remaining 380 held-out/robustness groups. All thirteen candidate results
remain in the reports; no validation result changed the nominee.

The following signed savings already charge one selector byte **per segment**,
first absolute tuples, mandatory tails and exact independent byte padding:

| Source / split | Profile groups | Scale-repeat savings min / median / max, B | Rice scale+gain k=1 savings min / median / max, B |
| --- | ---: | --- | --- |
{cost_table}

The large robustness maxima include recordings whose data cannot fit into a
32 KiB ATmega328P image even before program code. `byte-budget-context.json`
separates those cases: five robustness profile groups exceed 32 KiB in original
data alone. Remaining data-only eligibility still does not prove program fit.
No STOI, music quality or perceived-quality inference is made.

## Exact accounting assumptions

Repeat masks cover all 7 nonempty scale/lag/gain subsets. A selected later field
pays one flag plus its old 5/7/3 absolute bits only when changed. The six Rice
sketches select scale+gain or all three fields with common k=0/1/2. Zigzag delta
q<8 costs q+1+k; q>=8 spends eight zero bits and the full absolute field value,
not an escaped delta literal. The escape distinction must be explicit in a
future parser; existing v5 `readSpeechRice` is not assumed to be a free drop-in.

Each segment begins with all 15 absolute parameter bits. Every stored tuple is
preserved, including unplayed last packets and lag when gain is 0. Scale aliases
are not normalized. Histograms retain actual code units, transitions and
segment resets; they separate stored from audible tuples.

The existing source stream is never canonicalized for attribution. An actual
bit cursor counts its full consumed v5 payload, retaining original spectral
Rice choices, extras flag and every marker. Only the 15-bit tuple fields are
replaced in the hypothetical cost. A set extras flag with no active pulses and
even a legal marker 1 / amp 0 remain charged. Actual source padding is removed only
to calculate the new exact final padding for **each segment**, not one padded
concatenation of a recording.

The charged fixed overhead is 22 existing header bytes plus 1 method-selector
byte, reported as 23 overhead bytes in the counter. Proposed payload-bit columns
refer to the remaining bit-packed body. This accounting does not finalize the
selector's physical placement or silently reuse v5 flags. A new version/syntax
would be required.

## Byte allowance versus firmware saving

`whole_stream_saved_bytes` is signed. It is an **optimistic UPPER BOUND** on what
the data saving alone could pay for added decoder code, tables and layout in
that recording's image. It is not a measured net Flash reduction. Zero-byte
phrase cases cannot pay any positive program growth. A negative cost case needs
savings elsewhere merely to break even. Corpus totals are benchmark totals,
not an affordable code budget for one firmware image.

The optional per-segment `min(v5,new)` envelope is even more optimistic: it
ignores the program cost of supporting both formats. Uniform new-format costs
are the primary figures and drive nomination. All actual program Flash, SRAM,
stack, C fallback, malformed-input/lifetime behavior and active-IRQ timing
remain future acceptance requirements.

## Untested minimal-state design option

The already charged selector could sit at the start of a new version's payload,
included in the existing uint16 payload length. Storage remains 22 + 1 + body and
padding is identical. A scale-repeat-only prototype could validate selector 1
once and discard it, retaining `blockStep_` on repeats. No per-stream dynamic
method or raw scale-code member is required by that restricted design.

The existing **decoded** `lag_ == 0` sentinel distinguishes the first v5-style
tuple: `resetState()` sets it to 0, every `begin()` calls reset, and every valid
tuple stores 18..145, even for gain 0. Sample that state before assigning the new
lag; encoded lag code 0 itself is valid and means lag 18. Failed begins/sticky
errors and value copies must retain their existing contracts. This domain does
not apply to legacy raw v2/v3 modes where lag can remain 0 after output.
`blockStep_ == 0` is not a valid first-tuple sentinel because legal scales 0..5
all map to 0; scales 6..9 also alias to 1.

This is an **UNTESTED design hint**, received after cost nomination, with no
Flash/SRAM claim. Before any prototype, inspect all compact/version 5 branches,
host parsers, header bounds, reset/copy/error paths and existing-format fallback.
The measured-cost nomination remains independent of that implementation idea.

## Audit and reproduction

Nine focused cost/histogram groups pass. An independent indexed cursor and
existing BitWriter checked all 9,490 segment parameter/size calculations and all
5,980 complete chain rows. All 726 unique current v5 sources matched the existing
serializer with their **original** extras flag. Stored/audible repeat and delta
histograms were independently verified. Synthetic forced-empty partial tails
and legal zero-amplitude markers protect cases not present in this sample.

`chain-costs.csv` and `segment-costs.csv` are lossless scalar projections of the
audited costs; `histograms.json`, `summary.json` and `nomination.json` retain
source/split/cohort/profile separation. Private input paths, identities, audio
and per-recording fingerprints remain ignored. Source/runtime and exact measured
reproduction scripts are retained. The study took {summary['elapsed_seconds']:.2f} s;
the independent audit took {check['seconds']:.2f} s. No native decoder or target
firmware benchmark was run for a new format because none exists yet.

Run from the repository root with Python 3.12, the package versions in
`source-runtime.json`, and locally supplied frozen manifests/receipts:

```sh
python Codecs/LPX/research/{destination.name}/reproduction/study.py \\
  "$LPX_BASELINE" "$LPX_NONSPEECH" "$LPX_TUNING_EXPANDED" \\
  "$LPX_EVALUATION_EXPANDED" "$LPX_ADDITIONAL_EXPANDED" \\
  --output build/parameter-cost-replay
python Codecs/LPX/research/{destination.name}/reproduction/audit.py \\
  build/parameter-cost-replay \\
  Codecs/LPX/research/{destination.name}/reproduction/study.py \\
  build/parameter-cost-audit
```

No external upload is needed. Keep generated private receipts under ignored
`build/`, and do not use Python optimization flags: shared validation uses
assertions. Code/counter origin: `1e5b49b9`; unchanged MCU source: `5c7e0592`.
'''
    (destination/'README.md').write_text(content,encoding='utf-8',newline='\n')
    print(json.dumps({'public_files':len([p for p in destination.rglob('*') if p.is_file()]),'chain_rows':len(chains),'segment_rows':len(segments),'new_format_implemented':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('study','audit','drivers','destination'):parser.add_argument(name,type=Path)
    args=parser.parse_args();publish(args.study,args.audit,args.drivers,args.destination)
