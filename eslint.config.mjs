// Obsidian 社区审核镜像配置：typescript-eslint type-aware 扫描（unsafe-* 规则）
// 本地复现：npx eslint . （审核侧 128 issues 即来自这 5 条规则）
import tseslint from '@typescript-eslint/eslint-plugin';
import tsParser from '@typescript-eslint/parser';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
const root = dirname(fileURLToPath(import.meta.url));

const unsafeRules = {
  '@typescript-eslint/no-unsafe-call': 'error',
  '@typescript-eslint/no-unsafe-member-access': 'error',
  '@typescript-eslint/no-unsafe-assignment': 'error',
  '@typescript-eslint/no-unsafe-argument': 'error',
  '@typescript-eslint/no-unsafe-return': 'error',
};

export default [
  { ignores: ['node_modules/**', 'release/**', '.github/**'] },
  {
    files: ['src/**/*.ts', 'build.mjs', 'esbuild.config.mjs', 'scripts/**/*.mjs', 'scripts/**/*.mts'],
    languageOptions: {
      parser: tsParser,
      parserOptions: { project: './tsconfig.json', tsconfigRootDir: root },
    },
    plugins: { '@typescript-eslint': tseslint },
    rules: unsafeRules,
  },
];
