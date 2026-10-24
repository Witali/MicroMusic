(func $native.advance_to (param $0 i64)
  (local $1 i64)
  (local $2 i32)
  (local $3 i32)
  (local $4 i64)
  (local $5 i64)
  (local $scratch i64)
  (block $block
   (if
    (i64.lt_u
     (local.tee $0
      (select
       (select
        (local.get $0)
        (local.tee $1
         (i64.load
          (i32.const 73712)
         )
        )
        (i64.lt_u
         (local.get $0)
         (local.get $1)
        )
       )
       (local.get $0)
       (i32.load8_u
        (i32.const 65405)
       )
      )
     )
     (local.tee $1
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
     (br_if $block
      (i32.load
       (i32.const 64296)
      )
     )
     (i64.store
      (i32.const 64296)
      (i64.const 21474836482)
     )
     (return)
    )
   )
   (br_if $block
    (i32.load8_u
     (i32.const 64331)
    )
   )
   (if
    (i32.eqz
     (i32.load
      (i32.const 64296)
     )
    )
    (then
     (loop $label
      (if
       (i64.lt_u
        (local.tee $1
         (select
          (local.tee $1
           (call $native.next_event)
          )
          (local.get $0)
          (i64.gt_u
           (local.get $0)
           (local.get $1)
          )
         )
        )
        (local.tee $4
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
        (br_if $block
         (i32.load
          (i32.const 64296)
         )
        )
        (i64.store
         (i32.const 64296)
         (i64.const 25769803778)
        )
        (return)
       )
      )
      (call $native.service
       (block (result i64)
        (local.set $scratch
         (i64.load
          (i32.const 64184)
         )
        )
        (call $native.elapse
         (local.get $1)
        )
        (local.get $scratch)
       )
      )
      (br_if $block
       (i32.load8_u
        (i32.const 64331)
       )
      )
      (local.set $3
       (i32.const 0)
      )
      (block $block1
       (br_if $block1
        (i64.ne
         (local.tee $1
          (i64.load
           (i32.const 64176)
          )
         )
         (local.get $4)
        )
       )
       (br_if $block1
        (i32.lt_u
         (local.tee $3
          (i32.add
           (local.get $2)
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
       (br_if $block
        (i32.load
         (i32.const 64296)
        )
       )
       (i64.store
        (i32.const 64296)
        (i64.const 30064771074)
       )
       (return)
      )
      (block $block2
       (if
        (i64.eq
         (local.get $0)
         (local.get $1)
        )
        (then
         (br_if $block
          (i64.gt_u
           (call $native.next_event)
           (local.get $0)
          )
         )
         (br_if $block2
          (i64.le_u
           (local.tee $1
            (i64.load
             (i32.const 64176)
            )
           )
           (local.get $0)
          )
         )
         (br $block)
        )
       )
       (br_if $block
        (i64.lt_u
         (local.get $0)
         (local.get $1)
        )
       )
      )
      (local.set $2
       (local.get $3)
      )
      (br_if $label
       (i32.eqz
        (i32.load
         (i32.const 64296)
        )
       )
      )
     )
    )
   )
   (br_if $block
    (i64.le_u
     (local.get $0)
     (local.get $1)
    )
   )
   (call $native.elapse
    (local.get $0)
   )
  )
 )
