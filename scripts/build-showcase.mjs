import { readFile, writeFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const pageUrl = new URL('index.html', root);
const cssUrl = new URL('assets/site.css', root);
const simulatorUrl = new URL('assets/simulator.mjs', root);
const appUrl = new URL('assets/app.mjs', root);

function replaceBlock(page, startMarker, endMarker, content) {
  const start = page.indexOf(startMarker);
  const end = page.indexOf(endMarker);
  if (start < 0 || end < start || page.indexOf(startMarker, start + 1) >= 0 || page.indexOf(endMarker, end + 1) >= 0) {
    throw new Error(`Expected one ordered ${startMarker} / ${endMarker} pair in index.html`);
  }
  return `${page.slice(0, start + startMarker.length)}\n${content}\n  ${page.slice(end)}`;
}

const [page, css, simulatorSource, appSource] = await Promise.all([
  readFile(pageUrl, 'utf8'),
  readFile(cssUrl, 'utf8'),
  readFile(simulatorUrl, 'utf8'),
  readFile(appUrl, 'utf8'),
]);

const exportLine = 'export function evaluateScenario(';
const importLine = "import { evaluateScenario } from './simulator.mjs';";
if (simulatorSource.split(exportLine).length !== 2 || !appSource.startsWith(importLine)) {
  throw new Error('The simulator module format changed; update the standalone bundle builder.');
}
if (/<\/style/i.test(css) || /<\/script/i.test(simulatorSource + appSource)) {
  throw new Error('Source contains an HTML closing tag that cannot be embedded directly.');
}

const simulator = simulatorSource.replace(exportLine, 'function evaluateScenario(').trimEnd();
const app = appSource.slice(importLine.length).trim();
const styles = `<style>\n${css.trimEnd()}\n</style>`;
const script = `<script>\n(() => {\n${simulator}\n\n${app}\n})();\n</script>`;
const withStyles = replaceBlock(page, '<!-- INLINE_STYLES_START -->', '<!-- INLINE_STYLES_END -->', styles);
const builtPage = replaceBlock(withStyles, '<!-- INLINE_SCRIPT_START -->', '<!-- INLINE_SCRIPT_END -->', script);

if (process.argv[2] === '--check') {
  if (builtPage !== page) {
    console.error('index.html is stale. Run: node scripts/build-showcase.mjs');
    process.exitCode = 1;
  } else {
    console.log('index.html contains the current standalone bundle.');
  }
} else if (process.argv.length === 2) {
  if (builtPage !== page) await writeFile(pageUrl, builtPage);
  console.log('Updated standalone index.html.');
} else {
  throw new Error('Usage: node scripts/build-showcase.mjs [--check]');
}
