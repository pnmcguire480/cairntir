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
            const committed = report.results.filter((result) => committedReceipt(result));
            const unconfirmed = report.results.length - committed.length;
            const receiptErrors = committed.some((result) => result.receipt_written === false);
            let message = report.projection.status === "complete" ? "Cairntir workspace refreshed." : "Cairntir workspace refresh failed.";
            if (committed.length) message += " " + committed.length + " correction(s) saved.";
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
