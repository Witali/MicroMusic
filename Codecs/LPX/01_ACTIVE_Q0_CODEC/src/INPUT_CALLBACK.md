# Sequential compressed input

Build the core and every consumer with `LPX4_ENABLE_INPUT_CALLBACK=1` to
enable a borrowed, synchronous byte reader:

```cpp
int16_t readCompressedByte(void* context);  // 0..255, or -1 on failure
decoder.beginStream(readCompressedByte, context, segmentBytes);
```

The source must already be positioned at the start of one complete LPX
segment, including its header. `segmentBytes` is a `uint16_t` stored span,
at most 65535 bytes. Large files use independently reset segments and a
transport with wider external addresses. The callback owns neither the
decoder nor the context; both the context and source must remain valid
until decoding finishes or another `begin`/`beginStream` replaces them.

The reader returns one byte and advances its source exactly once. A negative
return or a value above 255 stops decoding with a nonzero error. The reader
sets `END_OF_ROM`; subsequent parsing can classify the failure as `BAD_HEADER`,
`UNSUPPORTED`, or `CORRUPT_STREAM`. Callers should require a nonzero error,
rather than a particular error code for transport failure. Failure is sticky
until the next begin.
The core enforces the declared span before calling the reader. It does not
call a null reader or read an input declared shorter than the minimum header.
There is no retry, asynchronous wait, rewind, or hidden allocation.

Successful decoding stops at the declared sample count. A partial final
frame can leave stored packet-tail bytes unread, just as ROM decoding does.
The source must seek explicitly before opening the next reset segment;
do not assume that the last callback reached `segmentBytes`. Physical EOF
is detected only if decoding requests a missing byte. This API does not
validate storage checksums or authenticate the container.

`begin(progmem, size)` remains available in callback builds and clears any
previous reader. `beginStream` similarly clears the old ROM source and
resets decoding state. Separate decoder instances retain separate sources.
The callback executes on the caller's thread, including during `beginStream`
while the header is parsed. An interrupt-driven audio player should decode
in its producer loop and publish samples to its existing queue.

The setting is independent of the arithmetic backend, ROM table access,
and supported format selection. `LPX4_ENABLE_ASM=0` still selects the C
arithmetic fallback on AVR. The default callback setting is zero: the old
ROM code and class layout are retained. Opting in adds a function pointer
and a context pointer after the arithmetic workspace; its linked Flash and
timing costs must be measured with the transport and actual player.

`tests/test_input_callback.py` compares PCM16 and PWM8 against the model and
ROM input for profiles 4/6, short final frames, long segments, both input
cursor representations, common/v5-only builds, source replacement, declared
bounds, physical read failures, and legacy v4 in the common build.
