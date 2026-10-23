# Речь «Чего тебе нужно?» в памяти ATtiny13A

Сохранены два автоматически подобранных целочисленных варианта, 7500 Гц,
9216 отсчётов, длительность 1,2288 с. Основной `model.json` использует восемь
голосовых периодов по 32 четырёхбитных коэффициента. `stoi-model.json` содержит
десять периодов и исключает отдельное усиление 3/4, чтобы уменьшить машинный код.

| Вариант | STOI | eSTOI | Ошибка лог-спектра | Спектральный loss | Flash: данные | EEPROM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HQ4-T Auto, прежний проигрыватель | 0,900500 | 0,794606 | 0,935948 | 0,910148 | — | — |
| Предыдущая целочисленная модель, 16 периодов | 0,921174 | 0,862731 | 0,385720 | 0,372739 | — | — |
| **Основной: 8 периодов** | **0,910667** | **0,857155** | **0,370232** | **0,370121** | **260 байт** | **64 байта** |
| Альтернатива: 10 периодов, без усиления 3/4 | 0,912268 | 0,857241 | 0,383466 | 0,374295 | 304 байта | 64 байта |

Основной вариант выбран ради баланса: разница eSTOI с альтернативой меньше
0,0001, зато спектральная ошибка ниже и остаётся больше Flash. Полный размер
прошивки, машинный код, SRAM, стек и соблюдение периодов PWM устанавливаются
отдельными `build.json` и `build-stoi.json`. Размер данных в таблице не включает
машинный код. EEPROM хранит четыре последних упакованных периода; при
воспроизведении выполняется только чтение, без циклов записи.

Все модели декодируются общей точной спецификацией `fixed_period.py`.
`tiny_period.py` убирает неиспользуемые поля и делит словарь между Flash и EEPROM,
сохраняя каждый отсчёт PCM. Сохранены фазовая интерполяция, непрерывная фаза,
плавный переход параметров, белый высокочастотный остаток и DC-блокиратор со
сдвигом 7. Отдельное неголосовое возбуждение и FIR в этих моделях не нужны.

Словарь уменьшается полным перебором замен одного периода другим. Каждый
кандидат оценивается после целочисленного декодирования. Затем скрипт совместно
подбирает кадры, фазу и коэффициенты словаря, ограничивая допустимые режимы и
размер. Для исключения усиления 3/4 перебраны все 16 комбинаций замен четырёх
затронутых кадров на 1/2 или 1. Это автоматический локальный поиск, без ручной
правки отдельных фонем и без утверждения о глобальном оптимуме.

У обоих сохранённых вариантов нет отсечения до и после DC-блокиратора.
Среднее отклонение основного варианта составляет 0,00239 единицы восьмибитного
PCM; максимальное среднее по окну 64 отсчёта — 5,28125. Форма голосовой волны
принудительно не симметризуется. `quality.json` и `stoi-quality.json` содержат
свежие независимые измерения, хеши моделей, оригинала, декодеров и контрольного
HQ4-T, версии библиотек и проверку точного восстановления PCM из Flash/EEPROM.
STOI и спектральные метрики относятся к одной этой фразе и не заменяют
прослушивание или проверку более широкого набора речи. Физический MCU пока не
проверялся.

## Повторение

Канонический WAV находится вне отслеживаемых исходников; его SHA-256 сверяется с
`audio-references.json`. Все бинарники, WAV, контрольные точки и временные модели
пишутся в игнорируемый `build/`. Начальная модель и результаты поиска связаны в
`training.json`; версии раннего CLI указаны в соответствующих этапах. Текущий
CLI сохраняет ту же последовательность автоматических предложений, а также
поддерживает отдельное ограничение фактического размера Flash после разделения
с EEPROM.

```powershell
python tools/train-tiny-speech.py --model ATtiny13A/Sound/research/fixed-period/chego/white-model.json --reference C:/Work/MicroMusic/build/hq4-preview/chego/original.wav --output build/tiny-replay/eight --words 8 --proposals 12000 --stoi-floor .88 --spectral-ceiling .60
python tools/train-tiny-speech.py --model ATtiny13A/Sound/research/fixed-period/chego/white-model.json --reference C:/Work/MicroMusic/build/hq4-preview/chego/original.wav --output build/tiny-replay/ten --words 10 --proposals 6000 --stoi-floor .895 --spectral-ceiling .50
python tools/train-tiny-speech.py --model build/tiny-replay/ten/retuned-model.json --reference C:/Work/MicroMusic/build/hq4-preview/chego/original.wav --output build/tiny-replay/ten-pow2 --words 10 --proposals 0 --stoi-floor .89 --spectral-ceiling .45 --no-gain6
python tools/train-tiny-speech.py --model build/tiny-replay/ten-pow2/retuned-model.json --reference C:/Work/MicroMusic/build/hq4-preview/chego/original.wav --output build/tiny-replay/ten-final --words 10 --proposals 2000 --stoi-floor .909 --spectral-ceiling .40 --no-gain6 --max-flash-data-bytes 312
python tools/report-tiny-speech.py --model ATtiny13A/Sound/research/tiny-speech/chego/model.json --reference C:/Work/MicroMusic/build/hq4-preview/chego/original.wav --output build/tiny-review
python tools/build-tiny-speech.py --model ATtiny13A/Sound/research/tiny-speech/chego/model.json --output build/tiny-firmware
```

Проверка качества создаёт `tiny-raw-level.wav` с неизменённым восьмибитным
уровнем и отдельные WAV для сравнения при согласованной громкости.
