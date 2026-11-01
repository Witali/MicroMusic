import {test} from 'node:test';
import {pwmBoundaryCases,runPwmBoundaryCase} from './fixtures/attiny13a-pwm-boundaries.mjs';
for(const spec of pwmBoundaryCases)test('firmware PWM '+spec.id,()=>{runPwmBoundaryCase(spec);});
