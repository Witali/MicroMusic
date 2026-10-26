import {ATtiny13AProfile} from './attiny13a-profile.js';
import {ATtiny88Profile} from './attiny88-profile.js';

export const DEFAULT_DEVICE='ATtiny13A';
const profiles=new Map([ATtiny13AProfile,ATtiny88Profile].map(p=>[p.name,p]));
export function deviceProfile(name=DEFAULT_DEVICE){
  const profile=profiles.get(name);
  if(!profile)throw Error('Unsupported AVR device profile: '+name);
  return profile;
}
