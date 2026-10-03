'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const fsp = fs.promises;
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const Module = require('node:module');
const util = require('node:util');

const pluginPath = path.resolve(process.argv[2]);
const ORIGINAL = 'Synthetic original\n\n  preserve whitespace  \n';
const EDITED = '  Exact proposed correction\n\ntrailing space \n';
const NOTE = 'cairntir-sync/drawers/synthetic-note.md';
const WING = 'synthetic-wing';
const IDENTITY = 'd1d6919b-1e20-441f-a5b7-8c9c97b7a2dc';
const sourceHash = crypto.createHash('sha256').update(ORIGINAL).digest('hex');
const goodEntry = { drawer_id: 37, source_identity: IDENTITY, content_sha256: sourceHash, content: ORIGINAL, wing: WING, room: 'synthetic', layer: 'on_demand', current: true, editable: true, supersedes_id: null, note: NOTE };
let assertions = 0;
let cases = 0;
function check(condition, label) { assertions++; assert.ok(condition, label); }
function equal(actual, expected, label) { assertions++; assert.deepEqual(actual, expected, label); }
async function tick() { await new Promise(resolve => setImmediate(resolve)); }

async function fixture(overrides = {}) {
  const dir = await fsp.mkdtemp(path.join(os.tmpdir(), 'cairntir-plugin-public-'));
  await fsp.mkdir(path.join(dir, 'cairntir-sync', 'drawers'), { recursive: true });
  await fsp.mkdir(path.join(dir, 'cairntir-sync', 'outbox'), { recursive: true });
  await fsp.writeFile(path.join(dir, NOTE), ORIGINAL);
  const manifest = { schema: 'cairntir.obsidian-workspace.v1', wing: WING, drawers: [{ ...goodEntry, ...(overrides.entry || {}) }], ...(overrides.manifest || {}) };
  const manifestBytes = JSON.stringify(manifest);
  await fsp.writeFile(path.join(dir, 'cairntir-sync', 'workspace.json'), manifestBytes);
  const state = { dir, manifestBytes, notices: [], calls: [], commands: new Map(), controls: [], modals: [], events: [], response: overrides.response || 'success', settings: overrides.settings || { pythonExecutable: 'synthetic python.exe', cairntirHome: path.join(dir, 'synthetic-home'), wing: WING }, active: overrides.active === undefined ? NOTE : overrides.active };
  class Element {
    constructor() { this.children = []; this.value = ''; }
    empty() { this.children = []; }
    createEl(tag, options = {}) { const item = new Element(); item.tag = tag; item.text = options.text || ''; this.children.push(item); return item; }
    createDiv(options = {}) { return this.createEl('div', options); }
    setText(value) { this.text = value; return this; }
    addClass() { return this; }
    appendChild(item) { this.children.push(item); return item; }
    addEventListener(name, callback) { this[name] = callback; }
  }
  class Field {
    constructor(kind) { this.kind = kind; this.value = ''; this.disabled = false; this.inputEl = new Element(); state.controls.push(this); }
    setValue(value) { this.value = value; this.inputEl.value = value; return this; }
    setPlaceholder() { return this; }
    setDisabled(value) { this.disabled = value; return this; }
    setButtonText(value) { this.label = value; return this; }
    setCta() { return this; }
    setWarning() { return this; }
    onChange(callback) { this.change = callback; return this; }
    onClick(callback) { this.click = callback; return this; }
  }
  class Setting {
    constructor() {}
    setName() { return this; }
    setDesc() { return this; }
    addText(callback) { callback(new Field('text')); return this; }
    addTextArea(callback) { callback(new Field('textarea')); return this; }
    addButton(callback) { callback(new Field('button')); return this; }
  }
  class Modal {
    constructor(app) { this.app = app; this.contentEl = new Element(); this.modalEl = new Element(); this.titleEl = new Element(); }
    setTitle(value) { this.titleEl.setText(value); return this; }
    open() { state.modals.push(this); this.onOpen?.(); }
    close() { this.closed = true; this.onClose?.(); }
  }
  class Plugin {
    constructor(app) { this.app = app; }
    async loadData() { return { ...state.settings }; }
    async saveData(value) { state.savedSettings = value; }
    addCommand(command) { state.commands.set(command.id, command); }
    addSettingTab(tab) { state.settingTab = tab; }
    registerEvent(event) { state.events.push(event); }
    registerInterval() { throw new Error('Automatic background interval is not authorized'); }
  }
  class PluginSettingTab { constructor(app, plugin) { this.app = app; this.plugin = plugin; this.containerEl = new Element(); } }
  class FileSystemAdapter {
    getBasePath() { return dir; }
    async read(relative) { return fsp.readFile(path.join(dir, relative), 'utf8'); }
    async write(relative, text) { return fsp.writeFile(path.join(dir, relative), text); }
    async exists(relative) { try { await fsp.access(path.join(dir, relative)); return true; } catch { return false; } }
    async mkdir(relative) { return fsp.mkdir(path.join(dir, relative), { recursive: true }); }
  }
  const obsidian = { Plugin, Modal, Setting, PluginSettingTab, FileSystemAdapter, Platform: { isDesktop: true, isMobile: false }, normalizePath: value => value.replace(/\\/g, '/').replace(/\/+/g, '/'), Notice: class { constructor(message) { state.notices.push(String(message)); } } };
  async function output() {
    const files = await fsp.readdir(path.join(dir, 'cairntir-sync', 'outbox'));
    if (state.response === 'process-error') throw new Error('SYNTHETIC_PROCESS_FAILURE');
    if (state.response === 'malformed') return 'not valid JSON';
    const results = [];
    for (const file of files) {
      const request = JSON.parse(await fsp.readFile(path.join(dir, 'cairntir-sync', 'outbox', file), 'utf8'));
      const item = { file: 'cairntir-sync/outbox/' + file, status: 'committed', receipt: { request_id: request.request_id, status: 'committed', source_drawer_id: request.source_drawer_id, drawer_id: 38 } };
      if (state.response === 'missing-receipt') delete item.receipt;
      if (state.response === 'wrong-receipt') item.receipt.request_id = '98ee5644-ab70-4976-abf8-6bc1c8899849';
      if (state.response === 'wrong-file') item.file = 'cairntir-sync/outbox/unrelated.json';
      if (state.response === 'rejected') { item.status = 'rejected'; item.error = 'synthetic rejection'; delete item.receipt; }
      if (state.response === 'receipt-error') item.receipt_written = false;
      results.push(item);
    }
    return JSON.stringify({ schema: 'cairntir.obsidian-sync.v1', wing: state.response === 'wrong-wing' ? 'other-wing' : WING, results, projection: state.response === 'projection-error' ? { status: 'error', error: 'synthetic projection error' } : { status: 'complete', current_count: 1 } });
  }
  function execFile(executable, args, options, callback) {
    state.calls.push({ executable, args, options });
    output().then(stdout => callback(null, stdout, ''), error => callback(error, '', ''));
    return { kill() {} };
  }
  execFile[util.promisify.custom] = (executable, args, options) => new Promise((resolve, reject) => execFile(executable, args, options, (error, stdout, stderr) => error ? reject(error) : resolve({ stdout, stderr })));
  const originalLoad = Module._load;
  Module._load = function(request, parent, isMain) {
    if (request === 'obsidian') return obsidian;
    if (request === 'child_process' || request === 'node:child_process') return { execFile, exec() { throw new Error('Shell exec is forbidden'); }, execSync() { throw new Error('Shell execSync is forbidden'); }, spawn() { throw new Error('Use the specified execFile interface'); } };
    return originalLoad.call(this, request, parent, isMain);
  };
  let Export;
  try { delete require.cache[pluginPath]; Export = require(pluginPath); } finally { Module._load = originalLoad; }
  check(typeof Export === 'function', 'CommonJS Plugin class export');
  const app = { vault: { adapter: new FileSystemAdapter(), on(name, callback) { return { name, callback }; }, getAbstractFileByPath(relative) { return { path: relative }; }, async read(file) { return fsp.readFile(path.join(dir, file.path), 'utf8'); } }, workspace: { getActiveFile() { return state.active ? { path: state.active, extension: 'md' } : null; }, on(name, callback) { return { name, callback }; } } };
  state.plugin = new Export(app);
  await state.plugin.onload();
  await tick();
  state.command = async id => { const command = state.commands.get(id); check(Boolean(command), 'registered command ' + id); if (command.callback) await command.callback(); else { check(command.checkCallback(false) !== false, 'command callable'); } await tick(); };
  state.open = async () => { await state.command('propose-correction'); return state.controls.find(control => control.kind === 'textarea'); };
  state.submit = async value => {
    const textarea = state.controls.find(control => control.kind === 'textarea');
    check(Boolean(textarea), 'correction textarea present');
    equal(textarea.value, ORIGINAL, 'textarea preserves exact original');
    textarea.value = value; textarea.inputEl.value = value; await textarea.change?.(value);
    const button = state.controls.find(control => control.kind === 'button' && control.label === 'Submit correction');
    check(Boolean(button?.click), 'explicit submit control present');
    await button.click(); await tick();
  };
  state.files = () => fsp.readdir(path.join(dir, 'cairntir-sync', 'outbox'));
  state.clean = async () => { await state.plugin.onunload?.(); check(path.resolve(dir).startsWith(path.resolve(os.tmpdir()) + path.sep), 'temporary root scope'); await fsp.rm(dir, { recursive: true, force: true }); };
  return state;
}

