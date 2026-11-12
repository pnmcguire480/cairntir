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
const WING = 'questions';
const NOTE = 'cairntir-sync/memory/drawer-37.md';
const QID = 'd1d6919b-1e20-441f-a5b7-8c9c97b7a2dc';
const ORIGINAL = '  Original question, exact café text.\r\n';
const PROPOSED = '  New question, exact café text.\n\t';
const RESOLUTION = '  Declared answer based on recorded measurements.\n';
const hash = text => crypto.createHash('sha256').update(text, 'utf8').digest('hex');
const question = {question_id: QID, drawer_id: 37, content: ORIGINAL, content_sha256: hash(ORIGINAL), owner: null, evidence: [], status: 'open', legacy: false, resolution: null, note: NOTE};
const supports = [7,8].map((id, index) => ({drawer_id: id, source_identity: ['76b07d56-0f5d-48ec-85ac-b2f1e833074e','f7735f19-6adb-44f2-bb80-c48408463a03'][index], content: 'Measurement ' + id, content_sha256: hash('Measurement ' + id), wing: WING, room: 'work', layer: 'on_demand', current: true, editable: true, supersedes_id: null, note: `cairntir-sync/memory/drawer-${id}.md`}));
const ref = entry => ({drawer_id: entry.drawer_id, source_identity: entry.source_identity, content_sha256: entry.content_sha256});
let cases = 0, assertions = 0;
function check(value, label) { assertions++; assert.ok(value, label); }
function equal(value, expected, label) { assertions++; assert.deepEqual(value, expected, label); }
const tick = () => new Promise(resolve => setImmediate(resolve));
const saved = state => state.notices.some(text => /\b(saved|committed)\b/i.test(text) && !/\b(not saved|not committed|unsaved|uncommitted)\b/i.test(text));

