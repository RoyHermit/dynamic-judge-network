import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Script } from 'node:vm';

test('a downloaded index.html contains the styles and executable simulator script', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');

  assert.doesNotMatch(html, /<link\b[^>]*\brel=["']stylesheet["'][^>]*>/i);
  assert.doesNotMatch(html, /<script\b[^>]*\bsrc=/i);
  assert.match(html, /<style\b[^>]*>[\s\S]+<\/style>/i);

  const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)];
  assert.equal(scripts.length, 1);
  new Script(scripts[0][1]);
});
