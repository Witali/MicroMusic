// Minimal standalone WASM allocator. Native builds use their C library instead.
// One worker owns this heap; no host imports, file system, threads or JS hooks.
// Keep the free list in address order and coalesce neighbors after each free.
#if defined(__wasm__)
#include <stdint.h>
#include <stddef.h>
#include <string.h>
extern "C" unsigned char __heap_base;
namespace {
struct Block { size_t size;Block* next; };
static Block* freeList;
static uintptr_t heapEnd;
static bool grow(uintptr_t end) {
    size_t current=__builtin_wasm_memory_size(0),pages=(end+65535)/65536;
    return pages<=current || __builtin_wasm_memory_grow(0,pages-current)!=size_t(-1);
}
}
extern "C" {
// libc++'s fatal allocation diagnostics may reference stdio. This standalone
// module has no descriptors: fail writes locally rather than importing WASI.
uint16_t __wasi_fd_write(int32_t,const void*,size_t,size_t* written) { if(written)*written=0;return 8; }
void* malloc(size_t size) {
    if(!size)size=1;if(size>0x3fffffff)return nullptr;
    size=(size+7)&~size_t(7);Block** link=&freeList;
    for(Block* block=freeList;block;link=&block->next,block=block->next)if(block->size>=size) {
        if(block->size>=size+sizeof(Block)+8) {
            auto tail=reinterpret_cast<Block*>(reinterpret_cast<uintptr_t>(block+1)+size);
            tail->size=block->size-size-sizeof(Block);tail->next=block->next;*link=tail;block->size=size;
        } else *link=block->next;
        return block+1;
    }
    if(!heapEnd)heapEnd=(reinterpret_cast<uintptr_t>(&__heap_base)+7)&~uintptr_t(7);
    uintptr_t end=heapEnd+sizeof(Block)+size;if(end<heapEnd || !grow(end))return nullptr;
    auto block=reinterpret_cast<Block*>(heapEnd);block->size=size;heapEnd=end;return block+1;
}
void free(void* pointer) {
    if(!pointer)return;auto block=static_cast<Block*>(pointer)-1;Block** link=&freeList;Block* previous=nullptr;
    while(*link && reinterpret_cast<uintptr_t>(*link)<reinterpret_cast<uintptr_t>(block)) { previous=*link;link=&(*link)->next; }
    block->next=*link;*link=block;
    if(block->next && reinterpret_cast<unsigned char*>(block+1)+block->size==reinterpret_cast<unsigned char*>(block->next)) {
        block->size+=sizeof(Block)+block->next->size;block->next=block->next->next;
    }
    if(previous && reinterpret_cast<unsigned char*>(previous+1)+previous->size==reinterpret_cast<unsigned char*>(block)) {
        previous->size+=sizeof(Block)+block->size;previous->next=block->next;
    }
}
void* calloc(size_t count,size_t size) {
    if(count && size>size_t(-1)/count)return nullptr;void* p=malloc(count*size);if(p)memset(p,0,count*size);return p;
}
void* __libc_calloc(size_t count,size_t size) { return calloc(count,size); }
void* realloc(void* pointer,size_t size) {
    if(!pointer)return malloc(size);if(!size) { free(pointer);return nullptr; }
    auto block=static_cast<Block*>(pointer)-1;if(block->size>=size)return pointer;
    void* p=malloc(size);if(!p)return nullptr;memcpy(p,pointer,block->size);free(pointer);return p;
}
__attribute__((noreturn)) void abort() { __builtin_trap(); }
}
void* operator new(size_t size) { void* p=malloc(size);if(!p)abort();return p; }
void* operator new[](size_t size) { return ::operator new(size); }
void operator delete(void* p) noexcept { free(p); }
void operator delete[](void* p) noexcept { free(p); }
#endif
