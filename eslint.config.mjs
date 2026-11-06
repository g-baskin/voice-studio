import js from '@eslint/js';
import globals from 'globals';

export default [
  {
    ignores: [
      'node_modules/**',
      '.venv/**',
      'engines/**/.venv/**',
      'dist/**',
      'build/**',
      'frontend/**',
      'src/naturalvoice/ui/**',
    ],
  },
  js.configs.recommended,
  {
    files: ['tests/browser_*.cjs'],
    // Playwright page.evaluate callbacks execute in the browser.
    languageOptions: { globals: globals.browser },
  },
  {
    files: ['src/naturalvoice/web/sw.js'],
    languageOptions: { globals: globals.serviceworker },
  },
  {
    files: ['scripts/*.cjs', 'tests/*.cjs', '*.mjs'],
    languageOptions: { globals: globals.node },
  },
];
