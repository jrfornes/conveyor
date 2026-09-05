import { beltRoutes, formatAge, handoffLabel, slugify, tasksInLane } from './util';

describe('util', () => {
  const tasks = [
    { name: 'a', lane: 'coder', task_id: '1', audit_count: 0, retry_count: 0, created_at: '', updated_at: '' },
    { name: 'b', lane: 'done', task_id: '2', audit_count: 1, retry_count: 0, created_at: '', updated_at: '' },
  ];

  it('filters tasks by lane', () => {
    expect(tasksInLane(tasks, 'coder').map((t) => t.name)).toEqual(['a']);
    expect(tasksInLane(tasks, 'done').map((t) => t.name)).toEqual(['b']);
  });

  it('formats age', () => {
    expect(formatAge(undefined)).toBe('—');
    expect(formatAge(45)).toBe('45s');
    expect(formatAge(120)).toBe('2m');
    expect(formatAge(3700)).toBe('1h 1m');
  });
});

  it('derives belt routes with no findings edge for one role', () => {
    expect(beltRoutes(['coder'])).toEqual([
      { from: 'operator', to: 'coder', verdict: 'ready' },
      { from: 'coder', to: 'done', verdict: 'pass' },
    ]);
  });

  it('derives belt routes for two roles', () => {
    expect(beltRoutes(['coder', 'reviewer'])).toEqual([
      { from: 'operator', to: 'coder', verdict: 'ready' },
      { from: 'coder', to: 'reviewer', verdict: 'ready' },
      { from: 'reviewer', to: 'done', verdict: 'pass' },
      { from: 'reviewer', to: 'coder', verdict: 'findings' },
    ]);
  });

  it('bounces findings to the penultimate role on a long belt', () => {
    const r = beltRoutes(['a', 'b', 'c', 'd']);
    expect(r).toContain({ from: 'd', to: 'c', verdict: 'findings' });
    expect(r).toContain({ from: 'c', to: 'd', verdict: 'ready' });
    expect(r.filter((h) => h.verdict === 'findings').length).toBe(1);
  });

  it('labels handoffs', () => {
    const three = ['specifier', 'coder', 'reviewer'];
    expect(handoffLabel(three, 'specifier', 0)).toBe('(held for approval)');
    expect(handoffLabel(three, 'specifier', 1)).toBe('ready → reviewer');
    expect(handoffLabel(three, 'specifier', 2)).toBe('pass → done · findings → coder');
    expect(handoffLabel(three, null, 0)).toBe('ready → coder');
    expect(handoffLabel(['coder'], null, 0)).toBe('pass → done');
  });

  it('slugifies names the way the server does', () => {
    expect(slugify('Review belt')).toBe('review-belt');
    expect(slugify('  Spec, no gate! ')).toBe('spec-no-gate');
    expect(slugify('!!!')).toBe('');
  });
});
