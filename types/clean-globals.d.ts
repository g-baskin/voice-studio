// Runtime globals declared by the inline template-controls script in index.html.
import type { CleanElements, ElementFor } from './dom';

declare global {
  function $<K extends string>(selector: K): K extends `#s-${string}` ? HTMLInputElement : ElementFor<CleanElements, K>;
  let file: File | null;
  let templatesReady: boolean;
  const SLIDERS: [string, string][];
  interface CleanupTemplate {
    name?: string;
    preset: string;
    settings: Record<string, number>;
    description?: string;
  }
  let savedTemplates: Record<string, CleanupTemplate>;
  function selectedTemplate(): CleanupTemplate;
  function currentControls(): Record<string, number>;
  function applyTemplate(): void;
}
