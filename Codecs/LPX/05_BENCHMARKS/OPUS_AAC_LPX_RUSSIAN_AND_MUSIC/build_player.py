import base64, html, json, pathlib
from collections import defaultdict
BASE=pathlib.Path(__file__).resolve().parent
ROWS=json.loads((BASE/'comparison.json').read_text())
index={(r['sample'],r['codec'],r.get('target_kbps')):r for r in ROWS}
samples={
 'chego':('«Чего тебе нужно?»',{
  'Оригинал':BASE/'data/chego_reference.wav',
  'LPX4 Q0':BASE/'data/chego_lpx4.wav',
  'LPX3 Rice v7':BASE/'data/chego_lpx3_rice.wav',
  'Opus 24 кбит/с':BASE/'encoded/chego_opus_24.s16',
  'Opus 32 кбит/с':BASE/'encoded/chego_opus_32.s16',
  'AAC-LC 32 кбит/с':BASE/'encoded/chego_aac_32.s16',
 }),
 'otvet':('«Что ж ты не отвечаешь?»',{
  'Оригинал':BASE/'data/otvet_reference.wav',
  'LPX4 Q0':BASE/'data/otvet_lpx4.wav',
  'LPX3 Rice v7':BASE/'data/otvet_lpx3_rice.wav',
  'Opus 24 кбит/с':BASE/'encoded/otvet_opus_24.s16',
  'Opus 32 кбит/с':BASE/'encoded/otvet_opus_32.s16',
  'AAC-LC 32 кбит/с':BASE/'encoded/otvet_aac_32.s16',
 })
}
import numpy as np, soundfile as sf, io
rows=[]
for key,(title,opts) in samples.items():
 variants=[]
 for name,file in opts.items():
  if not file.exists():continue
  if file.suffix=='.s16':
   y=np.fromfile(file,dtype='<i2'); stream=io.BytesIO(); sf.write(stream,y,8000,format='WAV',subtype='PCM_16'); raw=stream.getvalue()
  else:raw=file.read_bytes()
  metric=None
  if name=='LPX4 Q0':metric=index.get((key,'LPX4 Q0',None))
  elif name=='LPX3 Rice v7':metric=index.get((key,'LPX3 Rice v7',None))
  elif name=='Opus 24 кбит/с':metric=index.get((key,'OPUS',24))
  elif name=='Opus 32 кбит/с':metric=index.get((key,'OPUS',32))
  elif name=='AAC-LC 32 кбит/с':metric=index.get((key,'AAC',32))
  variants.append({'name':name,'b64':base64.b64encode(raw).decode(),'ser':round(metric['ser_db'],2) if metric and 'ser_db' in metric else None,'stoi':round(metric['stoi'],4) if metric and 'stoi' in metric else None,'bytes':metric['bytes'] if metric else None})
 rows.append({'title':title,'variants':variants})
css='''body{font-family:system-ui,-apple-system,sans-serif;max-width:850px;margin:auto;padding:2rem;color:#e5e7eb;background:#0b1220}h1{font-size:1.5rem}section{background:#172337;border:1px solid #334155;border-radius:14px;padding:20px;margin-bottom:20px}label{display:block;padding:8px 0}.sound{display:grid;grid-template-columns:minmax(170px,1fr) minmax(110px,1fr) auto;gap:12px;align-items:center;border-top:1px solid #334155;padding:12px 0}.sound:first-of-type{border:0}audio{width:100%;max-width:300px}.meta{font-size:.82rem;color:#b6c3d6}.warn{font-size:.9rem;color:#b6c3d6;padding:12px;border-left:3px solid #c79a40}a{color:#9acaff}@media(max-width:600px){.sound{grid-template-columns:1fr;gap:4px}}'''
out=['<!doctype html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MicroMusic LPX / Opus / AAC — A/B</title><style>'+css+'</style></head><body>','<h1>MicroMusic — сравнение LPX4, LPX3, Opus и AAC</h1>',
'<p class="warn">Все фразы из приватных тестов; результаты нельзя считать проверкой на независимой речи. PCM 8 кГц, моно. SER сравнивает восстановленный сигнал с исходной записью без дополнительной подгонки уровня.</p>']
for entry in rows:
 out.append('<section><h2>'+html.escape(entry['title'])+'</h2>')
 for row in entry['variants']:
  meta=('Исходный PCM' if row['bytes'] is None else f"{row['bytes']} Б · SER {row['ser']:.2f} дБ · STOI {row['stoi']:.4f}")
  out.append('<div class="sound"><div><strong>'+html.escape(row['name'])+'</strong><div class="meta">'+html.escape(meta)+'</div></div><audio controls preload="none" src="data:audio/wav;base64,'+row['b64']+'"></audio></div>')
 out.append('</section>')
out.append('<p class="meta">Opus использует настройку application=audio. AAC-LC — штатный кодировщик FFmpeg. Битрейты в имени файла целевые, реальная длина контейнера учитывается в размерах.</p></body></html>')
(BASE/'MicroMusic_AB_comparison_PRIVATE.html').write_text('\n'.join(out),encoding='utf-8')
print(BASE/'MicroMusic_AB_comparison_PRIVATE.html', (BASE/'MicroMusic_AB_comparison_PRIVATE.html').stat().st_size)
