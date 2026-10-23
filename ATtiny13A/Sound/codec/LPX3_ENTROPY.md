# Lossless packing after the LPC2/LPX3 quality stage

The current quality study temporarily removes the 1-KB constraint. Compression
still matters, so `lpx3_entropy.py` tries three reversible DEFLATE layouts and
canonical Huffman coding after
excitation quantization. It preserves the complete original LPX3 container,
including LPC2 parameters, all scales, codes and unused final padding bits.
Recovered synthesis must therefore be identical; this stage cannot improve or
degrade voice quality. It also cannot repair an already clipped source.

The separately versioned LPX4 v1 6/8-bit experiment uses the same container
layout and is also supported. LPX3 v1 remains restricted to 2/3/4 bits; no
higher-resolution stream is mislabeled as an original LPX3 file.

DEFLATE alternatives are: ordinary packed LPX3; expanded one-byte excitation symbols;
or those symbols plus modulo differences of adjacent scale/code values. Every
alternative includes its real header and compressor overhead. Original LPX3
remains a candidate, so selected storage never grows. No source waveform,
external coefficients or uncompressed residual is stored separately.

`LPZ1` has a 17-byte little-endian `<4sBIII` header: magic, reversible transform
0/1/2/3, original length, transformed length and CRC32 of the restored LPX3/LPX4.
Methods 0/1/2 contain one zlib stream whose inflated size is the transformed
length. Method 3 contains an uncompressed canonical-Huffman payload of exactly
that transformed length: original 24-byte LPX header + original LPC2 base +
original per-block scales + `2**bits` one-byte code lengths + one original
padding byte + MSB-first Huffman symbols. Zero lengths denote absent symbols;
nonzero lengths are bounded to 32. Canonical order is (length, symbol).
The final Huffman byte uses zero low-bit padding. The separate padding byte
preserves unused high bits of the original LSB-first LPX excitation stream.
Empty, oversubscribed and incomplete trees are rejected, except the explicitly
allowed one-symbol tree of length one. No DEFLATE implementation is needed to
read method 3. Readers lacking method 3 reject it instead of guessing.

Length bounds, EOF, trailing compressed bytes, original
descriptor/sample count, exact reconstructed length and checksum are checked.
The storage limit is 64 MiB; this is a local speech experiment, not arbitrary
unbounded decompression. Plain LPX3 requires no wrapper if it wins.

```
python tools/pack-lpx3-entropy.py input.lpx3 --output build/example.lpz
python tools/pack-lpx3-entropy.py build/example.lpz --decode --output build/restored.lpx3
python tools/test-lpx3-entropy.py
```

The existing LPX3/LPX4 decoder then reads the recovered original. Its numerical output
does not depend on the original WAV. This wrapper is implemented for PC use;
decoder code size, SRAM and runtime on an AVR have not been measured.
Source-payload counts exclude executable code. Five tests exercise 2/3/4/6/8-bit
codes, non-byte-aligned tails, all transforms, actual compression, fallback
size, corruption, truncation, trailing bytes and oversized descriptors. A manually
specified canonical bitstream checks bit order and original padding independently
of the encoder, alongside byte-exact round trips.

## Measured six-bit streams

The user preferred Vinni's six-bit coded excitation to Q3 and then parametric
LPC2 Improved. Preserve that six-bit baseline while reducing storage. These are
complete container sizes, including the wrapper and codebook, excluding decoder
code:

| Recording | Original | DEFLATE minimum | Huffman | Saved from original |
|---|---:|---:|---:|---:|
| Vinni, 2.9696 s | 17,562 | 17,186 | 16,407 | 1,155 (6.58%) |
| Full tail with bell | 15,215 | 15,005 | 14,313 | 902 |
| Chego | 7,380 | 7,291 | 6,939 | 441 |
| Otvechaesh | 6,323 | 6,176 | 6,014 | 309 |

All restored original container bytes match exactly. This establishes identical
decoder input, not just a close perceptual score. Measurements and hashes are
retained in `../research/lpc2-comparison/lossless-storage.json`. The additional
LPV1 variable-width study is lossy and remains a separate listening candidate;
its lower waveform error does not guarantee preserved intelligibility.
