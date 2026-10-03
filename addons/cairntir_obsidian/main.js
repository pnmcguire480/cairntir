const { Plugin, PluginSettingTab, Setting, Modal, Notice, FileSystemAdapter } = require("obsidian");
const { execFile } = require("child_process");
const { randomUUID, createHash } = require("crypto");

const WORKSPACE = "cairntir-sync/workspace.json";
const OUTBOX = "cairntir-sync/outbox";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const DEFAULTS = { pythonExecutable: "", cairntirHome: "", wing: "" };

function explain(error) {
    return typeof error === "string" ? error.slice(0, 300) : "See the sync report for details.";
}

function committedReceipt(result, request) {
    const receipt = result && result.receipt;
    if (!receipt || result.status !== "committed" ||
        receipt.schema !== "cairntir.obsidian-correction-receipt.v1" ||
        receipt.status !== "committed" || !UUID.test(receipt.request_id) ||
        result.file !== OUTBOX + "/" + receipt.request_id + ".json" ||
        !Number.isSafeInteger(receipt.source_drawer_id) || receipt.source_drawer_id <= 0 ||
        !UUID.test(receipt.source_identity) ||
        !Number.isSafeInteger(receipt.correction_drawer_id) || receipt.correction_drawer_id <= 0 ||
        typeof receipt.content_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(receipt.content_sha256) ||
        typeof receipt.replayed !== "boolean") return false;
    return !request || (
        receipt.request_id === request.request_id &&
        receipt.source_drawer_id === request.source_drawer_id &&
        receipt.source_identity === request.source_identity &&
        receipt.content_sha256 === createHash("sha256").update(request.content, "utf8").digest("hex")
    );
}

function questionReceipt(result, request) {
    const receipt = result && result.receipt;
    if (!receipt || result.status !== "committed" ||
        receipt.schema !== "cairntir.question-receipt.v1" || receipt.status !== "committed" ||
        !UUID.test(receipt.request_id) || !UUID.test(receipt.question_id) ||
        result.file !== OUTBOX + "/" + receipt.request_id + ".json" ||
        !Number.isSafeInteger(receipt.question_drawer_id) || receipt.question_drawer_id <= 0 ||
        typeof receipt.question_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(receipt.question_sha256) ||
        typeof receipt.replayed !== "boolean" || !["open", "resolve"].includes(receipt.operation)) return false;
    if (receipt.operation === "open" ? receipt.resolution_drawer_id !== null :
        !Number.isSafeInteger(receipt.resolution_drawer_id) || receipt.resolution_drawer_id <= 0) return false;
    if (!request) return true;
    return receipt.request_id === request.request_id &&
        request.schema === "cairntir.question-" + receipt.operation + ".v1" &&
        (receipt.operation === "open" ?
            receipt.question_sha256 === createHash("sha256").update(request.content, "utf8").digest("hex") :
            receipt.question_id === request.question_id &&
            receipt.question_drawer_id === request.question_drawer_id &&
            receipt.question_sha256 === request.question_sha256);
}

function evidenceReference(workspace, id, wing) {
    const matches = workspace.drawers.filter(entry => entry && entry.drawer_id === id);
    const entry = matches.length === 1 ? matches[0] : null;
    if (!entry || entry.wing !== wing || !Number.isSafeInteger(id) || id <= 0 ||
        typeof entry.source_identity !== "string" || !UUID.test(entry.source_identity) ||
        typeof entry.content !== "string" || typeof entry.content_sha256 !== "string" ||
        createHash("sha256").update(entry.content, "utf8").digest("hex") !== entry.content_sha256) {
        throw new Error("Evidence is unavailable or changed. Refresh the workspace and reopen the form.");
    }
    return { drawer_id: id, source_identity: entry.source_identity, content_sha256: entry.content_sha256 };
}

class QuestionModal extends Modal {
    constructor(plugin, operation, config, workspace, questions, selected) {
        super(plugin.app);
        Object.assign(this, { plugin, operation, config, workspace, questions, selected });
        this.content = "";
        this.room = "questions";
        this.owner = "";
        this.evidence = "";
        this.controls = [];
        this.pending = null;
        this.submitting = false;
    }

