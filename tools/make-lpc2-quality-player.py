"""Review source, current codec, LPC2 and automatically selected excitation.

This creates an ignored listening artifact; quality thresholds are engineering
selection criteria, never a claim that subjective naturalness has been proved.
"""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import sys

import numpy as np
from scipy.signal import butter, sosfilt
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from lpx3_entropy import pack, unpack


def sha(data):
    return hashlib.sha256(data).hexdigest()


def local(relative):
    result = (ROOT/relative).resolve()
    if not result.is_relative_to(ROOT):
        raise ValueError('Review source escapes the development checkout')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',required=True,type=Path,help='Review configuration with recordings, relative reference/report paths and common targets')
    p.add_argument('--output',required=True,type=Path)
    a = p.parse_args()
    config = json.loads(a.manifest.read_text(encoding='utf-8'))
    targets = config.get('targets',dict(stoi=.98,estoi=.95,raw_snr_db=26.))
    a.output.mkdir(parents=True,exist_ok=True)
    for folder in ('audio','containers','reports'):
        (a.output/folder).mkdir(exist_ok=True)
    esc = lambda value: html.escape(str(value),quote=True)
    sections = []
    results = dict(schema='lpc2-quality-listening-selection-v1',targets=targets,recordings=[],
        input_manifest_sha256=sha(a.manifest.read_bytes()),
        selection='Smallest complete stored container meeting all common targets; otherwise highest waveform SNR, explicitly marked below target',
        listening='Same 70Hz highpass, one RMS match to original, common peak scale per recording; raw WAVs linked separately',
        decoder_code_included=False,avr_implemented=False)
    for entry in config['recordings']:
        ident = entry['id']
        if not ident or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in ident):
            raise ValueError('Unsafe recording ID')
        reference_path, report_path = local(entry['reference']),local(entry['report'])
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if sha(reference_path.read_bytes()) != report['reference_sha256']:
            raise ValueError('Review original and codec report disagree')
        reference,sr = sf.read(reference_path,dtype='float64')
        if sr != report['sample_rate'] or len(reference) != report['samples']:
            raise ValueError('Review sample rate/count changed')
        profiles = {name:dict(row) for name,row in report['profiles'].items()}
        for extra in entry.get('additional_profiles',[]):
            extra_report_path=local(extra['report'])
            extra_report=json.loads(extra_report_path.read_text(encoding='utf-8'))
            if extra_report['reference_sha256'] != report['reference_sha256']:
                raise ValueError('Additional profile uses a different original')
            for name,row in extra_report['profiles'].items():
                row=dict(row)
                if name in profiles:
                    if row['container_sha256'] != profiles[name]['container_sha256']:
                        raise ValueError('Duplicate profile has changed encoded bytes')
                    continue
                row.update(row.pop('metrics',{}))
                row['audio']=os.path.relpath(extra_report_path.parent/row.get('audio',name+'.wav'),report_path.parent)
                row['_container_path']=str(extra_report_path.parent/row['container'])
                profiles[name]=row
        alternatives=[]
        for name,row in profiles.items():
            if name == 'lpc2-improved':
                continue
            source=Path(row.get('_container_path',report_path.parent/row['container'])).resolve()
            if not source.is_relative_to(ROOT):
                raise ValueError('Container outside development checkout')
            raw=source.read_bytes()
            if sha(raw) != row['container_sha256']:
                raise ValueError('Changed excitation container')
            if raw[:4] in (b'LPX3',b'LPX4'):
                stored,storage=pack(raw)
                assert unpack(stored)==raw
            else:
                stored=raw
                storage=dict(method='original-other-format',stored_bytes=len(raw),original_bytes=len(raw),exact_original_restored=True)
            filename=ident+'-'+name+'.bin'
            if any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-. ' for c in filename):
                raise ValueError('Unsafe profile name')
            (a.output/'containers'/filename).write_bytes(stored)
            passed=all(np.isfinite(row[key]) and row[key]>=minimum for key,minimum in targets.items())
            alternatives.append(dict(name=name,row=row,storage=storage,passed=passed,download=filename))
        if not alternatives:
            raise ValueError('No coded excitation profile for '+ident)
        eligible=[item for item in alternatives if item['passed']]
        selected=min(eligible,key=lambda item:item['storage']['stored_bytes']) if eligible else max(alternatives,key=lambda item:item['row']['raw_snr_db'])
        names=[('Original',reference)]
        before=next(iter(report.get('before',{}).items()),None)
        if before:
            names.append(('Before',sf.read(report_path.parent/before[1]['audio'],dtype='float64')[0]))
        names.append(('LPC2 Improved',sf.read(report_path.parent/profiles['lpc2-improved']['audio'],dtype='float64')[0]))
        preferred=entry.get('preferred_profile','lpx4-6bit')
        names.append((preferred,sf.read(report_path.parent/profiles[preferred]['audio'],dtype='float64')[0]))
        if selected['name'] != preferred:
            names.append((selected['name'],sf.read(report_path.parent/selected['row']['audio'],dtype='float64')[0]))
        if any(audio.shape!=reference.shape or not np.isfinite(audio).all() for _,audio in names):
            raise ValueError('Listening audio duration/nonfinite mismatch')
        hp=butter(2,70,fs=sr,btype='highpass',output='sos')
        filtered=[sosfilt(hp,audio) for _,audio in names]
        target_rms=np.sqrt(np.mean(filtered[0]**2))
        matched=[audio*target_rms/(np.sqrt(np.mean(audio**2))+1e-20) for audio in filtered]
        gain=.88/max(1e-20,max(float(np.max(abs(audio))) for audio in matched))
        labels=['Оригинал']+(['Прежний результат'] if before else [])+['LPC2 Improved','Кодированное возбуждение, 6 бит']
        if selected['name'] != preferred:
            labels.append('Кандидат по общим порогам: '+selected['name'])
        controls=[]
        for i,((name,raw),audio,label) in enumerate(zip(names,matched,labels)):
            filename=f'{ident}-{i}.wav'
            sf.write(a.output/'audio'/filename,audio*gain,sr,subtype='FLOAT')
            rawfile=f'{ident}-{i}-raw.wav'
            sf.write(a.output/'audio'/rawfile,raw,sr,subtype='FLOAT')
            controls.append(f'<label>{esc(label)}<audio controls preload="none" src="audio/{esc(filename)}"></audio></label>')
        sequence=np.concatenate([np.r_[audio*gain,np.zeros(round(.3*sr))] for audio in matched])
        sequence_name=ident+'-comparison.wav'
        sf.write(a.output/'audio'/sequence_name,sequence,sr,subtype='FLOAT')
        summary=dict(id=ident,listening_baseline=preferred,selected=selected['name'],quality_targets_met=bool(eligible),
            selected_storage=selected['storage'],selected_metrics={key:selected['row'][key] for key in ('stoi','estoi','raw_snr_db','spectrogram_loss')},
            alternatives=[dict(name=item['name'],quality_targets_met=item['passed'],storage=item['storage'],
                metrics={key:item['row'][key] for key in ('stoi','estoi','raw_snr_db','spectrogram_loss')}) for item in alternatives],
            comparison_audio='audio/'+sequence_name,reference_sha256=report['reference_sha256'])
        results['recordings'].append(summary)
        (a.output/'reports'/(ident+'.json')).write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
        quality=selected['row'];kbps=selected['storage']['stored_bytes']*8*sr/len(reference)/1000
        caption=f'{selected["name"]}: STOI {quality["stoi"]:.3f}, eSTOI {quality["estoi"]:.3f}, SNR {quality["raw_snr_db"]:.1f} дБ; {selected["storage"]["stored_bytes"]} байт, {kbps:.1f} кбит/с.'
        rows=''.join(f'<tr><td>{esc(item["name"])}</td><td>{item["row"]["container_bytes"]}</td><td><a href="containers/{esc(item["download"])}">{item["storage"]["stored_bytes"]}</a></td><td>{item["row"]["stoi"]:.3f}</td><td>{item["row"]["raw_snr_db"]:.1f}</td></tr>' for item in alternatives)
        credit=f'<p><a href="{esc(entry["source_page"])}">Источник</a> · {esc(entry.get("license",""))}</p>' if entry.get('source_page') else ''
        sections.append(f'<article id="{esc(ident)}"><h2>{esc(entry.get("title",ident))}</h2><p>{esc(entry.get("speaker",""))} · {esc(entry.get("language",""))}</p><div class="players">'+''.join(controls)+f'</div><p><a href="audio/{esc(sequence_name)}">Всё сравнение подряд</a></p><p>Кандидат по численным порогам: {esc(caption)}</p>'+('' if eligible else '<p>Общие целевые пороги пока не достигнуты; показан наиболее точный из готовых вариантов.</p>')+f'<details><summary>Размер и точность вариантов</summary><table><tr><th>Профиль</th><th>До упаковки</th><th>После упаковки, байты</th><th>STOI</th><th>SNR, дБ</th></tr>{rows}</table><p>Полные контейнеры с параметрами и заголовками; исполняемый декодер не учтён. AVR ещё не проверен.</p><a href="reports/{esc(ident)}.json">Измерения JSON</a> · <a href="audio/{esc(ident)}-{len(names)-1}-raw.wav">Последний WAV без обработки уровня</a></details>{credit}</article>')
    page='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LPC2 — сравнение качества речи</title><style>body{font:17px/1.5 system-ui;background:#101823;color:#e9f0f8;max-width:1400px;margin:auto;padding:24px}p{color:#c4d2e3}article{background:#1b2838;border:1px solid #3a5067;border-radius:15px;padding:22px;margin:24px 0}.players{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px}label{display:grid;gap:8px}audio{width:100%}a{color:#8ed6ff}table{border-collapse:collapse}td,th{text-align:left;padding:8px 16px;border-bottom:1px solid #4b6075}summary{cursor:pointer}</style><h1>Качество речи: LPC2 и точное возбуждение</h1><p>Сравнение при одинаковых исходнике, времени и частоте 7500 Гц. Это исследовательские эталоны качества: потоки возбуждения здесь НЕ помещаются в 1 КБ. Обязательный бюджет конечной ATtiny13A-прошивки — 1024 байта вместе с декодером; её разработка ведётся отдельно. LPC2 Improved использует свой стандартный источник; новый вариант передаёт возбуждение, автоматически подобранное по оригиналу.</p><p>Кнопки выровнены по громкости: одинаковый фильтр 70 Гц, один RMS на всю запись и общий запас пика. Сырые файлы доступны отдельно. Выбор наименьшего потока выполняется по общим численным порогам; естественность оценивается прослушиванием.</p>'''
    page+='<p>На Винни 6-битный вариант выбран на слух как лучший: он сохранён отдельной кнопкой в каждой записи. Более компактный кандидат рядом требует отдельного прослушивания и не заменяет этот эталон автоматически. Общие пороги кандидата: '+esc(targets)+'.</p>'
    page+=''.join(sections)+'<script>for(const a of document.querySelectorAll("audio"))a.addEventListener("play",()=>{for(const b of document.querySelectorAll("audio"))if(a!==b)b.pause()})</script></html>'
    (a.output/'index.html').write_text(page,encoding='utf-8',newline='\n')
    (a.output/'selection.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(recordings=len(results['recordings']),targets_met=sum(r['quality_targets_met'] for r in results['recordings']),output=str(a.output/'index.html'))))


if __name__=='__main__':
    main()
