# Q04 real-browser workflow

These cases run the actual Q04 worker (`src/cairntir/_paladin_ui_worker.py`)
and producer (`src/cairntir/_paladin_ui_producer.cjs`) against the frozen
fixtures in `tests/acceptance/paladin_ui_unit/fixtures`, in a real headless
Chromium. Results are checked with that packet's frozen, independently written
oracle (`require_variant`), unchanged.

The browser tools are not Cairntir dependencies. Prepare them once in a folder
outside the repository, then point `CAIRNTIR_Q04_TOOLS` at it:

```bash
mkdir q04-tools && cd q04-tools
printf '{"name":"cairntir-q04-tools","private":true}\n' > package.json
npm install --ignore-scripts --save-exact playwright@1.62.1 playwright-core@1.62.1 pngjs@7.0.0 pixelmatch@7.1.0
PLAYWRIGHT_BROWSERS_PATH="$PWD/browsers" node node_modules/playwright-core/cli.js install chromium
```

Playwright 1.62.1 packages Chromium 151.0.7922.34, the exact version the
worker and producer require. Node must be on `PATH`. Without
`CAIRNTIR_Q04_TOOLS` these cases skip with that reason; a skip is not a pass.
