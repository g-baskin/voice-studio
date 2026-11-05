<script lang="ts" module>
  export type MenuItem = { label: string; shortcut?: string; disabled?: boolean; checked?: boolean; run: () => void };
  export type Menu = { label: string; items: (MenuItem | 'separator')[] };
</script>

<script lang="ts">
  import { tick } from 'svelte';

  let { menus }: { menus: Menu[] } = $props();

  let open = $state<number | null>(null);
  let bar: HTMLDivElement | undefined = $state();

  function items(index: number): HTMLElement[] {
    return [
      ...(bar?.querySelectorAll<HTMLElement>(
        `[data-menu="${index}"] [role="menu"] [role^="menuitem"]:not([disabled])`,
      ) ?? []),
    ];
  }

  async function show(index: number, focus: 'first' | 'last' | null = 'first') {
    open = index;
    await tick();
    const list = items(index);
    if (focus) (focus === 'first' ? list[0] : list.at(-1))?.focus();
  }

  function close(returnFocus = true) {
    const was = open;
    open = null;
    if (returnFocus && was !== null) bar?.querySelector<HTMLElement>(`[data-top="${was}"]`)?.focus();
  }

  function choose(item: MenuItem) {
    close();
    item.run();
  }

  function topKey(e: KeyboardEvent, index: number) {
    const count = menus.length;
    if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      void show(index);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      void show(index, 'last');
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault();
      const next = (index + (e.key === 'ArrowRight' ? 1 : count - 1)) % count;
      bar?.querySelector<HTMLElement>(`[data-top="${next}"]`)?.focus();
      if (open !== null) void show(next, null);
    }
  }

  function listKey(e: KeyboardEvent, index: number) {
    const list = items(index);
    const at = list.indexOf(document.activeElement as HTMLElement);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const step = e.key === 'ArrowDown' ? 1 : list.length - 1;
      list[(at + step) % list.length]?.focus();
    } else if (e.key === 'Home' || e.key === 'End') {
      e.preventDefault();
      (e.key === 'Home' ? list[0] : list.at(-1))?.focus();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      close();
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault();
      const next = (index + (e.key === 'ArrowRight' ? 1 : menus.length - 1)) % menus.length;
      void show(next);
    } else if (e.key === 'Tab') close(false);
  }

  function outside(e: PointerEvent) {
    if (open !== null && !bar?.contains(e.target as Node)) close(false);
  }
</script>

<svelte:window onpointerdown={outside} />

<div class="menubar" role="menubar" aria-label="Editor menu" bind:this={bar}>
  {#each menus as menu, i (menu.label)}
    <div class="menu" data-menu={i}>
      <button
        type="button"
        class="top"
        role="menuitem"
        aria-haspopup="menu"
        aria-expanded={open === i}
        data-top={i}
        tabindex={i === 0 ? 0 : -1}
        onclick={() => (open === i ? close() : void show(i, null))}
        onpointerenter={() => open !== null && open !== i && void show(i, null)}
        onkeydown={(e) => topKey(e, i)}>{menu.label}</button
      >
      {#if open === i}
        <div class="list" role="menu" aria-label={menu.label} tabindex="-1" onkeydown={(e) => listKey(e, i)}>
          {#each menu.items as item, j (j)}
            {#if item === 'separator'}
              <div class="sep" role="separator"></div>
            {:else}
              <button
                type="button"
                role={item.checked === undefined ? 'menuitem' : 'menuitemcheckbox'}
                aria-checked={item.checked}
                disabled={item.disabled}
                tabindex="-1"
                onclick={() => choose(item)}
              >
                <span class="tick" aria-hidden="true">{item.checked ? '✓' : ''}</span>
                <span class="label">{item.label}</span>
                {#if item.shortcut}<kbd>{item.shortcut}</kbd>{/if}
              </button>
            {/if}
          {/each}
        </div>
      {/if}
    </div>
  {/each}
</div>

<style>
  .menubar {
    display: flex;
    gap: 1px;
  }
  .menu {
    position: relative;
  }
  .top {
    font: inherit;
    font-size: 0.85rem;
    color: var(--ink);
    background: none;
    border: 0;
    border-radius: 5px;
    padding: 4px 9px;
    cursor: default;
  }
  .top:hover,
  .top[aria-expanded='true'] {
    background: var(--bg);
  }
  .list {
    position: absolute;
    z-index: 30;
    top: calc(100% + 2px);
    left: 0;
    min-width: 250px;
    padding: 5px;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: 0 8px 28px rgb(0 0 0 / 0.22);
  }
  .list button {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    font: inherit;
    font-size: 0.85rem;
    color: var(--ink);
    text-align: left;
    background: none;
    border: 0;
    border-radius: 5px;
    padding: 5px 8px 5px 4px;
    cursor: default;
  }
  .list button:hover:not(:disabled),
  .list button:focus-visible {
    background: var(--accent);
    color: var(--accent-ink);
    outline: none;
  }
  .list button:disabled {
    color: var(--muted);
    opacity: 0.6;
  }
  .tick {
    width: 1em;
    text-align: center;
  }
  .label {
    flex: 1;
  }
  kbd {
    font: inherit;
    font-size: 0.78rem;
    opacity: 0.75;
  }
  .sep {
    height: 1px;
    margin: 4px 6px;
    background: var(--line);
  }
</style>
