'use strict';
// Retain frozen public form controls; replace only the child-process boundary.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const child = require('node:child_process');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const python = process.argv[3];
const source = process.argv[4];
const original = path.resolve(process.argv[5]);
assert.equal(crypto.createHash('sha256').update(fs.readFileSync(original)).digest('hex'),
  '1157de20f381158503cf1c4aa8f50dab1ce6f45ec32007f69c0d201accc09846');
let prefix = fs.readFileSync(original, 'utf8').split('(async()=>{')[0];
const begin = prefix.indexOf('  function execFile(executable,args,options,callback) {');
const end = prefix.indexOf('  execFile[util.promisify.custom]', begin);
assert(begin > 0 && end > begin, 'frozen fixture process seam exists');
prefix = prefix.slice(0, begin) + `  function execFile(executable,args,options,callback) {
    state.calls.push({executable,args,options});
    if(state.failAckNext) {
      state.failAckNext=false;
      const files=fs.readdirSync(state.outbox);
      assert.equal(files.length,1);
      const request=JSON.parse(fs.readFileSync(path.join(state.outbox,files[0]),'utf8'));
      state.failedAckPath=path.join(state.dir,'cairntir-sync/acknowledgements',request.request_id+'.json');
      fs.mkdirSync(state.failedAckPath,{recursive:true});
    }
    const env={...options.env,PYTHONPATH:path.join(state.dir,'shim')+path.delimiter+process.argv[4],
      PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',HF_HUB_OFFLINE:'1',TRANSFORMERS_OFFLINE:'1',
      CAIRNTIR_DISABLE_AUTOREGISTER:'1',CAIRNTIR_DISABLE_UPDATE_CHECK:'1'};
    delete env.CAIRNTIR_GRANT_FILE;
    return actualChild.execFile(executable,args,{...options,env,timeout:15000},(error,stdout,stderr)=>{
      if(error){error.stdout=stdout;error.stderr=stderr;}
      callback(error,stdout,stderr);
    });
  }
` + prefix.slice(end);
assert(prefix.includes('getActiveFile:()=>new TFile(NOTE)'), 'frozen active-file seam exists');
prefix = prefix.replace('getActiveFile:()=>new TFile(NOTE)',
  'getActiveFile:()=>new TFile(state.activeNote || NOTE)');
