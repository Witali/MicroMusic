"""Generate the shared, path-free inventory of public speech compression assets."""
import argparse
import hashlib
import json
from pathlib import Path
import wave

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
def link(path):return f'[{path}](../{path})'


def document():
    definitions=read('web-player/speech-examples.json')
    nano=read('web-player/firmware-atmega328p.json')
    extra=ROOT/'web-player/firmware-attiny13a-speech-extra.json'
    tiny=read('web-player/hq4-firmware.json')['entries']+(read('web-player/firmware-attiny13a-speech-extra.json')['entries'] if extra.exists() else [])
    rows=['# Речевые примеры: исходники, сжатие и прошивки','',
        'Общий порядок задаёт '+link('web-player/speech-examples.json')+'. Качества относятся к выбранной фразе и микроконтроллеру. ATtiny13A использует один выбранный образ; LPX имеет собственные варианты качества.','',
        '## Исходные записи','',
        'Используются только уже открытые записи проекта. Новые варианты не обрезают фразы и не меняют скорость. Изменение частоты дискретизации сохраняет время; Tiny добавляет только нулевой хвост последнего 64-отсчётного блока.','',
        '| № | Фраза | Исходный WAV | Гц / отсчётов | SHA-256 |','| --- | --- | --- | --- | --- |']
    for example in definitions['examples']:
        path='web-player/'+example['originalAudioUrl']
        with wave.open(str(ROOT/path),'rb') as audio:rate,count=audio.getframerate(),audio.getnframes()
        rows.append(f"| {example['order']} | {example['title']} | {link(path)} | {rate} / {count} | `{hashlib.sha256((ROOT/path).read_bytes()).hexdigest()}` |")
    rows+=['','## LPX: каждый сжатый файл','',
        'Новые первые три фразы: '+link('tools/prepare-shared-speech.py')+' → `speech_v4.encode` (профиль 4 или 6, `pre=13926`, `bandwidth=0.97`, `allow_zero_scale=False`) → точная переупаковка `speech_compact.repack` в LPX v5. Вход 7500 → 8000 Гц через `scipy.signal.resample_poly(16, 15)`, PCM16, без усиления. Каждый результат проверяется по независимой модели и двум нативным декодерам: общему и v5-only.','',
        'Варианты bread сохранены из прежнего набора побайтно. Их прежние скрипты, параметры и экспериментальный формат S15 описаны в '+link('web-player/audio/lpx-bread/README.md')+'. Новая сборка Nano переиспользует эти потоки; S15 на Nano не заявлен.','',
        '| Фраза | LPX-файл | Формат / профиль | Байт | Связанный WAV | Скрипт |','| --- | --- | --- | ---: | --- | --- |']
    previews=[*read('web-player/audio/lpx-speech/manifest.json')['clips'],dict(read('web-player/audio/lpx-bread/manifest.json'),clipId='bread')]
    for clip in previews:
        for variant in clip['variants']:
            script='tools/prepare-shared-speech.py' if clip['clipId']!='bread' else ('Codecs/LPX/research/lpx-s15-2026-11-01/README.md' if variant['id']=='low15' else 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/encode_speech_voice.py')
            rows.append(f"| {clip['clipId']} | {link('web-player/'+variant['stream'])} | {'S15 v8' if variant['id']=='low15' else 'LPX v5'} / {variant['profile']} | {variant['bytes']} | {link('web-player/'+variant['audio'])} | {link(script)} |")
    rows+=['','WAV в этой таблице — точные 8-битные PWM-отсчёты декодера в PCM16: `(duty - 128) * 256`. Они служат превью ATtiny88 и Nano, не являются записью аналогового выхода платы.','',
        '## Arduino Nano: полные HEX','',
        'Сборщик '+link('tools/build-nano-speech-catalog.py')+' встраивает указанный LPX в существующий `AVR_V5_PLAYER`: ATmega328P, 16 МГц, FIFO 256 / prefill 192, D3 / OC2B, 8 кГц. ASM включается отдельным `--enable-asm`; без него выбран C. Все восемь сохранённых HEX проверены в simavr 1.6 с активными IRQ: весь поток, точное совпадение с WAV и ноль underruns. Физическая плата не проверялась.','',
        '| HEX | LPX | Код / полный Flash, Б | Static SRAM, Б | Отсчётов / пропусков |','| --- | --- | ---: | ---: | --- |']
    for variant in nano['variants']:
        rows.append(f"| {link('web-player/'+variant['source'])} | {variant['clipId']} / {variant['id']} | {variant['programFlashBytes']} / {variant['flashBytes']} | {variant['staticSramBytes']} | {variant['timing']['playedSamples']} / {variant['timing']['underruns']} |")
    tiny88=read('web-player/firmware-lpx-attiny88.json')
    rows+=['','## ATtiny88: LPX в 512 байтах RAM','',
        'Сборщик '+link('tools/build-tiny88-speech-catalog.py')+' переиспользует полные LPX-потоки и WAV без перекодирования. Выбран существующий AVR25 ASM без аппаратного MUL, профиль SRAM512, FIFO 24 / prefill 18 и `--mul16-unroll 2`. Для каждой полной прошивки проверены все PWM-отсчёты против независимого C-декодера и уже сохранённого WAV, активные таймеры/IRQ, ноль underruns и положительный запас стека. Переключаемые C-арифметика и C-ISR сохранены; C-арифметика не заявлена как режим реального времени. Физическая плата не измерялась.','',
        'Полный HEX ограничен **8192 байтами Flash**, включая звук. USB-загрузчик MH-ET LIVE допускает только **6012 байт** приложения: при превышении страница показывает предупреждение, а скачивание остаётся доступным для загрузки через ISP. Образы больше 6 КБ также требуют ISP; превышение 8 КБ отклоняется сборщиком. Выход этого плеера — **D9 / PB1 / OC1A**, 62,5 кГц PWM и 8 кГц PCM при 16 МГц. Speex для ATtiny88 не добавлен.','',
        '| Фраза / профиль | HEX | Код / звук / полный Flash, Б | Static / пик стека / запас, Б | USB-загрузчик |','| --- | --- | ---: | ---: | --- |']
    for variant in tiny88['variants']:
        rows.append(f"| {variant['clipId']} / {variant['id']} | {link('web-player/'+variant['source'])} | {variant['programFlashBytes']} / {variant['flashBytes']-variant['programFlashBytes']} / {variant['flashBytes']} | {variant['staticSramBytes']} / {variant['peakStackBytes']} / {variant['stackMarginBytes']} | {'Помещается' if variant['fitsStandardBootloader'] else 'Нужен ISP'} |")
    rows+=['','Ограничения и воспроизведение проверок: '+link('Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/README.md')+'. Численные сравнения памяти, Flash и времени: '+link('Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/budget-measurements.json')+'. Измеряемый запас использует соглашение наблюдателя: `static + peakStack + margin = 511`.','',
        '```text','python tools/build-tiny88-speech-catalog.py --retain --queue 24 --mul16-unroll 2','```','',
        'На Windows добавьте `--wsl Ubuntu`, используя установленные в WSL AVR-GCC 7.3.0, g++, simavr 1.6 и libelf. `--retain` сохраняет проверенные HEX и каталог локально; команда не выполняет push, публикацию или прошивку платы.']
    speex=read('web-player/firmware-speex-atmega328p.json')
    rows+=['','## Speex на Arduino Nano: три фразы, три битрейта','',
        'Сборщик '+link('tools/build-speex-nano-catalog.py')+' использует те же полные открытые исходники первых трёх фраз. FFmpeg / libspeex 1.2.1 кодирует CBR с complexity 10: NB 2,15 кбит/с при 8 кГц, WB 3,95 и 9,8 кбит/с при 16 кГц. VAD, DTX и ABR выключены. Ресэмплирование сохраняет длительность и уровень; добавляется 80 мс нулевого хвоста и выравнивание до полного кадра, задержка кодека не вырезается. Ogg-заголовки и комментарии не публикуются.','',
        'Исходники записаны при 7500 Гц: режим WB с выходом 16 кГц не восстанавливает отсутствующие в них высокие частоты. Номинальные битрейты отличаются от хранения с выравниванием пакетов по байтам: 2,4 / 4,0 / 10,0 кбит/с соответственно.','',
        'PCM захватывается из исполняемого AVR ASM-декодера, затем полный связанный плеер проверяется против этого захвата с активными таймерами и IRQ в AVR8js 0.21.1. WAV содержит все реальные PWM-отсчёты `(duty - 128) * 256`, включая задержку и хвост. Это проверка транспортировки и тайминга; независимые проверки арифметики кодека сохранены в '+link('Codecs/Speex/AVR/reports/prepared-admission.json')+'. Полный C-декодер при подготовке этих примеров не исполняется. Аналоговый выход физической платы не измерялся.','',
        'Все опубликованные прошивки используют **D3 / PD3 / OC2B**, как LPX: PWM 62,5 кГц, PCM 8 или 16 кГц. При сборке можно выбрать `--pwm-pin 3` или `--pwm-pin 9` (`SPEEX_AVR_PWM_PIN=3/9`). Сборщик каталога по умолчанию выбирает D3; низкоуровневые сборщики сохраняют прежний D9. Выбор арифметики C/ASM независим от выбора контакта.','',
        '| Фраза / профиль | Сжатый поток | PWM WAV | HEX | Код / полный Flash, Б | Static / свободная SRAM на пике, Б | Отсчётов / пропусков |',
        '| --- | --- | --- | --- | ---: | ---: | --- |']
    for variant in speex['variants']:
        rows.append(f"| {variant['clipId']} / {variant['label']} | {link('web-player/'+variant['stream'])} | {link('web-player/'+variant['audio'])} | {link('web-player/'+variant['source'])} | {variant['programFlashBytes']} / {variant['flashBytes']} | {variant['staticSramBytes']} / {variant['freeSramAtPeak']} | {variant['samples']} / {variant['timing']['underruns']} |")
    rows+=['','Для воспроизведения нужны AVR-GCC 7.3.0 проекта, Node.js, зависимости AVR8js из `Codecs/Speex/AVR` и FFmpeg с libspeex. Контрольные суммы исходников, точных потоков, WAV и HEX, а также результаты IRQ-проверок находятся в '+link('web-player/firmware-speex-atmega328p.json')+'.','',
        '```text','python tools/build-speex-nano-catalog.py --avr-gcc /path/to/avr-gcc --node /path/to/node --pwm-pin 3 --publish','```']
    rows+=['','## ATtiny13A: выбранные образы','',
        'Основные три образа сохранены в '+link('web-player/hq4-firmware.json')+'; добавленная фраза — в '+link('web-player/firmware-attiny13a-speech-extra.json')+'. Каталоги содержат полный Flash HEX и при необходимости EEPROM HEX, контрольные суммы и пути исходников.','',
        '| Фраза | Кодек | Сохранённый источник | Скрипт сборки / подбора | Flash / EEPROM, Б |','| --- | --- | --- | --- | ---: |']
    for entry in tiny:
        phrase=entry['audioReferenceId']
        if phrase=='bread':source='ATtiny13A/Sound/research/shared-speech/bread-model.json';script='tools/build-shared-tiny-speech.py'
        elif phrase=='vinni':source='ATtiny13A/Sound/codec/release/vinni/speech.hq';script='tools/build-hq4-oneshot.py'
        else:source=f'ATtiny13A/Sound/research/tiny-speech/{phrase}/model.json';script='tools/build-tiny-speech.py'
        rows.append(f"| {phrase} | {entry['codec']} | {link(source)} | {link(script)} | {entry['flashBytes']} / {entry['eepromBytes']} |")
    selection=ROOT/'ATtiny13A/Sound/research/shared-speech/bread-selection.json'
    if selection.exists():
        report=read(str(selection.relative_to(ROOT)));chosen=report['selected']
        rows+=['',f"Для bread сравнивались оба режима высоты, словари 1/2/4/8 периодов, региональное удержание параметров и по {report['proposalsPerPitchMode']} предложений точного поиска на режим. Выбран `{chosen['mode']}`: {chosen['flashBytes']} Б Flash + {chosen['eepromBytes']} Б EEPROM. Полная матрица, критерий выбора и проверки сохранены в "+link(str(selection.relative_to(ROOT)))+'. Субъективное превосходство автоматически не утверждается; варианты для прослушивания находятся в локальном `build/shared-speech/`.']
        rows+=['',
            'Необязательное первоначальное измерение воспроизводит '+link('tools/probe-tiny-speech-budget.py')+': открытый bread-исходник, словарь 8 периодов, 2 старта, ассемблированный кандидат 1074 Б Flash + 64 Б EEPROM. Он превышает Flash; это измерение размера, без допуска воспроизведения. Результаты остаются в `build/shared-speech/tiny-initial-probe/` и не меняют выбранную прошивку.','',
            '```text','python tools/probe-tiny-speech-budget.py --avr-bin /path/to/avr/bin','```']
        noise_path=ROOT/'ATtiny13A/Sound/research/shared-speech/bread-noise-refinement.json'
        if noise_path.exists():
            noise=read(str(noise_path.relative_to(ROOT)));selected=noise['selected'];initial=noise['initialDenoised']
            rows+=['','### Подбор менее шумного варианта','',
                'После замечания о шуме выполнен отдельный поиск '+link('tools/refine-shared-tiny-noise.py')+'. Он сравнивает исходник и точный PWM без подгонки громкости, на общей временной шкале: STFT 256 и 1024, уровни остаточного шума, варианты высоты и ограниченное уточнение словаря/параметров. Порог разборчивости и формула спектральной оценки сохранены в '+link(str(noise_path.relative_to(ROOT)))+'.', '',
                f"Проверено {noise['candidateCount']} помещающихся кандидатов; {noise['refinementSteps']} шагов уточнения, seed {noise['seed']}. Начальный победитель прежней оценки (1022 Б) сохранён в "+link('ATtiny13A/Sound/research/shared-speech/bread-search-model.json')+'. Текущий файл `bread-model.json` содержит выбранную спектральную модель.','',
                '| Этап спектрального поиска | Flash, Б | STOI | Log-ошибка спектра | Избыток ВЧ-энергии |','| --- | ---: | ---: | ---: | ---: |']
            for label,value in [('Первичное уменьшение шума',initial),('Текущий выбранный образ',selected)]:
                rows.append(f"| {label} | {value['flashBytes']} | {value['stoi']:.6f} | {value['rawLogSpectralError']:.6f} | {value['highBandExcess']:.8f} |")
            incumbent=noise.get('baseline',noise.get('incumbent'))
            if incumbent:
                rows.append(f"| Прежний образ без изменений | {incumbent['flashBytes']} | {incumbent['stoi']:.6f} | {incumbent['rawLogSpectralError']:.6f} | {incumbent['highBandExcess']:.8f} |")
                reduction=(1-selected['highBandExcess']/incumbent['highBandExcess'])*100
                rows+=['',f"Относительно неизменённого прежнего образа измеренный избыток ВЧ-энергии уменьшился на {reduction:.3f}%. Это величина конкретной спектральной оценки, не процент воспринимаемого шума и не оценка аналогового выхода."]
            rows+=['',
                'Меньше спектральная ошибка и измеренный избыток ВЧ, но STOI понизился. Это явный компромисс в пользу спектра и меньшего шума, а не улучшение всех метрик. Неизменённый источник и сравнения для прослушивания находятся в `build/shared-speech/noise-refinement/`: `original.wav`, `previous.wav`, `selected.wav`, `spectrogram.png`.','',
                f"Исходник длится {noise['inputDurationSeconds']:.4f} с; образ — {noise['firmwareDurationSeconds']:.4f} с. Разница — 48 конечных нулевых отсчётов, без обрезки или изменения частоты воспроизведения. Измеренный сдвиг RMS-огибающей прежнего образа: {noise['incumbentEnvelopeLagSeconds']:.4f} с. Это проверка времени, а не доказательство одинакового субъективного темпа и тембра."]
    rows+=['','## Файлы полной формы сигнала','',
        'Скрипт '+link('tools/build-speech-waveforms.mjs')+' исполняет сохранённые Flash/EEPROM в AVR-эмуляторе и записывает все отсчёты каждой Tiny-фразы. Это не исходная запись и не повторное сжатие. Манифест '+link('web-player/audio/speech-waveforms/manifest.json')+' связывает WAV с точными хешами выбранных образов и PWM.','',
        '| Образ | WAV полной фразы | Гц / отсчётов | Генератор |','| --- | --- | --- | --- |']
    for waveform in read('web-player/audio/speech-waveforms/manifest.json')['entries']:
        rows.append(f"| `{waveform['id']}` | {link('web-player/'+waveform['audio'])} | {waveform['sampleHz']} / {waveform['phraseSamples']} | {link('tools/build-speech-waveforms.mjs')} |")
    rows+=['',
        '«Вид сигнала» переключает полную форму фразы и текущее окно 85 мс без перезапуска звука. «Сигнал и звук» выбирает PWM до фильтра или выход. Для полной формы Tiny используется тот же ресэмплер и DSP плеера через '+link('web-player/lib/speech-waveform.js')+'; LPX использует точные нативные WAV. Во время прослушивания Tiny звук по-прежнему создаёт исполняемая прошивка.']
    rows+=['','## Воспроизведение результата','',
        'Нужны установленные зависимости кодеков Python и нативный C++ компилятор, AVR-GCC проекта; для Nano — simavr observer. Все журналы и промежуточные WAV остаются в `build/`. Пути ниже заменяются на пути установленных инструментов.','',
        '```text','python tools/prepare-shared-speech.py --retain',
        'python tools/build-nano-speech-catalog.py --avr-bin /path/to/avr/bin --observer build/nano-lpx/observer/sim_player --lib /path/to/simavr/lib --enable-asm',
        'python tools/build-shared-tiny-speech.py --avr-bin /path/to/avr/bin --proposals 3000 --starts 4 --seed 23120',
        'python tools/refine-shared-tiny-noise.py --avr-bin /path/to/avr/bin --steps 800 --seed 23121',
        'python tools/build-shared-tiny-speech.py --avr-bin /path/to/avr/bin --reuse-search --noise-model build/shared-speech/noise-refinement/model.json --noise-report build/shared-speech/noise-refinement/report.json',
        'node tools/build-speech-waveforms.mjs',
        'python tools/document-speech-assets.py --check','```','',
        'Команды выполняются в указанном порядке: сначала заново получается базовая Tiny-модель, затем спектральный поиск и проверяется конечный образ. Первая Tiny-команда временно выбирает победителя прежней оценки; вторая применяет спектральную модель. После изменения выбранного образа WAV полной формы надо пересоздать. Для обновления этой таблицы запустите `python tools/document-speech-assets.py` без `--check`.','',
        'На Windows к Nano-команде добавляется `--wsl Ubuntu`. `--reuse-search` у Tiny повторно проверяет уже полученные модели, предварительно сверяя источник и параметры. Первые три Tiny-образа воспроизводит `tools/build-hq4-catalog.py`; их исторический поиск моделей сохранён отдельно. Контрольные суммы исходников в новых рецептах нормализуют текст к LF; HEX и звуковые потоки сохраняют точные байты.','']
    return '\n'.join(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');args=p.parse_args()
    path=ROOT/'docs/speech-assets.md';text=document()
    if args.check:
        if path.read_text(encoding='utf-8')!=text:raise ValueError('Speech asset documentation is stale')
    else:path.write_text(text,encoding='utf-8',newline='\n')
    print('Speech asset inventory verified' if args.check else 'Speech asset inventory written')


if __name__=='__main__':main()
