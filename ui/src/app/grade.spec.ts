import { displayGradeMd, gradeDisplay } from './grade';

describe('grade', () => {
  it('maps legal grades to tooltips and classes', () => {
    expect(gradeDisplay('Ready').tooltip).toContain('approve');
    expect(gradeDisplay('Ready').cssClass).toBe('grade-ready');
    expect(gradeDisplay('Gaps').cssClass).toBe('grade-gaps');
    expect(gradeDisplay('Unusable').cssClass).toBe('grade-unusable');
    expect(gradeDisplay('unparsed').cssClass).toBe('grade-unparsed');
    expect(gradeDisplay('-').label).toBe('—');
  });

  it('hides trivial Ready grade body', () => {
    expect(displayGradeMd('Ready', 'Grade: Ready\n\n1. none\n')).toBe('');
    expect(displayGradeMd('Gaps', 'Grade: Gaps\n\n1. no repro\n')).toContain('no repro');
    expect(displayGradeMd('Ready', 'Grade: Ready\n\n1. none\n2. extra\n')).toContain('extra');
  });
});