function validateCall(state, call) {
  equal(call.executable, state.settings.pythonExecutable, 'configured Python executable');
  equal(call.args, ['-m','cairntir','obsidian-sync',state.dir,'--wing',WING], 'exact non-shell argv');
  equal(call.options.windowsHide, true, 'Windows process hidden');
  equal(call.options.timeout, 120000, 'bounded timeout');
  check(Number.isSafeInteger(call.options.maxBuffer) && call.options.maxBuffer > 0, 'explicit bounded output buffer');
  check(call.options.shell === undefined || call.options.shell === false, 'no shell');
  equal(call.options.env.CAIRNTIR_HOME, state.settings.cairntirHome, 'configured store');
  equal(call.options.env.PYTHONUTF8, '1', 'UTF-8');
}
function claimsSaved(state) { return state.notices.some(message => /\b(saved|committed)\b/i.test(message) && !/\b(not saved|not committed|uncommitted|unsaved)\b/i.test(message)); }
async function run(name, operation) { await operation(); cases++; process.stdout.write(JSON.stringify({ case: name, result: 'PASS' }) + '\n'); }

(async () => {
  await run('load and explicit refresh', async () => {
    const state = await fixture(); try {
      equal(state.calls.length, 0, 'load does not sync'); equal(await state.files(), [], 'load does not submit');
      check(state.commands.has('refresh-workspace') && state.commands.has('propose-correction'), 'both public commands');
      for (const event of state.events) await event.callback?.({ path: NOTE });
      equal(state.calls.length, 0, 'events do not sync');
      await state.command('refresh-workspace'); equal(state.calls.length, 1, 'explicit refresh invokes once'); validateCall(state, state.calls[0]);
    } finally { await state.clean(); }
  });
  for (const key of ['pythonExecutable','cairntirHome','wing']) await run('missing setting ' + key, async () => {
    const settings = { pythonExecutable: 'synthetic-python', cairntirHome: 'synthetic-home', wing: WING, [key]: '' };
    const state = await fixture({ settings }); try { await state.command('refresh-workspace'); equal(state.calls.length, 0, 'incomplete settings block process'); check(state.notices.length > 0, 'settings feedback'); } finally { await state.clean(); }
  });
  for (const scenario of [{ active:'untracked.md' },{ active:null },{ entry:{current:false} },{ entry:{editable:false} },{ entry:{wing:'other-wing'} },{ manifest:{wing:'other-wing'} },{ manifest:{schema:'other-schema'} },{ manifest:{drawers:[goodEntry,{...goodEntry}]} }]) await run('ineligible note ' + JSON.stringify(scenario), async () => {
    const state = await fixture(scenario); try { await state.open(); equal(state.calls.length, 0, 'ineligible note no process'); equal(await state.files(), [], 'ineligible note no proposal'); check(!state.controls.some(control => control.kind === 'textarea'), 'ineligible note no correction dialog'); } finally { await state.clean(); }
  });
  await run('cancel', async () => { const state = await fixture(); try { await state.open(); equal(state.calls.length,0,'opening no process'); state.modals.at(-1)?.close(); equal(await state.files(),[],'cancel no proposal'); } finally { await state.clean(); } });
  await run('exact correction and committed receipt', async () => {
    const state = await fixture(); try {
      await state.open(); await state.submit(EDITED);
      const files = await state.files(); equal(files.length,1,'one proposal');
      const request = JSON.parse(await fsp.readFile(path.join(state.dir,'cairntir-sync','outbox',files[0]),'utf8'));
      equal(Object.keys(request).sort(),['schema','request_id','wing','source_drawer_id','source_identity','source_sha256','content'].sort(),'request exact keys');
      check(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.json$/i.test(files[0]),'UUID v4 filename');
      equal(files[0],request.request_id+'.json','request filename binding'); equal(request.schema,'cairntir.obsidian-correction.v1','request schema'); equal(request.wing,WING,'request wing'); equal(request.source_drawer_id,37,'source drawer'); equal(request.source_identity,IDENTITY,'source identity'); equal(request.source_sha256,sourceHash,'source digest'); equal(request.content,EDITED,'verbatim edited content');
      equal(state.calls.length,1,'one submit sync'); validateCall(state,state.calls[0]); check(claimsSaved(state),'matching commit acknowledged');
      equal(await fsp.readFile(path.join(state.dir,NOTE),'utf8'),ORIGINAL,'plugin preserves original note'); equal(await fsp.readFile(path.join(state.dir,'cairntir-sync','workspace.json'),'utf8'),state.manifestBytes,'plugin preserves manifest');
    } finally { await state.clean(); }
  });
  for (const response of ['process-error','malformed','wrong-wing','missing-receipt','wrong-receipt','wrong-file','rejected']) await run('no false save: ' + response, async () => {
    const state = await fixture({ response }); try {
      await state.open(); await state.submit(EDITED); check(!claimsSaved(state),'unconfirmed correction never claimed saved'); equal((await state.files()).length,1,'failed request retained'); check(state.notices.length>0,'actionable error feedback');
      const retained = await state.files(); const bytes = await fsp.readFile(path.join(state.dir,'cairntir-sync','outbox',retained[0]),'utf8'); state.response='success'; await state.command('refresh-workspace'); equal(await state.files(),retained,'retry no duplicate proposal'); equal(await fsp.readFile(path.join(state.dir,'cairntir-sync','outbox',retained[0]),'utf8'),bytes,'retry preserves exact pending request');
    } finally { await state.clean(); }
  });
  for (const response of ['projection-error','receipt-error']) await run('partial commit: ' + response, async () => {
    const state = await fixture({ response }); try { await state.open(); await state.submit(EDITED); check(claimsSaved(state),'committed database saved acknowledged'); equal((await state.files()).length,1,'partial failure request retained'); check(state.notices.some(message=>/retry|failed|error|could not|needs/i.test(message)),'partial failure disclosed'); } finally { await state.clean(); }
  });
  process.stdout.write(JSON.stringify({ schema:'cairntir.public-obsidian-plugin-result.v1',result:'PASS',cases,assertions,scope:'mock plugin boundary only' })+'\n');
})().catch(error => { process.stderr.write(error.stack+'\n'); process.exitCode=1; });
