'use strict';
// Reuse the frozen Obsidian API fixture; replace only its child-process boundary.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const child = require('node:child_process');
const assert = require('node:assert/strict');
const python = process.argv[3];
const source = process.argv[4];
const original = path.join(__dirname, 'originals', 'v2-obsidian-plugin', 'test-obsidian-plugin-v3.cjs');
let prefix = fs.readFileSync(original, 'utf8').split('(async () => {')[0];
const begin = prefix.indexOf('  function execFile(executable, args, options, callback) {');
const end = prefix.indexOf('  execFile[util.promisify.custom]', begin);
assert(begin > 0 && end > begin, 'frozen fixture seam exists');
prefix = prefix.slice(0, begin) + `  function execFile(executable, args, options, callback) {
    state.calls.push({ executable, args, options });
    const env = { ...options.env,
      PYTHONPATH: path.join(state.dir, 'shim') + path.delimiter + process.argv[4],
      CAIRNTIR_DISABLE_AUTOREGISTER: '1', CAIRNTIR_DISABLE_UPDATE_CHECK: '1' };
    delete env.CAIRNTIR_GRANT_FILE;
    return require('node:child_process').execFile(executable, args,
      { ...options, env, timeout: 15000 }, (error, stdout, stderr) => {
        if (error) { error.stdout = stdout; error.stderr = stderr; }
        callback(error, stdout, stderr);
      });
  }
` + prefix.slice(end);
// Capture the real child module before the fixture installs its loader shim.
prefix = prefix.replace("return require('node:child_process').execFile(executable, args,",
                        "return actualChild.execFile(executable, args,");
prefix = "const actualChild = require('node:child_process');\n" + prefix;
prefix += '\nmodule.exports = { fixture, ORIGINAL, WING, NOTE, claimsSaved, validateCall };\n';
const fixtureModule = new Module(path.join(__dirname, 'real-plugin-fixture.cjs'), module);
fixtureModule.filename = path.join(__dirname, 'real-plugin-fixture.cjs');
fixtureModule.paths = module.paths;
fixtureModule._compile(prefix, fixtureModule.filename);
const { fixture, ORIGINAL, WING, claimsSaved, validateCall } = fixtureModule.exports;
function py(code, args, env) {
  const result = child.spawnSync(python, ['-c', code, ...args],
    { env, encoding: 'utf8', timeout: 15000, windowsHide: true });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return JSON.parse(result.stdout);
}
(async () => {
  const state = await fixture({ settings: { pythonExecutable: python,
    cairntirHome: 'unused until fixture creates the home', wing: WING } });
  try {
    const home = path.join(state.dir, 'home');
    state.settings.cairntirHome = home;
    state.plugin.settings.cairntirHome = home;
    fs.mkdirSync(home);
    fs.mkdirSync(path.join(state.dir, '.obsidian'));
    fs.mkdirSync(path.join(state.dir, 'shim'));
    fs.writeFileSync(path.join(state.dir, 'shim', 'sitecustomize.py'),
      'import cairntir.cli as cli\nfrom cairntir.memory.embeddings import HashEmbeddingProvider\ncli.production_embedding_provider = lambda: HashEmbeddingProvider(dimension=16)\n');
    const env = { ...process.env, PYTHONPATH: source, PYTHONUTF8: '1',
      CAIRNTIR_HOME: home, CAIRNTIR_DISABLE_AUTOREGISTER: '1', CAIRNTIR_DISABLE_UPDATE_CHECK: '1' };
    delete env.CAIRNTIR_GRANT_FILE;
    const seeded = py('import sys,json; from pathlib import Path; from cairntir.memory.store import DrawerStore; from cairntir.memory.embeddings import HashEmbeddingProvider; from cairntir.memory.taxonomy import Drawer; s=DrawerStore(Path(sys.argv[1])/"cairntir.db",HashEmbeddingProvider(dimension=16)); d=s.add(Drawer(wing=sys.argv[2],room="synthetic",content=sys.argv[3])); print(json.dumps(dict(id=d.id,identity=s.portable_identity(d.id)))); s.close()',
      [home, WING, ORIGINAL], env);
    const manifestPath = path.join(state.dir, 'cairntir-sync', 'workspace.json');
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    manifest.drawers[0].drawer_id = seeded.id;
    manifest.drawers[0].source_identity = seeded.identity;
    fs.writeFileSync(manifestPath, JSON.stringify(manifest));
    await state.open();
    const correction = '  Real-process café 雪 🧭\r\n\r\ntrailing space \r\n';
    await state.submit(correction);
    assert.equal(state.calls.length, 1, 'one real process on explicit submission');
    validateCall(state, state.calls[0]);
    assert(claimsSaved(state), state.notices.join('\n'));
    const files = await state.files();
    assert.equal(files.length, 1);
    const proposalPath = path.join(state.dir, 'cairntir-sync', 'outbox', files[0]);
    const proposalBytes = fs.readFileSync(proposalPath);
    const request = JSON.parse(proposalBytes);
    assert.equal(request.content, correction);
    assert.equal(request.source_drawer_id, seeded.id);
    assert.equal(request.source_identity, seeded.identity);
    const ackPath = path.join(state.dir, 'cairntir-sync', 'acknowledgements', request.request_id + '.json');
    const first = JSON.parse(fs.readFileSync(ackPath, 'utf8'));
    assert.equal(first.status, 'committed');
    // Force acknowledgement failure after committed data, then retry it.
    fs.unlinkSync(ackPath);
    fs.mkdirSync(ackPath);
    await state.command('refresh-workspace');
    assert.equal(state.calls.length, 2);
    assert(state.notices.some(x => /acknowledg|receipt/i.test(x)), state.notices.join('\n'));
    fs.rmdirSync(ackPath);
    await state.command('refresh-workspace');
    assert.equal(state.calls.length, 3);
    const last = JSON.parse(fs.readFileSync(ackPath, 'utf8'));
    assert.equal(last.correction_drawer_id, first.correction_drawer_id);
    assert.equal(last.replayed, true);
    assert.deepEqual(fs.readFileSync(proposalPath), proposalBytes);
    const stored = py('import sys,json; from pathlib import Path; from cairntir.memory.store import DrawerStore; from cairntir.memory.embeddings import HashEmbeddingProvider; s=DrawerStore(Path(sys.argv[1])/"cairntir.db",HashEmbeddingProvider(dimension=16)); print(json.dumps([dict(id=d.id,content=d.content,supersedes_id=d.supersedes_id) for d in s.list_by(limit=None,include_expired=True)])); s.close()', [home], env);
    assert.equal(stored.length, 2);
    assert.equal(stored.find(x => x.id === seeded.id).content, ORIGINAL);
    assert.equal(stored.find(x => x.id === first.correction_drawer_id).content, correction);
    assert.equal(stored.find(x => x.id === first.correction_drawer_id).supersedes_id, seeded.id);
    process.stdout.write(JSON.stringify({ actual_python_processes: 3, result: 'PASS',
      graphical_obsidian: 'not exercised' }) + '\n');
  } finally { await state.clean(); }
})().catch(error => { process.stderr.write(error.stack + '\n'); process.exitCode = 1; });
