// Phrase identity/order is independent of microcontroller and codec quality.
export function readSpeechExamples(data){
  if(data.schemaVersion!==1||!Array.isArray(data.examples)||!Array.isArray(data.unavailable)
    ||data.examples.length!==4||new Set(data.examples.map(item=>item?.id)).size!==4
    ||data.examples.some(item=>!['chego','otvechaesh','vinni','bread'].includes(item.id)||typeof item.title!=='string')
    ||data.unavailable.some(item=>!Number.isInteger(item.flashBytes)||!Number.isInteger(item.flashLimitBytes)||item.flashBytes<=item.flashLimitBytes))
    throw Error('Неверный общий набор речевых примеров.');
  return data;
}

export function orderSpeechEntries(entries,definition){
  if(!definition)return entries;
  const rank=new Map(definition.examples.map((item,index)=>[item.id,index]));
  return [...entries].sort((a,b)=>(rank.get(a.audioReferenceId)??99)-(rank.get(b.audioReferenceId)??99));
}

export function selectSpeechEntry(entries,previous){
  const phrase=entries.filter(entry=>entry.audioReferenceId===previous?.audioReferenceId);
  return phrase.find(entry=>entry.profile===previous?.profile)||phrase[0]||entries[0];
}

export function speechCatalogRows(entries,selected,definition,device){
  if(!definition)return entries;
  return definition.examples.map(example=>{
    const variants=entries.filter(entry=>entry.audioReferenceId===example.id);
    const chosen=variants.find(entry=>entry.id===selected?.id)||variants[0];
    if(chosen)return {...chosen,selection:chosen,title:example.title,order:example.order,
      profileCaption:chosen.profileLabel};
    const measurement=definition.unavailable.find(item=>item.phraseId===example.id&&item.device===device);
    return {id:'unavailable-'+device+'-'+example.id,title:example.title,description:example.title,
      audioReferenceId:example.id,order:example.order,kind:'unavailable',available:false,
      unavailableReason:measurement?`${measurement.flashBytes.toLocaleString('ru')} Б Flash / лимит ${measurement.flashLimitBytes.toLocaleString('ru')} Б · образ не помещается`:'Пример для этой платы не загружен',
      flashBytes:measurement?.flashBytes};
  });
}

export function speechProfileUI(document,entries,selected){
  const variants=entries.filter(entry=>entry.audioReferenceId&&entry.audioReferenceId===selected.audioReferenceId);
  const select=document.getElementById('speech-profile-select');select.replaceChildren();
  for(const entry of variants){
    const option=document.createElement('option');option.value=entry.id;option.textContent=entry.profileLabel||entry.title;select.append(option);
  }
  select.value=selected.id;
  document.getElementById('speech-profile-control').hidden=variants.length<2;
}
