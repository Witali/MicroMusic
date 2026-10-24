#!/usr/bin/env python3
"""Acquire credited human speech and prepare deterministic Speex NB3 test clips.

Audio and derived clips stay under ignored build/real-speech. Attribution and
source snapshots accompany every generated listening bundle. No speech is TTS.
Requires FFmpeg with libspeex; no encoder change is made to the AVR decoder.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import wave

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/real-speech'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(args):
    subprocess.run([str(x) for x in args], check=True)


def download(url, output):
    if output.exists():
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(5):
        try:
            request = Request(url, headers={'User-Agent': 'MicroMusic-Speex-Evaluation/1.0 (local audio codec research; source credits retained)'})
            with urlopen(request, timeout=40) as response:
                data = response.read()
            if len(data) < 1024:
                raise ValueError('Unexpectedly small source file')
            output.write_bytes(data)
            time.sleep(2)
            return
        except Exception as error:
            if attempt == 4:
                raise
            delay = 5 * (attempt + 1)
            if isinstance(error, HTTPError) and error.code == 429:
                retry = error.headers.get('Retry-After', '45')
                delay = max(30, int(retry) if retry.isdigit() else 45)
            print('Retry download after', delay, 'seconds:', type(error).__name__, flush=True)
            time.sleep(delay)


def packets(data):
    """Read complete, single-serial Ogg pages, including continued packets."""
    pos = 0
    pending = bytearray()
    serial = None
    previous = None
    while pos < len(data):
        if data[pos:pos+5] != b'OggS\0' or pos+27 > len(data):
            raise ValueError('Invalid Ogg page')
        current, sequence = struct.unpack_from('<II', data, pos+14)
        if serial is None:
            serial = current
        if current != serial or (previous is not None and sequence != previous+1):
            raise ValueError('Unsupported interleaved/chained or missing Ogg page')
        previous = sequence
        if bool(data[pos+5] & 1) != bool(pending):
            raise ValueError('Invalid continuation flag')
        n = data[pos+26]
        lace = data[pos+27:pos+27+n]
        cursor = pos+27+n
        if len(lace) != n:
            raise ValueError('Truncated lacing table')
        for size in lace:
            if cursor+size > len(data):
                raise ValueError('Truncated packet')
            pending.extend(data[cursor:cursor+size])
            cursor += size
            if size < 255:
                yield bytes(pending)
                pending.clear()
        pos = cursor
    if pending:
        raise ValueError('Truncated final packet')


def extract(ogg, raw):
    iterator = iter(packets(ogg.read_bytes()))
    header = next(iterator)
    if len(header) < 80 or not header.startswith(b'Speex   '):
        raise ValueError('Not a Speex header')
    rate, mode, version, channels, bitrate, frame, vbr, fpp, extra = struct.unpack_from('<9i', header, 36)
    if (rate, mode, channels, bitrate, frame, vbr, fpp, extra) != (8000,0,1,8000,160,0,1,0):
        raise ValueError('Unexpected encoder profile')
    next(iterator)  # comments
    frames = list(iterator)
    if not frames or any(len(f) != 20 or f[0] >> 3 != 3 for f in frames):
        raise ValueError('Expected only NB mode-3 packets')
    raw.write_bytes(b''.join(frames))
    return len(frames)


def read_pcm(path):
    with wave.open(str(path), 'rb') as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1,2,8000)
        data = wav.readframes(wav.getnframes())
    return list(struct.unpack('<' + 'h'*(len(data)//2), data))


def write_pcm(path, samples):
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
        wav.writeframes(struct.pack('<'+'h'*len(samples), *samples))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'tests/real-speech-sources.json').read_text(encoding='utf-8'))
    OUT.mkdir(parents=True, exist_ok=True)
    sources = []
    clips = []
    for item in manifest['sources']:
        item = dict(item)
        name = item['file']
        key = hashlib.md5(name.encode('utf-8')).hexdigest()  # Wikimedia media path, not integrity
        item['url'] = f'https://upload.wikimedia.org/wikipedia/commons/{key[0]}/{key[:2]}/' + quote(name)
        item['page'] = 'https://commons.wikimedia.org/wiki/File:' + quote(name)
        original = OUT / 'originals' / (item['id'] + '.ogg')
        download(item['url'], original)
        item['sha256'] = digest(original.read_bytes())
        # Keep the description page with attribution, article and license links.
        download(item['page'], OUT / 'originals' / (item['id'] + '.html'))
        sources.append(item)
        for segment, start in zip('ab', item['starts']):
            label = item['id'] + '_' + segment
            folder = OUT / 'clips' / label
            folder.mkdir(parents=True, exist_ok=True)
            for rate, filename in [(48000,'original.wav'), (8000,'input.wav')]:
                command([args.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y',
                         '-ss',start,'-i',original,'-t',manifest['clip_seconds'],'-vn','-ac','1',
                         '-ar',rate,'-c:a','pcm_s16le',folder/filename])
            clips.append({'id':label,'source':item['id'],'language':item['language'],
                          'speaker':item['speaker'],'voice':item['voice'],'start_seconds':start,
                          'seconds':manifest['clip_seconds'],'condition':'natural'})
        print('Prepared', item['id'], flush=True)
    for stress in manifest['stress']:
        base = next(c for c in clips if c['id'] == stress['base'])
        clip = dict(base, id=base['id']+'_'+stress['condition'], condition=stress['condition'])
        folder = OUT / 'clips' / clip['id']
        folder.mkdir(parents=True, exist_ok=True)
        samples = read_pcm(OUT / 'clips' / base['id'] / 'input.wav')
        if stress['condition'] == 'quiet_minus24dB':
            samples = [round(x * 10**(-24/20)) for x in samples]
        else:
            rng = random.Random(20261023)
            noise = [rng.gauss(0,1) for _ in samples]
            gain = (sum(x*x for x in samples)/sum(x*x for x in noise))**.5 * 10**(-15/20)
            samples = [max(-32768,min(32767,round(x+gain*n))) for x,n in zip(samples,noise)]
        write_pcm(folder/'input.wav', samples)
        # For stress cases, 'original' means the modified signal fed to encoder.
        write_pcm(folder/'original.wav', samples)
        clips.append(clip)
    for clip in clips:
        folder = OUT / 'clips' / clip['id']
        command([args.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-i',folder/'input.wav',
                 '-af','apad=pad_dur=0.04','-c:a','libspeex','-ar','8000','-ac','1','-b:a','8000',
                 '-abr','0','-vad','0','-dtx','0','-frames_per_packet','1','-f','ogg',folder/'encoded.ogg'])
        clip['frames'] = extract(folder/'encoded.ogg', folder/'encoded.spxraw')
        clip['input_sha256'] = digest((folder/'input.wav').read_bytes())
        clip['encoded_sha256'] = digest((folder/'encoded.spxraw').read_bytes())
        (OUT/'streams').mkdir(exist_ok=True)
        shutil.copyfile(folder/'encoded.spxraw', OUT/'streams'/(clip['id']+'.spxraw'))
        print('Encoded', clip['id'], clip['frames'], 'frames', flush=True)
    output = {'sources':sources,'clips':clips,'ffmpeg':subprocess.check_output([args.ffmpeg,'-version'],text=True).splitlines()[0],
              'changes':'8-second excerpts, mono/resampled; stress variants explicitly attenuated or mixed with seeded white noise; Speex NB3 CBR 8kbps, 40ms zero tail.'}
    (OUT / 'corpus.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    attribution = ['# Speech source credits\n', output['changes'] + '\n',
                   'Each excerpt and its decoded derivatives retain the source license. Article author credits are linked by each archived source page.\n']
    for s in sources:
        attribution += [f"## {s['id']}: {s['title']}\n", f"Speaker: {s['speaker']}. {s.get('additional_credits','')}\n",
                        f"Source and article credits: {s['page']}\n", f"License: {s['license']} ({s['license_url']})\n"]
    (OUT/'ATTRIBUTION.md').write_text('\n'.join(attribution),encoding='utf-8')
    print('Prepared',len(clips),'clips;',sum(c['frames'] for c in clips),'frames',flush=True)


if __name__ == '__main__':
    main()
