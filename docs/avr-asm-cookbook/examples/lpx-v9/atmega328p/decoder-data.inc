/* Allocate backend-specific decoder state and tables. */
#include "../common/decoder-tables.inc"
	.section	.progmem.data._ZL11scaleValues,"a",@progbits
	.type	_ZL11scaleValues, @object
	.size	_ZL11scaleValues, 64
_ZL11scaleValues:
	.word	0
	.word	0
	.word	0
	.word	0
	.word	0
	.word	0
	.word	1
	.word	1
	.word	1
	.word	1
	.word	2
	.word	3
	.word	4
	.word	6
	.word	8
	.word	12
	.word	16
	.word	23
	.word	33
	.word	46
	.word	66
	.word	93
	.word	131
	.word	185
	.word	262
	.word	371
	.word	524
	.word	741
	.word	1049
	.word	1483
	.word	2097
	.word	2966
.global	lpx25_queue
	.section	.bss._ZL7decoder,"aw",@nobits
	.type	_ZL7decoder, @object
	.size	_ZL7decoder, 396
_ZL7decoder:
	.zero	396
