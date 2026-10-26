#include "bandgap.h"

static int bad(attiny13a_bandgap_t *s, uint8_t fault) {
    if (!s->fault) s->fault = fault;
    return 0;
}
int attiny13a_bandgap_init(attiny13a_bandgap_t *s, uint32_t startup_ns,
                          uint64_t now_ps) {
    *s = (attiny13a_bandgap_t){.now_ps=now_ps,
        .ready_at_ps=AT13_BANDGAP_NEVER, .startup_ps=(uint64_t)startup_ns*1000};
    if (now_ps == AT13_BANDGAP_NEVER) return bad(s, AT13_BANDGAP_BAD_TIME);
    return 1;
}
uint64_t attiny13a_bandgap_next_event(const attiny13a_bandgap_t *s) {
    return s->fault ? AT13_BANDGAP_NEVER : s->ready_at_ps;
}
int attiny13a_bandgap_advance(attiny13a_bandgap_t *s, uint64_t now_ps) {
    if (s->fault) return 0;
    if (now_ps == AT13_BANDGAP_NEVER || now_ps < s->now_ps)
        return bad(s, AT13_BANDGAP_BAD_TIME);
    if (s->ready_at_ps != AT13_BANDGAP_NEVER && s->ready_at_ps <= now_ps) {
        s->ready = 1;
        s->ready_at_ps = AT13_BANDGAP_NEVER;
    }
    s->now_ps = now_ps;
    return 1;
}
int attiny13a_bandgap_set(attiny13a_bandgap_t *s, uint32_t owners,
                         int powered, uint64_t now_ps) {
    if (s->fault) return 0;
    if ((owners & ~7u) || (powered != 0 && powered != 1))
        return bad(s, AT13_BANDGAP_BAD_INPUT);
    if (!attiny13a_bandgap_advance(s, now_ps)) return 0;
    uint8_t previous = s->enabled;
    s->owner_mask = (uint8_t)owners;
    s->powered = (uint8_t)powered;
    s->enabled = powered && owners;
    if (!s->enabled) {
        s->ready = 0;
        s->ready_at_ps = AT13_BANDGAP_NEVER;
    } else if (!previous) {
        s->ready = 0;
        if (s->startup_ps >= AT13_BANDGAP_NEVER - now_ps)
            return bad(s, AT13_BANDGAP_TIME_OVERFLOW);
        s->ready_at_ps = now_ps + s->startup_ps;
    }
    return attiny13a_bandgap_advance(s, now_ps);
}
