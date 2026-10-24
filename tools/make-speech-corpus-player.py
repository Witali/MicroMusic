"""Create an ignored listening gallery from prepared bilingual speech tests."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_file(root, relative):
    root = root.resolve()
    path = (root/relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Audio path escapes its declared input root')
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True, type=Path)
    p.add_argument('--references-root', required=True, type=Path)
    p.add_argument('--benchmark', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    manifest = json.loads(a.manifest.read_text(encoding='utf-8'))
    if manifest.get('schema') != 'micromusic-speech-corpus-v1':
        p.error('Expected prepared bilingual corpus manifest')
    rows = {}
    if a.benchmark:
        report = json.loads(a.benchmark.read_text(encoding='utf-8'))
        if report['manifest_sha256'] != digest(a.manifest):
            raise ValueError('Benchmark belongs to a different prepared corpus')
        rows = {row['metadata']['id']: row for row in report['clips']}
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output/'audio').mkdir(exist_ok=True)
    esc = lambda value: html.escape(str(value), quote=True)
    sources = {source['id']: source for source in manifest['sources']}
    parts = ['''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Русская и английская речь — тесты кодека</title><style>body{font:17px/1.5 system-ui;background:#101823;color:#e8eff9;max-width:1200px;margin:auto;padding:24px}p{color:#c3d2e4}h1{font-size:2rem}h2{margin-top:2rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:18px}article{background:#1a2838;border:1px solid #3a4a60;border-radius:14px;padding:18px}h3{margin-top:0}audio{width:100%}label{display:grid;gap:8px;margin:14px 0}a{color:#8dd4ff}.tag{display:inline-block;border:1px solid #52718c;border-radius:8px;padding:2px 8px;font-size:.85rem}small{display:block;color:#b6c6db}summary{cursor:pointer}</style><h1>Русская и английская речь</h1><p>8 дикторов, по два мужских и два женских голоса на каждый язык. Использован уже собранный в проекте набор Speex, с исходными записями и их атрибуцией. Здесь короткие окна 2,048 с; они могут обрезать слово. Полные отрывки около 8 с тоже подготовлены.</p><p>Уровень звука сохранён. Тихие примеры остаются тихими; нормализация не применяется. Базовый HQ4 здесь — автоматическая инициализация точной численной модели без дополнительного поиска. Его качество не является пределом кодека. Новые прошивки в AVR ещё не проверены.</p>''']
    for language, title in (('ru', 'Русская речь'), ('en', 'English speech')):
        parts += [f'<h2>{title}</h2><div class="grid">']
        for entry in manifest['clips']:
            if entry['variant'] != 'center2048' or entry['language'] != language:
                continue
            identifier = entry['id']
            if not identifier or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in identifier):
                raise ValueError('Unsafe corpus recording ID')
            reference = local_file(a.references_root, entry['reference'])
            if digest(reference) != entry['reference_sha256']:
                raise ValueError('Changed prepared reference: '+identifier)
            target = a.output/'audio'/(identifier+'-reference.wav')
            shutil.copyfile(reference, target)
            source = sources[entry['source_id']]
            condition = {'natural':'Обычная запись', 'quiet_minus24dB':'Тихо: −24 дБ',
                         'white_noise_15dB':'Шум: SNR 15 дБ'}.get(entry['condition'], entry['condition'])
            voice = {'male':'мужской голос', 'female':'женский голос'}.get(entry['voice'], entry['voice'])
            parts += [f'<article><h3>{esc(entry["speaker"])}</h3><span class="tag">{esc(voice)}</span> <span class="tag">{esc(condition)}</span>',
                f'<p>{esc(source.get("title",entry["source_id"]))}<small>{esc(identifier)} · {entry["source_start_seconds"]:.3f}–{entry["source_end_seconds"]:.3f} с исходной записи</small></p>',
                f'<label>Оригинал, 7500 Гц<audio controls preload="none" src="audio/{esc(target.name)}"></audio></label>']
            row = rows.get(identifier)
            if row and row['status'] == 'complete':
                if row['metadata']['reference_sha256'] != entry['reference_sha256']:
                    raise ValueError('Benchmark reference differs: '+identifier)
                decoded = local_file(a.benchmark.parent, f'models/{identifier}/decoded.wav')
                audio_target = a.output/'audio'/(identifier+'-hq4.wav')
                shutil.copyfile(decoded, audio_target)
                parts += [f'<label>Базовый HQ4, исходный уровень<audio controls preload="none" src="audio/{esc(audio_target.name)}"></audio></label>',
                    f'<p>STOI {row["metrics"]["stoi"]:.3f} · eSTOI {row["metrics"]["estoi"]:.3f}<small>Данные {row["size"]["stream_bytes"]} байт; оценка Flash {row["size"]["estimated_flash_bytes"]} байт. Без AVR-квалификации.</small></p>']
            elif row:
                parts.append(f'<p>Базовый прогон: {esc(row["status"])}. Причина сохранена в отчёте.</p>')
            parts += [f'<details><summary>Источник и условия использования</summary><p><a href="{esc(source["page"])}">{esc(source.get("title",source["id"]))}</a><br>{esc(source["license"])}<br>{esc(source.get("additional_credits",""))}</p></details></article>']
        parts.append('</div>')
    parts += ['<p>Группы настройки и оценки разделены по дикторам. Сводные оценки не заменяют проверку каждой записи и трёх прежних публичных примеров.</p>',
        '<script>for(const a of document.querySelectorAll("audio"))a.addEventListener("play",()=>{for(const b of document.querySelectorAll("audio"))if(a!==b)b.pause()})</script></html>']
    (a.output/'index.html').write_text(''.join(parts), encoding='utf-8', newline='\n')
    print(json.dumps(dict(output=str(a.output/'index.html'), examples=sum(c['variant']=='center2048' for c in manifest['clips']), benchmark_loaded=bool(rows))))


if __name__ == '__main__':
    main()
