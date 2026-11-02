// Shared hardware presentation for every AVR player collection.
export const tiny88Boards={
  'bare-8mhz':{cpuHz:8000000,catalog:'./firmware-attiny88.json'},
  'mh-et-live-16mhz':{cpuHz:16000000,catalog:'./firmware-attiny88-16mhz.json'},
};
export const boardId=value=>Object.hasOwn(tiny88Boards,value)?value:'bare-8mhz';

export function applyDeviceLayout(document,{device,board:currentBoard,speech:speechCollection}) {
  const $=id=>document.getElementById(id);
  const selectedEngine=()=>document.querySelector('input[name="engine"]:checked').value;
  const tiny88=device==='attiny88', name=tiny88?'ATtiny88':'ATtiny13A';
  const micronucleus=tiny88&&currentBoard==='mh-et-live-16mhz';
  const mhz=tiny88?tiny88Boards[currentBoard].cpuHz/1000000:9.6;
  document.body.dataset.device=device;
  document.body.dataset.board=tiny88?currentBoard:'';
  $('device-select').value=device;
  $('device-control').hidden=false;
  $('board-control').hidden=!tiny88;
  $('board-select').value=currentBoard;
  $('board-isp-option').disabled=speechCollection;
  $('board-isp-option').textContent='ATtiny88 · 8 МГц · ISP';
  $('board-note').textContent=micronucleus?'Внешний генератор · загрузка по USB · тембры во Flash':'Внутренний RC · загрузка Flash и EEPROM через ISP';
  $('tiny88-clock').textContent=mhz+' MHz · '+(micronucleus?'MH-ET LIVE':'PDIP-28');
  $('chip-attiny13a').hidden=tiny88; $('chip-attiny88').hidden=!tiny88;
  $('tiny88-power').hidden=!tiny88;
  $('tiny88-power').textContent=micronucleus?'MH-ET LIVE: питание по USB · моно / R — D10 · L — D9.':'PDIP-28: питание VCC 7 и AVCC 20 · земля GND 8 и 22.';
  document.querySelector('.tiny88-vcc').textContent=micronucleus?'USB 5 В':'VCC 7';
  document.querySelector('.tiny88-gnd').textContent=micronucleus?'GND':'GND 8';
  $('machine-memory').textContent=tiny88?'8':'1';
  $('machine-details').textContent=tiny88?`512 Б SRAM · 64 Б EEPROM · ${mhz} МГц`:'64 Б SRAM · 64 Б EEPROM · 9,6 МГц';
  $('fuses').setAttribute('aria-label',micronucleus?'Штатные настройки платы MH-ET LIVE':'Рекомендуемые фьюзы '+name);
  $('fuse-low').textContent=micronucleus?'—':tiny88?'0xEE':'0x7A';
  $('fuse-high').textContent=micronucleus?'—':tiny88?'0xDF':'0xFF';
  $('fuse-high-note').textContent=micronucleus?'сохранить фьюзы платы':tiny88?'SPI включён · RESET включён':'сохранить заводской';
  $('fuse-extended').hidden=!tiny88; $('fuse-extended-value').textContent=micronucleus?'—':'0xFF';
  $('fuse-clock-value').textContent=micronucleus?'Внешний генератор · 16 МГц':'Внутренний RC · '+(tiny88?'8':'9,6')+' МГц';
  $('fuse-clock-note').textContent=micronucleus?'Штатный Micronucleus · делитель /1 в прошивке':'CKDIV8 отключён · делитель /1';
  $('fuse-datasheet').href=tiny88?'https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf':'https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf';
  $('fuse-datasheet').textContent='Фьюзы в datasheet, §'+(tiny88?'20.2':'17.2')+' ↗';
  for(const choice of document.querySelectorAll('input[name="engine"]'))choice.disabled=false;
  if(document.querySelector('input[name="engine"]:checked').disabled){
    for(const choice of document.querySelectorAll('input[name="engine"]'))choice.checked=choice.value==='wasm';
  }
  $('package-file').disabled=false;
  $('package-import-label').textContent=micronucleus?'Открыть пакет UM88 для Micronucleus':tiny88?'Открыть пакет UM88':'Открыть пакет ATtiny13A';
  $('engine-note').textContent='При смене — сброс на начало.';
  if(!speechCollection) {
    document.title=`MicroMusic / ${name} — плеер прошивок`;
    document.querySelector('.intro .eyebrow').textContent=name+' / МУЗЫКА ИЗ МАШИННОГО КОДА';
    document.querySelector('.library h2').textContent=tiny88?'Музыка на ATtiny88':'Как звучит один килобайт?';
    document.querySelector('.source-only').hidden=tiny88;
    const history=document.querySelector('.header-link');
    history.href=tiny88?'https://github.com/Witali/MicroMusic/blob/main/ATtiny88/Music/HARDWARE_REVIEW_RU.md':'../ATtiny13A/Music/DEVELOPMENT_HISTORY_RU.txt';
    history.textContent=tiny88?'Подключение ATtiny88 ↗':'История разработки ↗';
  }
}
