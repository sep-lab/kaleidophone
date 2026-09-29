// Load canvas/lib plain scripts into a node vm context, the way the browser sees them:
// one shared global scope, files concatenated in order. Only DOM-free files can be loaded.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

export const CANVAS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export function loadLib(names, extra = '') {
  const code = names.map(n => fs.readFileSync(path.join(CANVAS, 'lib', `${n}.js`), 'utf8')).join('\n') + '\n' + extra;
  const ctx = vm.createContext({ Math, console });
  // top-level const/let/function declarations of a script are not properties of the context;
  // re-export the names the tests need through one object
  vm.runInContext(code + '\n;globalThis.__lib = { ' + EXPORTS.join(', ') + ' };', ctx);
  return ctx.__lib;
}
const EXPORTS = ['TAU', 'clamp', 'lerp', 'ease', 'easeOut', 'step', 'smooth', 'pulse', 'kf', 'hsh', 'HS', 'hash', 'mulberry32',
  'makeGrid', 'ENV', 'envInit', 'envAt', 'envAvg', 'strokeScale', 'remap', 'fract', 'rad'];
export function loadLibWith(names, exports) {
  const code = names.map(n => fs.readFileSync(path.join(CANVAS, 'lib', `${n}.js`), 'utf8')).join('\n');
  const ctx = vm.createContext({ Math, console });
  vm.runInContext(code + '\n;globalThis.__lib = { ' + exports.join(', ') + ' };', ctx);
  return ctx.__lib;
}