async function fixture(operation, response = 'success') {
  const dir = await fsp.mkdtemp(path.join(os.tmpdir(), 'cairntir-question-plugin-'));
  const outbox = path.join(dir, 'cairntir-sync/outbox');
  await fsp.mkdir(outbox, {recursive:true});
  await fsp.mkdir(path.join(dir, 'cairntir-sync/memory'), {recursive:true});
  await fsp.writeFile(path.join(dir, NOTE), ORIGINAL);
  const register = {schema:'cairntir.question-register.v1', wing:WING, questions:[{...question}]};
  const workspace = {schema:'cairntir.obsidian-workspace.v1', wing:WING, drawers:[...supports.map(item=>({...item})), {drawer_id:37, source_identity:QID, content:ORIGINAL, content_sha256:hash(ORIGINAL), wing:WING, room:'work', layer:'on_demand', current:true, editable:false, supersedes_id:null, note:NOTE}]};
  const state = {dir, outbox, operation, response, register, workspace, controls:[], modals:[], notices:[], calls:[], commands:new Map(), events:[], queueFailure:false, settings:{pythonExecutable:'C:/public-fixture/python.exe', cairntirHome:path.join(dir,'store'), wing:WING}};
  state.saveManifests = async () => {
    await fsp.writeFile(path.join(dir,'cairntir-sync/questions.json'), JSON.stringify(register));
    await fsp.writeFile(path.join(dir,'cairntir-sync/workspace.json'), JSON.stringify(workspace));
  };
  await state.saveManifests();
  class Element {
    constructor() { this.children=[]; this.style={}; }
    empty() { this.children=[]; }
    createEl(tag, options={}) { const child=new Element(); child.tag=tag; child.text=options.text||''; this.children.push(child); return child; }
    createDiv(options={}) { return this.createEl('div',options); }
    setText(value) { this.text=value; return this; }
    addClass() { return this; }
    appendChild(child) { this.children.push(child); return child; }
    addEventListener(name, callback) { this[name]=callback; }
  }
  class Field {
    constructor(kind, setting) { this.kind=kind; this.setting=setting; this.value=''; this.disabled=false; this.inputEl=new Element(); this.buttonEl=new Element(); state.controls.push(this); }
    setValue(value) { this.value=value; this.inputEl.value=value; return this; }
    setPlaceholder() { return this; }
    setDisabled(value) { this.disabled=value; return this; }
    setButtonText(value) { this.label=value; return this; }
    setCta() { this.cta=true; return this; }
    setWarning() { return this; }
    onChange(callback) { this.change=callback; return this; }
    onClick(callback) { this.click=callback; return this; }
    addOption() { return this; }
    addOptions() { return this; }
  }
  class Setting {
    constructor() { this.name=''; }
    setName(value) { this.name=String(value); return this; }
    setDesc() { return this; }
    addText(callback) { callback(new Field('text',this)); return this; }
    addTextArea(callback) { callback(new Field('textarea',this)); return this; }
    addDropdown(callback) { callback(new Field('dropdown',this)); return this; }
    addButton(callback) { callback(new Field('button',this)); return this; }
  }
  class Modal {
    constructor(app) { this.app=app; this.contentEl=new Element(); this.titleEl=new Element(); this.modalEl=new Element(); }
    open() { state.modals.push(this); this.onOpen?.(); }
    close() { this.closed=true; this.onClose?.(); }
    setTitle(value) { this.titleEl.setText(value); return this; }
  }
  class Plugin {
    constructor(app) { this.app=app; }
    async loadData() { return {...state.settings}; }
    async saveData() {}
    addCommand(command) { state.commands.set(command.id,command); }
    addSettingTab() {}
    registerEvent(event) { state.events.push(event); }
    registerInterval() { throw new Error('No automatic polling/mutation authorized'); }
  }
  class PluginSettingTab { constructor(app, plugin) { this.app=app; this.plugin=plugin; this.containerEl=new Element(); } }
  class FileSystemAdapter {
    getBasePath() { return dir; }
    async read(relative) { return fsp.readFile(path.join(dir,relative),'utf8'); }
    async exists(relative) { return fs.existsSync(path.join(dir,relative)); }
    async write(relative,text) { if(state.queueFailure && relative.startsWith('cairntir-sync/outbox/')) throw new Error('Synthetic queue failure'); return fsp.writeFile(path.join(dir,relative),text); }
  }
  class TFile { constructor(relative) { this.path=relative; this.basename=path.basename(relative,'.md'); this.extension='md'; } }
  async function output() {
    if(state.response==='process-error') throw new Error('Synthetic process failure');
    if(state.response==='malformed') return 'not JSON';
    const response=state.response.replace(/^exit1-/,'');
    const results=[];
    for(const filename of await fsp.readdir(outbox)) {
      const request=JSON.parse(await fsp.readFile(path.join(outbox,filename),'utf8'));
      const isOpen=request.schema==='cairntir.question-open.v1';
      const receipt={schema:'cairntir.question-receipt.v1',operation:isOpen?'open':'resolve',status:'committed',request_id:request.request_id,question_id:isOpen?'09ba594b-806e-4634-9a94-aa7ee06bd292':request.question_id,question_drawer_id:isOpen?50:request.question_drawer_id,question_sha256:isOpen?hash(request.content):request.question_sha256,resolution_drawer_id:isOpen?null:51,replayed:false};
      const item={file:'cairntir-sync/outbox/'+filename,status:'committed',receipt,receipt_written:true};
      if(response==='missing-receipt') delete item.receipt;
      if(response==='wrong-request') receipt.request_id='6e5078d2-a7c6-4e41-b8e7-4319e1be1975';
      if(response==='wrong-file') item.file='cairntir-sync/outbox/unrelated.json';
      if(response==='wrong-operation') receipt.operation=isOpen?'resolve':'open';
      if(response==='wrong-question') receipt.question_id='d45d8f17-6d1e-4a32-a711-e7dc98e7bccf';
      if(response==='wrong-question-id') receipt.question_drawer_id=99;
      if(response==='wrong-question-hash') receipt.question_sha256='0'.repeat(64);
      if(response==='bad-schema') receipt.schema='wrong';
      if(response==='bad-status') receipt.status='rejected';
      if(response==='bad-replayed') receipt.replayed='false';
      if(response==='bad-question-id') receipt.question_drawer_id=true;
      if(response==='bad-question-uuid') receipt.question_id='not-a-uuid';
      if(response==='bad-resolution-id') receipt.resolution_drawer_id=0;
      if(response==='unexpected-open-resolution') receipt.resolution_drawer_id=51;
      if(response==='rejected') {item.status='rejected';item.error='Synthetic declared rejection';delete item.receipt;}
      if(response==='receipt-error') item.receipt_written=false;
      results.push(item);
      if(response==='duplicate') results.push(JSON.parse(JSON.stringify(item)));
      if(response==='mixed') results.push({file:'cairntir-sync/outbox/unrelated.json',status:'rejected',error:'Unrelated request rejected'});
    }
    return JSON.stringify({schema:response==='bad-report-schema'?'wrong':'cairntir.obsidian-sync.v1',wing:response==='wrong-wing'?'foreign':WING,results,projection:response==='projection-error'?{status:'error',error:'Synthetic projection error'}:{status:'complete',current_count:4}});
  }
  function execFile(executable,args,options,callback) {
    state.calls.push({executable,args,options});
    output().then(stdout=>{
      let error=null;
      if(state.response.startsWith('exit1-')) error=Object.assign(new Error('partial'),{code:1,killed:false,signal:null});
      if(state.response==='killed') error=Object.assign(new Error('killed'),{code:1,killed:true,signal:null});
      if(state.response==='signal') error=Object.assign(new Error('signal'),{code:1,killed:false,signal:'SIGTERM'});
      if(state.response==='spawn') error=Object.assign(new Error('spawn'),{code:'ENOENT',killed:false,signal:null});
      if(state.response==='exit2') error=Object.assign(new Error('exit2'),{code:2,killed:false,signal:null});
      if(state.response==='string-exit1') error=Object.assign(new Error('string'),{code:'1',killed:false,signal:null});
      callback(error,stdout,'');
    },error=>callback(error,'',''));
    return {kill(){}};
  }
  execFile[util.promisify.custom]=(exe,args,opts)=>new Promise((resolve,reject)=>execFile(exe,args,opts,(error,stdout,stderr)=>error?reject(error):resolve({stdout,stderr})));
  const obsidian={Plugin,Modal,Setting,PluginSettingTab,FileSystemAdapter,TFile,Notice:class {constructor(message){state.notices.push(String(message));}},Platform:{isDesktop:true,isMobile:false},normalizePath:value=>value.replace(/\\/g,'/')};
  const originalLoad=Module._load;
  Module._load=function(name,parent,isMain) {
    if(name==='obsidian') return obsidian;
    if(name==='child_process'||name==='node:child_process') return {execFile,exec(){throw new Error('No shell allowed');}};
    return originalLoad.call(this,name,parent,isMain);
  };
  let Export;
  try {delete require.cache[pluginPath];Export=require(pluginPath);} finally {Module._load=originalLoad;}
  const app={vault:{adapter:new FileSystemAdapter(),on:(name,callback)=>({name,callback}),async createFolder(relative){await fsp.mkdir(path.join(dir,relative),{recursive:true});},async create(relative,text){if(state.queueFailure)throw new Error('Synthetic queue failure');await fsp.writeFile(path.join(dir,relative),text,{flag:'wx'});return new TFile(relative);},getAbstractFileByPath:relative=>new TFile(relative),getFileByPath:relative=>new TFile(relative),async read(file){return fsp.readFile(path.join(dir,file.path),'utf8');}},workspace:{getActiveFile:()=>new TFile(NOTE),on:(name,callback)=>({name,callback}),async openLinkText(){}}};
  state.plugin=new Export(app);await state.plugin.onload();await tick();
  state.command=async id=>{const command=state.commands.get(id);check(command,'registered '+id);if(command.callback)await command.callback();else check(command.checkCallback(false)!==false,'enabled '+id);await tick();};
  state.open=()=>state.command(operation==='open'?'open-question':'resolve-question');
  state.set=async(role,value)=>{
    const field=state.controls.find(control=>control.kind!=='button' && (role==='content'?control.kind==='textarea' && !/evidence/i.test(control.setting.name):new RegExp(role,'i').test(control.setting.name)));
    check(field,'visible '+role+' field');field.value=value;field.inputEl.value=value;await field.change?.(value);
  };
  state.fill=async(evidence='7,8',owner='  Patrick  ')=>{
    await state.set('content',operation==='open'?PROPOSED:RESOLUTION);
    if(operation==='open'){await state.set('room','work');await state.set('owner',owner);}
    await state.set('evidence',evidence);
  };
  state.submit=async()=>{const button=state.controls.find(control=>control.kind==='button' && (control.cta || /submit|resolve|retry|record|save/i.test(control.label||'')) && !/cancel/i.test(control.label||''));check(button?.click,'explicit submit control');await button.click();await tick();};
  state.files=()=>fsp.readdir(outbox);
  state.request=async()=>{const files=await state.files();equal(files.length,1,'one retained request');return JSON.parse(await fsp.readFile(path.join(outbox,files[0]),'utf8'));};
  state.clean=async()=>{await state.plugin.onunload?.();check(path.resolve(dir).startsWith(path.resolve(os.tmpdir())+path.sep),'owned temp scope');await fsp.rm(dir,{recursive:true,force:true});};
  return state;
}

