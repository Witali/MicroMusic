; Intel 8080, reflected CRC-32C table generator, packed layout.
; 57 bytes including DI+HLT. Stores T[i] little-endian to 8000+4*i.
; Uses stack pointer SP exclusively to WRITE data in RAM with PUSH.
; No CALL/RET, no interrupts. Memory 8000-83FF must be writable.
        ORG 0000H
        DI
        LXI SP,08400H   ; fill downward, from i=FFH to i=00H
        MVI L,00H       ; first DCR gives FF
NEXT:   DCR L           ; FF..00, matched to descending stack
        MOV E,L
        XRA A           ; clear A, CY
        MOV B,A         ; high 3 bytes of CRC become zero
        MOV C,A
        MOV D,A
        MVI H,08H
BIT:    MOV A,B
        RAR
        MOV B,A
        MOV A,C
        RAR
        MOV C,A
        MOV A,D
        RAR
        MOV D,A
        MOV A,E
        RAR
        MOV E,A
        JNC NOXOR
        MOV A,B
        XRI 082H
        MOV B,A
        MOV A,C
        XRI 0F6H
        MOV C,A
        MOV A,D
        XRI 03BH
        MOV D,A
        MOV A,E
        XRI 078H
        MOV E,A
NOXOR:  DCR H
        JNZ BIT
        PUSH B          ; store MSB half of T[i]
        PUSH D          ; store LSB half of T[i]
        MOV A,L
        ORA A
        JNZ NEXT
        HLT