    onOpen() {
        const opening = this.operation === "open";
        this.titleEl.setText(opening ? "Open question" : "Resolve question");
        if (!opening) {
            new Setting(this.contentEl).setName("Question").addDropdown(field => {
                for (const entry of this.questions) field.addOption(entry.question_id, entry.content.slice(0, 100));
                field.setValue(this.selected.question_id).onChange(value => {
                    this.selected = this.questions.find(entry => entry.question_id === value);
                });
                this.controls.push(field);
            });
        }
        new Setting(this.contentEl).setName(opening ? "Question text" : "Resolution")
            .addTextArea(field => {
                field.setValue(this.content).onChange(value => { this.content = value; });
                field.inputEl.rows = 12;
                this.controls.push(field);
            });
        if (opening) {
            for (const [key, label] of [["room", "Room"], ["owner", "Owner (optional)"]]) {
                new Setting(this.contentEl).setName(label).addText(field => {
                    field.setValue(this[key]).onChange(value => { this[key] = value; });
                    this.controls.push(field);
                });
            }
        }
        new Setting(this.contentEl).setName("Evidence memory IDs")
            .setDesc(opening ? "Optional, separated by commas." : "At least one supporting memory; separate IDs by commas.")
            .addText(field => {
                field.setValue(this.evidence).onChange(value => { this.evidence = value; });
                this.controls.push(field);
            });
        new Setting(this.contentEl)
            .addButton(button => button.setButtonText("Cancel").onClick(() => this.close()))
            .addButton(button => {
                this.submitButton = button;
                button.setButtonText(opening ? "Record question" : "Submit resolution")
                    .setCta().onClick(() => this.submit());
            });
    }

    async submit() {
        if (this.submitting) return;
        this.submitting = true;
        this.submitButton.setDisabled(true);
        try {
            if (JSON.stringify(this.config) !== JSON.stringify(this.plugin.configuration())) {
                throw new Error("Settings changed. Restore them to retry, or reopen the form.");
            }
            if (!this.pending) {
                if (!this.content.trim()) throw new Error("Enter the question or resolution text.");
                const tokens = this.evidence.trim() ? this.evidence.split(",").map(value => value.trim()) : [];
                if (tokens.some(value => !/^[1-9][0-9]*$/.test(value))) throw new Error("Use positive memory IDs separated by commas.");
                const ids = tokens.map(Number);
                if (new Set(ids).size !== ids.length) throw new Error("Select each evidence memory only once.");
                if (this.operation === "resolve" && !ids.length) throw new Error("Select supporting evidence for the resolution.");
                const fresh = await this.plugin.readQuestionWorkspace(this.config);
                const evidence = ids.map(id => {
                    const before = evidenceReference(this.workspace, id, this.config.wing);
                    const after = evidenceReference(fresh, id, this.config.wing);
                    if (JSON.stringify(before) !== JSON.stringify(after)) throw new Error("Selected evidence changed. Refresh and reopen the form.");
                    return before;
                });
                const request = {
                    schema: "cairntir.question-" + this.operation + ".v1",
                    request_id: randomUUID(), wing: this.config.wing, content: this.content, evidence
                };
                if (this.operation === "open") {
                    if (!/^[a-z0-9][a-z0-9._:-]{0,62}[a-z0-9]$/.test(this.room)) throw new Error("Enter a valid Cairntir room identifier.");
                    request.room = this.room;
                    request.owner = this.owner.trim() ? this.owner : null;
                } else {
                    const register = await this.plugin.readQuestionRegister(this.config);
                    const current = register.questions.find(entry => entry.question_id === this.selected.question_id);
                    if (!current || current.status !== "open" || current.drawer_id !== this.selected.drawer_id ||
                        current.content_sha256 !== this.selected.content_sha256) throw new Error("The question changed. Refresh and reopen the resolution.");
                    Object.assign(request, {
                        question_id: current.question_id, question_drawer_id: current.drawer_id,
                        question_sha256: current.content_sha256
                    });
                }
                const file = OUTBOX + "/" + request.request_id + ".json";
                try {
                    if (!await this.app.vault.adapter.exists(OUTBOX)) await this.app.vault.createFolder(OUTBOX);
                    await this.app.vault.create(file, JSON.stringify(request, null, 2) + "\n");
                } catch {
                    throw new Error("Could not queue the request. Check vault permissions and retry.");
                }
                this.pending = { file, request };
                for (const field of this.controls) field.setDisabled(true);
                this.submitButton.setButtonText("Retry request");
            }
            const report = await this.plugin.sync(this.config);
            const matches = report.results.filter(result => result.file === this.pending.file);
            const result = matches.length === 1 ? matches[0] : null;
            if (!questionReceipt(result, this.pending.request)) {
                throw new Error("No matching acknowledgement. Request retained; review the sync report and retry.");
            }
            if (result.receipt_written === false) {
                new Notice("Question saved in Cairntir; acknowledgement writing failed. Request retained; retry.");
            } else if (report.projection.status === "error") {
                new Notice("Question saved in Cairntir; workspace refresh failed. Request retained; retry.");
            } else {
                new Notice(this.operation === "open" ? "Question saved in Cairntir." : "Question resolution saved in Cairntir.");
                this.close();
            }
        } catch (error) {
            new Notice(error.message);
        } finally {
            this.submitting = false;
            this.submitButton.setDisabled(false);
        }
    }

