 (func $native.next_event_scan (result i64)
  (local $0 i64)
  (local $1 i64)
  (local $2 i64)
  (local $3 i64)
  (local $4 i64)
  (local $5 i32)
  (local $6 i32)
  (local $7 i32)
  (local $8 i64)
  (local $9 i32)
  (local $10 i32)
  (local $11 i32)
  (local $12 i32)
  (local $scratch i32)
  (local $scratch_14 i32)
  (global.set $global$0
   (local.tee $9
    (i32.sub
     (global.get $global$0)
     (i32.const 16)
    )
   )
  )
  (local.set $6
   (i32.eqz
    (block (result i32)
     (local.set $scratch_14
      (i32.or
       (i32.load8_u
        (i32.const 74916)
       )
       (i32.or
        (i32.load8_u
         (i32.const 74912)
        )
        (block (result i32)
         (local.set $scratch
          (i32.or
           (i32.load8_u
            (i32.const 74911)
           )
           (i32.and
            (i32.load8_u
             (i32.const 74908)
            )
            (i32.const 4)
           )
          )
         )
         (local.set $2
          (i64.const -1)
         )
         (local.set $0
          (i64.const -1)
         )
         (block $block
          (br_if $block
           (i32.lt_u
            (i32.sub
             (local.tee $6
              (i32.and
               (local.tee $5
                (i32.load8_u
                 (i32.const 74331)
                )
               )
               (i32.const 7)
              )
             )
             (i32.const 6)
            )
            (i32.const -5)
           )
          )
          (br_if $block
           (i32.eqz
            (i32.load8_u
             (i32.const 74344)
            )
           )
          )
          (br_if $block
           (i32.and
            (i32.load8_u
             (i32.const 74340)
            )
            (i32.const 2)
           )
          )
          (br_if $block
           (i32.eq
            (i32.and
             (i32.load8_u
              (i32.const 74339)
             )
             (i32.const 129)
            )
            (i32.const 129)
           )
          )
          (br_if $block
           (i32.eq
            (i32.and
             (local.tee $10
              (i32.load8_u
               (i32.const 74330)
              )
             )
             (i32.const 49)
            )
            (i32.const 17)
           )
          )
          (br_if $block
           (i32.eq
            (i32.or
             (local.tee $5
              (i32.and
               (i32.shr_u
                (local.get $5)
                (i32.const 1)
               )
               (i32.const 4)
              )
             )
             (i32.and
              (local.get $10)
              (i32.const 1)
             )
            )
            (i32.const 4)
           )
          )
          (local.set $0
           (i64.extend_i32_u
            (i32.sub
             (local.tee $6
              (i32.load offset=9776
               (i32.shl
                (local.get $6)
                (i32.const 2)
               )
              )
             )
             (i32.rem_u
              (i32.load16_u
               (i32.const 74328)
              )
              (local.get $6)
             )
            )
           )
          )
          (block $block1
           (if
            (i32.eq
             (i32.or
              (i32.and
               (local.get $10)
               (i32.const 3)
              )
              (local.get $5)
             )
             (i32.const 5)
            )
            (then
             (br_if $block1
              (i32.eqz
               (i32.load8_u
                (i32.const 74335)
               )
              )
             )
            )
           )
           (local.set $0
            (i64.add
             (i64.mul
              (i64.extend_i32_u
               (i32.sub
                (call $native.event_distance)
                (i32.const 1)
               )
              )
              (i64.extend_i32_u
               (local.get $6)
              )
             )
             (local.get $0)
            )
           )
          )
          (local.set $0
           (select
            (i64.const -1)
            (local.tee $0
             (i64.add
              (local.tee $1
               (i64.load
                (i32.const 74312)
               )
              )
              (local.get $0)
             )
            )
            (i64.lt_u
             (local.get $0)
             (local.get $1)
            )
           )
          )
         )
         (block $block2
          (br_if $block2
           (i64.lt_s
            (local.get $0)
            (i64.const 0)
           )
          )
          (if
           (i64.le_u
            (local.tee $1
             (i64.shl
              (local.get $0)
              (i64.const 1)
             )
            )
            (local.tee $0
             (i64.load
              (i32.const 64632)
             )
            )
           )
           (then
            (local.set $2
             (i64.load
              (i32.const 64624)
             )
            )
            (br $block2)
           )
          )
          (br_if $block2
           (i32.load8_u
            (i32.const 65853)
           )
          )
          (local.set $3
           (i64.load
            (i32.const 64624)
           )
          )
          (if
           (i64.gt_u
            (local.tee $0
             (call $native.duration
              (i64.sub
               (local.get $1)
               (local.get $0)
              )
              (i64.mul
               (i64.load32_u
                (i32.const 64752)
               )
               (select
                (i64.const 1000000000000)
                (i64.shl
                 (i64.load32_u
                  (i32.const 64032)
                 )
                 (i64.const 1)
                )
                (i32.load8_u
                 (i32.const 64788)
                )
               )
              )
              (i64.shl
               (i64.load32_u
                (i32.const 64620)
               )
               (i64.const 1)
              )
              (i64.load
               (i32.const 64640)
              )
             )
            )
            (i64.xor
             (local.get $3)
             (i64.const -1)
            )
           )
           (then
            (i32.store8
             (i32.const 64864)
             (i32.const 0)
            )
            (br_if $block2
             (i32.load
              (i32.const 64744)
             )
            )
            (i64.store
             (i32.const 64744)
             (i64.const 4294967298)
            )
            (br $block2)
           )
          )
          (local.set $2
           (i64.add
            (local.get $0)
            (local.get $3)
           )
          )
         )
         (if
          (i32.load8_u
           (i32.const 65852)
          )
          (then
           (local.set $2
            (select
             (local.get $2)
             (local.tee $0
              (if (result i64)
               (i32.load8_u
                (i32.const 65820)
               )
               (then
                (i64.const -1)
               )
               (else
                (i64.load
                 (i32.const 65784)
                )
               )
              )
             )
             (i64.gt_u
              (local.get $0)
              (local.get $2)
             )
            )
           )
          )
         )
         (if
          (i32.load8_u
           (i32.const 64789)
          )
          (then
           (local.set $2
            (select
             (local.tee $1
              (select
               (local.get $2)
               (local.tee $0
                (select
                 (local.tee $3
                  (i64.load
                   (i32.const 64928)
                  )
                 )
                 (local.tee $0
                  (select
                   (local.tee $1
                    (i64.load
                     (i32.const 64936)
                    )
                   )
                   (local.tee $0
                    (i64.load
                     (i32.const 64944)
                    )
                   )
                   (i64.gt_u
                    (local.get $0)
                    (local.get $1)
                   )
                  )
                 )
                 (i64.gt_u
                  (local.get $0)
                  (local.get $3)
                 )
                )
               )
               (i64.gt_u
                (local.get $0)
                (local.get $2)
               )
              )
             )
             (select
              (local.get $1)
              (local.tee $0
               (i64.load
                (i32.const 64840)
               )
              )
              (i64.gt_u
               (local.get $0)
               (local.get $1)
              )
             )
             (i64.eqz
              (local.get $0)
             )
            )
           )
          )
         )
         (local.get $scratch)
        )
       )
      )
     )
     (local.set $8
      (i64.const -1)
     )
     (local.set $0
      (i64.const -1)
     )
     (block $block5
      (br_if $block5
       (i64.eq
        (local.tee $4
         (block $block3 (result i64)
          (local.set $1
           (i64.load
            (i32.const 64632)
           )
          )
          (local.set $7
           (i32.const 0)
          )
          (drop
           (br_if $block3
            (i64.const -1)
            (i32.eqz
             (i32.load8_u
              (i32.const 74391)
             )
            )
           )
          )
          (block $block4
           (br_if $block4
            (i32.ne
             (local.tee $6
              (i32.load8_u
               (i32.const 74393)
              )
             )
             (i32.load8_u
              (i32.const 74394)
             )
            )
           )
           (br_if $block4
            (i32.ne
             (i32.load8_u
              (i32.const 74378)
             )
             (local.get $6)
            )
           )
           (br_if $block4
            (i32.ne
             (i32.load8_u
              (i32.const 74395)
             )
             (i32.and
              (i32.load8_u
               (i32.const 74380)
              )
              (local.get $6)
             )
            )
           )
           (br_if $block4
            (i32.load8_u
             (i32.const 74396)
            )
           )
           (br_if $block4
            (i32.ne
             (i32.load8_u
              (i32.const 74397)
             )
             (i32.and
              (i32.shr_u
               (local.get $6)
               (i32.const 1)
              )
              (i32.const 1)
             )
            )
           )
           (br_if $block4
            (i32.ne
             (local.tee $6
              (i32.and
               (i32.shr_u
                (local.get $6)
                (i32.const 2)
               )
               (i32.const 1)
              )
             )
             (i32.load8_u
              (i32.const 74398)
             )
            )
           )
           (br_if $block4
            (i32.ne
             (i32.load8_u
              (i32.const 74399)
             )
             (local.get $6)
            )
           )
           (local.set $7
            (i32.eq
             (i32.load8_u
              (i32.const 74400)
             )
             (local.get $6)
            )
           )
          )
          (select
           (i64.const -1)
           (select
            (i64.const -1)
            (local.tee $1
             (i64.add
              (local.get $1)
              (i64.const 1)
             )
            )
            (local.get $7)
           )
           (i64.eqz
            (local.get $1)
           )
          )
         )
        )
        (i64.const -1)
       )
      )
      (if
       (i64.ge_u
        (local.tee $1
         (i64.load
          (i32.const 64632)
         )
        )
        (local.get $4)
       )
       (then
        (local.set $0
         (i64.load
          (i32.const 64624)
         )
        )
        (br $block5)
       )
      )
      (br_if $block5
       (i32.load8_u
        (i32.const 65853)
       )
      )
      (local.set $3
       (i64.load
        (i32.const 64624)
       )
      )
      (if
       (i64.gt_u
        (local.tee $1
         (call $native.duration
          (i64.sub
           (local.get $4)
           (local.get $1)
          )
          (i64.mul
           (i64.load32_u
            (i32.const 64752)
           )
           (select
            (i64.const 1000000000000)
            (i64.shl
             (i64.load32_u
              (i32.const 64032)
             )
             (i64.const 1)
            )
            (i32.load8_u
             (i32.const 64788)
            )
           )
          )
          (i64.shl
           (i64.load32_u
            (i32.const 64620)
           )
           (i64.const 1)
          )
          (i64.load
           (i32.const 64640)
          )
         )
        )
        (i64.xor
         (local.get $3)
         (i64.const -1)
        )
       )
       (then
        (i32.store8
         (i32.const 64864)
         (i32.const 0)
        )
        (br_if $block5
         (i32.load
          (i32.const 64744)
         )
        )
        (i64.store
         (i32.const 64744)
         (i64.const 4294967298)
        )
        (br $block5)
       )
      )
      (local.set $0
       (i64.add
        (local.get $1)
        (local.get $3)
       )
      )
     )
     (local.get $scratch_14)
    )
   )
  )
  (local.set $4
   (select
    (local.get $2)
    (local.get $0)
    (i64.gt_u
     (local.get $0)
     (local.get $2)
    )
   )
  )
  (local.set $2
   (i64.const -1)
  )
  (block $block6
   (br_if $block6
    (i32.eqz
     (i32.load8_u
      (i32.const 74521)
     )
    )
   )
   (br_if $block6
    (i32.eqz
     (i32.load8_u
      (i32.const 74512)
     )
    )
   )
   (local.set $2
    (i64.load
     (i32.const 74440)
    )
   )
  )
  (block $block7
   (br_if $block7
    (i64.eq
     (local.tee $3
      (select
       (local.get $2)
       (local.tee $0
        (select
         (local.tee $3
          (i64.load
           (i32.const 74552)
          )
         )
         (local.tee $0
          (select
           (local.tee $1
            (i64.load
             (i32.const 74536)
            )
           )
           (local.tee $0
            (i64.load
             (i32.const 74544)
            )
           )
           (i64.gt_u
            (local.get $0)
            (local.get $1)
           )
          )
         )
         (i64.gt_u
          (local.get $0)
          (local.get $3)
         )
        )
       )
       (i64.gt_u
        (local.get $0)
        (local.get $2)
       )
      )
     )
     (i64.const -1)
    )
   )
   (if
    (i64.ge_u
     (local.tee $0
      (i64.load
       (i32.const 64632)
      )
     )
     (local.get $3)
    )
    (then
     (local.set $8
      (i64.load
       (i32.const 64624)
      )
     )
     (br $block7)
    )
   )
   (br_if $block7
    (i32.load8_u
     (i32.const 65853)
    )
   )
   (local.set $1
    (i64.load
     (i32.const 64624)
    )
   )
   (if
    (i64.gt_u
     (local.tee $0
      (call $native.duration
       (i64.sub
        (local.get $3)
        (local.get $0)
       )
       (i64.mul
        (i64.load32_u
         (i32.const 64752)
        )
        (select
         (i64.const 1000000000000)
         (i64.shl
          (i64.load32_u
           (i32.const 64032)
          )
          (i64.const 1)
         )
         (i32.load8_u
          (i32.const 64788)
         )
        )
       )
       (i64.shl
        (i64.load32_u
         (i32.const 64620)
        )
        (i64.const 1)
       )
       (i64.load
        (i32.const 64640)
       )
      )
     )
     (i64.xor
      (local.get $1)
      (i64.const -1)
     )
    )
    (then
     (i32.store8
      (i32.const 64864)
      (i32.const 0)
     )
     (br_if $block7
      (i32.load
       (i32.const 64744)
      )
     )
     (i64.store
      (i32.const 64744)
      (i64.const 4294967298)
     )
     (br $block7)
    )
   )
   (local.set $8
    (i64.add
     (local.get $0)
     (local.get $1)
    )
   )
  )
  (local.set $2
   (select
    (local.get $4)
    (local.get $8)
    (i64.lt_u
     (local.get $4)
     (local.get $8)
    )
   )
  )
  (if
   (i32.eqz
    (local.get $6)
   )
   (then
    (local.set $0
     (i64.const -1)
    )
    (local.set $1
     (i64.const -1)
    )
    (if
     (i32.and
      (i32.load8_u
       (i32.const 74908)
      )
      (i32.const 4)
     )
     (then
      (local.set $1
       (i64.load
        (i32.const 74848)
       )
      )
     )
    )
    (block $block8
     (br_if $block8
      (i32.eqz
       (local.tee $5
        (i32.load8_u
         (i32.const 74911)
        )
       )
      )
     )
     (br_if $block8
      (i32.load8_u
       (i32.const 74916)
      )
     )
     (local.set $1
      (select
       (local.get $1)
       (local.tee $3
        (i64.load
         (select
          (i32.const 74864)
          (i32.const 74856)
          (i32.and
           (local.get $5)
           (i32.const 8)
          )
         )
        )
       )
       (i64.lt_u
        (local.get $1)
        (local.get $3)
       )
      )
     )
    )
    (block $block9
     (br_if $block9
      (i64.lt_s
       (local.get $1)
       (i64.const 0)
      )
     )
     (if
      (i64.le_u
       (local.tee $3
        (i64.shl
         (local.get $1)
         (i64.const 1)
        )
       )
       (local.tee $1
        (i64.load
         (i32.const 64632)
        )
       )
      )
      (then
       (local.set $0
        (i64.load
         (i32.const 64624)
        )
       )
       (br $block9)
      )
     )
     (br_if $block9
      (i32.load8_u
       (i32.const 65853)
      )
     )
     (local.set $4
      (i64.load
       (i32.const 64624)
      )
     )
     (if
      (i64.gt_u
       (local.tee $1
        (call $native.duration
         (i64.sub
          (local.get $3)
          (local.get $1)
         )
         (i64.mul
          (i64.load32_u
           (i32.const 64752)
          )
          (select
           (i64.const 1000000000000)
           (i64.shl
            (i64.load32_u
             (i32.const 64032)
            )
            (i64.const 1)
           )
           (i32.load8_u
            (i32.const 64788)
           )
          )
         )
         (i64.shl
          (i64.load32_u
           (i32.const 64620)
          )
          (i64.const 1)
         )
         (i64.load
          (i32.const 64640)
         )
        )
       )
       (i64.xor
        (local.get $4)
        (i64.const -1)
       )
      )
      (then
       (i32.store8
        (i32.const 64864)
        (i32.const 0)
       )
       (br_if $block9
        (i32.load
         (i32.const 64744)
        )
       )
       (i64.store
        (i32.const 64744)
        (i64.const 4294967298)
       )
       (br $block9)
      )
     )
     (local.set $0
      (i64.add
       (local.get $1)
       (local.get $4)
      )
     )
    )
    (local.set $2
     (select
      (local.get $2)
      (local.get $0)
      (i64.gt_u
       (local.get $0)
       (local.get $2)
      )
     )
    )
   )
  )
  (if
   (i64.ne
    (local.tee $1
     (i64.load
      (i32.const 64712)
     )
    )
    (i64.const 0)
   )
   (then
    (local.set $0
     (i64.const -1)
    )
    (block $block10
     (br_if $block10
      (i64.lt_s
       (local.get $1)
       (i64.const 0)
      )
     )
     (if
      (i64.le_u
       (local.tee $3
        (i64.shl
         (local.get $1)
         (i64.const 1)
        )
       )
       (local.tee $1
        (i64.load
         (i32.const 64632)
        )
       )
      )
      (then
       (local.set $0
        (i64.load
         (i32.const 64624)
        )
       )
       (br $block10)
      )
     )
     (br_if $block10
      (i32.load8_u
       (i32.const 65853)
      )
     )
     (local.set $4
      (i64.load
       (i32.const 64624)
      )
     )
     (if
      (i64.gt_u
       (local.tee $1
        (call $native.duration
         (i64.sub
          (local.get $3)
          (local.get $1)
         )
         (i64.mul
          (i64.load32_u
           (i32.const 64752)
          )
          (select
           (i64.const 1000000000000)
           (i64.shl
            (i64.load32_u
             (i32.const 64032)
            )
            (i64.const 1)
           )
           (i32.load8_u
            (i32.const 64788)
           )
          )
         )
         (i64.shl
          (i64.load32_u
           (i32.const 64620)
          )
          (i64.const 1)
         )
         (i64.load
          (i32.const 64640)
         )
        )
       )
       (i64.xor
        (local.get $4)
        (i64.const -1)
       )
      )
      (then
       (i32.store8
        (i32.const 64864)
        (i32.const 0)
       )
       (br_if $block10
        (i32.load
         (i32.const 64744)
        )
       )
       (i64.store
        (i32.const 64744)
        (i64.const 4294967298)
       )
       (br $block10)
      )
     )
     (local.set $0
      (i64.add
       (local.get $1)
       (local.get $4)
      )
     )
    )
    (local.set $2
     (select
      (local.get $2)
      (local.get $0)
      (i64.gt_u
       (local.get $0)
       (local.get $2)
      )
     )
    )
   )
  )
  (if
   (i64.ne
    (local.tee $1
     (i64.load
      (i32.const 64720)
     )
    )
    (i64.const 0)
   )
   (then
    (local.set $0
     (i64.const -1)
    )
    (block $block11
     (br_if $block11
      (i64.lt_s
       (local.get $1)
       (i64.const 0)
      )
     )
     (if
      (i64.le_u
       (local.tee $3
        (i64.shl
         (local.get $1)
         (i64.const 1)
        )
       )
       (local.tee $1
        (i64.load
         (i32.const 64632)
        )
       )
      )
      (then
       (local.set $0
        (i64.load
         (i32.const 64624)
        )
       )
       (br $block11)
      )
     )
     (br_if $block11
      (i32.load8_u
       (i32.const 65853)
      )
     )
     (local.set $4
      (i64.load
       (i32.const 64624)
      )
     )
     (if
      (i64.gt_u
       (local.tee $1
        (call $native.duration
         (i64.sub
          (local.get $3)
          (local.get $1)
         )
         (i64.mul
          (i64.load32_u
           (i32.const 64752)
          )
          (select
           (i64.const 1000000000000)
           (i64.shl
            (i64.load32_u
             (i32.const 64032)
            )
            (i64.const 1)
           )
           (i32.load8_u
            (i32.const 64788)
           )
          )
         )
         (i64.shl
          (i64.load32_u
           (i32.const 64620)
          )
          (i64.const 1)
         )
         (i64.load
          (i32.const 64640)
         )
        )
       )
       (i64.xor
        (local.get $4)
        (i64.const -1)
       )
      )
      (then
       (i32.store8
        (i32.const 64864)
        (i32.const 0)
       )
       (br_if $block11
        (i32.load
         (i32.const 64744)
        )
       )
       (i64.store
        (i32.const 64744)
        (i64.const 4294967298)
       )
       (br $block11)
      )
     )
     (local.set $0
      (i64.add
       (local.get $1)
       (local.get $4)
      )
     )
    )
    (local.set $2
     (select
      (local.get $2)
      (local.get $0)
      (i64.gt_u
       (local.get $0)
       (local.get $2)
      )
     )
    )
   )
  )
  (block $block12
   (br_if $block12
    (local.get $6)
   )
   (local.set $1
    (i64.const -1)
   )
   (block $block13
    (br_if $block13
     (i32.eqz
      (i32.load8_u
       (i32.const 74912)
      )
     )
    )
    (br_if $block13
     (i32.and
      (i32.load8_u
       (i32.const 74900)
      )
      (i32.const 128)
     )
    )
    (local.set $1
     (i64.load
      (i32.const 74872)
     )
    )
   )
   (block $block14
    (br_if $block14
     (i32.eqz
      (i32.load8_u
       (i32.const 74916)
      )
     )
    )
    (br_if $block14
     (i32.and
      (i32.load8_u
       (i32.const 74901)
      )
      (i32.const 1)
     )
    )
    (local.set $1
     (select
      (local.get $1)
      (local.tee $0
       (i64.load
        (i32.const 74880)
       )
      )
      (i64.gt_u
       (local.get $0)
       (local.get $1)
      )
     )
    )
   )
   (br_if $block12
    (i64.eq
     (local.get $1)
     (i64.const -1)
    )
   )
   (local.set $3
    (i64.load
     (i32.const 64624)
    )
   )
   (block $block15
    (if
     (i64.le_u
      (local.get $1)
      (local.tee $4
       (i64.load
        (i32.const 64648)
       )
      )
     )
     (then
      (local.set $0
       (local.get $3)
      )
      (br $block15)
     )
    )
    (local.set $0
     (i64.const -1)
    )
    (if
     (i64.gt_u
      (local.tee $1
       (call $native.duration
        (i64.sub
         (local.get $1)
         (local.get $4)
        )
        (select
         (i64.const 1000000000000)
         (i64.shl
          (i64.load32_u
           (i32.const 64032)
          )
          (i64.const 1)
         )
         (local.tee $5
          (i32.load8_u
           (i32.const 64788)
          )
         )
        )
        (i64.const 1000000000)
        (select
         (i64.mul
          (local.tee $1
           (i64.load
            (i32.const 64656)
           )
          )
          (i64.const 1000000000)
         )
         (local.get $1)
         (local.get $5)
        )
       )
      )
      (i64.xor
       (local.get $3)
       (i64.const -1)
      )
     )
     (then
      (i32.store8
       (i32.const 64864)
       (i32.const 0)
      )
      (br_if $block15
       (i32.load
        (i32.const 64744)
       )
      )
      (i64.store
       (i32.const 64744)
       (i64.const 4294967298)
      )
      (br $block15)
     )
    )
    (local.set $0
     (i64.add
      (local.get $1)
      (local.get $3)
     )
    )
   )
   (local.set $2
    (select
     (local.get $2)
     (local.get $0)
     (i64.gt_u
      (local.get $0)
      (local.get $2)
     )
    )
   )
  )
  (block $block16
   (br_if $block16
    (i32.or
     (i32.load8_u
      (i32.const 64779)
     )
     (i32.load8_u
      (i32.const 64780)
     )
    )
   )
   (block $block17
    (if
     (i32.load8_u
      (i32.const 65853)
     )
     (then
      (br_if $block16
       (i32.load
        (i32.const 74200)
       )
      )
      (br_if $block17
       (i64.ge_u
        (i64.load
         (i32.const 64624)
        )
        (i64.load
         (i32.const 74184)
        )
       )
      )
      (br $block16)
     )
    )
    (br_if $block16
     (i64.lt_u
      (i64.load
       (i32.const 64624)
      )
      (i64.load
       (i32.const 64736)
      )
     )
    )
   )
   (local.set $6
    (i32.const 0)
   )
   (block $block18
    (br_if $block18
     (i32.load8_u
      (i32.const 74680)
     )
    )
    (br_if $block18
     (i32.eqz
      (i32.and
       (local.tee $5
        (i32.load8_u
         (i32.const 74676)
        )
       )
       (i32.const 72)
      )
     )
    )
    (br_if $block18
     (i32.gt_u
      (local.tee $5
       (i32.or
        (i32.and
         (i32.shr_u
          (local.get $5)
          (i32.const 2)
         )
         (i32.const 8)
        )
        (i32.and
         (local.get $5)
         (i32.const 7)
        )
       )
      )
      (i32.const 9)
     )
    )
    (local.set $6
     (select
      (i32.const 1)
      (i32.sub
       (local.tee $6
        (i32.shl
         (i32.const 2048)
         (local.get $5)
        )
       )
       (local.tee $5
        (i32.load
         (i32.const 74672)
        )
       )
      )
      (i32.ge_u
       (local.get $5)
       (local.get $6)
      )
     )
    )
   )
   (br_if $block16
    (i32.eqz
     (local.get $6)
    )
   )
   (local.set $1
    (i64.load
     (i32.const 64624)
    )
   )
   (if
    (i64.gt_u
     (local.tee $0
      (call $native.duration
       (i64.extend_i32_u
        (local.get $6)
       )
       (select
        (i64.const 1000000000000)
        (i64.shl
         (i64.load32_u
          (i32.const 64032)
         )
         (i64.const 1)
        )
        (i32.load8_u
         (i32.const 64788)
        )
       )
       (i64.load32_u
        (i32.const 64036)
       )
       (i64.load
        (i32.const 64672)
       )
      )
     )
     (i64.xor
      (local.get $1)
      (i64.const -1)
     )
    )
    (then
     (i32.store8
      (i32.const 64864)
      (i32.const 0)
     )
     (br_if $block16
      (i32.load
       (i32.const 64744)
      )
     )
     (i64.store
      (i32.const 64744)
      (i64.const 4294967298)
     )
     (br $block16)
    )
   )
   (local.set $2
    (select
     (local.get $2)
     (local.tee $0
      (i64.add
       (local.get $0)
       (local.get $1)
      )
     )
     (i64.gt_u
      (local.get $0)
      (local.get $2)
     )
    )
   )
  )
  (if
   (i32.and
    (i32.load8_u
     (i32.const 74676)
    )
    (i32.const 16)
   )
   (then
    (local.set $0
     (i64.const -1)
    )
    (block $block19
     (br_if $block19
      (i64.lt_s
       (local.tee $1
        (i64.load
         (i32.const 74656)
        )
       )
       (i64.const 0)
      )
     )
     (if
      (i64.le_u
       (local.tee $3
        (i64.shl
         (local.get $1)
         (i64.const 1)
        )
       )
       (local.tee $1
        (i64.load
         (i32.const 64632)
        )
       )
      )
      (then
       (local.set $0
        (i64.load
         (i32.const 64624)
        )
       )
       (br $block19)
      )
     )
     (br_if $block19
      (i32.load8_u
       (i32.const 65853)
      )
     )
     (local.set $4
      (i64.load
       (i32.const 64624)
      )
     )
     (if
      (i64.gt_u
       (local.tee $1
        (call $native.duration
         (i64.sub
          (local.get $3)
          (local.get $1)
         )
         (i64.mul
          (i64.load32_u
           (i32.const 64752)
          )
          (select
           (i64.const 1000000000000)
           (i64.shl
            (i64.load32_u
             (i32.const 64032)
            )
            (i64.const 1)
           )
           (i32.load8_u
            (i32.const 64788)
           )
          )
         )
         (i64.shl
          (i64.load32_u
           (i32.const 64620)
          )
          (i64.const 1)
         )
         (i64.load
          (i32.const 64640)
         )
        )
       )
       (i64.xor
        (local.get $4)
        (i64.const -1)
       )
      )
      (then
       (i32.store8
        (i32.const 64864)
        (i32.const 0)
       )
       (br_if $block19
        (i32.load
         (i32.const 64744)
        )
       )
       (i64.store
        (i32.const 64744)
        (i64.const 4294967298)
       )
       (br $block19)
      )
     )
     (local.set $0
      (i64.add
       (local.get $1)
       (local.get $4)
      )
     )
    )
    (local.set $2
     (select
      (local.get $2)
      (local.get $0)
      (i64.gt_u
       (local.get $0)
       (local.get $2)
      )
     )
    )
   )
  )
  (if
   (i32.lt_s
    (i32.load8_s
     (i32.const 64776)
    )
    (i32.const 0)
   )
   (then
    (local.set $0
     (i64.const -1)
    )
    (block $block20
     (br_if $block20
      (i64.lt_s
       (local.tee $1
        (i64.load
         (i32.const 64680)
        )
       )
       (i64.const 0)
      )
     )
     (if
      (i64.le_u
       (local.tee $3
        (i64.shl
         (local.get $1)
         (i64.const 1)
        )
       )
       (local.tee $1
        (i64.load
         (i32.const 64632)
        )
       )
      )
      (then
       (local.set $0
        (i64.load
         (i32.const 64624)
        )
       )
       (br $block20)
      )
     )
     (br_if $block20
      (i32.load8_u
       (i32.const 65853)
      )
     )
     (local.set $4
      (i64.load
       (i32.const 64624)
      )
     )
     (if
      (i64.gt_u
       (local.tee $1
        (call $native.duration
         (i64.sub
          (local.get $3)
          (local.get $1)
         )
         (i64.mul
          (i64.load32_u
           (i32.const 64752)
          )
          (select
           (i64.const 1000000000000)
           (i64.shl
            (i64.load32_u
             (i32.const 64032)
            )
            (i64.const 1)
           )
           (i32.load8_u
            (i32.const 64788)
           )
          )
         )
         (i64.shl
          (i64.load32_u
           (i32.const 64620)
          )
          (i64.const 1)
         )
         (i64.load
          (i32.const 64640)
         )
        )
       )
       (i64.xor
        (local.get $4)
        (i64.const -1)
       )
      )
      (then
       (i32.store8
        (i32.const 64864)
        (i32.const 0)
       )
       (br_if $block20
        (i32.load
         (i32.const 64744)
        )
       )
       (i64.store
        (i32.const 64744)
        (i64.const 4294967298)
       )
       (br $block20)
      )
     )
     (local.set $0
      (i64.add
       (local.get $1)
       (local.get $4)
      )
     )
    )
    (local.set $2
     (select
      (local.get $2)
      (local.get $0)
      (i64.gt_u
       (local.get $0)
       (local.get $2)
      )
     )
    )
   )
  )
  (block $block21
   (br_if $block21
    (i32.eqz
     (i32.load
      (i32.const 64756)
     )
    )
   )
   (br_if $block21
    (i32.load8_u
     (i32.const 65853)
    )
   )
   (local.set $0
    (i64.const -1)
   )
   (block $block22
    (br_if $block22
     (i64.eq
      (local.tee $4
       (i64.load
        (i32.const 64688)
       )
      )
      (i64.const -1)
     )
    )
    (local.set $1
     (i64.load
      (i32.const 64624)
     )
    )
    (if
     (i64.ge_u
      (local.tee $3
       (i64.load
        (i32.const 64632)
       )
      )
      (local.get $4)
     )
     (then
      (local.set $0
       (local.get $1)
      )
      (br $block22)
     )
    )
    (if
     (i64.gt_u
      (local.tee $3
       (call $native.duration
        (i64.sub
         (local.get $4)
         (local.get $3)
        )
        (i64.mul
         (i64.load32_u
          (i32.const 64752)
         )
         (select
          (i64.const 1000000000000)
          (i64.shl
           (i64.load32_u
            (i32.const 64032)
           )
           (i64.const 1)
          )
          (i32.load8_u
           (i32.const 64788)
          )
         )
        )
        (i64.shl
         (i64.load32_u
          (i32.const 64620)
         )
         (i64.const 1)
        )
        (i64.load
         (i32.const 64640)
        )
       )
      )
      (i64.xor
       (local.get $1)
       (i64.const -1)
      )
     )
     (then
      (i32.store8
       (i32.const 64864)
       (i32.const 0)
      )
      (br_if $block22
       (i32.load
        (i32.const 64744)
       )
      )
      (i64.store
       (i32.const 64744)
       (i64.const 4294967298)
      )
      (br $block22)
     )
    )
    (local.set $0
     (i64.add
      (local.get $1)
      (local.get $3)
     )
    )
   )
   (local.set $2
    (select
     (local.get $2)
     (local.get $0)
     (i64.gt_u
      (local.get $0)
      (local.get $2)
     )
    )
   )
  )
  (local.set $1
   (select
    (local.get $2)
    (local.tee $0
     (block $block24 (result i64)
      (local.set $5
       (i32.load8_u
        (i32.const 74775)
       )
      )
      (block $block23
       (if
        (i32.load8_u
         (i32.const 74776)
        )
        (then
         (if
          (i32.eq
           (local.get $5)
           (i32.const 2)
          )
          (then
           (br_if $block23
            (i64.gt_u
             (local.tee $0
              (i64.load
               (i32.const 74736)
              )
             )
             (i64.load
              (i32.const 74688)
             )
            )
           )
          )
         )
         (br $block24
          (i64.const -1)
         )
        )
       )
       (local.set $0
        (i64.const -1)
       )
       (block $block26
        (block $block25
         (br_table $block25 $block26 $block23
          (i32.sub
           (local.get $5)
           (i32.const 2)
          )
         )
        )
        (br $block24
         (i64.load
          (i32.const 74712)
         )
        )
       )
       (local.set $0
        (i64.load
         (i32.const 74720)
        )
       )
      )
      (local.get $0)
     )
    )
    (i64.gt_u
     (local.get $0)
     (local.get $2)
    )
   )
  )
  (local.set $2
   (block $block27 (result i64)
    (if
     (i32.eqz
      (i32.load8_u
       (i32.const 65853)
      )
     )
     (then
      (br $block27
       (select
        (select
         (local.get $1)
         (local.tee $0
          (i64.load
           (i32.const 64736)
          )
         )
         (i64.gt_u
          (local.get $0)
          (local.get $1)
         )
        )
        (local.get $1)
        (i64.lt_u
         (i64.load
          (i32.const 64624)
         )
         (local.get $0)
        )
       )
      )
     )
    )
    (local.set $5
     (call $native.attiny13a_clki_peek
      (local.get $9)
     )
    )
    (select
     (select
      (local.tee $1
       (select
        (select
         (local.get $1)
         (local.tee $0
          (i64.load
           (local.get $9)
          )
         )
         (i64.gt_u
          (local.get $0)
          (local.get $1)
         )
        )
        (local.get $1)
        (i32.eq
         (local.get $5)
         (i32.const 1)
        )
       )
      )
      (local.tee $0
       (i64.load
        (i32.const 74184)
       )
      )
      (i64.gt_u
       (local.get $0)
       (local.get $1)
      )
     )
     (local.get $1)
     (i64.gt_u
      (local.get $0)
      (i64.load
       (i32.const 64624)
      )
     )
    )
   )
  )
  (if
   (i32.load16_u
    (i32.const 64762)
   )
   (then
    (local.set $2
     (select
      (local.get $2)
      (local.tee $0
       (i64.load offset=107768
        (i32.shl
         (i32.load16_u
          (i32.const 64760)
         )
         (i32.const 4)
        )
       )
      )
      (i64.gt_u
       (local.get $0)
       (local.get $2)
      )
     )
    )
   )
  )
  (global.set $global$0
   (i32.add
    (local.get $9)
    (i32.const 16)
   )
  )
  (local.get $2)
 )
