import { ConveyorTask, Hop } from './models';

/** Map board tasks into lane columns for the kanban view. */
export function tasksInLane(tasks: ConveyorTask[], lane: string): ConveyorTask[] {
  return tasks.filter((t) => t.lane === lane);
}

export function formatAge(seconds?: number): string {
  if (seconds == null) return '—';
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

/**
 * Belt edges for an ordered role list — the client mirror of
 * `presets.routes()` (and of `config.routes()` minus the intake edge).
 * A one-role belt has no `findings` edge: there is no previous role.
 */
export function beltRoutes(roles: string[]): Hop[] {
  if (!roles.length) return [];
  const out: Hop[] = [{ from: 'operator', to: roles[0], verdict: 'ready' }];
  for (let i = 0; i < roles.length - 1; i++) {
    out.push({ from: roles[i], to: roles[i + 1], verdict: 'ready' });
  }
  const last = roles[roles.length - 1];
  out.push({ from: last, to: 'done', verdict: 'pass' });
  if (roles.length > 1) {
    out.push({ from: last, to: roles[roles.length - 2], verdict: 'findings' });
  }
  return out;
}

/** What role `i` does with its handoff: forward, held, or terminal. */
export function handoffLabel(roles: string[], gate: string | null, i: number): string {
  if (i === roles.length - 1) {
    const prev = i > 0 ? roles[i - 1] : null;
    return prev ? `pass → done · findings → ${prev}` : 'pass → done';
  }
  if (gate === roles[i]) return '(held for approval)';
  return `ready → ${roles[i + 1]}`;
}

/**
 * Client mirror of `presets.slug()`, for previewing the filename in the editor
 * dialog. The server allocates the real slug (it may suffix a taken one) and
 * always wins; keep the two in step.
 */
export function slugify(name: string): string {
  return (name || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48);
}
