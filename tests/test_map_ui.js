// Run with node tests/test_map_ui.js; exercises actual map functions without a browser.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const html = fs.readFileSync(path.join(__dirname, '../templates/map.html'), 'utf8');
function section(start, end) {
  const a = html.indexOf(start), b = html.indexOf(end, a + start.length);
  assert(a >= 0 && b > a, start);
  return html.slice(a, b);
}
function environment() {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {style: {}, classList: {add(){}, remove(){}}, textContent: ''});
    return elements.get(id);
  };
  const c = {console: {log(){}, error(){}}, API: '/api', selectedId: null,
    selectionRequest: 0, signsData: [], signTypes: [],
    document: {getElementById: element}, toast(){}, toggleDescField(){},
    parseSide: () => 'left', loadVideoForSign: async () => {}, renderMarkers(){},
    cancelVideoLoad(){}, clearSelectedTrack(){}};
  vm.createContext(c);
  return {c, element};
}
async function main() {
  {
    const {c} = environment();
    let sequence = 0;
    const timers = new Map(), saved = [];
    Object.assign(c, {setTimeout: fn => {timers.set(++sequence, fn); return sequence;},
      clearTimeout: id => timers.delete(id), saveAzimuthToServer: (id, angle) => saved.push([id, angle])});
    vm.runInContext(section('const azimuthSaveTimers', 'let currentDragSignId'), c);
    c.scheduleAzimuthSave('a', 5); c.scheduleAzimuthSave('b', 10); c.scheduleAzimuthSave('a', 15);
    [...timers.values()].forEach(fn => fn());
    assert.deepEqual(saved, [['b', 10], ['a', 15]]);
  }
  {
    const {c, element} = environment();
    const pending = {}, videos = [];
    c.fetch = url => new Promise(resolve => pending[url] = resolve);
    c.loadVideoForSign = async props => videos.push(props.type);
    vm.runInContext(section('async function selectSign(id)', 'function parseSide'), c);
    vm.runInContext(section('function closeDetail()', '// ── Edit'), c);
    const a = c.selectSign('a'), b = c.selectSign('b');
    const response = type => ({ok:true, json:async()=>({properties:{type, azimuth:0}})});
    pending['/api/sign/b'](response('B')); await b;
    pending['/api/sign/a'](response('A')); await a;
    assert.equal(element('detail-type').textContent, 'B');
    assert.equal(element('df-azimuth').textContent, '0°');
    assert.deepEqual(videos, ['B']);
    const loading = c.selectSign('c'); c.closeDetail();
    pending['/api/sign/c'](response('C')); await loading;
    assert.equal(element('detail-content').style.display, 'none');
  }
  {
    const {c} = environment();
    let resolveFetch;
    c.selectedId = 'a'; c.signsData = [{id:'a'}, {id:'b', type:'B'}];
    c.document.getElementById('edit-type').value = 'new';
    c.document.getElementById('edit-desc').value = 'text';
    c.fetch = url => { assert.equal(url, '/api/sign/a'); return new Promise(r => resolveFetch = r); };
    vm.runInContext(section('async function saveSign()', 'async function deleteSign()'), c);
    const saving = c.saveSign(); c.selectedId = 'b';
    resolveFetch({ok:true,json:async()=>({})}); await saving;
    assert.equal(c.signsData[0].type, 'new'); assert.equal(c.signsData[1].type, 'B');
  }
  {
    const {c} = environment();
    let resolveConfirm, deleted;
    c.selectedId='a'; c.signsData=[{id:'a'}, {id:'b'}];
    c.showConfirmDialog = () => new Promise(r => resolveConfirm=r);
    c.fetch = async url => {deleted=url; return {ok:true,json:async()=>({})};};
    c.closeDetail=()=>{throw Error('Must not close another sign');};
    vm.runInContext(section('async function deleteSign()', '// Кастомный диалог подтверждения'),c);
    const deleting=c.deleteSign(); c.selectedId='b'; resolveConfirm(true); await deleting;
    assert.equal(deleted,'/api/sign/a'); assert.equal(c.signsData[0].id,'b');
  }
  {
    const {c} = environment();
    const buttons = [1,2,5].map(speed => ({dataset:{speed:String(speed)},
      classList:{toggle(name, active){this.active=active;}}, setAttribute(){}}));
    c.document.querySelectorAll=()=>buttons;
    vm.runInContext(section('function setPlaybackSpeed(speed)', '// Полноэкранный режим'),c);
    c.setPlaybackSpeed(2);
    assert.deepEqual(buttons.map(b=>b.classList.active),[false,true,false]);
    assert.equal(c.document.getElementById('map-video').playbackRate,2);
  }
  {
    // Holding a selected sign captures wheel outside its icon and always releases.
    function target() {
      const listeners = new Map();
      return {style: {}, classList: {add(){}, remove(){}},
        addEventListener(type, fn, options) {
          if (!listeners.has(type)) listeners.set(type, new Map());
          listeners.get(type).set(fn, options);
        },
        removeEventListener(type, fn) { listeners.get(type)?.delete(fn); },
        emit(type, event = {}) { for (const fn of [...(listeners.get(type)?.keys() || [])]) fn({type, button:0, ...event}); },
        count(type) { return listeners.get(type)?.size || 0; },
        listeners};
    }
    const {c} = environment();
    const doc = target(), win = target(), marker = target(), handle = target();
    handle.contains = value => value === handle;
    marker.querySelector = selector => selector === '.sign-marker-compass-handle' ? handle : null;
    doc.createElement = target; doc.body = {appendChild(){}};
    const layer = target(); layer.on = layer.addEventListener; layer.off = layer.removeEventListener;
    function toggle(initial) { let enabled = initial; return {
      enabled: () => enabled, enable(){enabled = true;}, disable(){enabled = false;}
    }; }
    layer.dragging = toggle(true);
    const zoom = toggle(true), saved = [], tasks = [];
    Object.assign(c, {document: doc, window: win, map: {scrollWheelZoom: zoom},
      setTimeout: fn => tasks.push(fn), rebuilt: 0,
      selectSign: id => {c.selectedId = id;},
      selectedId: 'a', signsData: [{id:'a', azimuth:0}],
      scheduleAzimuthSave: (id, angle) => saved.push(angle),
      updateAzimuthVisuals: (id, el, angle) => c.signsData[0].azimuth = angle});
    vm.runInContext(section('// Keep server echoes', '// ── Markers'), c);
    vm.runInContext(section('function renderMarkers() {', '  console.log(`[renderMarkers]') + '\n rebuilt++; }', c);
    vm.runInContext('let azimuthBadge = null; let currentDragSignId = null;\n' +
      section('function attachAzimuthControls(', '// Обновление визуальных элементов азимута'), c);
    c.attachAzimuthControls('a', marker, layer);
    c.attachAzimuthControls('a', marker, layer);
    assert.equal(marker.count('mousedown'), 1);
    assert.equal([...marker.listeners.get('mousedown').values()][0], true);
    function press() { marker.emit('mousedown', {button:0, target:marker}); }
    function wheel(deltaY, shiftKey = false) {
      let blocked = 0;
      doc.emit('wheel', {deltaY, shiftKey, buttons:0, clientX:100, clientY:100,
        preventDefault(){blocked++;}, stopPropagation(){}, stopImmediatePropagation(){}});
      return blocked;
    }
    assert.equal(wheel(1), 0);
    press(); assert.equal(zoom.enabled(), false);
    assert.equal(wheel(1), 1); assert.equal(c.signsData[0].azimuth, 5);
    // Disabling an active Leaflet drag here used to remove the clustered marker.
    assert.equal(layer.dragging.enabled(), true);
    let frozen = false;
    doc.emit('mousemove', {preventDefault(){}, stopImmediatePropagation(){frozen=true;}});
    assert.equal(frozen, true);
    // A save echo after a pause in scrolling must not remove the held marker.
    c.applySignsSnapshot([{id:'a', azimuth:0}, {id:'b', azimuth:90}]);
    c.renderMarkers(); assert.equal(c.rebuilt, 0);
    wheel(-1, true); assert.equal(c.signsData[0].azimuth, 4);
    wheel(0); assert.equal(saved.length, 2);
    doc.emit('mouseup', {button:2}); assert.equal(zoom.enabled(), false);
    doc.emit('mouseup', {button:0}); assert.equal(zoom.enabled(), true);
    tasks.splice(0).forEach(fn => fn());
    assert.equal(c.rebuilt, 1);
    assert.equal(c.signsData[0].azimuth, 4);
    assert.equal(c.signsData[1].azimuth, 90);
    assert.equal(layer.dragging.enabled(), true); assert.equal(wheel(1), 0);
    press(); win.emit('blur'); assert.equal(zoom.enabled(), true); assert.equal(doc.count('wheel'), 0);
    press(); layer.emit('remove'); assert.equal(zoom.enabled(), true); assert.equal(doc.count('wheel'), 0);
    zoom.disable(); layer.dragging.disable(); press(); wheel(1); doc.emit('mouseup');
    assert.equal(zoom.enabled(), false); assert.equal(layer.dragging.enabled(), false);
    c.selectedId = 'b'; press(); wheel(1); assert.equal(c.selectedId, 'a');
    doc.emit('mouseup', {button:0});
    assert.match(section('function renderMarkers()', 'const azimuthSaveTimers'), /\.on\("add"/);
  }
  {
    // Deferred redraws need the dropped coordinates before PATCH finishes.
    const {c} = environment();
    const requests = [];
    c.signsData = [{id:'a', lat:1, lon:2}];
    const positions = [];
    c.markers = {a:{setLatLng: value => positions.push(value)}};
    c.fetch = () => new Promise(resolve => requests.push(resolve));
    vm.runInContext(section('async function onMarkerDragEnd(', '// ── Sign selection'), c);
    const first = c.onMarkerDragEnd('a', {lat:3, lng:4});
    assert.equal(c.signsData[0].lat, 3);
    requests.shift()({ok:false, status:500}); await first;
    assert.equal(c.signsData[0].lat, 1);
    assert.equal(positions.length, 1);
    const second = c.onMarkerDragEnd('a', {lat:5, lng:6});
    const third = c.onMarkerDragEnd('a', {lat:7, lng:8});
    requests.shift()({ok:true,json:async()=>({})}); await second;
    assert.equal(c.signsData[0].lat, 7, 'Older acknowledgement must not undo a newer drag');
    requests.shift()({ok:true,json:async()=>({})}); await third;
  }
  {
    const {c} = environment();
    Object.assign(c, {AbortController, DOMException, setTimeout, clearTimeout});
    vm.runInContext(section('let currentVideoIdx =', '// Диагностика видео-кодеков'), c);
    assert.equal(c.signFrame({absolute_frame_numbers:'[0, 2]'}), 1);
    assert.equal(c.signFrame({abs_frame:[0]}), 0);
    assert.throws(() => c.signFrame({abs_frame:''}));
    const listeners = new Map();
    const video = {
      addEventListener: (name, fn) => listeners.set(name, fn),
      removeEventListener: name => listeners.delete(name), replaceChildren(){},
      load(){listeners.get('loadedmetadata')?.();}
    };
    // Metadata can arrive synchronously from cache: subscribe before load().
    await c.loadMediaSource(video, '/cached', new AbortController().signal);
    assert.equal(listeners.size, 0);
    video.load = () => {};
    const controller = new AbortController();
    const loading = c.loadMediaSource(video, '/slow', controller.signal);
    controller.abort();
    await assert.rejects(loading, {name:'AbortError'});
    assert.equal(listeners.size, 0);
  }
  {
    const {c, element} = environment();
    Object.assign(c, {AbortController, DOMException, setTimeout, clearTimeout});
    vm.runInContext(section('let currentVideoIdx =', '// Диагностика видео-кодеков'), c);
    element('map-video').pause = () => {};
    for (const id of ['btn-clip-mode', 'btn-full-mode']) element(id).classList.toggle = () => {};
    const sources = [];
    let finishOld;
    c.showSelectedTrack = () => {};
    c.fetch = url => {
      if (url.endsWith('frame=10')) return new Promise(resolve => finishOld = resolve);
      return Promise.resolve({ok:true, json:async()=>({video_idx:1,seconds:20,total_seconds:100,duration:50})});
    };
    c.loadMediaSource = async (video, src) => {
      sources.push(src);
      if (src === '/api/video/1') throw new Error('unsupported');
      video.duration = 50;
    };
    c.prepareVideoSource = async () => {};
    const old = c.loadVideoMode({abs_frame:[10]}, false);
    await c.loadVideoMode({abs_frame:[20]}, true);
    finishOld({ok:true,json:async()=>({video_idx:0,seconds:5,total_seconds:5,duration:10})});
    await old;
    assert.deepEqual(sources, ['/api/video/1', '/api/video_clip/1?start=0&duration=0']);
    assert.equal(element('map-video').currentTime, 20);
    assert.equal(element('map-video').style.display, 'block');
    assert.equal(vm.runInContext('isFullVideo', c), true);
  }
  assert.equal((html.match(/socket\.on\("processing_finished"/g)||[]).length,1);
  {
    const {c} = environment();
    const selected = [], flights = [];
    let finishFirst;
    let calls = 0;
    Object.assign(c, {window:{}, editorFocusRequest:0,
      signsData:[{id:'a',lat:53,lon:27},{id:'b',lat:54,lon:28}],
      loadSigns:()=> ++calls === 1 ? new Promise(resolve=>finishFirst=resolve) : Promise.resolve(),
      map:{getZoom:()=>17,stop(){},flyTo:(coords)=>flights.push(coords)},
      selectSign:id=>selected.push(id),setTimeout});
    vm.runInContext(section('window.focusSignFromEditor =', '// ── Обработка ошибок'),c);
    const first = c.window.focusSignFromEditor('a');
    await c.window.focusSignFromEditor('b');
    finishFirst(); await first;
    assert.deepEqual(selected,['b']);
    assert.equal(flights.length,1);
    await c.window.focusSignFromEditor('a');
    assert.deepEqual(selected,['b','a']);
  }
  console.log('11 UI regression scenarios passed');
}
main().catch(err=>{console.error(err);process.exitCode=1;});
