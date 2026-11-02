// Shared hardware presentation for every AVR player collection.
export const tiny88Boards={
  'bare-8mhz':{cpuHz:8000000,catalog:'./firmware-attiny88.json'},
  'mh-et-live-16mhz':{cpuHz:16000000,catalog:'./firmware-attiny88-16mhz.json'},
};
export const boardId=value=>Object.hasOwn(tiny88Boards,value)?value:'bare-8mhz';

export const playerDevices={
  attiny13a:{name:'ATtiny13A',flashBytes:1024,sramBytes:64,eepromBytes:64,cpuHz:9600000},
  attiny88:{name:'ATtiny88',flashBytes:8192,sramBytes:512,eepromBytes:64,cpuHz:8000000},
  atmega328p:{name:'Arduino Nano / ATmega328P',flashBytes:32768,sramBytes:2048,eepromBytes:1024,cpuHz:16000000},
};

// All collections use the same header, hardware, transport, signal and library
// slots in index.html. A device changes their content, never their order.
export function applyCollectionLayout(document,{device,speech,preview=false,codec}) {
  const nano=device==='atmega328p',lpx=preview||nano;
  const name=playerDevices[device].name;
  if(!speech)return;
  document.title=`MicroMusic / ${name} — речевые кодеки`;
  document.querySelector('.intro .eyebrow').textContent=name+' / РЕЧЕВЫЕ КОДЕКИ';
  document.querySelector('.intro h1').textContent=nano?'Речь с LPX и Speex.':lpx?'Речь с кодеком LPX.':'Речь в одном килобайте.';
  document.querySelector('.subtitle').textContent=lpx?'Речевые профили LPX. Сравните с исходной записью.':'Три фразы — три выбранных варианта. Сравните прошивку с оригиналом.';
  document.querySelector('.library h2').textContent=lpx?'Выберите качество':'Выберите фразу';
  document.querySelector('.library-caption').textContent=nano?'Речевые прошивки для Arduino Nano · ATmega328P · 16 МГц.':lpx?'Речевые профили LPX для выбранной платы.':'Слушайте речь из прошивки и сравнивайте с исходной записью.';
  document.querySelector('.source-only').hidden=true;
  const history=document.querySelector('.header-link');
  history.href=codec==='speex'?'https://github.com/Witali/MicroMusic/blob/main/Codecs/Speex/AVR/README.md':lpx?'https://github.com/Witali/MicroMusic/blob/main/Codecs/LPX/README.md':'https://github.com/Witali/MicroMusic/blob/main/ATtiny13A/Sound/AUDIO_REFERENCES.md';
  history.textContent=codec==='speex'?'Кодек Speex ↗':lpx?'Кодек LPX ↗':'Звуковые эталоны ↗';
  document.querySelector('footer span:last-child').textContent='Речевые кодеки · AVR-прошивки и сравнение с оригиналом';
}

export function applyDeviceLayout(document,{device,board:currentBoard,speech:speechCollection,pwmOutput='D3 / PD3 / OC2B'}) {
  const $=id=>document.getElementById(id);
  const selectedEngine=()=>document.querySelector('input[name="engine"]:checked').value;
  const tiny88=device==='attiny88',nano=device==='atmega328p',name=playerDevices[device].name;
  const micronucleus=tiny88&&currentBoard==='mh-et-live-16mhz';
  const mhz=tiny88?tiny88Boards[currentBoard].cpuHz/1000000:9.6;
  document.body.dataset.device=device;
  document.body.dataset.board=tiny88?currentBoard:'';
  $('device-select').value=device;
  $('device-control').hidden=false;
  $('device-note').textContent=nano?'Речевые прошивки · Arduino Nano · 16 МГц':speechCollection?'Речевые прошивки и профили выбранного чипа':'Та же мелодия · прошивка для выбранного чипа';
  $('board-control').hidden=!tiny88;
  $('board-select').value=currentBoard;
  $('board-isp-option').disabled=speechCollection;
  $('board-isp-option').textContent='ATtiny88 · 8 МГц · ISP';
  $('board-note').textContent=micronucleus?'Внешний генератор · загрузка по USB · тембры во Flash':'Внутренний RC · загрузка Flash и EEPROM через ISP';
  $('tiny88-clock').textContent=mhz+' MHz · '+(micronucleus?'MH-ET LIVE':'PDIP-28');
  $('chip-attiny13a').hidden=tiny88||nano; $('chip-attiny88').hidden=!tiny88;
  $('chip-nano').hidden=!nano;
  $('tiny88-power').hidden=!tiny88&&!nano;
  $('tiny88-power').textContent=micronucleus?'MH-ET LIVE: питание по USB · моно / R — D10 · L — D9.':'PDIP-28: питание VCC 7 и AVCC 20 · земля GND 8 и 22.';
  document.querySelector('.tiny88-vcc').textContent=micronucleus?'USB 5 В':'VCC 7';
  document.querySelector('.tiny88-gnd').textContent=micronucleus?'GND':'GND 8';
  $('machine-memory').textContent=String(playerDevices[device].flashBytes/1024);
  $('machine-details').textContent=nano?'2 КБ SRAM · 1 КБ EEPROM · 16 МГц':tiny88?`512 Б SRAM · 64 Б EEPROM · ${mhz} МГц`:'64 Б SRAM · 64 Б EEPROM · 9,6 МГц';
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
  if(nano){
    document.body.dataset.board='arduino-nano-16mhz';
    $('tiny88-power').textContent='Arduino Nano · 16 МГц · PWM: '+pwmOutput+' · выход через RC-фильтр на вход усилителя · общая земля GND.';
    $('chip-nano').setAttribute('aria-label','Arduino Nano, ATmega328P, 16 МГц, выход PWM '+pwmOutput);
    document.querySelector('.nano-output').textContent=(pwmOutput.startsWith('D9')?'D9 / OC1A':'D3 / OC2B')+' → RC → AUDIO';
    $('package-file').disabled=true;
  }
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
