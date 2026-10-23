; Intel 8080 ROM integrity self-test (39 bytes, optimized byte update + faster addressing).
; CRC-16 polynomial x^16+x^5+x^3+x^2+1 = 0x002D, primitive.
; Init 0; non-reflected; final XOR 0; ROM footer FFFEh/FFFFh hi/lo.
; No RAM, no stack. A15 must be wired for 64 KiB.
;
; State: H = CRC high, C = CRC low; DE = ROM address.
; B and L are scratch; A is accumulator.
; p(x) = (1+x^2)(1+x^3); byte update:
;   t = incoming XOR old high CRC
;   u = t XOR (t<<2)
;   w = u XOR (u<<3)
;   newCRC = (oldCRC_low << 8) XOR w
;
        ORG 0000H
        XRA A
        MOV D,A         ; ROM address DE=0
        MOV E,A
        MOV H,A         ; CRC high H=0
        MOV C,A         ; CRC low C=0
NEXT:   LDAX D          ; A = ROM[DE]
        XRA H           ; t = byte XOR CRC high
        MOV L,A         ; L = t
        MVI H,0         ; HL = t (16-bit)
        DAD H           ; HL <<= 1
        DAD H           ; HL <<= 1
        XRA L           ; u = t XOR (t << 2) (low byte), A retained t
        MOV L,A         ; HL now contains 16-bit u
        MOV B,L         ; B = u low
        MOV A,H         ; A = u high
        DAD H           ; HL <<= 1
        DAD H           ; HL <<= 1
        DAD H           ; HL <<= 1
        XRA H           ; XOR high of u<<3 and high of u
        XRA C           ; add old low CRC as new high
        MOV H,A         ; new CRC high
        MOV A,L
        XRA B           ; low of u<<3 XOR original u low
        MOV C,A         ; new CRC low
        INR E           ; E++, sets zero flag on wrap
        JNZ NEXT        ; typical case: 15 T-state address loop
        INR D           ; high byte increments every 256 bytes
        JNZ NEXT        ; D wrap => 64 KiB processed
        ORA H           ; A still CRC low, C = A; compare CRC to zero
        JNZ FINISH      ; INTE low after hardware RESET on failure
        EI              ; INTE high on success
FINISH: HLT             ; halt in both cases
