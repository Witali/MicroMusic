(func $native.advance_half_until_ps (param $0 i64) (param $1 i64) (param $2 i32) (param $3 i32) (result i32)
  (local $4 i64)
  (local $5 i64)
  (local $6 i64)
  (local $7 i32)
  (local $8 i64)
  (local $9 i32)
  (local $10 i64)
  (local $11 i64)
  (local $12 i64)
  (local $13 i32)
  (local $scratch i64)
  (block $block4
   (block $block2
    (block $block21
     (block $block1
      (block $block
       (if
        (local.get $2)
        (then
         (i64.store
          (local.get $2)
          (i64.const 0)
         )
         (br_if $block
          (i32.load8_u
           (i32.const 64327)
          )
         )
        )
       )
       (i32.store8
        (i32.const 64416)
        (i32.const 0)
       )
       (local.set $7
        (i32.const -1)
       )
       (br_if $block1
        (i32.load
         (i32.const 64296)
        )
       )
       (i64.store
        (i32.const 64296)
        (i64.const 60129542145)
       )
       (br $block2)
      )
      (if
       (i32.ne
        (i32.load8_u
         (i32.const 64340)
        )
        (i32.const 1)
       )
       (then
        (i32.store8
         (i32.const 64416)
         (i32.const 0)
        )
        (local.set $7
         (i32.const -1)
        )
        (br_if $block1
         (i32.load
          (i32.const 64296)
         )
        )
        (i64.store
         (i32.const 64296)
         (i64.const 51539607565)
        )
        (br $block2)
       )
      )
      (br_if $block2
       (i32.load
        (i32.const 64296)
       )
      )
      (if
       (i64.gt_u
        (local.tee $4
         (i64.load
          (i32.const 64176)
         )
        )
        (local.get $1)
       )
       (then
        (i64.store
         (i32.const 64296)
         (i64.const 51539607554)
        )
        (i32.store8
         (i32.const 64416)
         (i32.const 0)
        )
        (br $block2)
       )
      )
      (block $block5
       (block $block8
        (if
         (i32.load8_u
          (i32.const 65405)
         )
         (then
          (local.set $10
           (i64.const -1)
          )
          (block $block3
           (if
            (i64.lt_u
             (local.tee $5
              (i64.xor
               (local.tee $8
                (i64.load
                 (i32.const 64184)
                )
               )
               (i64.const -1)
              )
             )
             (local.get $0)
            )
            (then
             (i64.store
              (i32.const 64296)
              (i64.const 4294967298)
             )
             (i32.store8
              (i32.const 64416)
              (i32.const 0)
             )
             (br $block3)
            )
           )
           (local.set $10
            (i64.add
             (local.get $0)
             (local.get $8)
            )
           )
          )
          (i32.store8
           (i32.const 65407)
           (i32.const 0)
          )
          (br_if $block2
           (i64.gt_u
            (local.get $0)
            (local.get $5)
           )
          )
          (br_if $block2
           (i32.load8_u
            (i32.const 64331)
           )
          )
          (br_if $block4
           (i64.eqz
            (local.get $0)
           )
          )
          (br_if $block1
           (i32.load8_u
            (i32.const 64332)
           )
          )
          (br_if $block1
           (i32.load
            (i32.const 73752)
           )
          )
          (br_if $block1
           (i64.lt_u
            (local.get $4)
            (i64.load
             (i32.const 73736)
            )
           )
          )
          (local.set $12
           (i64.load
            (i32.const 73712)
           )
          )
          (if
           (i32.load8_u
            (i32.const 64341)
           )
           (then
            (br_if $block1
             (i64.ne
              (i64.load
               (i32.const 64496)
              )
              (i64.const -1)
             )
            )
           )
          )
          (local.set $6
           (select
            (local.get $1)
            (local.get $12)
            (i64.lt_u
             (local.get $1)
             (local.get $12)
            )
           )
          )
          (br_if $block5
           (i64.ge_u
            (local.tee $5
             (local.get $8)
            )
            (local.get $10)
           )
          )
          (block $block6
           (if
            (local.get $3)
            (then
             (br_if $block5
              (i64.ge_u
               (local.get $4)
               (local.get $6)
              )
             )
             (br_if $block5
              (i32.le_u
               (local.get $3)
               (i32.load16_u
                (i32.const 64322)
               )
              )
             )
             (br_if $block6
              (i32.load8_u
               (i32.const 64325)
              )
             )
             (br_if $block6
              (i32.gt_u
               (local.get $3)
               (i32.load16_u
                (i32.const 64318)
               )
              )
             )
             (br $block5)
            )
           )
           (br_if $block5
            (i64.ge_u
             (local.get $4)
             (local.get $6)
            )
           )
           (loop $label
            (call $native.advance_to
             (select
              (local.tee $5
               (call $native.next_event)
              )
              (local.get $6)
              (i64.lt_u
               (local.get $5)
               (local.get $6)
              )
             )
            )
            (local.set $7
             (i32.load8_u
              (i32.const 64331)
             )
            )
            (local.set $9
             (i32.load
              (i32.const 64296)
             )
            )
            (block $block7
             (br_if $block7
              (i64.ne
               (local.get $4)
               (local.tee $11
                (i64.load
                 (i32.const 64176)
                )
               )
              )
             )
             (br_if $block7
              (local.get $9)
             )
             (br_if $block8
              (i32.eqz
               (local.get $7)
              )
             )
            )
            (br_if $block5
             (i64.ge_u
              (local.tee $5
               (i64.load
                (i32.const 64184)
               )
              )
              (local.get $10)
             )
            )
            (br_if $block5
             (i64.le_u
              (local.get $6)
              (local.get $11)
             )
            )
            (br_if $block5
             (local.get $9)
            )
            (local.set $4
             (local.get $11)
            )
            (br_if $label
             (i32.eqz
              (local.get $7)
             )
            )
           )
           (br $block5)
          )
          (loop $label1
           (call $native.advance_to
            (select
             (local.tee $5
              (call $native.next_event)
             )
             (local.get $6)
             (i64.lt_u
              (local.get $5)
              (local.get $6)
             )
            )
           )
           (local.set $7
            (i32.load8_u
             (i32.const 64331)
            )
           )
           (local.set $9
            (i32.load
             (i32.const 64296)
            )
           )
           (block $block9
            (br_if $block9
             (i64.ne
              (local.get $4)
              (local.tee $11
               (i64.load
                (i32.const 64176)
               )
              )
             )
            )
            (br_if $block9
             (local.get $9)
            )
            (br_if $block8
             (i32.eqz
              (local.get $7)
             )
            )
           )
           (br_if $block5
            (i64.ge_u
             (local.tee $5
              (i64.load
               (i32.const 64184)
              )
             )
             (local.get $10)
            )
           )
           (br_if $block5
            (i64.le_u
             (local.get $6)
             (local.get $11)
            )
           )
           (br_if $block5
            (local.get $9)
           )
           (br_if $block5
            (local.get $7)
           )
           (br_if $block5
            (i32.le_u
             (local.get $3)
             (i32.load16_u
              (i32.const 64322)
             )
            )
           )
           (local.set $4
            (local.get $11)
           )
           (br_if $label1
            (i32.load8_u
             (i32.const 64325)
            )
           )
           (br_if $label1
            (i32.lt_u
             (i32.load16_u
              (i32.const 64318)
             )
             (local.get $3)
            )
           )
          )
          (br $block5)
         )
        )
        (br_if $block2
         (i32.load8_u
          (i32.const 64331)
         )
        )
        (br_if $block1
         (i32.load8_u
          (i32.const 64332)
         )
        )
        (br_if $block1
         (i64.lt_u
          (local.get $4)
          (i64.load
           (i32.const 64288)
          )
         )
        )
        (if
         (i64.lt_u
          (i64.xor
           (local.tee $11
            (i64.load
             (i32.const 64184)
            )
           )
           (i64.const -1)
          )
          (local.get $0)
         )
         (then
          (i64.store
           (i32.const 64296)
           (i64.const 4294967298)
          )
          (i32.store8
           (i32.const 64416)
           (i32.const 0)
          )
          (br $block2)
         )
        )
        (br_if $block4
         (i64.eqz
          (local.get $0)
         )
        )
        (if
         (i32.load8_u
          (i32.const 64341)
         )
         (then
          (br_if $block1
           (i64.ne
            (i64.load
             (i32.const 64496)
            )
            (i64.const -1)
           )
          )
         )
        )
        (local.set $8
         (i64.add
          (local.get $0)
          (local.get $11)
         )
        )
        (block $block19
         (block $block10
          (br_if $block10
           (i64.lt_u
            (local.get $0)
            (i64.const 129)
           )
          )
          (br_if $block10
           (i32.eqz
            (local.get $3)
           )
          )
          (local.set $3
           (block $block11 (result i32)
            (local.set $13
             (i32.and
              (local.tee $9
               (local.get $3)
              )
              (i32.const 65535)
             )
            )
            (block $block12
             (loop $label3
              (drop
               (br_if $block11
                (i32.const 0)
                (i64.ge_u
                 (local.tee $6
                  (i64.load
                   (i32.const 64184)
                  )
                 )
                 (local.get $8)
                )
               )
              )
              (local.set $3
               (i32.const 0)
              )
              (br_if $block12
               (i64.ge_u
                (local.tee $5
                 (i64.load
                  (i32.const 64176)
                 )
                )
                (local.get $1)
               )
              )
              (br_if $block12
               (i32.load
                (i32.const 64296)
               )
              )
              (br_if $block12
               (i32.load8_u
                (i32.const 64331)
               )
              )
              (local.set $4
               (local.get $1)
              )
              (block $block13
               (br_if $block13
                (i64.eq
                 (local.get $8)
                 (i64.const -1)
                )
               )
               (br_if $block13
                (i32.load8_u
                 (i32.const 65405)
                )
               )
               (if
                (i64.gt_u
                 (local.tee $6
                  (call $native.duration
                   (i64.sub
                    (local.get $8)
                    (local.get $6)
                   )
                   (i64.mul
                    (i64.load32_u
                     (i32.const 64304)
                    )
                    (select
                     (i64.const 1000000000000)
                     (i64.shl
                      (i64.load32_u
                       (i32.const 63584)
                      )
                      (i64.const 1)
                     )
                     (i32.load8_u
                      (i32.const 64340)
                     )
                    )
                   )
                   (i64.shl
                    (i64.load32_u
                     (i32.const 64172)
                    )
                    (i64.const 1)
                   )
                   (i64.load
                    (i32.const 64192)
                   )
                  )
                 )
                 (i64.xor
                  (local.get $5)
                  (i64.const -1)
                 )
                )
                (then
                 (i32.store8
                  (i32.const 64416)
                  (i32.const 0)
                 )
                 (br_if $block13
                  (i32.load
                   (i32.const 64296)
                  )
                 )
                 (i64.store
                  (i32.const 64296)
                  (i64.const 4294967298)
                 )
                 (br $block13)
                )
               )
               (local.set $4
                (select
                 (local.tee $4
                  (i64.add
                   (local.get $5)
                   (local.get $6)
                  )
                 )
                 (local.get $1)
                 (i64.gt_u
                  (local.get $1)
                  (local.get $4)
                 )
                )
               )
              )
              (if
               (i32.load
                (i32.const 64308)
               )
               (then
                (local.set $5
                 (i64.const -1)
                )
                (block $block14
                 (br_if $block14
                  (i64.eq
                   (local.tee $6
                    (i64.load
                     (i32.const 64240)
                    )
                   )
                   (i64.const -1)
                  )
                 )
                 (if
                  (i64.ge_u
                   (local.tee $12
                    (i64.load
                     (i32.const 64184)
                    )
                   )
                   (local.get $6)
                  )
                  (then
                   (local.set $5
                    (i64.load
                     (i32.const 64176)
                    )
                   )
                   (br $block14)
                  )
                 )
                 (br_if $block14
                  (i32.load8_u
                   (i32.const 65405)
                  )
                 )
                 (local.set $10
                  (i64.load
                   (i32.const 64176)
                  )
                 )
                 (if
                  (i64.gt_u
                   (local.tee $6
                    (call $native.duration
                     (i64.sub
                      (local.get $6)
                      (local.get $12)
                     )
                     (i64.mul
                      (i64.load32_u
                       (i32.const 64304)
                      )
                      (select
                       (i64.const 1000000000000)
                       (i64.shl
                        (i64.load32_u
                         (i32.const 63584)
                        )
                        (i64.const 1)
                       )
                       (i32.load8_u
                        (i32.const 64340)
                       )
                      )
                     )
                     (i64.shl
                      (i64.load32_u
                       (i32.const 64172)
                      )
                      (i64.const 1)
                     )
                     (i64.load
                      (i32.const 64192)
                     )
                    )
                   )
                   (i64.xor
                    (local.get $10)
                    (i64.const -1)
                   )
                  )
                  (then
                   (i32.store8
                    (i32.const 64416)
                    (i32.const 0)
                   )
                   (br_if $block14
                    (i32.load
                     (i32.const 64296)
                    )
                   )
                   (i64.store
                    (i32.const 64296)
                    (i64.const 4294967298)
                   )
                   (br $block14)
                  )
                 )
                 (local.set $5
                  (i64.add
                   (local.get $6)
                   (local.get $10)
                  )
                 )
                )
                (local.set $4
                 (select
                  (local.get $4)
                  (local.get $5)
                  (i64.lt_u
                   (local.get $4)
                   (local.get $5)
                  )
                 )
                )
               )
              )
              (br_if $block12
               (i32.load
                (i32.const 64296)
               )
              )
              (block $block15
               (if
                (i64.gt_u
                 (local.tee $10
                  (i64.load
                   (i32.const 64176)
                  )
                 )
                 (local.get $4)
                )
                (then
                 (i64.store
                  (i32.const 64296)
                  (i64.const 21474836482)
                 )
                 (i32.store8
                  (i32.const 64416)
                  (i32.const 0)
                 )
                 (br $block15)
                )
               )
               (br_if $block15
                (i32.load8_u
                 (i32.const 64331)
                )
               )
               (local.set $7
                (i32.const 0)
               )
               (loop $label2
                (if
                 (i64.lt_u
                  (local.tee $5
                   (select
                    (local.tee $5
                     (call $native.next_event)
                    )
                    (local.get $4)
                    (i64.gt_u
                     (local.get $4)
                     (local.get $5)
                    )
                   )
                  )
                  (local.tee $6
                   (i64.load
                    (i32.const 64176)
                   )
                  )
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
                   (i64.const 25769803778)
                  )
                  (br $block15)
                 )
                )
                (call $native.service
                 (block (result i64)
                  (local.set $scratch
                   (i64.load
                    (i32.const 64184)
                   )
                  )
                  (block $block16
                   (br_if $block16
                    (i64.le_u
                     (local.get $5)
                     (local.get $6)
                    )
                   )
                   (br_if $block16
                    (i32.load
                     (i32.const 64296)
                    )
                   )
                   (local.set $3
                    (i32.const 2)
                   )
                   (br_if $block12
                    (i32.ge_u
                     (i32.load16_u
                      (i32.const 64322)
                     )
                     (local.get $13)
                    )
                   )
                   (br_if $block16
                    (i32.load8_u
                     (i32.const 64325)
                    )
                   )
                   (br_if $block12
                    (i32.le_u
                     (local.get $9)
                     (i32.load16_u
                      (i32.const 64318)
                     )
                    )
                   )
                  )
                  (call $native.elapse
                   (local.get $5)
                  )
                  (local.get $scratch)
                 )
                )
                (br_if $block15
                 (i32.load8_u
                  (i32.const 64331)
                 )
                )
                (local.set $3
                 (i32.const 0)
                )
                (block $block17
                 (br_if $block17
                  (i64.ne
                   (local.tee $5
                    (i64.load
                     (i32.const 64176)
                    )
                   )
                   (local.get $6)
                  )
                 )
                 (br_if $block17
                  (i32.lt_u
                   (local.tee $3
                    (i32.add
                     (local.get $7)
                     (i32.const 1)
                    )
                   )
                   (i32.const 17)
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
                  (i64.const 30064771074)
                 )
                 (br $block15)
                )
                (block $block18
                 (if
                  (i64.eq
                   (local.get $4)
                   (local.get $5)
                  )
                  (then
                   (br_if $block15
                    (i64.gt_u
                     (call $native.next_event)
                     (local.get $4)
                    )
                   )
                   (br_if $block18
                    (i64.le_u
                     (local.tee $5
                      (i64.load
                       (i32.const 64176)
                      )
                     )
                     (local.get $4)
                    )
                   )
                   (br $block15)
                  )
                 )
                 (br_if $block15
                  (i64.lt_u
                   (local.get $4)
                   (local.get $5)
                  )
                 )
                )
                (local.set $7
                 (local.get $3)
                )
                (br_if $label2
                 (i32.eqz
                  (i32.load
                   (i32.const 64296)
                  )
                 )
                )
               )
               (br_if $block15
                (i64.le_u
                 (local.get $4)
                 (local.get $5)
                )
               )
               (call $native.elapse
                (local.get $4)
               )
              )
              (br_if $label3
               (i64.ne
                (i64.load
                 (i32.const 64176)
                )
                (local.get $10)
               )
              )
              (br_if $label3
               (i32.load
                (i32.const 64296)
               )
              )
              (br_if $label3
               (i32.load8_u
                (i32.const 64331)
               )
              )
             )
             (local.set $3
              (i32.const 0)
             )
             (i64.store
              (i32.const 64296)
              (i64.const 55834574850)
             )
             (i32.store8
              (i32.const 64416)
              (i32.const 0)
             )
            )
            (local.get $3)
           )
          )
          (br $block19)
         )
         (local.set $3
          (i32.const 0)
         )
         (br_if $block19
          (i64.le_u
           (local.get $8)
           (local.get $11)
          )
         )
         (loop $label4
          (br_if $block19
           (i64.le_u
            (local.get $1)
            (local.get $4)
           )
          )
          (br_if $block19
           (local.get $7)
          )
          (br_if $block19
           (local.get $9)
          )
          (local.set $4
           (select
            (local.tee $4
             (call $native.at_half
              (local.get $8)
             )
            )
            (local.get $1)
            (i64.gt_u
             (local.get $1)
             (local.get $4)
            )
           )
          )
          (if
           (i32.load
            (i32.const 64308)
           )
           (then
            (local.set $4
             (select
              (local.get $4)
              (local.tee $5
               (call $native.at_half
                (i64.load
                 (i32.const 64240)
                )
               )
              )
              (i64.lt_u
               (local.get $4)
               (local.get $5)
              )
             )
            )
           )
          )
          (br_if $block19
           (i32.load
            (i32.const 64296)
           )
          )
          (local.set $5
           (i64.load
            (i32.const 64176)
           )
          )
          (call $native.advance_to
           (local.get $4)
          )
          (local.set $9
           (i32.load8_u
            (i32.const 64331)
           )
          )
          (local.set $7
           (i32.load
            (i32.const 64296)
           )
          )
          (block $block20
           (br_if $block20
            (i64.ne
             (local.get $5)
             (local.tee $4
              (i64.load
               (i32.const 64176)
              )
             )
            )
           )
           (br_if $block20
            (local.get $7)
           )
           (br_if $block20
            (local.get $9)
           )
           (i64.store
            (i32.const 64296)
            (i64.const 55834574850)
           )
           (i32.store8
            (i32.const 64416)
            (i32.const 0)
           )
           (br $block19)
          )
          (br_if $label4
           (i64.lt_u
            (i64.load
             (i32.const 64184)
            )
            (local.get $8)
           )
          )
         )
        )
        (i64.store
         (local.get $2)
         (local.tee $1
          (i64.sub
           (i64.load
            (i32.const 64184)
           )
           (local.get $11)
          )
         )
        )
        (br_if $block21
         (i64.lt_u
          (local.get $0)
          (local.get $1)
         )
        )
        (br_if $block2
         (i32.load
          (i32.const 64296)
         )
        )
        (local.set $7
         (i32.const -1)
        )
        (br_if $block1
         (i32.load8_u
          (i32.const 64331)
         )
        )
        (local.set $7
         (select
          (i32.const 1)
          (local.get $3)
          (i64.eq
           (local.get $0)
           (local.get $1)
          )
         )
        )
        (br $block1)
       )
       (i64.store
        (i32.const 64296)
        (i64.const 55834574850)
       )
       (i32.store8
        (i32.const 64416)
        (i32.const 0)
       )
       (local.set $5
        (i64.load
         (i32.const 64184)
        )
       )
      )
      (i64.store
       (local.get $2)
       (local.tee $4
        (i64.sub
         (local.get $5)
         (local.get $8)
        )
       )
      )
      (br_if $block21
       (i64.lt_u
        (local.get $0)
        (local.get $4)
       )
      )
      (br_if $block2
       (i32.load
        (i32.const 64296)
       )
      )
      (local.set $7
       (i32.const -1)
      )
      (br_if $block1
       (i32.load8_u
        (i32.const 64331)
       )
      )
      (local.set $7
       (i32.const 1)
      )
      (br_if $block1
       (i64.eq
        (local.get $0)
        (local.get $4)
       )
      )
      (block $block22
       (br_if $block22
        (i32.eqz
         (local.get $3)
        )
       )
       (local.set $7
        (i32.const 2)
       )
       (br_if $block1
        (i32.le_u
         (local.get $3)
         (i32.load16_u
          (i32.const 64322)
         )
        )
       )
       (br_if $block22
        (i32.load8_u
         (i32.const 64325)
        )
       )
       (br_if $block1
        (i32.le_u
         (local.get $3)
         (i32.load16_u
          (i32.const 64318)
         )
        )
       )
      )
      (i32.store8
       (i32.const 65407)
       (select
        (i32.const 1)
        (select
         (i32.const 2)
         (i32.const 1)
         (i64.eq
          (i64.load
           (i32.const 64176)
          )
          (local.get $6)
         )
        )
        (i64.le_u
         (local.get $1)
         (local.get $12)
        )
       )
      )
      (return
       (i32.const 0)
      )
     )
     (return
      (local.get $7)
     )
    )
    (i32.store8
     (i32.const 64416)
     (i32.const 0)
    )
    (br_if $block2
     (i32.load
      (i32.const 64296)
     )
    )
    (i64.store
     (i32.const 64296)
     (i64.const 60129542146)
    )
   )
   (return
    (i32.const -1)
   )
  )
  (call $native.advance_to
   (local.get $4)
  )
  (select
   (i32.const -1)
   (select
    (i32.const -1)
    (i32.const 1)
    (i32.load8_u
     (i32.const 64331)
    )
   )
   (i32.load
    (i32.const 64296)
   )
  )
 )
