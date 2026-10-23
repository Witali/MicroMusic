#include "power_reset.h"

static int bad(power_reset_t *p, uint8_t fault) {
    if(!p->fault) p->fault=fault;
    return 0;
}
static uint64_t minimum(uint64_t a, uint64_t b) { return a<b?a:b; }
static uint64_t deadline(power_reset_t *p, uint64_t duration) {
    if(duration>=POWER_RESET_NEVER-p->now) {
        bad(p,POWER_RESET_TIME_OVERFLOW);
        return POWER_RESET_NEVER;
    }
    return p->now+duration;
}
static void emit(power_reset_t *p,uint8_t kind,uint8_t set,uint8_t clear) {
    if(p->count==POWER_RESET_EVENT_CAPACITY) { bad(p,POWER_RESET_EVENT_OVERFLOW);return; }
    power_reset_event_t *e=&p->events[(p->head+p->count)%POWER_RESET_EVENT_CAPACITY];
    e->at=p->now;e->deadline=power_reset_next_deadline(p);
    e->kind=kind;e->sources=p->sources;e->causes=p->causes;
    e->flags_set=set;e->flags_clear=clear;p->count++;
}
void power_reset_typical_profile(power_reset_profile_t *p,uint64_t filter,
                                uint64_t timeout,uint64_t recovery) {
    *p=(power_reset_profile_t){.por_assert_uv=1300000,.por_release_uv=1400000,
        .bod_center_uv={4300000,2700000,1800000},.bod_hysteresis_uv=50000,
        .bod_filter_ticks=filter,.timeout_ticks=timeout,.bod_recovery_ticks=recovery};
}
static int valid_profile(const power_reset_profile_t *p) {
    if(!p||p->por_assert_uv<=0||p->por_release_uv<p->por_assert_uv||
       p->bod_hysteresis_uv<0||p->bod_filter_ticks==POWER_RESET_NEVER||
       p->timeout_ticks==POWER_RESET_NEVER||p->bod_recovery_ticks==POWER_RESET_NEVER) return 0;
    for(unsigned i=0;i<3;i++) {
        int64_t center=p->bod_center_uv[i],h=p->bod_hysteresis_uv;
        if(center<=h/2||center+(h+1)/2>INT32_MAX) return 0;
    }
    return 1;
}
int power_reset_bod_enabled(const power_reset_t *p) {
    return p->bod_code!=3&&!p->bod_sleep_off;
}
uint64_t power_reset_next_deadline(const power_reset_t *p) {
    return minimum(p->bod_deadline,minimum(p->release_deadline,p->recovery_deadline));
}
int power_reset_execution_blocked(const power_reset_t *p) {
    return p->held||p->recovery_deadline!=POWER_RESET_NEVER||p->fault;
}

/* Exact equality and qualification behavior are explicit digital conventions;
 * see power_reset.md. POR dominates BOD below the POR activation domain. */
