<script lang="ts">
  import { voiceGroups, voiceLabel } from '#lib/studio/logic.ts';
  import type { Voice } from '#lib/studio/types.ts';

  let {
    catalog,
    value,
    label,
    onchange,
  }: { catalog: Voice[]; value: string; label: string; onchange: (value: string) => void } = $props();

  const groups = $derived(voiceGroups(catalog));
  const missing = $derived(!!value && !catalog.some((v) => v.id === value));
</script>

<select aria-label={label} {value} onchange={(e) => onchange(e.currentTarget.value)}>
  {#if missing}<option {value}>{value} (missing)</option>{/if}
  {#each groups as g (g.label)}
    <optgroup label={g.label}>
      {#each g.voices as v (v.id)}<option value={v.id}>{voiceLabel(v)}</option>{/each}
    </optgroup>
  {/each}
</select>
