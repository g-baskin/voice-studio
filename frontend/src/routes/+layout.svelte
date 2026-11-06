<script lang="ts">
  import type { Snippet } from 'svelte';
  import { page } from '$app/state';
  import { NAV, PRODUCT } from '#lib/nav.ts';

  let { children }: { children: Snippet } = $props();
</script>

<a class="skip" href="#main">{page.data.skip ?? 'Skip to content'}</a>
<header class="apphead">
  <div class="apphead-inner">
    <a class="brand" href="/"><img src="/icon.svg" alt="" width="28" height="28" />{PRODUCT}</a>
    <nav class="appnav" aria-label="Main">
      {#each NAV as item (item.href)}
        <a href={item.href} aria-current={page.url.pathname === item.href ? 'page' : undefined}>{item.label}</a>
      {/each}
    </nav>
  </div>
</header>
<main id="main" class="page" tabindex="-1">
  {@render children()}
</main>

<style>
  .skip {
    position: absolute;
    top: -100px;
  }
  .skip:focus {
    top: 0;
  }
</style>