static void evaluate(power_reset_t *p) {
    if(p->vcc_uv<p->profile.por_assert_uv) p->por_active=1;
    else if(p->por_active&&p->vcc_uv>=p->profile.por_release_uv) p->por_active=0;
    if(!power_reset_bod_enabled(p)||p->por_active) {
        p->bod_active=0;p->bod_deadline=POWER_RESET_NEVER;
    } else {
        int64_t center=p->profile.bod_center_uv[p->bod_code];
        int64_t fall=center-p->profile.bod_hysteresis_uv/2;
        int64_t rise=center+(p->profile.bod_hysteresis_uv+1LL)/2;
        if(p->bod_active) {
            if(p->vcc_uv>rise) p->bod_active=0;
        } else if(p->vcc_uv<fall) {
            if(p->bod_deadline==POWER_RESET_NEVER) p->bod_deadline=deadline(p,p->profile.bod_filter_ticks);
        } else p->bod_deadline=POWER_RESET_NEVER;
    }
    uint8_t sources=(p->por_active?POWER_RESET_PORF:0)|
                    (p->bod_active?POWER_RESET_BORF:0)|p->other_sources;
    uint8_t added=sources&~p->sources;
    if(sources) {
        int changed=sources!=p->sources;
        p->sources=sources;p->release_deadline=POWER_RESET_NEVER;
        if(added) {
            /* A reset cancels sleep-only BOD disable and wake gating. BOD is
             * re-evaluated once more below after enabling its supply observer. */
            int was_off=p->bod_sleep_off;p->bod_sleep_off=0;
            p->recovery_deadline=POWER_RESET_NEVER;
            if(added&POWER_RESET_PORF) p->causes=0;
            p->causes|=added;
            uint8_t kind=p->held?POWER_RESET_HOLD:POWER_RESET_ASSERT;p->held=1;
            emit(p,kind,added,(added&POWER_RESET_PORF)?14:0);
            if(was_off&&!p->por_active) evaluate(p);
        } else if(changed) emit(p,POWER_RESET_HOLD,0,0);
    } else {
        int changed=p->sources!=0;p->sources=0;
        if(p->held&&p->release_deadline==POWER_RESET_NEVER) {
            p->release_deadline=deadline(p,p->profile.timeout_ticks);
            emit(p,POWER_RESET_HOLD,0,0);
        } else if(changed) emit(p,POWER_RESET_HOLD,0,0);
    }
}
int power_reset_advance(power_reset_t *p,uint64_t at) {
    if(p->fault) return 0;
    if(at<p->now||at==POWER_RESET_NEVER) return bad(p,POWER_RESET_BAD_TIME);
    for(uint64_t next;(next=power_reset_next_deadline(p))<=at;) {
        p->now=next;
        if(p->bod_deadline==next) {
            p->bod_deadline=POWER_RESET_NEVER;p->bod_active=1;evaluate(p);
        }
        if(p->recovery_deadline==next) {
            p->recovery_deadline=POWER_RESET_NEVER;emit(p,POWER_RESET_BOD_READY,0,0);
        }
        if(p->release_deadline==next) {
            p->release_deadline=POWER_RESET_NEVER;p->held=0;
            emit(p,POWER_RESET_RELEASE,0,0);p->causes=0;
        }
        if(p->fault) return 0;
    }
    p->now=at;return 1;
}
int power_reset_init(power_reset_t *p,const power_reset_profile_t *profile,
                     uint8_t fuse_high,uint64_t at,int32_t vcc_uv) {
    int valid=valid_profile(profile);
    power_reset_profile_t copied={0};
    if(valid) copied=*profile; /* Also supports re-init from p->profile. */
    *p=(power_reset_t){.bod_deadline=POWER_RESET_NEVER,
        .release_deadline=POWER_RESET_NEVER,.recovery_deadline=POWER_RESET_NEVER};
    if(!valid) return bad(p,POWER_RESET_BAD_PROFILE);
    if(at==POWER_RESET_NEVER||vcc_uv<0) return bad(p,POWER_RESET_BAD_INPUT);
    p->profile=copied;p->now=at;p->vcc_uv=vcc_uv;p->bod_code=(fuse_high>>1)&3;
    evaluate(p);return power_reset_advance(p,at);
}
int power_reset_set_inputs(power_reset_t *p,uint64_t at,int32_t uv,uint8_t mask) {
    if(uv<0||(mask&~(POWER_RESET_EXTRF|POWER_RESET_WDRF))) return bad(p,POWER_RESET_BAD_INPUT);
    if(!power_reset_advance(p,at)) return 0;
    p->vcc_uv=uv;p->other_sources=mask;
    evaluate(p);return power_reset_advance(p,at);
}
int power_reset_set_vcc(power_reset_t *p,uint64_t at,int32_t uv) {
    return power_reset_set_inputs(p,at,uv,p->other_sources);
}
int power_reset_set_other_sources(power_reset_t *p,uint64_t at,uint8_t mask) {
    return power_reset_set_inputs(p,at,p->vcc_uv,mask);
}
int power_reset_sleep(power_reset_t *p,uint64_t at,uint8_t mode,int authorized) {
    if(mode>2) return bad(p,POWER_RESET_BAD_INPUT);
    if(!power_reset_advance(p,at)) return 0;
    if(power_reset_execution_blocked(p)||p->bod_sleep_off) return 0;
    if(mode==2&&authorized&&p->bod_code!=3) {
        p->bod_sleep_off=1;evaluate(p);emit(p,POWER_RESET_BOD_OFF,0,0);
    }
    return !p->fault;
}
int power_reset_wake(power_reset_t *p,uint64_t at) {
    if(!power_reset_advance(p,at)) return 0;
    if(p->bod_sleep_off) {
        p->bod_sleep_off=0;p->recovery_deadline=deadline(p,p->profile.bod_recovery_ticks);
        evaluate(p);emit(p,POWER_RESET_BOD_RECOVER,0,0);
        return power_reset_advance(p,at);
    }
    return 1;
}
int power_reset_pop_event(power_reset_t *p,power_reset_event_t *event) {
    if(!p->count) return 0;
    *event=p->events[p->head];p->head=(p->head+1)%POWER_RESET_EVENT_CAPACITY;p->count--;return 1;
}
int power_reset_eeprom_voltage_uncertain(const power_reset_t *p) {
    return p->vcc_uv<1900000;
}
