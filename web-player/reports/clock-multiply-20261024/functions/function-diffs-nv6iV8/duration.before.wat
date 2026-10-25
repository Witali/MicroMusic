(func $native.duration (param $0 i64) (param $1 i64) (param $2 i64) (param $3 i64) (result i64)
  (local $4 i64)
  (local $5 i64)
  (local $6 i64)
  (local $7 i32)
  (local $8 i32)
  (local $9 i64)
  (local $10 i32)
  (global.set $global$0
   (local.tee $8
    (i32.sub
     (global.get $global$0)
     (i32.const 16)
    )
   )
  )
  (block $block1
   (block $block
    (br_if $block
     (i64.eqz
      (local.get $2)
     )
    )
    (br_if $block
     (i64.le_u
      (local.get $1)
      (local.get $3)
     )
    )
    (if
     (i64.eqz
      (local.get $0)
     )
     (then
      (local.set $2
       (i64.const 0)
      )
      (br $block1)
     )
    )
    (block $block2
     (if
      (i64.ge_u
       (local.tee $5
        (i64.div_u
         (i64.const -1)
         (local.get $1)
        )
       )
       (local.get $0)
      )
      (then
       (local.set $4
        (i64.div_u
         (local.tee $0
          (i64.mul
           (local.get $0)
           (local.get $1)
          )
         )
         (local.get $2)
        )
       )
       (local.set $0
        (i64.rem_u
         (local.get $0)
         (local.get $2)
        )
       )
       (br $block2)
      )
     )
     (if
      (i64.ge_u
       (local.get $5)
       (local.tee $6
        (i64.sub
         (local.get $0)
         (i64.mul
          (local.tee $4
           (i64.div_u
            (local.get $0)
            (local.get $2)
           )
          )
          (local.get $2)
         )
        )
       )
      )
      (then
       (call $native.__multi3
        (local.get $8)
        (local.get $1)
        (local.get $4)
       )
       (br_if $block
        (i64.ne
         (i64.load offset=8
          (local.get $8)
         )
         (i64.const 0)
        )
       )
       (br_if $block
        (i64.gt_u
         (local.tee $5
          (i64.div_u
           (local.tee $0
            (i64.mul
             (local.get $1)
             (local.get $6)
            )
           )
           (local.get $2)
          )
         )
         (i64.xor
          (local.tee $1
           (i64.mul
            (local.get $1)
            (local.get $4)
           )
          )
          (i64.const -1)
         )
        )
       )
       (local.set $4
        (i64.add
         (local.get $1)
         (local.get $5)
        )
       )
       (local.set $0
        (i64.rem_u
         (local.get $0)
         (local.get $2)
        )
       )
       (br $block2)
      )
     )
     (br_if $block
      (i64.ge_u
       (local.tee $0
        (i64.add
         (i64.add
          (i64.shr_u
           (local.tee $4
            (i64.add
             (i64.shr_u
              (local.tee $6
               (i64.mul
                (local.tee $4
                 (i64.and
                  (local.get $1)
                  (i64.const 4294967295)
                 )
                )
                (local.tee $5
                 (i64.and
                  (local.get $0)
                  (i64.const 4294967295)
                 )
                )
               )
              )
              (i64.const 32)
             )
             (i64.mul
              (local.get $4)
              (local.tee $0
               (i64.shr_u
                (local.get $0)
                (i64.const 32)
               )
              )
             )
            )
           )
           (i64.const 32)
          )
          (i64.mul
           (local.get $0)
           (local.tee $0
            (i64.shr_u
             (local.get $1)
             (i64.const 32)
            )
           )
          )
         )
         (i64.shr_u
          (local.tee $1
           (i64.add
            (i64.mul
             (local.get $0)
             (local.get $5)
            )
            (i64.and
             (local.get $4)
             (i64.const 4294967295)
            )
           )
          )
          (i64.const 32)
         )
        )
       )
       (local.get $2)
      )
     )
     (local.set $5
      (i64.or
       (i64.and
        (local.get $6)
        (i64.const 4294967295)
       )
       (i64.shl
        (local.get $1)
        (i64.const 32)
       )
      )
     )
     (local.set $1
      (i64.const 62)
     )
     (local.set $4
      (i64.const 0)
     )
     (loop $label
      (local.set $0
       (i64.sub
        (local.tee $9
         (i64.or
          (i64.and
           (i64.shr_u
            (local.get $5)
            (local.get $1)
           )
           (i64.const 1)
          )
          (i64.shl
           (local.tee $0
            (i64.sub
             (local.tee $9
              (i64.or
               (i64.and
                (i64.shr_u
                 (local.get $5)
                 (local.tee $6
                  (i64.add
                   (local.get $1)
                   (i64.const 1)
                  )
                 )
                )
                (i64.const 1)
               )
               (i64.shl
                (local.get $0)
                (i64.const 1)
               )
              )
             )
             (select
              (i64.const 0)
              (local.get $2)
              (local.tee $7
               (i32.and
                (i64.gt_u
                 (local.get $2)
                 (local.get $9)
                )
                (i64.ge_s
                 (local.get $0)
                 (i64.const 0)
                )
               )
              )
             )
            )
           )
           (i64.const 1)
          )
         )
        )
        (select
         (i64.const 0)
         (local.get $2)
         (local.tee $10
          (i32.and
           (i64.gt_u
            (local.get $2)
            (local.get $9)
           )
           (i64.ge_s
            (local.get $0)
            (i64.const 0)
           )
          )
         )
        )
       )
      )
      (local.set $4
       (i64.or
        (i64.or
         (select
          (i64.const 0)
          (i64.shl
           (i64.const 1)
           (local.get $6)
          )
          (local.get $7)
         )
         (local.get $4)
        )
        (select
         (i64.const 0)
         (i64.shl
          (i64.const 1)
          (local.get $1)
         )
         (local.get $10)
        )
       )
      )
      (br_if $label
       (i64.ne
        (local.tee $1
         (i64.sub
          (local.get $1)
          (i64.const 2)
         )
        )
        (i64.const -2)
       )
      )
     )
    )
    (br_if $block
     (i64.lt_u
      (local.get $4)
      (local.tee $5
       (i64.div_u
        (local.get $3)
        (local.get $2)
       )
      )
     )
    )
    (br_if $block
     (i32.and
      (local.tee $7
       (i64.gt_u
        (local.tee $1
         (i64.sub
          (local.get $3)
          (i64.mul
           (local.get $2)
           (local.get $5)
          )
         )
        )
        (local.get $0)
       )
      )
      (i64.eq
       (local.get $4)
       (local.get $5)
      )
     )
    )
    (local.set $3
     (i64.sub
      (i64.sub
       (local.get $4)
       (local.get $5)
      )
      (i64.extend_i32_u
       (local.get $7)
      )
     )
    )
    (br_if $block
     (i32.and
      (i64.eq
       (local.get $3)
       (i64.const -1)
      )
      (i64.ne
       (local.get $1)
       (local.tee $0
        (i64.add
         (select
          (local.get $2)
          (i64.const 0)
          (local.get $7)
         )
         (local.get $0)
        )
       )
      )
     )
    )
    (local.set $2
     (i64.add
      (local.get $3)
      (i64.extend_i32_u
       (i64.ne
        (local.get $0)
        (local.get $1)
       )
      )
     )
    )
    (br $block1)
   )
   (i32.store8
    (i32.const 64864)
    (i32.const 0)
   )
   (local.set $2
    (i64.const -1)
   )
   (br_if $block1
    (i32.load
     (i32.const 64744)
    )
   )
   (i64.store
    (i32.const 64744)
    (i64.const 51539607554)
   )
  )
  (global.set $global$0
   (i32.add
    (local.get $8)
    (i32.const 16)
   )
  )
  (local.get $2)
 )
