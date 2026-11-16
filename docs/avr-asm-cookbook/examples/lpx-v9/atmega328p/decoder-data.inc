/* Allocate the decoder state and immutable lookup tables. */
	.section	.progmem.data._ZL9pulseHigh,"a",@progbits
	.type	_ZL9pulseHigh, @object
	.size	_ZL9pulseHigh, 25
_ZL9pulseHigh:
	.byte	0
	.byte	4
	.byte	8
	.byte	12
	.byte	16
	.byte	32
	.byte	36
	.byte	40
	.byte	44
	.byte	48
	.byte	64
	.byte	68
	.byte	72
	.byte	76
	.byte	80
	.byte	96
	.byte	100
	.byte	104
	.byte	108
	.byte	112
	.byte	-128
	.byte	-124
	.byte	-120
	.byte	-116
	.byte	-112
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
	.section	.progmem.data._ZL8bitMasks,"a",@progbits
	.type	_ZL8bitMasks, @object
	.size	_ZL8bitMasks, 9
_ZL8bitMasks:
	.byte	0
	.byte	1
	.byte	3
	.byte	7
	.byte	15
	.byte	31
	.byte	63
	.byte	127
	.byte	-1
	.section	.progmem.data._ZL10cosineEven,"a",@progbits
	.type	_ZL10cosineEven, @object
	.size	_ZL10cosineEven, 130
_ZL10cosineEven:
	.word	8192
	.word	8190
	.word	8182
	.word	8170
	.word	8153
	.word	8130
	.word	8103
	.word	8071
	.word	8035
	.word	7993
	.word	7946
	.word	7895
	.word	7839
	.word	7779
	.word	7713
	.word	7643
	.word	7568
	.word	7489
	.word	7405
	.word	7317
	.word	7225
	.word	7128
	.word	7027
	.word	6921
	.word	6811
	.word	6698
	.word	6580
	.word	6458
	.word	6333
	.word	6203
	.word	6070
	.word	5933
	.word	5793
	.word	5649
	.word	5501
	.word	5351
	.word	5197
	.word	5040
	.word	4880
	.word	4717
	.word	4551
	.word	4383
	.word	4212
	.word	4038
	.word	3862
	.word	3683
	.word	3503
	.word	3320
	.word	3135
	.word	2948
	.word	2760
	.word	2570
	.word	2378
	.word	2185
	.word	1990
	.word	1795
	.word	1598
	.word	1401
	.word	1202
	.word	1003
	.word	803
	.word	603
	.word	402
	.word	201
	.word	0
	.section	.bss._ZL7decoder,"aw",@nobits
	.type	_ZL7decoder, @object
	.size	_ZL7decoder, 396
_ZL7decoder:
	.zero	396
