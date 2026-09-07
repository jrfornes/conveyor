/** Display metadata for inbox grade values (Ready / Gaps / Unusable / unparsed / -). */
export interface GradeDisplay {
  label: string;
  tooltip: string;
  cssClass: string;
}

const GRADES: Record<string, GradeDisplay> = {
  Ready: {
    label: 'Ready',
    tooltip: 'Every rubric item present; can approve',
    cssClass: 'grade-ready',
  },
  Gaps: {
    label: 'Gaps',
    tooltip: 'Problem is clear; missing items listed; can approve or Improve',
    cssClass: 'grade-gaps',
  },
  Unusable: {
    label: 'Unusable',
    tooltip: 'No problem statement; approve refused without force',
    cssClass: 'grade-unusable',
  },
  unparsed: {
    label: 'unparsed',
    tooltip: 'grade.md has no Grade: line; re-grade',
    cssClass: 'grade-unparsed',
  },
  '-': {
    label: '—',
    tooltip: 'Not graded yet',
    cssClass: 'grade-none',
  },
};

export function gradeDisplay(grade: string): GradeDisplay {
  return GRADES[grade] ?? {
    label: grade,
    tooltip: grade,
    cssClass: 'grade-unknown',
  };
}

/** Hide the trivial Ready body ("1. none") in the review dialog. */
export function displayGradeMd(grade: string, gradeMd: string): string {
  if (grade !== 'Ready' || !gradeMd) return gradeMd;
  const body = gradeMd.replace(/^Grade:\s*Ready\s*\n?/i, '').trim();
  if (/^1\.\s*none\s*$/i.test(body)) return '';
  return gradeMd;
}
