"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const crypto = require("node:crypto");

const writes = [], processes = [], opened = [], notices = [], links = [];
const questionId = "c9c15f71-1426-4434-b8a7-c63740a46539";
const content = "Which recorded setting explains this result?";
const digest = crypto.createHash("sha256").update(content).digest("hex");
const note = "cairntir-sync/memory/drawer-2.md";
const entry = {
    question_id: questionId, drawer_id: 2, content, content_sha256: digest,
    owner: null, evidence: [], status: "open", legacy: false, resolution: null, note
};
const register = {schema: "cairntir.question-register.v1", wing: "questions", questions: [entry]};
const workspace = {schema: "cairntir.obsidian-workspace.v1", wing: "questions", drawers: [{
    drawer_id: 2, source_identity: questionId, content, content_sha256: digest, wing: "questions",
    room: "work", layer: "on_demand", current: true, editable: false, supersedes_id: null, note
}]};

class FileSystemAdapter {
    getBasePath() { return "C:/disposable-public-fixture"; }
    async read(path) {
        if (path === "cairntir-sync/questions.json") return JSON.stringify(register);
        if (path === "cairntir-sync/workspace.json") return JSON.stringify(workspace);
        throw new Error("No fixture file " + path);
    }
    async exists() { return true; }
    async write(path, data) { writes.push({path, data}); }
}
class Plugin {
    constructor(app) { this.app = app; this.commands = []; }
    async loadData() { return {pythonExecutable: "C:/fixture/python.exe", cairntirHome: "C:/fixture/home", wing: "questions"}; }
    addCommand(command) { this.commands.push(command); }
    addSettingTab() {}
    registerEvent() {}
}
class Modal {
    constructor(app) { this.app = app; this.contentEl = {empty() {}}; this.titleEl = {setText() {}}; }
    open() { opened.push(this); }
    close() {}
}
class PluginSettingTab {}
class Setting {}
class Notice { constructor(message) { notices.push(message); } }

const app = {
    vault: {
        adapter: new FileSystemAdapter(),
        async create(path, data) { writes.push({path, data}); },
        async createFolder(path) { writes.push({path}); },
        getAbstractFileByPath(path) { return {path}; },
        getFileByPath(path) { return {path}; }
    },
    workspace: {
        getActiveFile() { return {path: note}; },
        async openLinkText(path) { links.push(path); },
        getLeaf() { return {async openFile(file) { links.push(file.path); }}; }
    }
};
const context = {
    module: {exports: {}}, exports: {}, console, process, Buffer, setTimeout, clearTimeout,
    require(name) {
        if (name === "obsidian") return {Plugin, Modal, PluginSettingTab, Setting, Notice, FileSystemAdapter};
        if (name === "crypto" || name === "node:crypto") return crypto;
        if (name === "child_process" || name === "node:child_process") return {
            execFile(...args) { processes.push(args); throw new Error("No subprocess before explicit submission"); }
        };
        throw new Error("Unexpected dependency " + name);
    }
};

(async () => {
    vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), context, {filename: process.argv[2]});
    const plugin = new context.module.exports(app);
    await plugin.onload();
    for (const id of ["open-question", "resolve-question", "show-question-register"]) {
        assert.equal(plugin.commands.filter(command => command.id === id).length, 1, id);
    }
    assert.equal(writes.length, 0, "Plugin startup must not ingest or queue notes");
    assert.equal(processes.length, 0, "Plugin startup must not launch sync");
    const command = id => plugin.commands.find(command => command.id === id);
    await command("open-question").callback();
    assert.equal(opened.length, 1, "Opening a question must present an explicit form");
    await command("resolve-question").callback();
    assert.equal(opened.length, 2, "Resolving a selected open question must present an explicit form");
    assert.equal(writes.length, 0, "Opening forms must not queue requests");
    assert.equal(processes.length, 0, "Opening forms must not launch sync");
    await command("show-question-register").callback();
    assert(links.some(path => path.replace(/\.md$/, "") === "cairntir-sync/questions"));
    register.wing = "foreign";
    const priorNotices = notices.length;
    await command("resolve-question").callback();
    assert.equal(opened.length, 2, "Wrong-wing register must not open a resolution form");
    assert(notices.length > priorNotices, "Wrong-wing rejection must be visible");
    assert.equal(writes.length, 0);
    assert.equal(processes.length, 0);
    console.log(JSON.stringify({status: "PASS", scope: "Public mocked Obsidian command/no-eager-mutation checks; not submission or native UI proof"}));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