    onClose() {
        this.contentEl.empty();
        if (this.plugin.activeModal === this) this.plugin.activeModal = null;
    }
}

class CorrectionModal extends Modal {
    constructor(plugin, entry, config) {
        super(plugin.app);
        this.plugin = plugin;
        this.entry = entry;
        this.config = config;
        this.content = entry.content;
        this.pending = null;
        this.submitting = false;
    }

    onOpen() {
        this.titleEl.setText("Correct current memory");
        new Setting(this.contentEl)
            .setName("Correction")
            .setDesc("Submit a new memory that supersedes this version. History is preserved.")
            .addTextArea((text) => {
                this.text = text;
                text.setValue(this.content).onChange((value) => { this.content = value; });
                text.inputEl.rows = 16;
            });
        new Setting(this.contentEl)
            .addButton((button) => button.setButtonText("Cancel").onClick(() => this.close()))
            .addButton((button) => {
                this.submitButton = button;
                button.setButtonText("Submit correction").setCta().onClick(() => this.submit());
            });
    }

    async submit() {
        if (this.submitting) return;
        this.submitting = true;
        this.submitButton.setDisabled(true);
        try {
            if (JSON.stringify(this.config) !== JSON.stringify(this.plugin.configuration())) {
                throw new Error("Settings changed. Restore them to retry this request, or reopen the correction.");
            }
            if (!this.pending) {
                const current = await this.plugin.readEntry(this.entry.note, this.config);
                if (current.drawer_id !== this.entry.drawer_id ||
                    current.source_identity !== this.entry.source_identity ||
                    current.content_sha256 !== this.entry.content_sha256) {
                    throw new Error("The memory changed. Refresh the workspace and reopen the correction.");
                }
                this.pending = await this.plugin.queueCorrection(this.entry, this.content, this.config);
                this.text.setDisabled(true);
                this.submitButton.setButtonText("Retry request");
            }
            const report = await this.plugin.sync(this.config);
            const matches = report.results.filter((result) => result.file === this.pending.file);
            const result = matches.length === 1 ? matches[0] : null;
            if (!committedReceipt(result, this.pending.request)) {
                const detail = result && result.status === "rejected"
                    ? "Correction rejected: " + explain(result.error)
                    : "The correction has no matching commit receipt.";
                throw new Error(detail + " Request retained. Retry refresh, or reopen the current memory after resolving the error.");
            }
            if (result.receipt_written === false) {
                new Notice("Correction saved in Cairntir; its receipt could not be written. Request retained. Retry this request.");
            } else if (report.projection.status === "error") {
                new Notice("Correction saved in Cairntir; workspace refresh failed. Request retained. Retry refresh.");
            } else {
                new Notice("Correction saved in Cairntir.");
                this.close();
            }
        } catch (error) {
            new Notice(error.message);
        } finally {
            this.submitting = false;
            this.submitButton.setDisabled(false);
        }
    }

    onClose() {
        this.contentEl.empty();
        if (this.plugin.activeModal === this) this.plugin.activeModal = null;
    }
}

class CairntirSettings extends PluginSettingTab {
    constructor(app, plugin) {
        super(app, plugin);
        this.plugin = plugin;
    }

    display() {
        this.containerEl.empty();
        const fields = [
            ["pythonExecutable", "Python executable", "Full path to the Python environment containing Cairntir."],
            ["cairntirHome", "Cairntir home", "Explicit store directory. Use a disposable store for the first pilot."],
            ["wing", "Wing", "The project wing to project into this vault."]
        ];
        for (const [key, name, description] of fields) {
            new Setting(this.containerEl).setName(name).setDesc(description).addText((text) => {
                text.setValue(this.plugin.settings[key]).onChange(async (value) => {
                    this.plugin.settings[key] = value;
                    try {
                        await this.plugin.saveData(this.plugin.settings);
                    } catch {
                        new Notice("Could not save Cairntir settings. Check vault permissions and retry.");
                    }
                });
            });
        }
    }
}

