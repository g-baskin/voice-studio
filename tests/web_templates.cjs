// Execute the shipped inline script with a minimal DOM; no browser install needed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const page = fs.readFileSync(path.join(__dirname, '../src/naturalvoice/web/index.html'), 'utf8');
const script =
  page.match(/<script>([\s\S]*?)<\/script>/)[1] +
  '\n' +
  fs.readFileSync(path.join(__dirname, '../src/naturalvoice/web/workflow.js'), 'utf8');
const presets = JSON.parse(process.argv[2]);
const keys = ['ai_clean', 'dereverb', 'demetal', 'deharsh', 'warmth', 'denoise', 'room_tone'];

async function boot(failSettings = false) {
  const nodes = new Map();
  function node(id) {
    if (!nodes.has(id))
      nodes.set(id, {
        value: '',
        disabled: false,
        textContent: '',
        files: [],
        style: {},
        dataset: {},
        selectedOptions: [{ textContent: 'Test template' }],
        append() {},
        replaceChildren() {},
        setAttribute() {},
        classList: { add() {}, remove() {}, toggle() {} },
        click() {
          this.clicked = true;
        },
        set innerHTML(html) {
          this.html = html;
          for (const match of html.matchAll(/id="([^"]+)"/g)) node(match[1]);
        },
      });
    return nodes.get(id);
  }
  for (const match of page.split('<script>')[0].matchAll(/id="([^"]+)"/g)) node(match[1]);
  node('template').value = 'ad';
  node('cleanBtn').disabled = true;
  node('prog div');
  const requests = [];
  const events = {};
  const context = vm.createContext({
    document: {
      querySelector(s) {
        assert.ok(nodes.has(s.slice(1)), `Missing element ${s}`);
        return nodes.get(s.slice(1));
      },
      querySelectorAll() {
        return [];
      },
      createElement() {
        return node('generated-' + Math.random());
      },
    },
    window: {
      addEventListener(name, handler) {
        events[name] = handler;
      },
    },
    navigator: {},
    localStorage: {
      getItem() {
        return null;
      },
    },
    setTimeout,
    clearTimeout,
    FormData: class {
      constructor() {
        this.values = new Map();
      }
      append(k, v) {
        this.values.set(k, v);
      }
    },
    fetch: async (url, options) => {
      if (url === 'api/presets') return { ok: !failSettings, json: async () => presets };
      if (url === 'api/voices') return { ok: false };
      assert.equal(url, 'api/clean');
      requests.push(options.body.values);
      return { ok: false, json: async () => ({ detail: 'Intercepted test upload' }) };
    },
    setInterval() {
      return 1;
    },
    clearInterval() {},
  });
  vm.runInContext(script, context);
  node('file').files = [{ name: 'voice.wav', type: 'audio/wav', size: 100 }];
  node('file').onchange();
  assert.equal(node('cleanBtn').disabled, true, 'Do not upload before settings load');
  await new Promise((resolve) => setImmediate(resolve));
  return { node, requests, events };
}

(async () => {
  const { node, requests } = await boot();
  const expected = {
    clean: [0, 0, 0.25, 0.2, 0.25, 0, 0],
    ad: [1, 0.3, 0.7, 0.6, 0.5, 0, 0],
    metallic: [0, 0, 0.85, 0.4, 0.35, 0, 0],
    echo: [1, 0.6, 0.4, 0.3, 0.25, 0, 0],
    noise: [1, 0, 0.25, 0.2, 0.25, 0.2, 0],
    strong: [1, 0.6, 1, 0.9, 0.7, 0, 0],
  };
  assert.equal(node('cleanBtn').disabled, false);
  for (const [name, values] of Object.entries(expected)) {
    assert.ok(page.includes(`option value="${name}"`));
    node('template').value = name;
    node('template').onchange();
    keys.forEach((k, i) => {
      assert.equal(Number(node(`s-${k}`).value), values[i], `${name}: ${k}`);
      assert.equal(node(`v-${k}`).textContent, `${Math.round(values[i] * 100)}%`);
    });
    assert.ok(node('templateHelp').textContent.length > 10);
    // Every control resets, including a room-tone override from a previous run.
    keys.forEach((k) => {
      node(`s-${k}`).value = 0.95;
    });
    node('s-room_tone').oninput({ target: node('s-room_tone') });
    assert.match(node('templateState').textContent, /Custom settings/);
    node('resetTemplate').onclick();
    keys.forEach((k, i) => assert.equal(Number(node(`s-${k}`).value), values[i]));
    // The upload uses what is displayed, not hidden preset defaults.
    await node('cleanBtn').onclick();
    const sent = requests.at(-1);
    keys.forEach((k, i) => assert.equal(Number(sent.get(k)), values[i]));
  }
  node('s-warmth').value = 0.15;
  node('s-warmth').oninput({ target: node('s-warmth') });
  await node('cleanBtn').onclick();
  assert.equal(Number(requests.at(-1).get('warmth')), 0.15);
  node('drop').onclick();
  assert.equal(node('file').clicked, true);
  let prevented = false;
  node('drop').ondrop({
    preventDefault() {
      prevented = true;
    },
    dataTransfer: { files: [{ name: 'ad.mp4', size: 100 }] },
  });
  assert.equal(prevented, true);
  assert.equal(node('fileName').textContent, 'ad.mp4');
  const failed = await boot(true);
  assert.equal(failed.node('cleanBtn').disabled, true);
  assert.match(failed.node('templateHelp').textContent, /Refresh/);
  console.log(
    'Six templates: controls, percentages, reset, manual overrides, upload payloads, loading failure, and file handlers passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
