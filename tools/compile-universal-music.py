"""Events/arrangement -> UM88 -> AVR -> full audit -> local player package.

Publish the output directory only after every step passes. External MIDI is
read using midi-events.py; only its structured JSON is retained in the output.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('um_pipeline_arranger',ROOT/'tools/arrange-universal-music.py')
arranger=importlib.util.module_from_spec(spec);spec.loader.exec_module(arranger)


def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def run(command):
    result=subprocess.run([str(x) for x in command],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode:raise RuntimeError((result.stderr or result.stdout).strip())
    if result.stdout:print(result.stdout.strip())


def compile_music(source,config,output,*,backend='c',cpu_hz=None,buffer_frames=None,platform_header=None,avr_bin=None,preview_seconds=None):
    source=Path(source).resolve();config=Path(config).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError(f'Output already exists: {output}')
    if source.suffix.lower()!='.json' and source.is_relative_to(ROOT):
        raise ValueError('Read MIDI from an external location; repository sources must be JSON')
    document=arranger.event_tools.load(source)
    settings=json.loads(config.read_text(encoding='utf-8-sig'))
    score,report=arranger.arrange(document,settings)
    scratch=ROOT/'build/universal';scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pipeline-',dir=scratch) as work:
        trial=Path(work)
        save(trial/'score.json',score)
        command=[sys.executable,ROOT/'tools/build-universal-music.py','--backend',backend,'--score',trial/'score.json','--output-dir',trial/'firmware']
        if cpu_hz is not None:command+=['--cpu-hz',str(cpu_hz)]
        if buffer_frames is not None:command+=['--buffer-frames',str(buffer_frames)]
        if platform_header:command+=['--platform-header',Path(platform_header).resolve()]
        if avr_bin:command+=['--avr-bin',avr_bin]
        run(command)
        folder=trial/'firmware'/score['name']
        print(f"Full PWM audit: {score['controlTicks']} control ticks",flush=True)
        try:run(['node',ROOT/'tools/audit-universal-music.mjs','--directory='+str(trial/'firmware'),score['name']])
        except RuntimeError:
            failure=folder/'verification.json'
            if failure.exists():
                meta=json.loads((folder/'build-report.json').read_text(encoding='utf-8'))
                diagnostics=scratch/'failures';diagnostics.mkdir(exist_ok=True)
                retained=diagnostics/f"{score['name']}-{backend}-{meta['cpuHz']}.json"
                shutil.copyfile(failure,retained)
                reason=json.loads(failure.read_text(encoding='utf-8')).get('failure','Playback audit failed')
                raise ValueError(f'{reason}; diagnostic report: {retained}') from None
            raise
        verification=json.loads((folder/'verification.json').read_text(encoding='utf-8'))
        if verification['clippedChannelSamples']:
            diagnostics=scratch/'failures';diagnostics.mkdir(exist_ok=True)
            retained=diagnostics/f"{score['name']}-{backend}-{verification['cpuHz']}-clipping.json"
            shutil.copyfile(folder/'verification.json',retained)
            raise ValueError(f'PWM clipping detected; increase gainShift; diagnostic report: {retained}')
        for name,data in [('source-events.json',document),('arrangement.json',settings),('arrangement-report.json',report),
                          ('provenance.json',dict(inputName=source.name,inputSha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                                                 configurationSha256=hashlib.sha256(config.read_bytes()).hexdigest()))]:save(folder/name,data)
        shutil.copyfile(ROOT/'ATtiny13A/Music/instruments/FluidR3-MIT.txt',folder/'FluidR3-MIT.txt')
        shutil.copyfile(ROOT/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/LICENSE.txt',folder/'Microchip-device-license.txt')
        run(['node',ROOT/'tools/package-universal-music.mjs',folder])
        if preview_seconds is not None:run(['node',ROOT/'tools/render-universal-preview.mjs',folder,str(preview_seconds)])
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.um88-',dir=output.parent) as release:
            payload=Path(release)/'payload';shutil.copytree(folder,payload);payload.rename(output)
    print(f"Ready: {output}; {report['noteAttacks']} tonal attacks; {len(report['voiceSteals'])} shortened notes/tails; {sum(report['ignoredEvents'].values())} unsupported events")
    return output


def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('--arrangement',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--backend',choices=('c','avr-asm'),default='c')
    parser.add_argument('--cpu-hz',type=int);parser.add_argument('--buffer-frames',type=int);parser.add_argument('--platform-header',type=Path);parser.add_argument('--avr-bin')
    parser.add_argument('--preview-seconds',type=float)
    args=parser.parse_args()
    if args.preview_seconds is not None and not .1<=args.preview_seconds<=60:parser.error('preview-seconds must be 0.1..60')
    try:compile_music(args.input,args.arrangement,args.output,backend=args.backend,cpu_hz=args.cpu_hz,buffer_frames=args.buffer_frames,
                      platform_header=args.platform_header,avr_bin=args.avr_bin,preview_seconds=args.preview_seconds)
    except (ValueError,KeyError,TypeError,OSError,RuntimeError) as error:parser.exit(1,f'Compilation failed: {error}\n')


if __name__=='__main__':main()