prefix = "const actualChild = require('node:child_process');\n" + prefix;
prefix += '\nmodule.exports={fixture,PROPOSED,RESOLUTION,WING,saved};\n';
const fixtureModule = new Module(path.join(__dirname, 'real-question-fixture.cjs'), module);
fixtureModule.filename = path.join(__dirname, 'real-question-fixture.cjs');
fixtureModule.paths = module.paths;
fixtureModule._compile(prefix, fixtureModule.filename);
const {fixture,PROPOSED,RESOLUTION,WING,saved} = fixtureModule.exports;
function py(code,args,env) {
  const result=child.spawnSync(python,['-c',code,...args],
    {env,encoding:'utf8',timeout:15000,windowsHide:true});
  assert.equal(result.status,0,result.stdout+result.stderr);
  return JSON.parse(result.stdout);
}
function requestFiles(state) { return fs.readdirSync(state.outbox).sort(); }
function acknowledged(state,request) {
  return JSON.parse(fs.readFileSync(path.join(state.dir,'cairntir-sync/acknowledgements',request.request_id+'.json'),'utf8'));
}
(async()=>{
  const state=await fixture('open');
  try {
    assert.equal(state.calls.length,0,'startup cannot launch a process');
    const home=path.join(state.dir,'home');
    fs.mkdirSync(home);fs.mkdirSync(path.join(state.dir,'.obsidian'));
    fs.mkdirSync(path.join(state.dir,'shim'));
    fs.writeFileSync(path.join(state.dir,'shim','sitecustomize.py'),
      'import cairntir.cli as cli\nfrom cairntir.memory.embeddings import HashEmbeddingProvider\ncli.production_embedding_provider=lambda: HashEmbeddingProvider(dimension=16)\n');
    state.settings.pythonExecutable=python;state.settings.cairntirHome=home;
    state.plugin.settings.pythonExecutable=python;state.plugin.settings.cairntirHome=home;
    const env={...process.env,PYTHONPATH:source,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',
      CAIRNTIR_HOME:home,CAIRNTIR_DISABLE_AUTOREGISTER:'1',CAIRNTIR_DISABLE_UPDATE_CHECK:'1'};
    delete env.CAIRNTIR_GRANT_FILE;
    const entries=py('import sys,json,hashlib;from pathlib import Path;from cairntir.memory.store import DrawerStore;from cairntir.memory.embeddings import HashEmbeddingProvider;from cairntir.memory.taxonomy import Drawer;s=DrawerStore(Path(sys.argv[1])/"cairntir.db",HashEmbeddingProvider(dimension=16));ds=[s.add(Drawer(wing=sys.argv[2],room="evidence",content=x)) for x in ["Evidence A café\\r\\n","Evidence B exact  "]];print(json.dumps([dict(drawer_id=d.id,source_identity=s.portable_identity(d.id),content=d.content,content_sha256=hashlib.sha256(d.content.encode()).hexdigest(),wing=d.wing,room=d.room,layer="on_demand",current=True,editable=True,supersedes_id=None,note="cairntir-sync/memory/drawer-"+str(d.id)+".md") for d in ds]));s.close()',
      [home,WING],env);
    state.workspace.drawers=entries;state.register.questions=[];
    await state.saveManifests();
    await state.open();await state.fill(entries.map(x=>x.drawer_id).join(','),'  Process owner  ');
    assert.equal(state.calls.length,0,'opening/filling explicit form cannot launch');
    state.failAckNext=true;await state.submit();
    assert.equal(state.calls.length,1);
    assert(saved(state),state.notices.join('\n'));
    assert(state.notices.some(x=>/retry|fail|error|could not/i.test(x)),'ack failure disclosed');
    const firstFile=requestFiles(state)[0];
    const openingBytes=fs.readFileSync(path.join(state.outbox,firstFile));
    const opening=JSON.parse(openingBytes);
    assert.equal(opening.content,PROPOSED);assert.equal(opening.owner,'  Process owner  ');
    assert.deepEqual(opening.evidence,entries.map(x=>({drawer_id:x.drawer_id,source_identity:x.source_identity,content_sha256:x.content_sha256})));
    fs.rmdirSync(state.failedAckPath);await state.submit();
    assert.equal(state.calls.length,2);
    const opened=acknowledged(state,opening);assert.equal(opened.replayed,true);
    assert.deepEqual(fs.readFileSync(path.join(state.outbox,firstFile)),openingBytes);
    const registerPath=path.join(state.dir,'cairntir-sync/questions.json');
    let register=JSON.parse(fs.readFileSync(registerPath,'utf8'));
    assert.equal(register.questions.length,1);assert.equal(register.questions[0].status,'open');
    state.activeNote=register.questions[0].note;
    const markdown=path.join(state.dir,'cairntir-sync/questions.md');
    const annotation=Buffer.from('\r\nHuman process annotation café\nkeep exact.\r\n');
    fs.appendFileSync(markdown,annotation);
    state.controls=[];state.modals=[];state.notices=[];
    await state.command('resolve-question');await state.set('content',RESOLUTION);
    await state.set('evidence',String(entries[0].drawer_id));
    assert.equal(state.calls.length,2,'resolve form cannot launch');
    const index=path.join(state.dir,'cairntir-sync/index.md');
    const priorIndex=fs.readFileSync(index);const blocked=Buffer.from('Human unmarked index\r\n');
    fs.writeFileSync(index,blocked);await state.submit();
    assert.equal(state.calls.length,3);assert(saved(state),state.notices.join('\n'));
    assert(state.notices.some(x=>/retry|fail|error|could not/i.test(x)),'projection failure disclosed');
    assert.deepEqual(fs.readFileSync(index),blocked,'unmarked human target untouched');
    const secondFile=requestFiles(state).find(x=>x!==firstFile);
    const resolutionBytes=fs.readFileSync(path.join(state.outbox,secondFile));
    const resolution=JSON.parse(resolutionBytes);
    assert.equal(resolution.content,RESOLUTION);assert.equal(resolution.question_id,opened.question_id);
    assert.equal(resolution.question_drawer_id,opened.question_drawer_id);
    assert.equal(resolution.question_sha256,opened.question_sha256);
    fs.writeFileSync(index,priorIndex);await state.submit();
    assert.equal(state.calls.length,4);const resolved=acknowledged(state,resolution);
    assert.equal(resolved.replayed,true);
    assert.deepEqual(fs.readFileSync(path.join(state.outbox,secondFile)),resolutionBytes);
    await state.plugin.onunload?.();
    state.plugin=new state.plugin.constructor(state.plugin.app);
    await state.plugin.onload();
    assert.equal(state.calls.length,4,'plugin restart cannot launch automatically');
    await state.command('refresh-workspace');
    assert.equal(state.calls.length,5,'five actual configured CLI launches');
    for(const call of state.calls) {
      assert.equal(call.executable,python);assert.deepEqual(call.args,['-m','cairntir','obsidian-sync',state.dir,'--wing',WING]);
      assert.equal(call.options.env.CAIRNTIR_HOME,home);assert.equal(call.options.windowsHide,true);
      assert(call.options.shell===false || call.options.shell===undefined);
    }
    register=JSON.parse(fs.readFileSync(registerPath,'utf8'));
    assert.equal(register.questions[0].status,'resolved');
    assert.equal(register.questions[0].content,PROPOSED);
    assert.equal(register.questions[0].resolution.content,RESOLUTION);
    assert(fs.readFileSync(markdown).subarray(-annotation.length).equals(annotation));
    await state.command('show-question-register');assert.equal(state.calls.length,5);
    const stored=py('import sys,json;from pathlib import Path;from cairntir.memory.store import DrawerStore;from cairntir.memory.embeddings import HashEmbeddingProvider;s=DrawerStore(Path(sys.argv[1])/"cairntir.db",HashEmbeddingProvider(dimension=16));print(json.dumps([dict(id=r[0],content=r[1],supersedes_id=r[2]) for r in s._conn.execute("SELECT id,content,supersedes_id FROM drawers ORDER BY id")]));s.close()',[home],env);
    assert.equal(stored.length,4,'retry/refresh cannot duplicate drawers');
    assert.equal(stored.find(x=>x.id===opened.question_drawer_id).content,PROPOSED);
    assert.equal(stored.find(x=>x.id===resolved.resolution_drawer_id).content,RESOLUTION);
    assert.equal(stored.find(x=>x.id===resolved.resolution_drawer_id).supersedes_id,opened.question_drawer_id);
    for(const entry of entries)assert.equal(stored.find(x=>x.id===entry.drawer_id).content,entry.content);
    process.stdout.write(JSON.stringify({status:'PASS',actual_plugin_cli_launches:5,
      fixture_python_setup_reads:2,synthetic_provider:true,acknowledgement_and_projection_retry:'PASS',
      exact_user_bytes_and_no_duplicate_appends:'PASS',graphical_obsidian:'not exercised'})+'\n');
  } finally {await state.clean();}
})().catch(error=>{process.stderr.write(error.stack+'\n');process.exitCode=1;});
