# Further experiments

1. Split-vector quantization of K1..K8 with a small codebook held in EEPROM; measure loss vs extra decoder bytes. No guarantee of transparency.
2. Sparse zero-gain frame RLE, preserving synthesis state behavior, instead of replacing frames with literal silence.
3. Rate-distortion-optimized variable keyframe allocation. Spend extra bytes at phoneme transitions, not steady vowels.
4. Joint pitch and gain entropy model, with escape for unusual pitches. Preserve exact pitch or accept quantization explicitly.
5. Quantization-aware analysis-by-synthesis, using the actual AVR decoder, and explicit penalties for pitch, formants and clicks.
