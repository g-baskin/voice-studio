<script lang="ts">
  import type { Status } from '#lib/studio/types.ts';

  let { id, status }: { id: string; status: Status } = $props();
</script>

<p class="status" class:error={status.bad} {id} role="status" aria-live="polite">{status.text}</p>
