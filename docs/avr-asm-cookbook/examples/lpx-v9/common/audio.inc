/* Provide the link-time audio payload; all stream settings come from its header. */
	.section	.progmem.data._ZL5voice,"a",@progbits
	.type	_ZL5voice, @object
	.size	_ZL5voice, lpx_audio_end-_ZL5voice
_ZL5voice:
	.incbin LPX_AUDIO_FILE
lpx_audio_end:
