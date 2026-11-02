import {playerApp as currentPlayerApp} from './player-app.mjs';

// Exercise older/offline catalogs when the additional phrase assets are absent.
// The complete current phrase/quality behavior has a separate integration suite.
export function playerApp(options={}){
  return currentPlayerApp({...options,fetchHook:context=>{
    if(context.url.pathname.endsWith('/speech-examples.json')||context.url.pathname.endsWith('/audio/lpx-speech/manifest.json')||context.url.pathname.endsWith('/firmware-attiny13a-speech-extra.json'))
      return {ok:false,status:404};
    return options.fetchHook?.(context)??context.response;
  }});
}
export {deferred} from './player-app.mjs';
