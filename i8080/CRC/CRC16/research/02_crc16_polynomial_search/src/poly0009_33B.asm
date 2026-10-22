; Intel 8080 CRC-16 full 64-KiB ROM check, table-free, no RAM or stack.
; 33 bytes, 94.06 T/byte, nonprimitive polynomial 0x0009 = x^16+x^3+1.
; Faster but weaker than 39-byte 0x002D primitive CRC.
; Init CRC=0, MSB-first, no xorout; ROM CRC footer FFFEh/FFFFh (high,low).
; DE=read address; H=CRC high; C=CRC low; L=scratch; B=0.
; A retains t = ROM_byte XOR CRC_high throughout three DAD instructions.
        ORG 0000H
        XRA A
        MOV D,A
        MOV E,A
        MOV H,A
        MOV C,A
        MOV B,A          ; B=0, preserve zero throughout scanning
NEXT:   LDAX D          ; 7T, read ROM byte
        XRA H           ; 4T, t = byte XOR old CRC high
        MOV L,A         ; 5T, HL=t after next command
        MOV H,B         ; 5T, use zero register B instead of 7T MVI
        DAD H           ; 10T, t<<1
        DAD H           ; 10T, t<<2
        DAD H           ; 10T, t<<3
        XRA L           ; 4T, new CRC low=t XOR low(t<<3)
        MOV L,A         ; 5T, save low in L; old CRC low still C
        MOV A,H         ; 5T, high(t<<3)
        XRA C           ; 4T, new CRC high=old CRC low XOR high(t<<3)
        MOV H,A         ; 5T, retain new high
        MOV C,L         ; 5T, retain new low
        INR E           ; 5T
        JNZ NEXT        ; 10T, typical case
        INR D           ; 5T, once every 256 B
        JNZ NEXT        ; 10T, until 64KiB rollover
        ORA C           ; 4T, A is CRC high, C CRC low
        JNZ FINISH      ; 10T, fail => INTE stays 0 after reset
        EI              ; 4T, success => INTE becomes 1
FINISH: HLT             ; 7T
