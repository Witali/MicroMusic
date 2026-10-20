Сохранённые измерения банка FluidR3 GM 3.1 и лицензия MIT.
measurements.json — 80 тональных нот и огибающие;
strings-comparison.json — сравнение пяти струнных пресетов;
fit-report.json — подбор коротких таблиц волн;
percussion-measurements.json — историческое сравнение ударных;
violin-A4.wav — исходный звуковой пример Violin.

Источники и SHA-256 банка/рендерера указаны в измерительных JSON.
Банк SF2 в репозиторий не включён. Скрипты capture-fluid-grid.mjs и
compare-fluid-strings.mjs требуют явно передать внешний SF2 и движок.
Тональный анализ: tools/analyze-fluid-grid.py, analyze-fluid-strings.py.
Исторический анализ ударных использует промежуточные кандидаты из build/;
для их повторного получения нужны инструменты из истории до 2271291.
