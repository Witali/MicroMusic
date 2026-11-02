// One catalog component for music firmware, speech firmware and native previews.
export const bitrateLabel=bps=>`${bps%1000?'≈ ':''}${Math.round(bps/1000).toLocaleString('ru')} кбит/с`;
export function renderFirmwareCatalog(document,{entries,selectedId,query,onSelect}) {
  const $=id=>document.getElementById(id);
  const visible=entries.filter(entry=>`${entry.title} ${entry.description} ${entry.id} ${entry.flashBytes??entry.streamBytes}`.toLocaleLowerCase('ru').includes(query));
  $('catalog').replaceChildren();
  $('catalog-count').textContent=query?`${visible.length} / ${entries.length}`:entries.length;
  for(const entry of visible){
    const item=document.createElement('div');item.setAttribute('role','listitem');
    const button=document.createElement('button');button.className='firmware-card';button.dataset.firmware=entry.id;
    button.setAttribute('aria-pressed',String(selectedId===entry.id));
    if(entry.available===false){button.disabled=true;button.title=entry.unavailableReason;button.setAttribute('aria-disabled','true');}
    const number=document.createElement('span');number.className='card-number';number.textContent=entry.order;
    const body=document.createElement('span');body.className='card-body';
    const name=document.createElement('strong');name.textContent=entry.title;
    const meta=document.createElement('span');meta.className='card-meta';meta.textContent=firmwareSummary(entry);
    const arrow=document.createElement('span');arrow.className='card-arrow';arrow.textContent=selectedId===entry.id?'●':'↗';arrow.setAttribute('aria-hidden','true');
    body.append(name,meta);button.append(number,body,arrow);if(entry.available!==false)button.onclick=()=>onSelect(entry.selection||entry);item.append(button);$('catalog').append(item);
  }
  if(!visible.length){
    const message=document.createElement('p');message.className='empty';message.textContent='Ничего не найдено. Попробуйте другое название.';$('catalog').append(message);
  }
}

function firmwareSummary(entry){
  if(entry.available===false)return entry.unavailableReason;
  const voices=entry.voices??4;
  if(entry.playback==='native-pwm8'){
    const program=entry.firmware?.programFlashBytes??entry.flashMeasurement?.programFlashBytes;
    return `${entry.profileCaption?entry.profileCaption+' · ':''}${program?.toLocaleString('ru')??'—'} Б код · ${entry.streamBytes.toLocaleString('ru')} Б данных · ${bitrateLabel(entry.bitrateBps)}`;
  }
  if(entry.kind==='package')return 'FLASH + EEPROM · PB0 / PB1';
  if(entry.kind==='speech')return `${entry.flashBytes} Б Flash${entry.eepromBytes?` + ${entry.eepromBytes} Б EEPROM`:''} · речь ${(entry.sampleHz/1000).toLocaleString('ru')} кГц`;
  return `${entry.flashBytes} Б Flash${entry.eepromBytes?' + 64 Б EEPROM':''} · ${entry.status==='experimental'?'ТЕСТ':`${voices} ${voices===1?'ОСНОВНОЙ':'ОСНОВНЫХ'}`}${entry.releaseTailSlots?` · ${entry.releaseTailSlots} РЕЗЕРВНЫХ`:''}${entry.audioChannels===2?' · СТЕРЕО L / R':''}`;
}
