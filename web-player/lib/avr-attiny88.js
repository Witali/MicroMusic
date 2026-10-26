// Compatibility entry point; the CPU and peripheral implementation are shared.
import {AVRCore, AVR_PROFILES} from './avr-reference.js?v=20261025-board-um88-pipeline';
export const TARGET_PROFILES = Object.freeze({tiny88:AVR_PROFILES.attiny88});
export class AVRMusicTargetCore extends AVRCore {
  constructor(binary,eeprom,options={}) {
    super(binary,eeprom,{...options,target:options.target??'attiny88'});
    if(this.profile.id!=='attiny88')throw new Error('Unsupported music target: '+options.target);
    this.target='tiny88';
  }
}
export {AVRMusicTargetCore as AVRCore};
