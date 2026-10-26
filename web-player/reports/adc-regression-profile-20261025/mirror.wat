 (func $native.device.mirror
  (local $0 i32)
  (local $1 i32)
  (if
   (local.tee $0
    (i32.load
     (i32.const 64016)
    )
   )
   (then
    (i32.store8 offset=35
     (local.get $0)
     (i32.load8_u
      (i32.const 74509)
     )
    )
    (i32.store8 offset=36
     (local.get $0)
     (select
      (i32.shl
       (local.tee $1
        (i32.load8_u
         (i32.const 74504)
        )
       )
       (i32.const 6)
      )
      (local.get $1)
      (i32.and
       (i32.load8_u
        (i32.const 74510)
       )
       (i32.const 32)
      )
     )
    )
    (i32.store8 offset=37
     (local.get $0)
     (i32.shr_u
      (i32.load16_u
       (i32.const 74504)
      )
      (select
       (i32.const 2)
       (i32.const 8)
       (i32.and
        (i32.load8_u
         (i32.const 74510)
        )
        (i32.const 32)
       )
      )
     )
    )
    (i32.store8 offset=38
     (local.get $0)
     (i32.load8_u
      (i32.const 74508)
     )
    )
    (i32.store8 offset=39
     (local.get $0)
     (i32.load8_u
      (i32.const 74510)
     )
    )
    (i32.store8 offset=40
     (local.get $0)
     (i32.load8_u
      (i32.const 74620)
     )
    )
    (i32.store8 offset=52
     (local.get $0)
     (i32.load8_u
      (i32.const 74379)
     )
    )
    (i32.store8 offset=53
     (local.get $0)
     (i32.load8_u
      (i32.const 74380)
     )
    )
    (i32.store8 offset=54
     (local.get $0)
     (i32.load8_u
      (i32.const 74378)
     )
    )
    (i32.store8 offset=55
     (local.get $0)
     (i32.load8_u
      (i32.const 74377)
     )
    )
    (i32.store8 offset=56
     (local.get $0)
     (i32.load8_u
      (i32.const 74376)
     )
    )
    (i32.store8 offset=85
     (local.get $0)
     (i32.load8_u
      (i32.const 74383)
     )
    )
    (i32.store8 offset=90
     (local.get $0)
     (i32.load8_u
      (i32.const 74382)
     )
    )
    (i32.store8 offset=91
     (local.get $0)
     (i32.load8_u
      (i32.const 74381)
     )
    )
    (i32.store8 offset=65
     (local.get $0)
     (i32.load8_u
      (i32.const 74676)
     )
    )
    (i32.store8 offset=84
     (local.get $0)
     (i32.load8_u
      (i32.const 74677)
     )
    )
    (i32.store8 offset=60
     (local.get $0)
     (i32.load8_u
      (i32.const 74908)
     )
    )
    (i32.store8 offset=61
     (local.get $0)
     (i32.load8_u
      (i32.const 74909)
     )
    )
    (i32.store8 offset=62
     (local.get $0)
     (i32.load8_u
      (i32.const 74910)
     )
    )
    (i32.store8 offset=87
     (local.get $0)
     (i32.load8_u
      (i32.const 74911)
     )
    )
    (i32.store8 offset=69
     (local.get $0)
     (i32.load8_u
      (i32.const 64777)
     )
    )
    (i32.store8 offset=72
     (local.get $0)
     (i32.load8_u
      (i32.const 74339)
     )
    )
    (i32.store8 offset=79
     (local.get $0)
     (i32.load8_u
      (i32.const 74330)
     )
    )
    (i32.store8 offset=83
     (local.get $0)
     (i32.load8_u
      (i32.const 74331)
     )
    )
    (i32.store8 offset=82
     (local.get $0)
     (i32.load8_u
      (i32.const 74332)
     )
    )
    (i32.store8 offset=86
     (local.get $0)
     (i32.load8_u
      (i32.const 74333)
     )
    )
    (i32.store8 offset=73
     (local.get $0)
     (i32.load8_u
      (i32.const 74334)
     )
    )
    (i32.store8 offset=88
     (local.get $0)
     (i32.load8_u
      (i32.const 74337)
     )
    )
    (i32.store8 offset=89
     (local.get $0)
     (i32.load8_u
      (i32.const 74338)
     )
    )
    (i32.store8 offset=70
     (local.get $0)
     (i32.load8_u
      (i32.const 64776)
     )
    )
    (i32.store8 offset=80
     (local.get $0)
     (i32.load8_u
      (i32.const 64784)
     )
    )
   )
  )
 )
