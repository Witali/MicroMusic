PIC16F1503 — MicroMusic, повторный аудит таймингов по DS40001607D (2026-10-21)

1. Откройте web/player.html — автономный веб-эмулятор PIC и проигрыватель.
2. Прочитайте TIMING_AUDIT_DS40001607D_RU.md — исправления по таймингам, точность, ограничения.
3. Исходный ассемблер: firmware/micromusic.asm; оригинальный музыкальный HEX: firmware/micromusic_with_config.hex.
4. Для пересборки: python tools/build_firmware.py, затем python tools/build_player.py.
5. Прогон тестов: node --test tests/official_datasheet_audit.test.mjs tests/official_timing_v2.test.mjs tests/isa_timing_matrix.test.mjs
6. Полная партитура: node tests/audit_full_score.mjs (долго); последний отчёт reports/full_score_audit.json.
7. Музыкальный HEX НЕ менялся. Для реальной платы нужна независимая проверка на PIC16F1503.
