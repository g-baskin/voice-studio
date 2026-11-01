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
    files: ['src/naturalvoice/web/*.js'],
    languageOptions: { sourceType: 'script', globals: globals.browser },
  },
  {
    files: ['src/naturalvoice/web/workflow.js'],
    // Globals supplied by index.html's preceding script.
    languageOptions: {
      globals: {
        $: 'readonly',
        templatesReady: 'readonly',
        file: 'writable',
        savedTemplates: 'readonly',
        SLIDERS: 'readonly',
        selectedTemplate: 'readonly',
        currentControls: 'readonly',
        applyTemplate: 'readonly',
      },
    },
  },
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
