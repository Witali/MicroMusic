# Lossless packing after the LPC2/LPX3 quality stage

The current quality study temporarily removes the 1-KB constraint. Compression
still matters, so `lpx3_entropy.py` tries three reversible DEFLATE layouts after
excitation quantization. It preserves the complete original LPX3 container,
including LPC2 parameters, all scales, codes and unused final padding bits.
Recovered synthesis must therefore be identical; this stage cannot improve or
degrade voice quality. It also cannot repair an already clipped source.

Alternatives are: ordinary packed LPX3; expanded one-byte excitation symbols;
or those symbols plus modulo differences of adjacent scale/code values. Every
alternative includes its real header and compressor overhead. Original LPX3
remains a candidate, so selected storage never grows. No source waveform,
external coefficients or uncompressed residual is stored separately.

`LPZ1` has a 17-byte little-endian `<4sBIII` header: magic, reversible transform
0/1/2, original length, inflated length and CRC32 of the restored LPX3. The rest
is one zlib stream. Length bounds, EOF, trailing compressed bytes, original
descriptor/sample count, exact reconstructed length and checksum are checked.
The storage limit is 64 MiB; this is a local speech experiment, not arbitrary
unbounded decompression. Plain LPX3 requires no wrapper if it wins.

```
python tools/pack-lpx3-entropy.py input.lpx3 --output build/example.lpz
python tools/pack-lpx3-entropy.py build/example.lpz --decode --output build/restored.lpx3
python tools/test-lpx3-entropy.py
```

The existing LPX3 decoder then reads the recovered LPX3. Its numerical output
does not depend on the original WAV. This wrapper is implemented for PC use;
DEFLATE decoder code size, SRAM and runtime on an AVR have not been measured.
Source-payload counts exclude executable code. Four tests exercise 2/3/4-bit
codes, non-byte-aligned tails, all transforms, actual compression, fallback
size, corruption, truncation, trailing bytes and oversized descriptors.
