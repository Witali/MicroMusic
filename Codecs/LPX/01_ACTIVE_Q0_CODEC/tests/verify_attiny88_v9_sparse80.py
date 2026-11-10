"""Admit all three v9 profiles under a 5% program-growth ceiling.

Replay the e32e0c66 two-profile ELFs before comparing the new decoder. Keep
their historical receipts intact and bind their source digests to that commit.
All media below are public repository inputs or deterministic synthetic data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from verify_attiny88_universal import ROOT,REPO,streams
from build_attiny88_player import target_path
from verify_attiny88_player import verify
from speech_v9 import repack
from test_speech_v9 import sparse_fixture,all_pairs

REVISION='e32e0c66'
HISTORY=('universal-measurements.json','v9-measurements.json',
         'v9-next-measurements.json','v9-1500-measurements.json')
FIELDS=('samples','flash_bytes','program_excluding_audio_bytes','embedded_audio_bytes',
        'static_ram_bytes','stack_bytes','stack_margin','underruns','min_queue',
        'decode_mean','decode_active_irq_mean','decode_max','decode_cycles',
        'decode_irq_cycles','decode_cpu_cycles','decode_cpu_mean',
        'decode_active_cpu_mean','decode_cpu_max','irq_max','output_gap_min','output_gap_max')


def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))


def run(output,baseline,same_queue,wsl=None):
    output=Path(output).resolve();baseline=Path(baseline).resolve()
    same_queue=Path(same_queue).resolve()
    if REPO/'build' not in output.parents:raise ValueError('Use ignored build storage')
    output.mkdir(parents=True,exist_ok=True)
    path=lambda p:target_path(p,wsl)
    prefix=['wsl','-d',wsl,'--'] if wsl else []
    def command(*args):
        result=subprocess.run([*prefix,*args],capture_output=True)
        if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
        return result.stdout
    folder=ROOT/'examples/ATTINY88_V5_PLAYER'
    historical={name:read(folder/name) for name in HISTORY}
    for name in HISTORY:
        original=subprocess.check_output(['git','show',REVISION+':'+(folder/name).relative_to(REPO).as_posix()],cwd=REPO)
        assert sha(original.replace(b'\r\n',b'\n'))==sha((folder/name).read_bytes().replace(b'\r\n',b'\n')),name
    baseline_sources={}
    for receipt in historical.values():
        for name,digest in receipt['source_sha256'].items():
            original=subprocess.check_output(['git','show',REVISION+':'+name],cwd=REPO)
            actual=sha(original.replace(b'\r\n',b'\n'))
            assert actual==digest,(name,'historical source is not the stated revision')
            baseline_sources[name]=actual
    observer=output/'baseline-observer';observer.mkdir(exist_ok=True)
    hardware=baseline/'bread-quality/current/hardware.h'
    shutil.copyfile(hardware,observer/'hardware.h')
    command('gcc','-O2','-std=c11','-I'+path(observer),'-I/usr/include/simavr',
            path(ROOT.parent/'validation/attiny88/sim_player.c'),'-lsimavr','-lelf',
            '-o',path(observer/'sim_player'))
    # Standard-memory C arithmetic and the ordinary P6 parser supply an
    # independent, unpaced oracle for the synthetic sparse80 expansion.
    reference=output/'reference.cpp'
    reference.write_text(r'''
#include <fstream>
#include <iterator>
#include <vector>
#include <stdio.h>
#include "Lpx4HybridCore.h"
int main(int argc,char** argv){
 if(argc!=2)return 1;
 std::ifstream file(argv[1],std::ios::binary);
 std::vector<uint8_t> data((std::istreambuf_iterator<char>(file)),{});
 Lpx4HybridCore decoder;if(!decoder.begin(data.data(),data.size()))return 2;
 uint8_t pwm;while(decoder.next(pwm))putchar(pwm);
 return decoder.error()?3:0;
}
''',encoding='ascii')
    command('g++','-O2','-std=c++11','-DLPX4_ENABLE_ASM=0','-DLPX4_COMPACT_ONLY=1',
            '-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
            '-I'+path(ROOT/'src'),path(reference),path(ROOT/'src/Lpx4HybridCore.cpp'),
            '-o',path(output/'reference'))
    rows=[]
    def check(name,source,expected,kind,before=None):
        blob=source.read_bytes();encoded,stats=repack(blob)
        destination=output/name;destination.mkdir(exist_ok=True)
        media=destination/'stream.lpx';media.write_bytes(encoded)
        after=verify(media,destination/'current',wsl=wsl)
        cost=read(destination/'current/build.json')
        assert after['accepted'] and after['queue']==32 and after['irq_max']==38,name
        assert cost['universal'] and cost['compact_version']==9,name
        assert cost['supported_profiles']==[4,6,15]
        assert not any(flag.startswith('-DLPX4_FIXED_') for flag in cost['compiler_options'])
        actual=(destination/'current/actual.pwm').read_bytes()
        assert sha(actual)==expected,(name,'independent PWM oracle')
        assert len(encoded)<=len(blob)-9 and stats['payload_bits']<=stats['input_payload_bits']
        assert after['program_excluding_audio_bytes']*100<=5384*105,(name,'5% program cap')
        assert after['decode_cycles']==after['decode_cpu_cycles']+after['decode_irq_cycles']
        assert after['decode_irq_cycles']%38==0
        row={'case':name,'kind':kind,'profile':encoded[2]&127,'repack':stats,
             'data_sha256':sha(encoded),'pwm_sha256':expected,'pwm_exact':True,
             'after':{field:after[field] for field in FIELDS},
             'total_active_cycles_per_sample':after['decode_active_cpu_mean']+38}
        if before is not None:
            assert before['embedded_audio_bytes']==after['embedded_audio_bytes']
            assert after['program_excluding_audio_bytes']*100<=before['program_excluding_audio_bytes']*105
            row['before']={field:before[field] for field in FIELDS}
        rows.append(row)
        print(json.dumps({'case':name,'program_bytes':after['program_excluding_audio_bytes'],
                          'total_cycles':row['total_active_cycles_per_sample'],
                          'min_queue':after['min_queue'],'stack_margin':after['stack_margin']}),flush=True)
    for name,source in streams(output):
        old=baseline/name/'current';cost=read(old/'build.json')
        assert cost['universal'] and cost['compact_version']==9 and cost['queue']==44
        assert (old/'hardware.h').read_bytes()==hardware.read_bytes()
        destination=output/name;destination.mkdir(exist_ok=True)
        command('avr-objcopy','-O','binary','-R','.eeprom',path(old/'player.elf'),path(destination/'baseline.bin'))
        assert sha((destination/'baseline.bin').read_bytes())==cost['image_sha256']
        encoded,_=repack(source.read_bytes());assert sha(encoded)==cost['input_sha256']
        command(path(observer/'sim_player'),path(old/'player.elf'),
                path(destination/'baseline.pwm'),path(destination/'baseline.json'))
        before=read(destination/'baseline.json');stored=read(old/'timing.json')
        assert before==stored,(name,'frozen timing changed')
        expected=next(row for row in historical[HISTORY[-1]]['cases'] if row['case']==name)['pwm_sha256']
        assert sha((destination/'baseline.pwm').read_bytes())==expected
        before.update({field:cost[field] for field in
                       ('flash_bytes','program_excluding_audio_bytes','embedded_audio_bytes','static_ram_bytes')})
        check(name,source,expected,'existing',before)
    # Real public low-rate recordings have frozen output from independent paths.
    low=REPO/'web-player/audio/lpx-bread/low15.lpx'
    frozen=baseline.parents[1]/'tiny88-release/bread-low15'
    old_low=read(frozen/'verification.json')
    assert old_low['outputLevel']['numerator']==128
    check('bread-low15',low,sha((frozen/'expected.pwm').read_bytes()),'sparse80-public')
    fixture=ROOT/'tests/fixtures/chego-2k-v8.lpx'
    metadata=read(fixture.with_suffix('.json'))
    check('chego-2k',fixture,metadata['pwm_sha256'],'sparse80-public')
    for style,lag,pre,bright in [('changing',145,0,0),('clusters',18,16384,11469),
            ('changing',145,8192,11469),('changing',18,16383,11468),('clusters',145,1,1)]:
        name=f's80-{style}-lag{lag}-pre{pre}-bright{bright}'
        original,expanded=sparse_fixture(12800,style,pre,bright,lag)
        source=output/(name+'.lpx');source.write_bytes(original)
        reference=output/(name+'-v5.lpx');reference.write_bytes(expanded)
        expected=sha(command(path(output/'reference'),path(reference)))
        check(name,source,expected,'sparse80-synthetic')
    pair=output/'all-pairs.lpx';pair.write_bytes(bytes(all_pairs()))
    check('all-pairs',pair,historical['v9-measurements.json']['pulse_pair_irq_check']['pwm_sha256'],
          'all-400-pulse-pairs')
    same=read(same_queue/'verification.json');same_cost=read(same_queue/'build.json')
    assert same['accepted'] and same['queue']==32 and same_cost['compact_version']==9
    recorded={name.replace('\\','/'):digest for name,digest in same_cost['source_sha256'].items()}
    assert recorded['Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp']==sha(
        subprocess.check_output(['git','show',REVISION+':Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp'],cwd=REPO))
    largest=max(row['after']['program_excluding_audio_bytes'] for row in rows)
    assert largest*100<=same['program_excluding_audio_bytes']*105
    sources=[*sorted((ROOT/'src').glob('Lpx4*')),ROOT/'src/native_batch_decoder.cpp',
             ROOT/'tools/speech_v9.py',ROOT/'tools/build_attiny88_player.py',ROOT/'tools/verify_attiny88_player.py',
             ROOT/'tests/test_speech_v9.py',ROOT/'tests/verify_attiny88_universal.py',
             ROOT/'profiles/Lpx4Sram512.h',ROOT/'examples/ATTINY88_V5_PLAYER/player.cpp',
             ROOT.parent/'validation/attiny88/sim_player.c',Path(__file__),
             ROOT/'tests/fixtures/chego-2k-v8.json']
    report={'schema':'lpx-v9-sparse80-admission-v1','baseline_revision':REVISION,
            'clock_hz':16000000,'sample_hz':8000,'queue':32,'prefill':24,
            'profiles':[4,6,15],'maximum_program_growth_percent':5,
            'baseline_program_bytes':5384,'maximum_program_bytes':largest,
            'program_growth_percent':100*(largest-5384)/5384,
            'same_queue_baseline':{field:same[field] for field in FIELDS},
            'same_queue_program_growth_percent':100*(largest-same['program_excluding_audio_bytes'])/same['program_excluding_audio_bytes'],
            'parameters':'runtime LPX header','physical_board_measured':False,
            'cycle_accounting':'active decoder CPU mean plus complete ISR; queue management excluded',
            'source_hash_encoding':'text-lf','cases':rows,
            'binary_sha256':{'Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/fixtures/chego-2k-v8.lpx':sha(fixture.read_bytes())},
            'baseline_source_sha256':baseline_sources,
            'historical_receipt_sha256':{name:sha((folder/name).read_bytes().replace(b'\r\n',b'\n')) for name in HISTORY},
            'source_sha256':{p.relative_to(REPO).as_posix():sha(p.read_bytes().replace(b'\r\n',b'\n')) for p in sources}}
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path);parser.add_argument('baseline',type=Path)
    parser.add_argument('same_queue',type=Path);parser.add_argument('--wsl')
    args=parser.parse_args();run(args.output,args.baseline,args.same_queue,args.wsl)
