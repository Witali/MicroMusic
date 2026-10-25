The two quality refiners are OFFLINE tools. Both keep file length exactly unchanged.
Do not treat identical file size as identical quality: evaluate PCM-SNR/STOI/spectral discrepancy.
The first refiner operates ONLY on existing sparse CELP frame fields; the second changes
existing Q14 header fields. Neither changes the AVR decoding algorithm or L4HY bit syntax.
Use independent reference WAV to avoid over-fitting. Hard 16-MHz deadline is still unverified.
