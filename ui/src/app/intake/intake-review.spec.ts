import {
  isApprovableGrade,
  needsForceByDefault,
  parseGapLines,
  parseMarkedLines,
  rubricSummary,
  suggestTaskName,
} from './intake-review';

describe('intake-review helpers', () => {
  it('suggests task names from task_name, external_id, id, then title', () => {
    expect(suggestTaskName({ task_name: 'my-task', id: 'x', external_id: '-', title: 'T' })).toBe('my-task');
    expect(suggestTaskName({ task_name: '-', id: 'manual-1', external_id: 'PROJ-9', title: 'T' })).toBe('proj-9');
    expect(suggestTaskName({ task_name: '-', id: 'cave-lights', external_id: '-', title: 'Cave' })).toBe('cave-lights');
    expect(suggestTaskName({ task_name: '-', id: 'manual-0001', external_id: '-', title: 'Fix Login Bug' })).toBe(
      'fix-login-bug',
    );
  });

  it('parses numbered gaps from grade.md', () => {
    const gaps = parseGapLines('Grade: Gaps\n\n1. no repro\n2. scope open-ended\n');
    expect(gaps).toEqual([
      { num: '1', text: 'no repro' },
      { num: '2', text: 'scope open-ended' },
    ]);
  });

  it('detects quoted and invented markers', () => {
    const lines = parseMarkedLines('1. **quoted** — login works\n2. **invented** — add tests\nplain\n');
    expect(lines[0].marker).toBe('quoted');
    expect(lines[1].marker).toBe('invented');
    expect(lines[2].marker).toBeNull();
  });

  it('knows which grades need force', () => {
    expect(isApprovableGrade('Ready')).toBe(true);
    expect(isApprovableGrade('Gaps')).toBe(true);
    expect(isApprovableGrade('Unusable')).toBe(false);
    expect(isApprovableGrade('Unusable', true)).toBe(true);
    expect(needsForceByDefault('Unusable')).toBe(true);
    expect(needsForceByDefault('Ready')).toBe(false);
  });

  it('summarizes rubric checklist items', () => {
    const rubric = '## Items\n\n- **Repro:** steps\n- **Scope:** bounds\n';
    expect(rubricSummary(rubric)).toBe('Repro, Scope');
  });
});