function callValid(state) {
  equal(state.calls.length,1,'one sync after submit');const call=state.calls[0];
  equal(call.executable,state.settings.pythonExecutable,'configured executable');
  equal(call.args,['-m','cairntir','obsidian-sync',state.dir,'--wing',WING],'explicit argv');
  equal(call.options.env.CAIRNTIR_HOME,state.settings.cairntirHome,'configured home');
  check(call.options.shell===false || call.options.shell===undefined,'no shell');
  equal(call.options.windowsHide,true,'hidden process');
  check(Number.isFinite(call.options.timeout)&&call.options.timeout>0,'bounded timeout');
  check(Number.isSafeInteger(call.options.maxBuffer)&&call.options.maxBuffer>0,'bounded output');
}
async function run(name,body){await body();cases++;console.log(JSON.stringify({case:name,result:'PASS'}));}
async function withFixture(operation,response,body){const state=await fixture(operation,response);try{await body(state);}finally{await state.clean();}}

(async()=>{
  for(const operation of ['open','resolve']) {
    await run(operation+' idle/form/cancel',()=>withFixture(operation,'success',async state=>{
      equal(state.calls.length,0,'idle no process');equal(await state.files(),[],'idle no writes');
      for(const event of state.events)await event.callback?.({path:NOTE});
      await state.open();equal(state.calls.length,0,'form no process');equal(await state.files(),[],'form no writes');
      state.modals.at(-1)?.close();equal(await state.files(),[],'cancel no request');
    }));
    await run(operation+' exact fields and acknowledged success',()=>withFixture(operation,'success',async state=>{
      const beforeNote=await fsp.readFile(path.join(state.dir,NOTE));const beforeManifest=await fsp.readFile(path.join(state.dir,'cairntir-sync/workspace.json'));
      await state.open();await state.fill();await state.submit();const request=await state.request();
      equal(request.schema,`cairntir.question-${operation}.v1`,'core schema');equal(request.wing,WING,'wing');
      check(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(request.request_id),'canonical UUID');
      equal((await state.files())[0],request.request_id+'.json','filename binding');
      equal(request.evidence,supports.map(ref),'bound evidence references');
      equal(request.content,operation==='open'?PROPOSED:RESOLUTION,'exact user text');
      const common=['schema','request_id','wing','content','evidence'];
      if(operation==='open'){equal(request.room,'work','room');equal(request.owner,'  Patrick  ','exact declared owner');equal(Object.keys(request).sort(),[...common,'room','owner'].sort(),'exact opening fields');}
      else {equal(request.question_id,QID,'stable question UUID');equal(request.question_drawer_id,37,'local ID');equal(request.question_sha256,hash(ORIGINAL),'original question hash');equal(Object.keys(request).sort(),[...common,'question_id','question_drawer_id','question_sha256'].sort(),'exact resolution fields');}
      callValid(state);check(saved(state),'matching receipt visibly acknowledged');
      equal(await fsp.readFile(path.join(state.dir,NOTE)),beforeNote,'original note unchanged');
      equal(await fsp.readFile(path.join(state.dir,'cairntir-sync/workspace.json')),beforeManifest,'manifest unchanged');
    }));
    const invalid=['process-error','malformed','wrong-wing','bad-report-schema','missing-receipt','duplicate','wrong-request','wrong-file','wrong-operation','wrong-question-hash','bad-schema','bad-status','bad-replayed','bad-question-id','bad-question-uuid','rejected','killed','signal','spawn','exit2','string-exit1'];
    invalid.push(...(operation==='resolve'?['wrong-question','wrong-question-id','bad-resolution-id']:['unexpected-open-resolution']));
    for(const response of invalid)await run(operation+' no false saved: '+response,()=>withFixture(operation,response,async state=>{
      await state.open();await state.fill();await state.submit();check(!saved(state),'invalid/uncertain result must not claim saved');
      check(state.notices.length>0,'visible diagnostic');const files=await state.files();equal(files.length,1,'request retained');
      const bytes=await fsp.readFile(path.join(state.outbox,files[0]));state.response='success';await state.submit();
      equal(await state.files(),files,'retry keeps UUID');equal(await fsp.readFile(path.join(state.outbox,files[0])),bytes,'retry keeps exact payload');check(saved(state),'matching retry acknowledged');
    }));
    for(const response of ['receipt-error','projection-error','exit1-receipt-error','exit1-projection-error','exit1-mixed'])await run(operation+' partial commit: '+response,()=>withFixture(operation,response,async state=>{
      await state.open();await state.fill();await state.submit();check(saved(state),'authentic database commit acknowledged');equal((await state.files()).length,1,'partial request retained');
      if(!response.endsWith('mixed'))check(state.notices.some(text=>/retry|fail|error|could not|unavailable/i.test(text)),'partial failure disclosed');
    }));
    for(const setting of ['pythonExecutable','cairntirHome','wing'])await run(operation+' changed setting '+setting,()=>withFixture(operation,'success',async state=>{
      await state.open();await state.fill();state.plugin.settings[setting]+='-changed';await state.submit();equal(await state.files(),[],'changed settings no queue');equal(state.calls.length,0,'changed settings no process');check(!saved(state),'changed settings no success');
    }));
    await run(operation+' queue failure then retry',()=>withFixture(operation,'success',async state=>{
      await state.open();await state.fill();state.queueFailure=true;await state.submit();equal(await state.files(),[],'failed queue no file');equal(state.calls.length,0,'failed queue no process');check(!saved(state),'failed queue no success');state.queueFailure=false;await state.submit();equal((await state.files()).length,1,'retry queues once');callValid(state);check(saved(state),'retry commit acknowledged');
    }));
    for(const evidence of ['999','7,7'])await run(operation+' invalid evidence '+evidence,()=>withFixture(operation,'success',async state=>{
      await state.open();await state.fill(evidence);await state.submit();equal(await state.files(),[],'invalid evidence no queue');equal(state.calls.length,0,'invalid evidence no process');check(state.notices.length>0,'invalid evidence visible');
    }));
    await run(operation+' stale evidence before queue',()=>withFixture(operation,'success',async state=>{
      await state.open();await state.fill();state.workspace.drawers[0].content='Changed measured evidence';state.workspace.drawers[0].content_sha256=hash(state.workspace.drawers[0].content);await state.saveManifests();await state.submit();equal(await state.files(),[],'stale selected evidence no queue');equal(state.calls.length,0,'stale selected evidence no process');
    }));
  }
  await run('opening unassigned without evidence',()=>withFixture('open','success',async state=>{await state.open();await state.fill('','');await state.submit();const request=await state.request();equal(request.owner,null,'unassigned owner');equal(request.evidence,[],'optional opening evidence');check(saved(state),'unassigned open saved');}));
  await run('resolution cannot omit evidence',()=>withFixture('resolve','success',async state=>{await state.open();await state.fill('');await state.submit();equal(await state.files(),[],'unsupported resolution no queue');equal(state.calls.length,0,'unsupported resolution no process');}));
  for(const mutation of ['status','wing','schema','duplicate','hash'])await run('stale resolution register '+mutation,()=>withFixture('resolve','success',async state=>{
    await state.open();await state.fill();if(mutation==='status')state.register.questions[0].status='resolved';if(mutation==='wing')state.register.wing='foreign';if(mutation==='schema')state.register.schema='wrong';if(mutation==='duplicate')state.register.questions.push({...state.register.questions[0]});if(mutation==='hash')state.register.questions[0].content_sha256='0'.repeat(64);await state.saveManifests();await state.submit();equal(await state.files(),[],'stale register no queue');equal(state.calls.length,0,'stale register no process');check(state.notices.length>0,'stale register visible');
  }));
  console.log(JSON.stringify({schema:'cairntir.public-question-plugin-result.v1',result:'PASS',cases,assertions,scope:'Public mocked plugin boundary; native UI and actual backend process proof remain separate'}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
