(func $native.clki_service (param $0 i64)
  (local $1 i32)
  (local $2 i32)
  (local $3 i64)
  (local $4 i32)
  (local $5 i32)
  (local $6 i64)
  (local $7 i32)
  (local $8 i32)
  (local $9 i32)
  (local $10 i32)
  (local $11 i64)
  (local $12 i32)
  (local $13 i64)
  (local $14 i32)
  (local $15 i32)
  (local $16 i32)
  (global.set $global$0
   (local.tee $7
    (i32.sub
     (global.get $global$0)
     (i32.const 32)
    )
   )
  )
  (i32.store8
   (i32.const 65408)
   (i32.const 0)
  )
  (block $block
   (br_if $block
    (i32.eqz
     (i32.load16_u
      (i32.const 64314)
     )
    )
   )
   (loop $label
    (br_if $block
     (i64.ne
      (local.tee $3
       (i64.load
        (local.tee $2
         (i32.add
          (i32.shl
           (i32.and
            (i32.add
             (local.get $1)
             (i32.load16_u
              (i32.const 64312)
             )
            )
            (i32.const 127)
           )
           (i32.const 4)
          )
          (i32.const 107320)
         )
        )
       )
      )
      (i64.load
       (i32.const 64176)
      )
     )
    )
    (block $block4
     (block $block3
      (block $block2
       (block $block1
        (br_table $block1 $block2 $block3 $block4
         (i32.load8_u offset=12
          (local.get $2)
         )
        )
       )
       (br_if $block4
        (i32.eqz
         (i32.and
          (i32.load8_u
           (i32.const 63604)
          )
          (i32.const 1)
         )
        )
       )
       (i32.store8
        (i32.const 64334)
        (i32.or
         (i32.and
          (i32.load8_u offset=13
           (local.get $2)
          )
          (i32.const 32)
         )
         (i32.and
          (i32.load8_u
           (i32.const 64334)
          )
          (i32.const 223)
         )
        )
       )
       (i32.store8
        (i32.const 64335)
        (i32.or
         (i32.and
          (i32.load8_u offset=14
           (local.get $2)
          )
          (i32.const 32)
         )
         (i32.and
          (i32.load8_u
           (i32.const 64335)
          )
          (i32.const 223)
         )
        )
       )
       (call $native.external_reset_sync)
       (br $block4)
      )
      (br_if $block4
       (i32.ne
        (i32.load8_u offset=15
         (local.get $2)
        )
        (i32.const 5)
       )
      )
      (br_if $block4
       (i32.eqz
        (i32.load8_u
         (i32.const 65404)
        )
       )
      )
      (i32.store
       (i32.const 73860)
       (local.tee $2
        (i32.load offset=8
         (local.get $2)
        )
       )
      )
      (i32.store8
       (i32.const 64333)
       (i32.or
        (i32.load8_u
         (i32.const 64333)
        )
        (i32.const 32)
       )
      )
      (block $block5
       (br_if $block5
        (call $native.attiny13a_reset_input_set_voltage
         (local.get $3)
         (local.get $2)
         (i32.load
          (i32.const 64384)
         )
        )
       )
       (i32.store8
        (i32.const 64416)
        (i32.const 0)
       )
       (br_if $block5
        (i32.load
         (i32.const 64296)
        )
       )
       (i32.store
        (i32.const 64300)
        (i32.load8_u
         (i32.const 65372)
        )
       )
       (i32.store
        (i32.const 64296)
        (i32.const 17)
       )
      )
      (call $native.external_reset_sync)
      (br $block4)
     )
     (i32.store
      (i32.const 64384)
      (local.tee $2
       (i32.load offset=8
        (local.get $2)
       )
      )
     )
     (call $native.nvm_voltage_uncertain
      (select
       (select
        (local.tee $4
         (select
          (i32.const 128)
          (i32.const 0)
          (i32.lt_s
           (local.get $2)
           (i32.const 1900000)
          )
         )
        )
        (i32.or
         (local.get $4)
         (i32.const 256)
        )
        (i32.ge_s
         (local.get $2)
         (i32.load
          (i32.const 64380)
         )
        )
       )
       (local.get $4)
       (i32.load8_u
        (i32.const 64341)
       )
      )
     )
     (block $block6
      (br_if $block6
       (i32.eqz
        (local.tee $2
         (i32.load
          (i32.const 74452)
         )
        )
       )
      )
      (i32.store8
       (i32.const 64416)
       (i32.const 0)
      )
      (br_if $block6
       (i32.load
        (i32.const 64296)
       )
      )
      (i32.store
       (i32.const 64300)
       (local.get $2)
      )
      (i32.store
       (i32.const 64296)
       (i32.const 5)
      )
     )
     (block $block7
      (br_if $block7
       (i32.eqz
        (i32.load8_u
         (i32.const 65404)
        )
       )
      )
      (br_if $block7
       (call $native.attiny13a_reset_input_set_voltage
        (i64.load
         (i32.const 64176)
        )
        (select
         (i32.load
          (i32.const 73860)
         )
         (local.tee $2
          (i32.load
           (i32.const 64384)
          )
         )
         (i32.and
          (i32.load8_u
           (i32.const 64333)
          )
          (i32.const 32)
         )
        )
        (local.get $2)
       )
      )
      (i32.store8
       (i32.const 64416)
       (i32.const 0)
      )
      (br_if $block7
       (i32.load
        (i32.const 64296)
       )
      )
      (i32.store
       (i32.const 64300)
       (i32.load8_u
        (i32.const 65372)
       )
      )
      (i32.store
       (i32.const 64296)
       (i32.const 17)
      )
     )
     (local.set $2
      (i32.and
       (i32.load8_u
        (i32.const 64343)
       )
       (i32.const 8)
      )
     )
     (i32.store8
      (i32.const 64343)
      (local.tee $2
       (i32.or
        (block $block10 (result i32)
         (block $block8
          (br_if $block8
           (i32.eqz
            (i32.and
             (i32.load8_u
              (i32.const 63604)
             )
             (i32.const 1)
            )
           )
          )
          (block $block9
           (br_if $block9
            (i32.eqz
             (i32.and
              (i32.load8_u
               (i32.const 64334)
              )
              (i32.const 32)
             )
            )
           )
           (br_if $block9
            (i32.and
             (i32.load8_u
              (i32.const 64335)
             )
             (i32.const 32)
            )
           )
           (br $block10
            (i32.const 2)
           )
          )
          (br_if $block8
           (i32.eqz
            (i32.load8_u
             (i32.const 65404)
            )
           )
          )
          (br_if $block8
           (i32.eqz
            (i32.load8_u
             (i32.const 65370)
            )
           )
          )
          (br $block10
           (i32.const 2)
          )
         )
         (i32.const 0)
        )
        (local.get $2)
       )
      )
     )
     (call $native.power_reset_set_inputs
      (i64.load
       (i32.const 64176)
      )
      (i32.load
       (i32.const 64384)
      )
      (local.get $2)
     )
     (call $native.power_sync)
     (br_if $block4
      (call $native.analog_reference
       (i32.load
        (i32.const 64384)
       )
       (i32.load
        (i32.const 63596)
       )
       (i64.load
        (i32.const 64184)
       )
      )
     )
     (i32.store8
      (i32.const 64416)
      (i32.const 0)
     )
     (br_if $block4
      (i32.load
       (i32.const 64296)
      )
     )
     (i64.store
      (i32.const 64296)
      (i64.const 64424509444)
     )
    )
    (br_if $label
     (i32.lt_u
      (local.tee $1
       (i32.add
        (local.get $1)
        (i32.const 1)
       )
      )
      (i32.load16_u
       (i32.const 64314)
      )
     )
    )
   )
  )
  (call $native.service_async)
  (call $native.wake)
  (local.set $2
   (i32.const 1)
  )
  (block $block11
   (br_if $block11
    (i32.load8_u
     (i32.const 64332)
    )
   )
   (block $block12
    (if
     (i32.load8_u
      (i32.const 65405)
     )
     (then
      (br_if $block11
       (i32.load
        (i32.const 73752)
       )
      )
      (br_if $block12
       (i64.ge_u
        (i64.load
         (i32.const 64176)
        )
        (i64.load
         (i32.const 73736)
        )
       )
      )
      (br $block11)
     )
    )
    (br_if $block11
     (i64.lt_u
      (i64.load
       (i32.const 64176)
      )
      (i64.load
       (i32.const 64288)
      )
     )
    )
   )
   (local.set $2
    (i32.ne
     (i32.load8_u
      (i32.const 64331)
     )
     (i32.const 0)
    )
   )
  )
  (block $block15
   (block $block13
    (br_if $block13
     (i32.eqz
      (i32.load8_u
       (i32.const 73836)
      )
     )
    )
    (if
     (i32.lt_s
      (local.tee $1
       (i32.load
        (i32.const 64384)
       )
      )
      (i32.load
       (i32.const 73824)
      )
     )
     (then
      (i32.store
       (i32.const 73824)
       (local.get $1)
      )
     )
    )
    (if
     (i32.gt_s
      (i32.load
       (i32.const 73828)
      )
      (local.get $1)
     )
     (then
      (i32.store
       (i32.const 73828)
       (local.get $1)
      )
     )
    )
    (if
     (i32.lt_s
      (i32.load
       (i32.const 73832)
      )
      (local.get $1)
     )
     (then
      (i32.store
       (i32.const 73832)
       (local.get $1)
      )
     )
    )
    (local.set $1
     (i32.const 32)
    )
    (block $block14
     (br_if $block14
      (i64.eq
       (local.tee $3
        (i64.load
         (i32.const 64176)
        )
       )
       (i64.const -1)
      )
     )
     (br_if $block14
      (i32.ne
       (i32.load8_u
        (i32.const 73814)
       )
       (i32.const 1)
      )
     )
     (br_if $block14
      (i32.gt_u
       (local.get $2)
       (i32.const 1)
      )
     )
     (br_if $block14
      (i64.lt_u
       (local.get $3)
       (i64.load
        (i32.const 73760)
       )
      )
     )
     (if
      (i32.ne
       (i32.load8_u
        (i32.const 73813)
       )
       (local.get $2)
      )
      (then
       (i32.store16 align=1
        (i32.const 73817)
        (i32.const 0)
       )
       (i32.store8
        (i32.const 73813)
        (local.get $2)
       )
       (i64.store
        (i32.const 73792)
        (i64.const 0)
       )
       (i64.store
        (i32.const 73800)
        (i64.const 0)
       )
      )
     )
     (i64.store
      (i32.const 73760)
      (local.get $3)
     )
     (local.set $1
      (i32.const 0)
     )
    )
    (br_if $block13
     (i32.eqz
      (local.get $1)
     )
    )
    (i32.store8
     (i32.const 64416)
     (i32.const 0)
    )
    (br_if $block15
     (i32.load
      (i32.const 64296)
     )
    )
    (i32.store
     (i32.const 64296)
     (i32.const 18)
    )
    (i32.store
     (i32.const 64300)
     (i32.or
      (local.get $1)
      (i32.const 256)
     )
    )
    (br $block15)
   )
   (local.set $9
    (i32.load8_u
     (i32.const 64330)
    )
   )
   (block $block16
    (br_if $block16
     (i32.ne
      (call $native.attiny13a_clki_peek
       (i32.add
        (local.get $7)
        (i32.const 16)
       )
      )
      (i32.const 1)
     )
    )
    (br_if $block16
     (i64.ne
      (i64.load offset=16
       (local.get $7)
      )
      (i64.load
       (i32.const 64176)
      )
     )
    )
    (if
     (i32.ne
      (block $block18 (result i32)
       (local.set $4
        (i32.sub
         (global.get $global$0)
         (i32.const 16)
        )
       )
       (local.set $1
        (i32.const -2)
       )
       (block $block17
        (br_if $block17
         (i32.eqz
          (local.tee $8
           (i32.load
            (i32.const 65416)
           )
          )
         )
        )
        (br_if $block17
         (i32.eqz
          (local.tee $10
           (i32.load
            (i32.const 65440)
           )
          )
         )
        )
        (drop
         (br_if $block18
          (i32.const 0)
          (i32.eqz
           (local.tee $12
            (i32.load
             (i32.const 65448)
            )
           )
          )
         )
        )
        (i32.store offset=8
         (local.get $4)
         (i32.load offset=9 align=1
          (local.tee $1
           (i32.add
            (local.get $8)
            (i32.shl
             (local.tee $5
              (i32.load
               (i32.const 65444)
              )
             )
             (i32.const 4)
            )
           )
          )
         )
        )
        (i32.store offset=11 align=1
         (local.get $4)
         (i32.load offset=12 align=1
          (local.get $1)
         )
        )
        (local.set $3
         (i64.load
          (local.get $1)
         )
        )
        (i32.store8
         (i32.const 65452)
         (i32.load8_u offset=8
          (local.get $1)
         )
        )
        (i64.store
         (i32.const 65424)
         (local.get $3)
        )
        (i32.store
         (i32.const 65448)
         (i32.sub
          (local.get $12)
          (i32.const 1)
         )
        )
        (local.set $1
         (i32.const 1)
        )
        (i32.store
         (i32.const 65444)
         (select
          (i32.add
           (local.get $5)
           (i32.const 1)
          )
          (i32.const 0)
          (i32.ne
           (local.get $5)
           (i32.sub
            (local.get $10)
            (i32.const 1)
           )
          )
         )
        )
       )
       (local.get $1)
      )
      (i32.const 1)
     )
     (then
      (i32.store8
       (i32.const 64416)
       (i32.const 0)
      )
      (br_if $block15
       (i32.load
        (i32.const 64296)
       )
      )
      (i64.store
       (i32.const 64296)
       (i64.const 12884901906)
      )
      (br $block15)
     )
    )
    (call $native.clki_refill)
    (local.set $4
     (i32.load8_u
      (i32.const 64335)
     )
    )
    (local.set $1
     (i32.load8_u
      (i32.const 64334)
     )
    )
    (if
     (i32.load8_u
      (i32.const 65405)
     )
     (then
      (local.set $1
       (i32.or
        (local.get $1)
        (i32.const 8)
       )
      )
      (local.set $4
       (i32.or
        (i32.and
         (local.get $4)
         (i32.const -9)
        )
        (i32.shl
         (block $block19 (result i32)
          (drop
           (br_if $block19
            (i32.const 255)
            (i32.eqz
             (i32.load
              (i32.const 65416)
             )
            )
           )
          )
          (drop
           (br_if $block19
            (i32.const 255)
            (i32.eqz
             (i32.load
              (i32.const 65440)
             )
            )
           )
          )
          (i32.load8_u
           (i32.const 65452)
          )
         )
         (i32.const 3)
        )
       )
      )
     )
    )
    (call $native.system_gpio_external
     (i32.and
      (local.get $1)
      (i32.const 255)
     )
     (i32.and
      (local.get $4)
      (i32.const 255)
     )
     (i64.load
      (i32.const 64184)
     )
    )
    (call $native.capture_pins)
    (call $native.pin_voltages)
    (block $block20
     (if
      (i32.eqz
       (i32.load8_u
        (i32.const 73836)
       )
      )
      (then
       (local.set $2
        (i32.load8_u offset=24
         (local.get $7)
        )
       )
       (br $block20)
      )
     )
     (local.set $4
      (i32.load8_u offset=24
       (local.get $7)
      )
     )
     (local.set $5
      (select
       (select
        (local.tee $1
         (i32.load
          (i32.const 73832)
         )
        )
        (select
         (local.tee $5
          (i32.load
           (i32.const 73824)
          )
         )
         (local.tee $8
          (i32.load
           (i32.const 73828)
          )
         )
         (i32.lt_s
          (local.get $5)
          (local.get $8)
         )
        )
        (i32.gt_s
         (local.get $1)
         (i32.const 5500000)
        )
       )
       (i32.load
        (i32.const 64384)
       )
       (i32.load8_u
        (i32.const 73815)
       )
      )
     )
     (local.set $1
      (i32.const 32)
     )
     (block $block21
      (br_if $block21
       (i64.eq
        (local.tee $3
         (i64.load
          (i32.const 64176)
         )
        )
        (i64.const -1)
       )
      )
      (br_if $block21
       (i32.ne
        (i32.load8_u
         (i32.const 73814)
        )
        (i32.const 1)
       )
      )
      (br_if $block21
       (i64.lt_u
        (local.get $3)
        (i64.load
         (i32.const 73760)
        )
       )
      )
      (br_if $block21
       (i32.gt_u
        (local.get $4)
        (i32.const 1)
       )
      )
      (br_if $block21
       (i64.le_u
        (local.get $3)
        (local.tee $11
         (i64.load
          (i32.const 73768)
         )
        )
       )
      )
      (br_if $block21
       (i32.gt_u
        (local.get $2)
        (i32.const 1)
       )
      )
      (br_if $block21
       (i32.eq
        (local.get $4)
        (local.tee $8
         (i32.load8_u
          (i32.const 73812)
         )
        )
       )
      )
      (local.set $13
       (block $block22 (result i64)
        (if
         (i32.gt_u
          (local.tee $10
           (i32.sub
            (local.get $5)
            (i32.const 1800000)
           )
          )
          (i32.const 3700000)
         )
         (then
          (local.set $1
           (i32.const 1)
          )
          (br $block22
           (i64.const 0)
          )
         )
        )
        (local.set $1
         (i32.const 0)
        )
        (if
         (i32.gt_u
          (local.get $5)
          (i32.const 4499999)
         )
         (then
          (local.set $6
           (i64.const 20000)
          )
          (br $block22
           (i64.const 50000)
          )
         )
        )
        (local.set $6
         (select
          (i64.const 40000)
          (i64.const 100000)
          (local.tee $5
           (i32.gt_u
            (local.get $5)
            (i32.const 2699999)
           )
          )
         )
        )
        (select
         (i64.const 100000)
         (i64.const 250000)
         (local.get $5)
        )
       )
      )
      (if
       (i32.ne
        (i32.load8_u
         (i32.const 73813)
        )
        (local.get $2)
       )
       (then
        (i32.store16 align=1
         (i32.const 73817)
         (i32.const 0)
        )
        (i32.store8
         (i32.const 73813)
         (local.get $2)
        )
        (i64.store
         (i32.const 73792)
         (i64.const 0)
        )
        (i64.store
         (i32.const 73800)
         (i64.const 0)
        )
       )
      )
      (local.set $1
       (i32.or
        (select
         (select
          (select
           (select
            (i32.const 2)
            (i32.const 4)
            (local.get $8)
           )
           (i32.const 0)
           (i32.load8_u
            (i32.const 73815)
           )
          )
          (i32.const 0)
          (i64.lt_u
           (i64.sub
            (local.get $3)
            (local.get $11)
           )
           (local.get $6)
          )
         )
         (i32.const 0)
         (local.tee $5
          (i32.lt_u
           (local.get $10)
           (i32.const 3700001)
          )
         )
        )
        (local.get $1)
       )
      )
      (block $block23
       (br_if $block23
        (i32.eqz
         (local.get $4)
        )
       )
       (if
        (i32.load8_u
         (i32.const 73816)
        )
        (then
         (i64.store
          (i32.const 73784)
          (local.tee $6
           (i64.sub
            (local.get $3)
            (i64.load
             (i32.const 73776)
            )
           )
          )
         )
         (local.set $1
          (select
           (select
            (i32.or
             (local.get $1)
             (i32.const 8)
            )
            (local.get $1)
            (i64.lt_u
             (local.get $6)
             (local.get $13)
            )
           )
           (local.get $1)
           (local.get $5)
          )
         )
        )
       )
       (i32.store8
        (i32.const 73816)
        (i32.const 1)
       )
       (i64.store
        (i32.const 73776)
        (local.get $3)
       )
       (br_if $block23
        (local.get $2)
       )
       (if
        (i32.load8_u
         (i32.const 73817)
        )
        (then
         (local.set $6
          (i64.sub
           (local.get $3)
           (i64.load
            (i32.const 73792)
           )
          )
         )
         (if
          (i32.load8_u
           (i32.const 73818)
          )
          (then
           (local.set $1
            (select
             (i32.or
              (local.get $1)
              (i32.const 16)
             )
             (local.get $1)
             (i64.gt_u
              (select
               (i64.sub
                (local.get $6)
                (local.tee $11
                 (i64.load
                  (i32.const 73800)
                 )
                )
               )
               (i64.sub
                (local.get $11)
                (local.get $6)
               )
               (i64.gt_u
                (local.get $6)
                (local.get $11)
               )
              )
              (i64.div_u
               (select
                (local.get $6)
                (local.get $11)
                (i64.lt_u
                 (local.get $6)
                 (local.get $11)
                )
               )
               (i64.const 50)
              )
             )
            )
           )
          )
         )
         (i32.store8
          (i32.const 73818)
          (i32.const 1)
         )
         (i64.store
          (i32.const 73800)
          (local.get $6)
         )
        )
       )
       (i32.store8
        (i32.const 73817)
        (i32.const 1)
       )
       (i64.store
        (i32.const 73792)
        (local.get $3)
       )
      )
      (i32.store8
       (i32.const 73815)
       (i32.const 1)
      )
      (i64.store
       (i32.const 73768)
       (local.get $3)
      )
      (i32.store8
       (i32.const 73812)
       (local.get $4)
      )
      (i64.store
       (i32.const 73760)
       (local.get $3)
      )
      (i32.store
       (i32.const 73808)
       (i32.or
        (i32.load
         (i32.const 73808)
        )
        (local.get $1)
       )
      )
     )
     (i32.store
      (i32.const 73824)
      (local.tee $4
       (i32.load
        (i32.const 64384)
       )
      )
     )
     (block $block24
      (if
       (i32.eqz
        (local.tee $2
         (i32.load8_u offset=24
          (local.get $7)
         )
        )
       )
       (then
        (br_if $block24
         (i32.load8_u
          (i32.const 73816)
         )
        )
       )
      )
      (i32.store
       (i32.const 73828)
       (local.get $4)
      )
      (i32.store
       (i32.const 73832)
       (local.get $4)
      )
     )
     (br_if $block20
      (i32.eqz
       (local.get $1)
      )
     )
     (i32.store8
      (i32.const 64416)
      (i32.const 0)
     )
     (br_if $block15
      (i32.load
       (i32.const 64296)
      )
     )
     (i32.store
      (i32.const 64296)
      (i32.const 18)
     )
     (i32.store
      (i32.const 64300)
      (i32.or
       (local.get $1)
       (i32.const 256)
      )
     )
     (br $block15)
    )
    (local.set $2
     (i32.and
      (i32.shr_u
       (local.get $9)
       (i32.const 6)
      )
      (block (result i32)
       (block $block25
        (if
         (i32.eqz
          (local.get $2)
         )
         (then
          (local.set $3
           (i64.load
            (i32.const 64176)
           )
          )
          (br $block25)
         )
        )
        (block $block26
         (br_if $block26
          (i32.eqz
           (local.tee $2
            (i32.load
             (i32.const 73756)
            )
           )
          )
         )
         (br_if $block26
          (i64.le_u
           (i64.load
            (i32.const 64176)
           )
           (i64.load
            (i32.const 73744)
           )
          )
         )
         (i32.store
          (i32.const 73756)
          (i32.sub
           (local.get $2)
           (i32.const 1)
          )
         )
         (if
          (i32.load8_u
           (i32.const 64341)
          )
          (then
           (i32.store8
            (i32.const 64343)
            (i32.and
             (i32.load8_u
              (i32.const 64343)
             )
             (i32.const 247)
            )
           )
           (i32.store8
            (i32.const 64343)
            (local.tee $2
             (block $block29 (result i32)
              (block $block27
               (br_if $block27
                (i32.eqz
                 (i32.and
                  (i32.load8_u
                   (i32.const 63604)
                  )
                  (i32.const 1)
                 )
                )
               )
               (block $block28
                (br_if $block28
                 (i32.eqz
                  (i32.and
                   (i32.load8_u
                    (i32.const 64334)
                   )
                   (i32.const 32)
                  )
                 )
                )
                (br_if $block28
                 (i32.and
                  (i32.load8_u
                   (i32.const 64335)
                  )
                  (i32.const 32)
                 )
                )
                (br $block29
                 (i32.const 2)
                )
               )
               (br_if $block27
                (i32.eqz
                 (i32.load8_u
                  (i32.const 65404)
                 )
                )
               )
               (br_if $block27
                (i32.eqz
                 (i32.load8_u
                  (i32.const 65370)
                 )
                )
               )
               (br $block29
                (i32.const 2)
               )
              )
              (i32.const 0)
             )
            )
           )
           (call $native.power_reset_set_other_sources
            (i64.load
             (i32.const 64176)
            )
            (local.get $2)
           )
           (call $native.power_sync)
           (br $block26)
          )
         )
         (block $block32
          (block $block31
           (if
            (i32.and
             (i32.load8_u
              (i32.const 63604)
             )
             (i32.const 1)
            )
            (then
             (block $block30
              (br_if $block30
               (i32.eqz
                (i32.and
                 (i32.load8_u
                  (i32.const 64334)
                 )
                 (i32.const 32)
                )
               )
              )
              (br_if $block30
               (i32.and
                (i32.load8_u
                 (i32.const 64335)
                )
                (i32.const 32)
               )
              )
              (i32.store8
               (i32.const 64332)
               (i32.const 1)
              )
              (br $block26)
             )
             (br_if $block31
              (i32.load8_u
               (i32.const 65404)
              )
             )
            )
           )
           (i32.store8
            (i32.const 64332)
            (i32.const 0)
           )
           (br $block32)
          )
          (i32.store8
           (i32.const 64332)
           (local.tee $2
            (i32.ne
             (i32.load8_u
              (i32.const 65370)
             )
             (i32.const 0)
            )
           )
          )
          (br_if $block26
           (local.get $2)
          )
         )
         (call $native.reset_startup
          (i32.const 8)
         )
        )
        (local.set $3
         (i64.load
          (i32.const 64176)
         )
        )
        (br_if $block25
         (i32.eqz
          (local.tee $2
           (i32.load
            (i32.const 73752)
           )
          )
         )
        )
        (br_if $block25
         (i64.le_u
          (local.get $3)
          (i64.load
           (i32.const 73728)
          )
         )
        )
        (br_if $block25
         (i64.lt_u
          (local.get $3)
          (i64.load
           (i32.const 73736)
          )
         )
        )
        (i32.store
         (i32.const 73752)
         (i32.sub
          (local.get $2)
          (i32.const 1)
         )
        )
       )
       (i32.const 1)
      )
     )
    )
    (block $block33
     (br_if $block33
      (i32.eqz
       (i32.and
        (local.tee $1
         (call $native.system_sleep_clock_edge
          (i32.load8_u offset=24
           (local.get $7)
          )
          (i32.const 0)
          (local.get $3)
         )
        )
        (i32.const 32)
       )
      )
     )
     (i32.store8
      (i32.const 64416)
      (i32.const 0)
     )
     (br_if $block33
      (i32.load
       (i32.const 64296)
      )
     )
     (i32.store
      (i32.const 64300)
      (local.get $1)
     )
     (i32.store
      (i32.const 64296)
      (i32.const 7)
     )
    )
    (i32.store8 offset=15
     (local.get $7)
     (i32.const 0)
    )
    (if
     (i32.lt_s
      (local.tee $2
       (block $block38 (result i32)
        (local.set $1
         (i32.load8_u offset=24
          (local.get $7)
         )
        )
        (local.set $9
         (i32.add
          (local.get $7)
          (i32.const 15)
         )
        )
        (block $block34
         (br_if $block34
          (i32.lt_u
           (i32.and
            (i32.sub
             (local.tee $4
              (i32.load16_u
               (i32.const 73648)
              )
             )
             (i32.const 257)
            )
            (i32.const 65535)
           )
           (i32.const 65280)
          )
         )
         (br_if $block34
          (i32.and
           (i32.sub
            (local.get $4)
            (i32.const 1)
           )
           (local.get $4)
          )
         )
         (br_if $block34
          (i32.gt_u
           (local.tee $12
            (i32.load8_u
             (i32.const 73654)
            )
           )
           (i32.const 1)
          )
         )
         (br_if $block34
          (i32.gt_u
           (local.tee $10
            (i32.load8_u
             (i32.const 73655)
            )
           )
           (i32.const 1)
          )
         )
         (br_if $block34
          (i32.ge_u
           (local.tee $14
            (i32.load16_u
             (i32.const 73652)
            )
           )
           (select
            (i32.const 1)
            (local.tee $15
             (i32.shr_u
              (local.get $4)
              (i32.const 1)
             )
            )
            (i32.eq
             (local.get $4)
             (i32.const 1)
            )
           )
          )
         )
         (block $block35
          (if
           (local.tee $5
            (i32.load16_u
             (i32.const 73650)
            )
           )
           (then
            (local.set $8
             (i32.const -1)
            )
            (br_if $block35
             (i32.gt_u
              (local.get $5)
              (i32.const 256)
             )
            )
            (br_if $block35
             (i32.and
              (local.get $5)
              (i32.sub
               (local.get $5)
               (i32.const 1)
              )
             )
            )
           )
          )
          (br_if $block34
           (i32.gt_u
            (local.get $1)
            (i32.const 1)
           )
          )
          (br_if $block34
           (i32.ne
            (local.tee $16
             (i32.load8_u
              (i32.const 73656)
             )
            )
            (i32.ne
             (local.get $5)
             (i32.const 0)
            )
           )
          )
          (br_if $block34
           (i32.eq
            (local.get $1)
            (local.get $12)
           )
          )
          (br_if $block34
           (i32.gt_u
            (local.get $2)
            (i32.const 1)
           )
          )
          (br_if $block34
           (i32.eqz
            (local.get $9)
           )
          )
          (if
           (i32.ge_u
            (local.get $9)
            (i32.const 73648)
           )
           (then
            (local.set $8
             (i32.const -1)
            )
            (br_if $block35
             (i32.lt_u
              (i32.sub
               (local.get $9)
               (i32.const 73648)
              )
              (i32.const 10)
             )
            )
           )
          )
          (i32.store8
           (i32.const 73654)
           (local.get $1)
          )
          (local.set $8
           (i32.const 0)
          )
          (br_if $block35
           (i32.eqz
            (local.get $2)
           )
          )
          (block $block36
           (if
            (i32.ne
             (local.get $4)
             (i32.const 1)
            )
            (then
             (br_if $block35
              (i32.eqz
               (local.get $1)
              )
             )
             (i32.store16
              (i32.const 73652)
              (local.tee $2
               (i32.add
                (local.get $14)
                (i32.const 1)
               )
              )
             )
             (br_if $block35
              (i32.ne
               (i32.and
                (local.get $2)
                (i32.const 65535)
               )
               (local.get $15)
              )
             )
             (i32.store16
              (i32.const 73652)
              (i32.const 0)
             )
             (i32.store8
              (i32.const 73655)
              (local.tee $1
               (i32.xor
                (local.get $10)
                (i32.const 1)
               )
              )
             )
             (br $block36)
            )
           )
           (i32.store8
            (i32.const 73655)
            (local.get $1)
           )
           (br_if $block35
            (i32.eq
             (local.get $1)
             (local.get $10)
            )
           )
          )
          (block $block37
           (br_if $block37
            (i32.eqz
             (local.get $1)
            )
           )
           (br_if $block37
            (i32.eqz
             (local.get $16)
            )
           )
           (i32.store8
            (i32.const 73656)
            (i32.const 0)
           )
           (i32.store16
            (i32.const 73648)
            (local.get $5)
           )
           (i32.store align=2
            (i32.const 73650)
            (i32.const 0)
           )
          )
          (i32.store8
           (local.get $9)
           (local.get $1)
          )
          (local.set $8
           (i32.const 1)
          )
         )
         (br $block38
          (local.get $8)
         )
        )
        (i32.const -1)
       )
      )
      (i32.const 0)
     )
     (then
      (i32.store8
       (i32.const 64416)
       (i32.const 0)
      )
      (br_if $block15
       (i32.load
        (i32.const 64296)
       )
      )
      (i64.store
       (i32.const 64296)
       (i64.const 17179869202)
      )
      (br $block15)
     )
    )
    (block $block39
     (br_if $block39
      (i32.ne
       (local.get $2)
       (i32.const 1)
      )
     )
     (block $block42
      (block $block41
       (block $block40
        (if
         (i32.load8_u
          (i32.const 65406)
         )
         (then
          (local.set $3
           (i64.const -1)
          )
          (br_if $block40
           (i64.ne
            (local.tee $6
             (i64.load
              (i32.const 64184)
             )
            )
            (i64.const -1)
           )
          )
          (i32.store8
           (i32.const 64416)
           (i32.const 0)
          )
          (br_if $block41
           (i32.load
            (i32.const 64296)
           )
          )
          (i64.store
           (i32.const 64296)
           (i64.const 4294967298)
          )
          (br $block41)
         )
        )
        (br_if $block39
         (i32.eqz
          (i32.load8_u offset=15
           (local.get $7)
          )
         )
        )
        (i32.store8
         (i32.const 65408)
         (i32.const 2)
        )
        (i32.store8
         (i32.const 65406)
         (i32.const 1)
        )
        (br $block42)
       )
       (local.set $3
        (i64.add
         (local.get $6)
         (i64.const 1)
        )
       )
      )
      (i64.store
       (i32.const 64184)
       (local.get $3)
      )
      (i32.store8
       (i32.const 65408)
       (select
        (i32.const 2)
        (i32.const 1)
        (local.tee $2
         (i32.load8_u offset=15
          (local.get $7)
         )
        )
       )
      )
      (br_if $block39
       (i32.eqz
        (local.get $2)
       )
      )
     )
     (i64.store
      (i32.const 73720)
      (i64.load
       (i32.const 64176)
      )
     )
    )
    (i32.store
     (i32.const 64304)
     (i32.load16_u
      (i32.const 73648)
     )
    )
    (i32.store
     (i32.const 64308)
     (i32.load16_u
      (i32.const 73650)
     )
    )
   )
   (call $native.service_clocks
    (local.get $0)
   )
   (block $block43
    (br_if $block43
     (i32.eqz
      (i32.and
       (local.tee $2
        (call $native.system_sleep_clock_edge
         (i32.const 0)
         (i32.eq
          (i32.load8_u
           (i32.const 65408)
          )
          (i32.const 2)
         )
         (i64.load
          (i32.const 64176)
         )
        )
       )
       (i32.const 32)
      )
     )
    )
    (i32.store8
     (i32.const 64416)
     (i32.const 0)
    )
    (br_if $block43
     (i32.load
      (i32.const 64296)
     )
    )
    (i32.store
     (i32.const 64300)
     (local.get $2)
    )
    (i32.store
     (i32.const 64296)
     (i32.const 7)
    )
   )
   (block $block45
    (block $block44
     (br_if $block44
      (i32.and
       (i32.load8_u
        (i32.const 74460)
       )
       (i32.const 4)
      )
     )
     (br_if $block44
      (i32.load8_u
       (i32.const 74463)
      )
     )
     (br_if $block44
      (i32.load8_u
       (i32.const 74464)
      )
     )
     (br_if $block45
      (i32.eqz
       (i32.load8_u
        (i32.const 74468)
       )
      )
     )
    )
    (call $native.nvm_advance
     (i64.shr_u
      (i64.load
       (i32.const 64184)
      )
      (i64.const 1)
     )
     (i64.load
      (i32.const 64200)
     )
    )
   )
   (block $block46
    (br_if $block46
     (i32.eqz
      (i32.and
       (local.tee $2
        (call $native.system_watchdog_advance
         (i64.shr_u
          (i64.load
           (i32.const 64184)
          )
          (i64.const 1)
         )
         (i64.load
          (i32.const 64216)
         )
        )
       )
       (i32.const 12)
      )
     )
    )
    (i32.store8
     (i32.const 64416)
     (i32.const 0)
    )
    (br_if $block46
     (i32.load
      (i32.const 64296)
     )
    )
    (i32.store
     (i32.const 64300)
     (local.get $2)
    )
    (i32.store
     (i32.const 64296)
     (i32.const 6)
    )
   )
   (call $native.service_end)
   (br_if $block15
    (i32.eq
     (block $block48 (result i32)
      (local.set $0
       (i64.load
        (i32.const 64176)
       )
      )
      (local.set $2
       (i32.const -2)
      )
      (block $block47
       (br_if $block47
        (i32.eqz
         (local.tee $1
          (i32.load
           (i32.const 65416)
          )
         )
        )
       )
       (br_if $block47
        (i32.eqz
         (i32.load
          (i32.const 65440)
         )
        )
       )
       (local.set $2
        (i32.const -3)
       )
       (br_if $block47
        (i64.eq
         (local.get $0)
         (i64.const -1)
        )
       )
       (br_if $block47
        (i64.lt_u
         (local.get $0)
         (i64.load
          (i32.const 65424)
         )
        )
       )
       (drop
        (br_if $block48
         (i32.const -5)
         (i64.lt_u
          (i64.load
           (i32.const 65432)
          )
          (local.get $0)
         )
        )
       )
       (block $block49
        (br_if $block49
         (i32.eqz
          (i32.load
           (i32.const 65448)
          )
         )
        )
        (br_if $block49
         (i64.gt_u
          (i64.load
           (i32.add
            (local.get $1)
            (i32.shl
             (i32.load
              (i32.const 65444)
             )
             (i32.const 4)
            )
           )
          )
          (local.get $0)
         )
        )
        (br $block48
         (i32.const -6)
        )
       )
       (i64.store
        (i32.const 65424)
        (local.get $0)
       )
       (local.set $2
        (i32.const 1)
       )
      )
      (local.get $2)
     )
     (i32.const 1)
    )
   )
   (i32.store8
    (i32.const 64416)
    (i32.const 0)
   )
   (br_if $block15
    (i32.load
     (i32.const 64296)
    )
   )
   (i64.store
    (i32.const 64296)
    (i64.const 21474836498)
   )
  )
  (global.set $global$0
   (i32.add
    (local.get $7)
    (i32.const 32)
   )
  )
 )
