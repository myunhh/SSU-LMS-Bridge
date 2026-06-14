// scripts/ext-resolve-hook.mjs
// ESM resolve 훅 — Vite 는 확장자 없는 상대 import('./crypto')를 해석하지만
// Node ESM 은 확장자를 요구한다. 검증 스크립트(verify_lms_optin_relogin.mjs)가
// 실제 소스를 그대로 import 할 수 있도록, 확장자 없는 상대 경로에 .js 를 보충한다.
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export async function resolve(specifier, context, nextResolve) {
  if ((specifier.startsWith('./') || specifier.startsWith('../')) && !/\.[a-z]+$/i.test(specifier)) {
    try {
      const base = context.parentURL ? new URL(specifier, context.parentURL) : null;
      if (base) {
        const asJs = base.href + '.js';
        if (existsSync(fileURLToPath(asJs))) {
          return nextResolve(specifier + '.js', context);
        }
      }
    } catch { /* fall through */ }
  }
  return nextResolve(specifier, context);
}
