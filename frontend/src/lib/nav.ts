export type NavItem = { href: string; label: string; svelte: boolean };

// Pages not yet moved to SvelteKit are full page loads served by the Python app.
export const NAV: NavItem[] = [
  { href: '/', label: 'Clean', svelte: false },
  { href: '/speak', label: 'Speak', svelte: true },
  { href: '/studio', label: 'Studio', svelte: false },
  { href: '/voice-lab', label: 'Voice Lab', svelte: false },
  { href: '/backup', label: 'Backup', svelte: true },
];

export const PRODUCT = 'Shark Audio';