module.exports = class CairntirWorkspace extends Plugin {
    async onload() {
        this.settings = { ...DEFAULTS, ...await this.loadData() };
        this.syncing = false;
        this.activeModal = null;
        this.addSettingTab(new CairntirSettings(this.app, this));
        this.addCommand({
            id: "refresh-workspace",
            name: "Refresh workspace",
            callback: () => this.refreshWorkspace()
        });
        this.addCommand({
            id: "propose-correction",
            name: "Correct current memory",
            callback: () => this.proposeCorrection()
        });
        this.addCommand({ id: "open-question", name: "Open question", callback: () => this.proposeQuestion("open") });
        this.addCommand({ id: "resolve-question", name: "Resolve question", callback: () => this.proposeQuestion("resolve") });
        this.addCommand({ id: "show-question-register", name: "Show question register", callback: () => this.showQuestionRegister() });
    }

    async readQuestionWorkspace(config) {
        const workspace = JSON.parse(await this.app.vault.adapter.read(WORKSPACE));
        if (!workspace || workspace.schema !== "cairntir.obsidian-workspace.v1" ||
            workspace.wing !== config.wing || !Array.isArray(workspace.drawers)) {
            throw new Error("The workspace does not match this wing. Refresh and reopen the form.");
        }
        return workspace;
    }

    async readQuestionRegister(config) {
        const register = JSON.parse(await this.app.vault.adapter.read("cairntir-sync/questions.json"));
        if (!register || register.schema !== "cairntir.question-register.v1" ||
            register.wing !== config.wing || !Array.isArray(register.questions)) {
            throw new Error("The question register does not match this wing. Refresh the workspace.");
        }
        const seen = new Set();
        for (const entry of register.questions) {
            if (!entry || typeof entry.question_id !== "string" || !UUID.test(entry.question_id) ||
                seen.has(entry.question_id) || !Number.isSafeInteger(entry.drawer_id) || entry.drawer_id <= 0 ||
                typeof entry.content !== "string" || typeof entry.content_sha256 !== "string" ||
                createHash("sha256").update(entry.content, "utf8").digest("hex") !== entry.content_sha256 ||
                !["open", "resolved", "legacy_superseded_unverified"].includes(entry.status)) {
                throw new Error("The question register is invalid. Refresh before submitting a resolution.");
            }
            seen.add(entry.question_id);
        }
        return register;
    }

    async proposeQuestion(operation) {
        try {
            const config = this.configuration();
            const workspace = await this.readQuestionWorkspace(config);
            const questions = operation === "resolve" ?
                (await this.readQuestionRegister(config)).questions.filter(entry => entry.status === "open") : [];
            if (operation === "resolve" && !questions.length) throw new Error("No open question is available. Refresh the workspace.");
            const active = this.app.workspace.getActiveFile();
            const selected = questions.find(entry => active &&
                active.path === "cairntir-sync/memory/drawer-" + entry.drawer_id + ".md") || questions[0];
            if (this.activeModal) this.activeModal.close();
            this.activeModal = new QuestionModal(this, operation, config, workspace, questions, selected);
            this.activeModal.open();
        } catch (error) {
            new Notice(error.message);
        }
    }

    async showQuestionRegister() {
        try {
            const config = this.configuration();
            await this.readQuestionRegister(config);
            await this.app.workspace.openLinkText("cairntir-sync/questions.md", "", false);
        } catch (error) {
            new Notice(error.message);
        }
    }

    configuration() {
        const config = {};
        for (const key of Object.keys(DEFAULTS)) {
            if (typeof this.settings[key] !== "string" || !this.settings[key].trim()) {
                throw new Error("Configure Python executable, Cairntir home and wing in the Cairntir settings first.");
            }
            config[key] = this.settings[key].trim();
        }
        if (!(this.app.vault.adapter instanceof FileSystemAdapter)) {
            throw new Error("Cairntir requires a local desktop vault.");
        }
        return config;
    }

    async sync(config) {
        if (this.syncing) throw new Error("A sync is already running. Wait, then retry.");
        this.syncing = true;
        try {
            return await new Promise((resolve, reject) => {
                this.syncProcess = execFile(
                    config.pythonExecutable,
                    ["-m", "cairntir", "obsidian-sync", this.app.vault.adapter.getBasePath(), "--wing", config.wing],
                    {
                        env: { ...process.env, CAIRNTIR_HOME: config.cairntirHome, PYTHONUTF8: "1" },
                        windowsHide: true,
                        timeout: 120000,
                        maxBuffer: 4 * 1024 * 1024,
                        shell: false
                    },
                    (error, stdout) => {
                        if (error && !(error.code === 1 && error.killed === false && !error.signal)) {
                            reject(new Error("Cairntir sync failed. Check the configured Python environment, then retry refresh. Queued requests are retained."));
                            return;
                        }
                        try {
                            const report = JSON.parse(stdout);
                            if (report.schema !== "cairntir.obsidian-sync.v1" ||
                                report.wing !== config.wing || !Array.isArray(report.results) ||
                                !report.projection || !["complete", "error"].includes(report.projection.status) ||
                                !report.results.every((result) => result && typeof result.file === "string" &&
                                    ["committed", "rejected"].includes(result.status))) {
                                throw new Error("Invalid sync report");
                            }
                            resolve(report);
                        } catch {
                            reject(new Error("Cairntir returned an invalid sync report. Check the backend version and retry refresh. Queued requests are retained."));
                        }
                    }
                );
            });
        } finally {
            this.syncing = false;
            this.syncProcess = null;
        }
    }

    async refreshWorkspace() {
        try {
            const report = await this.sync(this.configuration());
            const committed = report.results.filter((result) => committedReceipt(result) || questionReceipt(result));
            const unconfirmed = report.results.length - committed.length;
            const receiptErrors = committed.some((result) => result.receipt_written === false);
            let message = report.projection.status === "complete" ? "Cairntir workspace refreshed." : "Cairntir workspace refresh failed.";
            const corrections = committed.filter(result => committedReceipt(result)).length;
            if (corrections) message += " " + corrections + " correction(s) saved.";
            if (committed.length > corrections) message += " " + (committed.length - corrections) + " question request(s) saved.";
            if (unconfirmed) message += " " + unconfirmed + " request(s) unconfirmed or rejected; review the sync report and retry.";
            if (receiptErrors) message += " Receipt writing failed; requests retained. Retry refresh.";
            if (report.projection.status === "error") message += " " + explain(report.projection.error) + " Retry refresh.";
            new Notice(message);
            return report;
        } catch (error) {
            new Notice(error.message);
            return null;
        }
    }

    async readEntry(note, config) {
        let manifest;
        try {
            manifest = JSON.parse(await this.app.vault.adapter.read(WORKSPACE));
        } catch {
            throw new Error("Cannot read the Cairntir workspace manifest. Run Refresh workspace first.");
        }
        if (!manifest || manifest.schema !== "cairntir.obsidian-workspace.v1" ||
            manifest.wing !== config.wing || !Array.isArray(manifest.drawers)) {
            throw new Error("The workspace does not match the configured wing. Run Refresh workspace first.");
        }
        const matches = manifest.drawers.filter((entry) => entry && entry.note === note);
        const entry = matches.length === 1 ? matches[0] : null;
        if (!entry || entry.current !== true || entry.editable !== true ||
            entry.wing !== config.wing || !Number.isSafeInteger(entry.drawer_id) || entry.drawer_id <= 0 ||
            typeof entry.source_identity !== "string" || !UUID.test(entry.source_identity) ||
            typeof entry.content !== "string" || typeof entry.content_sha256 !== "string" ||
            !/^[0-9a-f]{64}$/.test(entry.content_sha256) ||
            createHash("sha256").update(entry.content, "utf8").digest("hex") !== entry.content_sha256) {
            throw new Error("Select one current, editable Cairntir memory in this wing. Refresh the workspace if it is stale.");
        }
        return entry;
    }

    async proposeCorrection() {
        try {
            const config = this.configuration();
            const file = this.app.workspace.getActiveFile();
            if (!file) throw new Error("Open a current Cairntir memory before proposing a correction.");
            const entry = await this.readEntry(file.path, config);
            if (this.activeModal) this.activeModal.close();
            this.activeModal = new CorrectionModal(this, entry, config);
            this.activeModal.open();
        } catch (error) {
            new Notice(error.message);
        }
    }

    async queueCorrection(entry, content, config) {
        const id = randomUUID();
        const file = OUTBOX + "/" + id + ".json";
        const request = {
            schema: "cairntir.obsidian-correction.v1",
            request_id: id,
            wing: config.wing,
            source_drawer_id: entry.drawer_id,
            source_identity: entry.source_identity,
            source_sha256: entry.content_sha256,
            content
        };
        try {
            if (!await this.app.vault.adapter.exists(OUTBOX)) await this.app.vault.createFolder(OUTBOX);
            await this.app.vault.create(file, JSON.stringify(request, null, 2) + "\n");
        } catch {
            throw new Error("Could not queue the correction. Check vault permissions and retry; the original memory is unchanged.");
        }
        return { id, file, request };
    }

    onunload() {
        if (this.activeModal) this.activeModal.close();
        if (this.syncProcess) this.syncProcess.kill();
    }
};
