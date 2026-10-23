; Intel 8080, reflected CRC-32C Castagnoli table generator.
; 57 bytes including DI+HLT. 256 x 32-bit entries into RAM 8000h..83FFh.
; 4 x 256-byte planes: [8000+i]=LSB; [8100+i], [8200+i], [8300+i]=MSB.
; Renders T[i] = CRC32C_RAW(bytes([i]), initial CRC=0).
; All addresses 8080 RAM except program ROM, interrupts disabled.
        ORG 0000H
        DI
        MVI L,00H       ; table index 0..255
NEXT:   MOV E,L         ; CRC = table index
        XRA A           ; clear A, CY
        MOV B,A         ; high 3 bytes of CRC become zero
        MOV C,A
        MOV D,A
        MVI H,078H      ; eight increments reach 80H, our output page
BIT:    MOV A,B         ; shift 32-bit B:C:D:E right one bit
        RAR             ; incoming carry always 0 here
        MOV B,A
        MOV A,C
        RAR
        MOV C,A
        MOV A,D
        RAR
        MOV D,A
        MOV A,E
        RAR             ; CY = low bit of 32-bit CRC
        MOV E,A
        JNC NOXOR
        MOV A,B         ; XOR 82F63B78H
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
NOXOR:  INR H           ; after eighth increment H = 80H (sign set)
        JP BIT          ; Intel 8080: jump if S=0; stop at H=80H
                        ; H now is 80H; use as table page selector
        MOV M,E
        INR H
        MOV M,D
        INR H
        MOV M,C
        INR H
        MOV M,B
        INR L           ; 256 table elements; Z after FF -> 00
        JNZ NEXT
        HLT
