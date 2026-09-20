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
    parseSide: () => 'left', loadVideoForSign: async () => {}, renderMarkers(){}};
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
  assert.equal((html.match(/socket\.on\("processing_finished"/g)||[]).length,1);
  console.log('6 UI regression scenarios passed');
}
main().catch(err=>{console.error(err);process.exitCode=1;});
