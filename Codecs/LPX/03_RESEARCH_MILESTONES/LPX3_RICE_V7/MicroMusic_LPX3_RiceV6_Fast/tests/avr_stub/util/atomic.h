#pragma once
#define ATOMIC_RESTORESTATE 0
#define ATOMIC_BLOCK(how) for(int __once=1; __once; __once=0)
