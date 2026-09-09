import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router } from '@angular/router';
import { forkJoin, map, Observable } from 'rxjs';
import { UiStateService } from '../services/ui-state.service';
import {
  IntakeReviewDialogComponent,
  IntakeReviewData,
  IntakeReviewResult,
} from '../dialogs/intake-review-dialog.component';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { InboxDetail } from '../models';

/** Grades `inbox approve` accepts without `--force`. */
export const APPROVABLE_GRADES = new Set(['Ready', 'Gaps']);

export interface GapLine {
  num: string;
  text: string;
}

export interface MarkedLine {
  text: string;
  marker: 'quoted' | 'invented' | null;
}

export function isApprovableGrade(grade: string, force = false): boolean {
  return force || APPROVABLE_GRADES.has(grade);
}

export function needsForceByDefault(grade: string): boolean {
  return !APPROVABLE_GRADES.has(grade) && grade !== '-';
}

/** Default task filename for approve / start-task. */
export function suggestTaskName(item: Pick<InboxDetail, 'task_name' | 'id' | 'external_id' | 'title'>): string {
  const existing = (item.task_name || '').trim();
  if (existing && existing !== '-') return existing;
  const ext = (item.external_id || '').trim();
  if (ext && ext !== '-') {
    const fromExt = ext.toLowerCase().replace(/_/g, '-');
    if (/^[a-z0-9][a-z0-9.-]*$/.test(fromExt)) return fromExt;
  }
  if (/^[a-z0-9][a-z0-9.-]*$/.test(item.id) && !/^manual-\d+$/.test(item.id)) return item.id;
  const fromTitle = (item.title || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48);
  if (fromTitle && /^[a-z0-9][a-z0-9.-]*$/.test(fromTitle)) return fromTitle;
  if (/^[a-z0-9][a-z0-9.-]*$/.test(item.id)) return item.id;
  return item.id;
}

/** Numbered gap lines from grade.md body (after the Grade: line). */
export function parseGapLines(gradeMd: string): GapLine[] {
  const body = gradeMd.replace(/^Grade:\s*\S+\s*\n?/i, '').trim();
  if (!body) return [];
  const out: GapLine[] = [];
  for (const line of body.split('\n')) {
    const m = line.match(/^\s*(\d+)\.\s+(.*)$/);
    if (m) out.push({ num: m[1], text: m[2].trim() });
  }
  return out;
}

/** Detect ticket-reviewer **quoted** / **invented** markers on requirement lines. */
export function parseMarkedLines(text: string): MarkedLine[] {
  return (text || '').split('\n').map((raw) => {
    const line = raw.trimEnd();
    const quoted = /\*\*quoted\*\*/i.test(line);
    const invented = /\*\*invented\*\*/i.test(line);
    return {
      text: line,
      marker: quoted ? 'quoted' : invented ? 'invented' : null,
    };
  });
}

export function hasProposal(item: Pick<InboxDetail, 'proposed_md'>): boolean {
  return !!(item.proposed_md || '').trim();
}

export function rubricSummary(rubric: string): string {
  const items = (rubric || '')
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.startsWith('- **'))
    .map((l) => {
      const m = l.match(/^- \*\*([^*]+)\*\*/);
      return m ? m[1].trim().replace(/:+$/, '') : '';
    })
    .filter(Boolean);
  return items.length ? items.join(', ') : 'repro, expected vs actual, acceptance, scope, environment';
}

export function loadIntakeReviewData(api: ConveyorApiService, id: string): Observable<IntakeReviewData> {
  return forkJoin({
    item: api.inboxItem(id),
    settings: api.intakeSettings(),
  }).pipe(
    map(({ item, settings }) => ({
      ...item,
      rubric: settings.rubric,
      grade_contract: settings.grade_contract,
    })),
  );
}

export function openIntakeReviewDialog(
  dialog: MatDialog,
  data: IntakeReviewData,
): MatDialogRef<IntakeReviewDialogComponent, IntakeReviewResult | undefined> {
  return dialog.open(IntakeReviewDialogComponent, {
    width: '1040px',
    maxWidth: '96vw',
    maxHeight: '92vh',
    panelClass: 'intake-review-dialog',
    data,
    disableClose: true,
  });
}

export function handleIntakeReviewResult(
  result: IntakeReviewResult | undefined,
  deps: { ui: UiStateService; snack: MatSnackBar; router: Router },
): void {
  if (!result) return;
  deps.ui.refresh();
  if (result.action === 'skipped') {
    deps.snack.open('Skipped', undefined, { duration: 3000 });
    return;
  }
  deps.snack.open(result.message, undefined, { duration: 3000 });
  if (result.action === 'started') {
    void deps.router.navigateByUrl('/board');
  }
}

export function subscribeIntakeReview(
  dialog: MatDialog,
  api: ConveyorApiService,
  id: string,
  onClose: (result: IntakeReviewResult | undefined) => void,
  onError: (message: string) => void,
): void {
  loadIntakeReviewData(api, id).subscribe({
    next: (data) => {
      openIntakeReviewDialog(dialog, data).afterClosed().subscribe(onClose);
    },
    error: (e: { error?: { error?: string }; message?: string }) => {
      onError(e?.error?.error ?? e?.message ?? 'Load failed');
    },
  });
}
