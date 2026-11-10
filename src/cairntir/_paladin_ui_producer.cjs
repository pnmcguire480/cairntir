'use strict';

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const {pathToFileURL} = require('node:url');
const VERSION = '1';
const DEADLINE = Date.now() + 90000;
const ORIGIN = 'https://cairntir.invalid';
const RAW_CAP = 2097152;
const PNG_CAP = 8388608;

function need(value, message) {
    if (!value) throw new Error(message);
}
function remaining() {
    const value = DEADLINE - Date.now();
    need(value > 0, 'Producer work deadline exceeded');
    return value;
}
function canonical(value) {
    function normalize(item) {
        if (Array.isArray(item)) return item.map(normalize);
        if (item && typeof item === 'object') {
            const result = Object.create(null);
            for (const key of Object.keys(item).sort()) result[key] = normalize(item[key]);
            return result;
        }
        if (typeof item === 'number') need(Number.isFinite(item), 'Nonfinite JSON');
        return item;
    }
    return Buffer.from(JSON.stringify(normalize(value)), 'utf8');
}
function digest(bytes) {
    return crypto.createHash('sha256').update(bytes).digest('hex');
}
function exact(value, keys) {
    need(value !== null && typeof value === 'object' && !Array.isArray(value)
        && Object.keys(value).sort().join('\0') === [...keys].sort().join('\0'), 'Unexpected object fields');
    return value;
}
function safe(input) {
    need(typeof input === 'string' && path.isAbsolute(input) && !input.includes('\0'), 'Absolute path required');
    const result = path.resolve(input);
    for (let parent = result; ; parent = path.dirname(parent)) {
        try {
            need(!fs.lstatSync(parent).isSymbolicLink(), 'Reparse path refused');
        } catch (error) {
            if (error.code !== 'ENOENT') throw error;
        }
        if (path.dirname(parent) === parent) break;
    }
    return result;
}
function relative(input) {
    need(typeof input === 'string' && input.length > 0 && input.length <= 512
        && !/[\\:\r\n\0]/.test(input) && !path.posix.isAbsolute(input)
        && input.split('/').every(part => part && part !== '.' && part !== '..'), 'Unsafe relative path');
    return input;
}
function contained(root, child) {
    const result = safe(path.join(root, relative(child)));
    const rest = path.relative(safe(root), result);
    need(rest && !rest.startsWith('..' + path.sep) && rest !== '..' && !path.isAbsolute(rest), 'Path escaped');
    return result;
}
function readBytes(file, maximum) {
    remaining();
    const target = safe(file);
    const size = fs.statSync(target).size;
    need(fs.statSync(target).isFile() && size <= maximum, 'File byte cap exceeded');
    const data = fs.readFileSync(target);
    need(data.length === size && data.length <= maximum, 'Input changed while reading');
    return data;
}
function hashFile(file, maximum = 2147483648) {
    const target = safe(file);
    const size = fs.statSync(target).size;
    need(fs.statSync(target).isFile() && size <= maximum, 'File byte cap exceeded');
    const fd = fs.openSync(target, 'r');
    const hash = crypto.createHash('sha256');
    const buffer = Buffer.alloc(65536);
    let total = 0;
    try {
        for (;;) {
            remaining();
            const count = fs.readSync(fd, buffer, 0, buffer.length, null);
            if (!count) break;
            total += count;
            need(total <= size, 'Input grew while hashing');
            hash.update(buffer.subarray(0, count));
        }
    } finally {
        fs.closeSync(fd);
    }
    need(total === size && fs.statSync(target).size === size, 'Input changed while hashing');
    return {sha256: hash.digest('hex'), bytes: size};
}
function verify(file, row, maximum = 2147483648) {
    const observed = hashFile(file, maximum);
    need(observed.sha256 === row.sha256 && observed.bytes === row.bytes, 'Pinned file changed: ' + file);
    return observed;
}
function parseJSON(data) {
    const text = new TextDecoder('utf-8', {fatal: true}).decode(data);
    let at = 0;
    function whitespace() {
        while (/[ \t\r\n]/.test(text[at] || '') && at < text.length) at++;
    }
    function string() {
        need(text[at] === '"', 'JSON string required');
        const start = at++;
        while (at < text.length) {
            const char = text[at++];
            if (char === '"') return JSON.parse(text.slice(start, at));
            if (char === '\\') at++;
        }
        throw new Error('Unterminated JSON string');
    }
    function value(depth) {
        need(depth <= 64, 'JSON depth cap exceeded');
        whitespace();
        if (text[at] === '"') return string();
        if (text[at] === '{') {
            at++;
            const result = Object.create(null);
            whitespace();
            if (text[at] === '}') {at++; return result;}
            for (;;) {
                whitespace();
                const key = string();
                need(!Object.hasOwn(result, key), 'Duplicate JSON key');
                whitespace();
                need(text[at++] === ':', 'Invalid JSON object');
                result[key] = value(depth + 1);
                whitespace();
                const end = text[at++];
                if (end === '}') return result;
                need(end === ',', 'Invalid JSON object separator');
            }
        }
        if (text[at] === '[') {
            at++;
            const result = [];
            whitespace();
            if (text[at] === ']') {at++; return result;}
            for (;;) {
                result.push(value(depth + 1));
                whitespace();
                const end = text[at++];
                if (end === ']') return result;
                need(end === ',', 'Invalid JSON array separator');
            }
        }
        for (const [token, result] of [['true', true], ['false', false], ['null', null]]) {
            if (text.startsWith(token, at)) {at += token.length; return result;}
        }
        const match = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(text.slice(at));
        need(match, 'Invalid JSON value');
        at += match[0].length;
        const result = Number(match[0]);
        need(Number.isFinite(result), 'Nonfinite JSON');
        return result;
    }
    const result = value(0);
    whitespace();
    need(at === text.length, 'Trailing JSON bytes');
    return result;
}
function json(file, maximum = RAW_CAP) {
    return parseJSON(readBytes(file, maximum));
}
function writeJSON(file, value, maximum = RAW_CAP) {
    remaining();
    const data = canonical(value);
    need(data.length <= maximum, 'JSON output cap exceeded');
    fs.writeFileSync(file, data, {flag: 'wx'});
}
function artifact(root, file) {
    return {path: path.relative(root, file).split(path.sep).join('/'), ...hashFile(file, 134217728)};
}
function inventory(root, maximumFiles, maximumBytes) {
    const result = [];
    const pending = [safe(root)];
    let total = 0, directories = 0;
    while (pending.length) {
        remaining();
        const directory = pending.pop();
        need(++directories <= 8192, 'Directory count cap exceeded');
        for (const entry of fs.readdirSync(directory, {withFileTypes: true})) {
            const file = safe(path.join(directory, entry.name));
            need(!entry.isSymbolicLink(), 'Symlink refused');
            if (entry.isDirectory()) pending.push(file);
            else {
                need(entry.isFile(), 'Nonregular file refused');
                const row = artifact(root, file);
                total += row.bytes;
                result.push(row);
                need(result.length <= maximumFiles && total <= maximumBytes, 'Inventory cap exceeded');
            }
        }
    }
    result.sort((left, right) => left.path < right.path ? -1 : left.path > right.path ? 1 : 0);
    need(new Set(result.map(row => row.path.toLowerCase())).size === result.length, 'Path alias');
    return result;
}
function toolsFor(template) {
    exact(template.selected_tools, ['path', 'sha256', 'bytes']);
    verify(template.selected_tools.path, template.selected_tools, RAW_CAP);
    const manifest = exact(json(template.selected_tools.path), ['schema', 'tools', 'packaged_chromium_version']);
    need(manifest.schema === 'cairntir.paladin-ui-tools.v1' && manifest.packaged_chromium_version === '151.0.7922.34', 'Wrong tools schema');
    need(Array.isArray(manifest.tools) && manifest.tools.length === 9, 'Wrong tools count');
    const tools = Object.create(null);
    let count = 0, total = 0;
    for (const tool of manifest.tools) {
        exact(tool, ['id', 'root', 'entry_path', 'version', 'files']);
        need(!Object.hasOwn(tools, tool.id), 'Duplicate tool');
        need(Array.isArray(tool.files) && tool.files.length > 0, 'Empty selected tool');
        const names = tool.files.map(row => relative(exact(row, ['path', 'sha256', 'bytes']).path));
        need(JSON.stringify(names) === JSON.stringify([...names].sort()) && new Set(names.map(name => name.toLowerCase())).size === names.length, 'Tool order/alias differs');
        for (const row of tool.files) {
            count++;
            total += row.bytes;
            need(count <= 4096 && total <= 2147483648, 'Selected tool cap exceeded');
            verify(contained(tool.root, row.path), row);
        }
        need(names.includes(tool.entry_path), 'Tool entry absent');
        tool.entry = contained(tool.root, tool.entry_path);
        tools[tool.id] = tool;
    }
    need(Object.keys(tools).sort().join(',') === ['python', 'node', 'playwright', 'playwright-core', 'chrome', 'pngjs', 'pixelmatch', 'worker', 'producer'].sort().join(','), 'Tool identities differ');
    need(safe(process.execPath) === tools.node.entry && safe(__filename) === tools.producer.entry && tools.producer.version === VERSION, 'Wrong Node/producer origin');
    return {tools, manifest};
}
function verifyProject(template) {
    const project = template.project;
    exact(project, ['project_id', 'route_id', 'state_id', 'source_revision', 'snapshot_root', 'snapshot_sha256', 'files', 'entry_path']);
    const observed = inventory(project.snapshot_root, 128, 8388608);
    const expected = project.files.map(({path, sha256, bytes}) => ({path, sha256, bytes}));
    need(canonical(observed).equals(canonical(expected)) && digest(canonical(project.files)) === project.snapshot_sha256, 'Project snapshot differs');
    need(project.files.some(row => row.path === project.entry_path && row.media_type === 'text/html'), 'HTML entry absent');
    const font = template.render_policy.font;
    need(hashFile(contained(project.snapshot_root, font.path), 8388608).sha256 === font.sha256 && hashFile(contained(project.snapshot_root, font.license_path), 8388608).sha256 === font.license_sha256, 'Font payload differs');
}
function toolObservation(tool, version) {
    need(version === tool.version, 'Actual version differs: ' + tool.id);
    return {id: tool.id, entry_path: tool.entry, entry_sha256: hashFile(tool.entry).sha256, version};
}
function payloadHash(tool) {
    return digest(canonical(tool.files));
}
function selectorSet(template) {
    const selectors = new Set();
    for (const check of template.checks) {
        for (const key of ['selector', 'start_selector', 'control', 'panel']) if (check[key]) selectors.add(check[key]);
        for (const key of ['selectors', 'expected_focus']) if (check[key]) for (const value of check[key]) selectors.add(value);
    }
    for (const selector of template.render_policy.font.text_selectors) selectors.add(selector);
    need(selectors.size <= 32, 'Selector cap exceeded');
    return [...selectors];
}
function activeFunction() {
    return {tag_name: document.activeElement.tagName, id: document.activeElement.id};
}
function elementFunction() {
    const rect = this.getBoundingClientRect();
    const style = getComputedStyle(this);
    const opacity = Number(style.opacity);
    return {
        tag_name: this.tagName, id: this.id, text_content: (this.textContent || '').slice(0, 16385),
        rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
        visible: style.display !== 'none' && !['hidden', 'collapse'].includes(style.visibility)
            && opacity > 0 && rect.width > 0 && rect.height > 0,
        display: style.display, visibility: style.visibility, opacity, font_family: style.fontFamily,
    };
}
async function initialDOM(page, cdp, selectors, viewport) {
    await cdp.send('DOM.enable');
    await cdp.send('CSS.enable');
    await cdp.send('Accessibility.enable');
    const {root} = await cdp.send('DOM.getDocument', {depth: -1, pierce: false});
    const pending = [root];
    let count = 0;
    while (pending.length) {
        const node = pending.pop();
        need(++count <= 512, 'DOM node cap exceeded');
        pending.push(...(node.children || []), ...(node.shadowRoots || []));
        if (node.contentDocument) pending.push(node.contentDocument);
    }
    const document = await page.evaluate(() => ({
        language: document.documentElement.lang, title: document.title, url: location.href,
        ready_state: document.readyState, inner_width: innerWidth, inner_height: innerHeight,
        device_scale_factor: devicePixelRatio, scroll_width: document.documentElement.scrollWidth,
        client_width: document.documentElement.clientWidth,
        active_element: {tag_name: document.activeElement.tagName, id: document.activeElement.id},
    }));
    need(document.inner_width === viewport.width && document.inner_height === viewport.height
        && document.device_scale_factor === viewport.device_scale_factor && document.ready_state === 'complete',
        'Observed viewport/readiness differs');
    const rows = [];
    for (const selector of selectors) {
        remaining();
        const {nodeIds} = await cdp.send('DOM.querySelectorAll', {nodeId: root.nodeId, selector});
        need(nodeIds.length <= 512, 'DOM match cap exceeded');
        const matches = [];
        for (const nodeId of nodeIds) {
            const {node} = await cdp.send('DOM.describeNode', {nodeId});
            const {object} = await cdp.send('DOM.resolveNode', {nodeId, objectGroup: 'cairntir-ui'});
            const result = await cdp.send('Runtime.callFunctionOn', {
                objectId: object.objectId, functionDeclaration: elementFunction.toString(),
                returnByValue: true,
            });
            need(!result.exceptionDetails && result.result.value, 'DOM measurement unavailable');
            const observed = result.result.value;
            need(observed.text_content.length <= 16384 && observed.font_family.length <= 512
                && Number.isFinite(observed.opacity) && observed.opacity >= 0 && observed.opacity <= 1
                && Object.values(observed.rect).every(Number.isFinite), 'DOM measurement cap/type differs');
            matches.push({node_id: nodeId, backend_node_id: node.backendNodeId, ...observed});
        }
        rows.push({selector, count: nodeIds.length, matches});
    }
    const {nodes} = await cdp.send('Accessibility.getFullAXTree');
    need(Array.isArray(nodes) && nodes.length > 0 && nodes.length <= 1024
        && new Set(nodes.map(node => node.nodeId)).size === nodes.length, 'AX tree unavailable/oversized');
    const mappings = rows.map(row => {
        const backend = row.matches.map(match => match.backend_node_id);
        return {
            selector: row.selector, node_ids: row.matches.map(match => match.node_id),
            backend_node_ids: backend,
            ax_node_ids: nodes.filter(node => backend.includes(node.backendDOMNodeId)).map(node => node.nodeId),
        };
    });
    return {
        dom: {schema: 'cairntir.paladin-ui-dom.v1', viewport_id: viewport.id, document, selectors: rows},
        ax: {schema: 'cairntir.paladin-ui-ax.v1', viewport_id: viewport.id, nodes, selector_mappings: mappings},
    };
}
async function actualFonts(page, cdp, dom, font, viewport) {
    const readiness = await page.evaluate(async family => {
        await document.fonts.ready;
        const clean = value => value.replace(/^['"]|['"]$/g, '');
        return {
            ready: document.fonts.status === 'loaded',
            loaded: [...document.fonts].some(face => clean(face.family) === family && face.status === 'loaded'),
        };
    }, font.css_family);
    need(readiness.ready && readiness.loaded, 'Declared FontFace is not loaded');
    const observations = [];
    for (const selector of font.text_selectors) {
        const row = dom.selectors.find(item => item.selector === selector);
        need(row && row.count === 1 && row.matches[0].visible, 'Declared text node unavailable');
        const element = row.matches[0];
        const result = await cdp.send('CSS.getPlatformFontsForNode', {nodeId: element.node_id});
        need(Array.isArray(result.fonts) && result.fonts.length <= 16, 'Platform font evidence unavailable');
        const fonts = result.fonts.map(value => ({
            family_name: value.familyName, postscript_name: value.postScriptName,
            is_custom_font: value.isCustomFont, glyph_count: value.glyphCount,
        }));
        need(fonts.every(value => typeof value.family_name === 'string' && value.family_name
            && typeof value.postscript_name === 'string' && value.postscript_name
            && typeof value.is_custom_font === 'boolean' && Number.isInteger(value.glyph_count)
            && value.glyph_count >= 0), 'Platform font evidence unsupported');
        const positive = fonts.filter(value => value.glyph_count > 0);
        need(positive.length && positive.every(value => value.is_custom_font
            && value.family_name === font.platform_family && value.postscript_name === font.postscript_name),
            'Actual rendered font fallback or identity mismatch');
        const cssFamilies = element.font_family.split(',').map(value => value.trim().replace(/^['"]|['"]$/g, ''));
        need(cssFamilies.includes(font.css_family), 'Computed CSS font differs');
        observations.push({
            selector, backend_node_id: element.backend_node_id, document_fonts_ready: readiness.ready,
            font_face_loaded: readiness.loaded, computed_family: element.font_family, fonts,
        });
    }
    return {
        schema: 'cairntir.paladin-ui-fonts.v1', viewport_id: viewport.id,
        font_path: font.path, font_sha256: font.sha256, license_sha256: font.license_sha256,
        css_family: font.css_family, platform_family: font.platform_family,
        postscript_name: font.postscript_name, observations,
    };
}
function decodePNG(data, viewport, PNG) {
    need(data.length <= PNG_CAP && data.length >= 33
        && data.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
        && data.toString('ascii', 12, 16) === 'IHDR', 'Invalid PNG header');
    const width = data.readUInt32BE(16), height = data.readUInt32BE(20);
    need(width === viewport.width && height === viewport.height && width * height <= 1024000,
        'PNG dimensions differ before decode');
    const decoded = PNG.sync.read(data, {checkCRC: true});
    need(decoded.width === width && decoded.height === height && decoded.data.length === width * height * 4,
        'Decoded PNG dimensions differ');
    return decoded;
}
function visualObservation(template, viewport, directory, root, modules, baseline, currentData) {
    const {PNG, pixelmatch} = modules;
    const current = decodePNG(currentData, viewport, PNG);
    const currentRef = artifact(root, path.join(directory, 'current.png'));
    if (template.mode === 'capture-baseline') {
        return {current: currentRef, baseline: null, diff: null, width: viewport.width, height: viewport.height,
            compared_pixels: 0, mismatched_pixels: null, exact_changed_pixels: null,
            allowed_diff_pixels: null, diff_ratio: null};
    }
    const row = baseline.images.find(value => value.viewport_id === viewport.id);
    need(row && row.width === viewport.width && row.height === viewport.height
        && row.device_scale_factor === viewport.device_scale_factor, 'Approved image scope differs');
    exact(row.png, ['path', 'sha256', 'bytes']);
    verify(row.png.path, row.png, PNG_CAP);
    const baselineData = readBytes(row.png.path, PNG_CAP);
    const previous = decodePNG(baselineData, viewport, PNG);
    const baselinePath = path.join(directory, 'baseline.png');
    fs.writeFileSync(baselinePath, baselineData, {flag: 'wx'});
    const policy = template.checks.find(check => check.kind === 'rgba-diff');
    const options = Object.fromEntries(['threshold', 'includeAA', 'alpha', 'aaColor', 'diffColor', 'diffColorAlt', 'diffMask', 'checkerboard'].map(key => [key, policy[key]]));
    const diff = new PNG({width: viewport.width, height: viewport.height});
    const count = pixelmatch(previous.data, current.data, diff.data, viewport.width, viewport.height, options);
    let exactCount = 0;
    for (let at = 0; at < current.data.length; at += 4) {
        if ([0, 1, 2, 3].some(offset => previous.data[at + offset] !== current.data[at + offset])) exactCount++;
    }
    const diffData = PNG.sync.write(diff);
    need(diffData.length <= PNG_CAP, 'Diff PNG cap exceeded');
    fs.writeFileSync(path.join(directory, 'diff.png'), diffData, {flag: 'wx'});
    const total = viewport.width * viewport.height;
    const result = {
        current: currentRef, baseline: artifact(root, baselinePath),
        diff: artifact(root, path.join(directory, 'diff.png')), width: viewport.width, height: viewport.height,
        compared_pixels: total, mismatched_pixels: count, exact_changed_pixels: exactCount,
        allowed_diff_pixels: Math.floor(total * policy.allowed_diff_ratio), diff_ratio: count / total,
    };
    writeJSON(path.join(directory, 'comparison.json'), result);
    return result;
}
async function checkResult(check, state) {
    const {page, dom, ax, visual, paths, viewport} = state;
    let observation, pass, evidence;
    switch (check.kind) {
    case 'document-equals':
        observation = {value: dom.document[check.property]};
        pass = observation.value === check.expected;
        evidence = [paths.dom];
        break;
    case 'ax-role-name': {
        const selected = dom.selectors.find(row => row.selector === check.selector);
        const backend = selected.count === 1 ? selected.matches[0].backend_node_id : null;
        const nodes = selected.count === 1 ? ax.nodes.filter(value => value.backendDOMNodeId === backend) : [];
        need(selected.count !== 1 || nodes.length === 1, 'Native AX binding unavailable or ambiguous');
        const node = nodes[0] || null;
        observation = {
            selector_count: selected.count, backend_node_id: backend,
            ax_node_id: node ? node.nodeId : null, ignored: node ? node.ignored : null,
            role: node && node.role ? node.role.value : null,
            name: node && node.name ? node.name.value : null,
        };
        pass = observation.selector_count === 1 && observation.ignored === false
            && observation.role === check.role && observation.name === check.name;
        evidence = [paths.dom, paths.ax];
        break;
    }
    case 'keyboard-tab-order': {
        const initial = await page.evaluate(activeFunction);
        const startMatches = await page.evaluate(selector => document.activeElement.matches(selector), check.start_selector);
        const steps = [];
        for (const selector of check.expected_focus) {
            remaining();
            await page.keyboard.press('Tab');
            const actual = await page.evaluate(activeFunction);
            const matches = await page.evaluate(value => document.activeElement.matches(value), selector);
            steps.push({key: 'Tab', actual, expected_selector_matches: matches});
            state.events.push({ordinal: state.events.length + 1, check_id: check.id, key: 'Tab', active_element: actual});
        }
        observation = {initial, start_matches: startMatches, steps};
        pass = startMatches && steps.every(step => step.expected_selector_matches);
        evidence = [paths.keyboard];
        break;
    }
    case 'keyboard-key-state':
        await page.keyboard.press(check.key);
        observation = await page.evaluate(({control, panel}) => {
            const controls = [...document.querySelectorAll(control)], panels = [...document.querySelectorAll(panel)];
            const target = panels.length === 1 ? panels[0] : null;
            const rect = target ? target.getBoundingClientRect() : null;
            const style = target ? getComputedStyle(target) : null;
            return {
                actual_focus: {tag_name: document.activeElement.tagName, id: document.activeElement.id},
                control_focused: controls.length === 1 && document.activeElement === controls[0],
                control_count: controls.length, panel_count: panels.length,
                expanded: controls.length === 1 ? controls[0].getAttribute('aria-expanded') : null,
                panel_visible: !!(style && style.display !== 'none' && !['hidden', 'collapse'].includes(style.visibility)
                    && Number(style.opacity) > 0 && rect.width > 0 && rect.height > 0),
            };
        }, {control: check.control, panel: check.panel});
        state.events.push({ordinal: state.events.length + 1, check_id: check.id, key: check.key, active_element: observation.actual_focus});
        pass = observation.control_count === 1 && observation.panel_count === 1
            && observation.control_focused && observation.expanded === String(check.expanded)
            && observation.panel_visible === check.visible;
        evidence = [paths.keyboard];
        break;
    case 'required-visible':
        observation = {elements: check.selectors.map(selector => {
            const selected = dom.selectors.find(row => row.selector === selector);
            const match = selected.count === 1 ? selected.matches[0] : null;
            const rect = match ? match.rect : null, tolerance = check.tolerance_css_pixels;
            const within = !!(rect && rect.width > 0 && rect.height > 0 && rect.x >= -tolerance
                && rect.y >= -tolerance && rect.x + rect.width <= viewport.width + tolerance
                && rect.y + rect.height <= viewport.height + tolerance);
            return {selector, count: selected.count, rect, visible: !!(match && match.visible), within_viewport: within};
        })};
        pass = observation.elements.every(row => row.count === 1 && row.visible && row.within_viewport);
        evidence = [paths.dom];
        break;
    case 'horizontal-overflow':
        observation = {
            scroll_width: dom.document.scroll_width, client_width: dom.document.client_width,
            viewport_width: dom.document.inner_width,
            overflow_css_pixels: Math.max(0, dom.document.scroll_width - dom.document.client_width),
        };
        pass = observation.overflow_css_pixels <= check.maximum_css_pixels;
        evidence = [paths.dom];
        break;
    case 'rgba-diff':
        observation = visual;
        if (visual.baseline === null) return {check, status: 'UNREVIEWED', observation, evidence_paths: [visual.current.path], diagnostic: null};
        pass = visual.mismatched_pixels <= visual.allowed_diff_pixels;
        evidence = [paths.comparison];
        break;
    default:
        throw new Error('Unsupported machine check kind');
    }
    return {check, status: pass ? 'PASS' : 'FAIL', observation, evidence_paths: evidence, diagnostic: null};
}
async function main() {
    need(process.argv.length === 4 && process.argv[2] === '--request', 'Fixed --request invocation required');
    const requestPath = safe(process.argv[3]);
    const requestBytes = readBytes(requestPath, 262144);
    const request = exact(parseJSON(requestBytes), ['schema', 'run_id', 'attempt_id', 'action_id', 'contract_sha256', 'template_sha256', 'template']);
    need(request.schema === 'cairntir.paladin-ui-producer.v1', 'Wrong request schema');
    const template = exact(request.template, ['schema', 'mode', 'project', 'output_root', 'selected_tools', 'render_policy', 'checks', 'baseline_reference']);
    need(template.schema === 'cairntir.paladin-ui-producer-template.v1'
        && ['capture-baseline', 'compare'].includes(template.mode)
        && digest(canonical(template)) === request.template_sha256, 'Wrong prepared template');
    const root = safe(template.output_root);
    need(requestPath === path.join(root, 'request.json'), 'Wrong request path');
    const {tools, manifest} = toolsFor(template);
    verifyProject(template);
    const packageVersion = tool => {
        const selected = tool.files.find(row => row.path === 'package.json');
        need(selected, 'Package metadata not selected');
        const metadataPath = contained(tool.root, 'package.json');
        verify(metadataPath, selected, RAW_CAP);
        return json(metadataPath).version;
    };
    const playwright = require(tools.playwright.entry);
    require(tools['playwright-core'].entry);
    const {PNG} = require(tools.pngjs.entry);
    const pixelmatch = (await import(pathToFileURL(tools.pixelmatch.entry).href)).default;
    need(typeof pixelmatch === 'function' && typeof playwright.chromium.launch === 'function', 'Selected libraries unsupported');
    const coreBrowsersPath = contained(tools['playwright-core'].root, 'browsers.json');
    need(tools['playwright-core'].files.some(row => row.path === 'browsers.json'), 'Packaged browser metadata not selected');
    const packaged = json(coreBrowsersPath).browsers.find(row => row.name === 'chromium');
    need(packaged && packaged.browserVersion === manifest.packaged_chromium_version, 'Packaged browser version differs');
    const versions = {
        node: process.versions.node, playwright: packageVersion(tools.playwright),
        'playwright-core': packageVersion(tools['playwright-core']),
        pngjs: packageVersion(tools.pngjs), pixelmatch: packageVersion(tools.pixelmatch),
    };
    for (const key of Object.keys(versions)) need(versions[key] === tools[key].version, 'Selected library version differs');
    const visualChecks = template.checks.filter(check => check.kind === 'rgba-diff');
    need(visualChecks.length === 1, 'Exactly one visual metric is required');
    const visualPolicy = Object.fromEntries(Object.entries(visualChecks[0]).filter(([key]) => !['id', 'family', 'kind'].includes(key)));
    const policySHA = digest(canonical({render_policy: template.render_policy, visual_policy: visualPolicy}));
    let baseline = null;
    if (template.mode === 'compare') {
        const reference = template.baseline_reference;
        need(reference && reference.manifest_file.sha256 === reference.revision_sha256, 'Approved reference absent');
        verify(reference.manifest_file.path, reference.manifest_file, RAW_CAP);
        baseline = exact(json(reference.manifest_file.path), ['schema', 'scope', 'generation', 'previous_revision_sha256', 'candidate_id', 'candidate_manifest_sha256', 'baseline_origin', 'images']);
        need(baseline.schema === 'cairntir.paladin-ui-approved-baseline.v1'
            && digest(canonical(baseline)) === reference.revision_sha256
            && baseline.generation === reference.generation
            && baseline.scope.baseline_id === reference.baseline_id
            && baseline.scope.project_id === template.project.project_id
            && baseline.scope.route_id === template.project.route_id
            && baseline.scope.state_id === template.project.state_id
            && baseline.scope.policy_sha256 === policySHA
            && canonical(baseline.scope.viewports).equals(canonical(template.render_policy.viewports))
            && baseline.baseline_origin.source.snapshot_sha256 === reference.baseline_origin_snapshot_sha256,
            'Approved baseline scope differs');
    } else need(template.baseline_reference === null, 'Capture cannot self-approve');
    const output = path.join(root, 'producer');
    fs.mkdirSync(output);
    fs.mkdirSync(path.join(output, 'raw'));
    const selectors = selectorSet(template);
    const network = {schema: 'cairntir.paladin-ui-network.v1', events: []};
    const networkErrors = [];
    const inflight = new Set();
    const projectFiles = new Map(template.project.files.map(row => [ORIGIN + '/' + row.path, row]));
    let browser = null, disconnected = false, browserClosed = false, contextsClosed = true, renderer = null;
    const viewportRows = [];
    try {
        browser = await playwright.chromium.launch({
            executablePath: tools.chrome.entry, headless: true, timeout: remaining(),
            args: ['--no-first-run', '--disable-background-networking', '--disable-component-update',
                '--disable-default-apps', '--disable-sync', '--metrics-recording-only', '--no-default-browser-check'],
        });
        browser.on('disconnected', () => {disconnected = true;});
        versions.chrome = browser.version();
        need(versions.chrome === tools.chrome.version, 'Actual browser version differs');
        for (const viewport of template.render_policy.viewports) {
            remaining();
            contextsClosed = false;
            const context = await browser.newContext({
                viewport: {width: viewport.width, height: viewport.height},
                deviceScaleFactor: viewport.device_scale_factor, locale: template.render_policy.locale,
                timezoneId: template.render_policy.timezone_id, colorScheme: template.render_policy.color_scheme,
                reducedMotion: template.render_policy.reduced_motion, serviceWorkers: 'block', acceptDownloads: false,
            });
            let contextClosed = false;
            context.on('close', () => {contextClosed = true;});
            const serve = async route => {
                const req = route.request();
                const selected = projectFiles.get(req.url());
                const allowed = req.method() === 'GET' && !!selected;
                need(network.events.length < 256 && req.url().length <= 2048, 'Network event cap exceeded');
                network.events.push({
                    ordinal: network.events.length + 1, viewport_id: viewport.id, url: req.url(),
                    method: req.method(), resource_type: req.resourceType(),
                    decision: allowed ? 'fulfilled' : 'blocked',
                    project_path: allowed ? selected.path : null, sha256: allowed ? selected.sha256 : null,
                });
                if (!allowed) {
                    networkErrors.push('Unsupported network request: ' + req.url());
                    await route.abort('blockedbyclient');
                    return;
                }
                const file = contained(template.project.snapshot_root, selected.path);
                verify(file, selected, 8388608);
                await route.fulfill({status: 200, contentType: selected.media_type,
                    headers: {'cache-control': 'no-store'}, body: readBytes(file, 8388608)});
            };
            await context.route('**/*', route => {
                const task = serve(route).catch(error => {networkErrors.push(String(error));});
                inflight.add(task);
                task.finally(() => {inflight.delete(task);});
                return task;
            });
            await context.routeWebSocket('**/*', socket => {
                networkErrors.push('Unsupported WebSocket request');
                socket.close();
            });
            try {
                const page = await context.newPage();
                page.setDefaultTimeout(Math.min(30000, remaining()));
                page.setDefaultNavigationTimeout(remaining());
                await page.goto(ORIGIN + '/' + template.project.entry_path, {waitUntil: 'networkidle', timeout: remaining()});
                await page.evaluate(async () => {await document.fonts.ready;});
                const cdp = await context.newCDPSession(page);
                const {dom, ax} = await initialDOM(page, cdp, selectors, viewport);
                const font = template.render_policy.font;
                const fonts = await actualFonts(page, cdp, dom, font, viewport);
                need(network.events.some(row => row.project_path === font.path && row.decision === 'fulfilled'), 'Font request not measured');
                const actualFont = fonts.observations[0].fonts.find(row => row.glyph_count > 0);
                const actualRenderer = {
                    browser: {runtime_manifest_sha256: payloadHash(tools.chrome), version: versions.chrome},
                    os: {platform: os.platform(), release: os.release(), arch: os.arch()},
                    font: {file_sha256: font.sha256, custom_family: actualFont.family_name, postscript_name: actualFont.postscript_name},
                    pngjs: {payload_sha256: payloadHash(tools.pngjs), version: versions.pngjs},
                    pixelmatch: {payload_sha256: payloadHash(tools.pixelmatch), version: versions.pixelmatch},
                    policy_sha256: policySHA,
                };
                if (renderer) need(canonical(renderer).equals(canonical(actualRenderer)), 'Renderer changed between viewports');
                renderer = actualRenderer;
                if (baseline) need(baseline.scope.renderer_sha256 === digest(canonical(renderer)), 'Approved renderer is incompatible');
                const directory = path.join(output, 'raw', viewport.id);
                fs.mkdirSync(directory);
                const prefix = 'producer/raw/' + viewport.id + '/';
                const paths = Object.fromEntries(['dom', 'ax', 'fonts', 'keyboard', 'comparison'].map(key => [key, prefix + key + '.json']));
                writeJSON(path.join(directory, 'dom.json'), dom);
                writeJSON(path.join(directory, 'ax.json'), ax);
                writeJSON(path.join(directory, 'fonts.json'), fonts);
                const currentData = await page.screenshot({
                    type: 'png', fullPage: false, animations: 'disabled', caret: 'hide', timeout: remaining(),
                });
                decodePNG(currentData, viewport, PNG);
                fs.writeFileSync(path.join(directory, 'current.png'), currentData, {flag: 'wx'});
                const visual = visualObservation(template, viewport, directory, root, {PNG, pixelmatch}, baseline, currentData);
                const state = {page, dom, ax, visual, paths, viewport, events: []};
                const checks = [];
                for (const check of template.checks) {
                    remaining();
                    checks.push(await checkResult(check, state));
                }
                const keyboardRows = checks.filter(row => row.check.kind.startsWith('keyboard-'));
                need(state.events.length <= 128 && keyboardRows.length > 0, 'Keyboard event cap/inventory differs');
                writeJSON(path.join(directory, 'keyboard.json'), {
                    schema: 'cairntir.paladin-ui-keyboard.v1', viewport_id: viewport.id,
                    initial_active_element: dom.document.active_element, events: state.events, results: keyboardRows,
                });
                await cdp.send('Runtime.releaseObjectGroup', {objectGroup: 'cairntir-ui'});
                viewportRows.push({
                    id: viewport.id, width: viewport.width, height: viewport.height,
                    device_scale_factor: viewport.device_scale_factor, checks,
                    font_observations: fonts.observations,
                });
            } finally {
                await context.close();
                need(contextClosed, 'Context close event not observed');
                contextsClosed = true;
            }
        }
    } finally {
        if (browser) {
            await browser.close();
            browserClosed = !browser.isConnected();
        }
    }
    await Promise.all(inflight);
    need(browserClosed && disconnected && contextsClosed && viewportRows.length === 2, 'Browser lifecycle incomplete');
    need(networkErrors.length === 0, 'Offline resource failure: ' + networkErrors.join('; '));
    toolsFor(template);
    verifyProject(template);
    const selectedPaths = new Set(Object.values(tools).flatMap(tool => tool.files.map(row => contained(tool.root, row.path).toLowerCase())));
    for (const filename of Object.keys(require.cache)) need(selectedPaths.has(safe(filename).toLowerCase()), 'Loaded module is outside selected tool files: ' + filename);
    writeJSON(path.join(output, 'network.json'), network);
    const families = {};
    for (const family of ['accessibility', 'responsive', 'visual']) {
        const rows = viewportRows.flatMap(viewport => viewport.checks.filter(row => row.check.family === family));
        need(rows.length > 0, 'Missing measurement family');
        families[family] = rows.some(row => ['ERROR', 'UNSUPPORTED'].includes(row.status)) ? 'INCONCLUSIVE'
            : rows.some(row => row.status === 'FAIL') ? 'FAIL'
            : rows.some(row => row.status === 'UNREVIEWED') ? 'UNREVIEWED' : 'PASS';
    }
    const rawArtifacts = inventory(output, 256, 134217728).map(row => ({...row, path: 'producer/' + row.path}));
    const report = {
        schema: 'cairntir.paladin-ui-producer-result.v1', status: 'COMPLETE',
        ...Object.fromEntries(['run_id', 'attempt_id', 'action_id', 'contract_sha256', 'template_sha256'].map(key => [key, request[key]])),
        request_sha256: digest(requestBytes), mode: template.mode, project_id: template.project.project_id,
        current_source_revision: template.project.source_revision, current_snapshot_sha256: template.project.snapshot_sha256,
        baseline_origin_snapshot_sha256: template.baseline_reference ? template.baseline_reference.baseline_origin_snapshot_sha256 : null,
        baseline_reference: template.baseline_reference, selected_tools_sha256: template.selected_tools.sha256,
        tool_observations: ['node', 'playwright', 'playwright-core', 'chrome', 'pngjs', 'pixelmatch'].map(key => toolObservation(tools[key], versions[key])),
        policy_sha256: policySHA, renderer, renderer_sha256: digest(canonical(renderer)),
        browser_lifecycle: {context_closed: contextsClosed, browser_closed: browserClosed, disconnected_observed: disconnected},
        viewports: viewportRows, families,
        diagnostics: ['Actual Chrome ' + versions.chrome + '; packaged expected Chromium ' + manifest.packaged_chromium_version],
        raw_artifacts: rawArtifacts,
    };
    writeJSON(path.join(output, 'ui-result.json'), report, 1048576);
}
const watchdog = setTimeout(() => {
    process.stderr.write('Producer work deadline exceeded\n');
    process.exit(124);
}, 90000);
main().then(() => {
    clearTimeout(watchdog);
}).catch(error => {
    clearTimeout(watchdog);
    process.stderr.write(String(error && error.stack ? error.stack : error).slice(0, 8192) + '\n');
    process.exitCode = 1;
});