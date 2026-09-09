import { Component, Inject, OnDestroy, inject } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subscription } from 'rxjs';
import { InboxDetail } from '../models';
import { gradeDisplay } from '../grade';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { UiStateService } from '../services/ui-state.service';
import { ConfirmDialogComponent } from './confirm-dialog.component';
import {
  GapLine,
  MarkedLine,
  hasProposal,
  isApprovableGrade,
  needsForceByDefault,
  parseGapLines,
  parseMarkedLines,
  rubricSummary,
  suggestTaskName,
} from '../intake/intake-review';
import { attachmentLabel, isHttpUrl } from '../inbox/inbox-actions';

export type IntakeReviewResult =
  | { action: 'skipped' }
  | { action: 'approved'; taskName: string; message: string }
  | { action: 'started'; taskName: string; message: string };

export interface IntakeReviewData extends InboxDetail {
  rubric: string;
  grade_contract: string;
}

@Component({
  selector: 'app-intake-review-dialog',
  standalone: true,
  imports: [
    FormsModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatCheckboxModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
  ],
  template: `
    <h2 mat-dialog-title>
      Review {{ data.title }}
      @let g = gradeInfo(data.grade);
      <span class="grade-chip" [class]="g.cssClass" [matTooltip]="g.tooltip">{{ g.label }}</span>
    </h2>
    <mat-dialog-content>
      @if (actionError) {
        <div class="err" role="alert">{{ actionError }}</div>
      }
      @if (improving) {
        <div class="busy" role="status">
          <mat-spinner diameter="22"></mat-spinner>
          Ticket-reviewer is rewriting the proposal…
        </div>
      }
      <form [formGroup]="form">
        <mat-form-field appearance="outline" class="full">
          <mat-label>Task name</mat-label>
          <input matInput formControlName="name" [disabled]="busy" />
          <mat-hint>Written to tasks/&lt;name&gt;.md</mat-hint>
        </mat-form-field>

        @if (!hasProposalText) {
          <p class="warn">
            No proposed task yet — Approve commits the stripped original ticket, not a numbered rewrite.
            Run Improve first if you want ticket-reviewer to draft requirements.
          </p>
        }

        @if (gapLines.length) {
          <div class="gaps">
            <strong>Gaps</strong>
            <ul>
              @for (gap of gapLines; track gap.num) {
                <li><span class="num">{{ gap.num }}.</span> {{ gap.text }}</li>
              }
            </ul>
          </div>
        }

        <div class="cols">
          <div>
            <h3>Original ticket</h3>
            <pre class="mono pane">{{ data.source_md || '(empty)' }}</pre>
          </div>
          <div>
            <h3>Proposed task</h3>
            <mat-form-field appearance="outline" class="full">
              <textarea matInput formControlName="text" rows="16" [disabled]="busy"></textarea>
            </mat-form-field>
            @if (markedLines.length) {
              <div class="markers">
                <span class="legend"><span class="quoted">quoted</span> from ticket ·
                  <span class="invented">invented</span> filled by reviewer</span>
                <ul class="marker-list">
                  @for (row of markedLines; track $index) {
                    <li [class]="row.marker">{{ row.text }}</li>
                  }
                </ul>
              </div>
            }
          </div>
        </div>

        @if (data.attachments.length) {
          <div class="atts">
            <strong>Attachments</strong>
            <span>{{ selectedAttachmentCount }}/{{ data.attachments.length }} selected for ticket-reviewer</span>
            @if (isHttpUrl(data.url)) {
              <a [href]="data.url" target="_blank" rel="noopener">Open in {{ data.source }}</a>
            }
            <ul>
              @for (row of data.attachments; track row.id) {
                <li [class.off]="!row.selected">
                  {{ row.filename }}
                  <span class="muted">{{ attachmentLabel(row) }}{{ row.selected ? ' · selected' : '' }}</span>
                </li>
              }
            </ul>
          </div>
        }

        <p class="hint">Ready requires: {{ readySummary }}</p>

        @if (showForce) {
          <mat-checkbox [(ngModel)]="forceApprove" [ngModelOptions]="{ standalone: true }" [disabled]="busy">
            Force approve (grade is {{ data.grade }}; normally refused without --force)
          </mat-checkbox>
        }

        <mat-form-field appearance="outline" class="full">
          <mat-label>Improve notes</mat-label>
          <textarea matInput formControlName="comments" rows="3" [disabled]="busy"></textarea>
          <mat-hint>Sent to ticket-reviewer on Improve again. Clear before Approve.</mat-hint>
        </mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" [disabled]="busy" (click)="cancel()">Cancel</button>
      <button mat-button type="button" color="warn" [disabled]="busy" (click)="skip()">Skip</button>
      <button mat-stroked-button type="button" [disabled]="!canImprove" (click)="improveAgain()">
        Improve again
      </button>
      <button mat-stroked-button type="button" [disabled]="!canApprove" (click)="approve(false)">
        Approve only
      </button>
      <button mat-flat-button type="button" color="primary" [disabled]="!canApprove" (click)="approve(true)">
        Approve and start
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    h2.mat-mdc-dialog-title {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .full { width: 100%; box-sizing: border-box; }
    .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .cols > div { min-width: 0; overflow: hidden; }
    h3 {
      margin: 6px 0 4px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: rgba(0, 0, 0, 0.55);
    }
    .grade-chip {
      display: inline-block;
      font-size: 11px;
      font-weight: 500;
      padding: 2px 8px;
      border-radius: 10px;
      border: 1px solid transparent;
    }
    .grade-ready { background: #e8f5e9; color: #1b5e20; border-color: #a5d6a7; }
    .grade-gaps { background: #fff8e1; color: #8a6100; border-color: #ffe0a3; }
    .grade-unusable { background: #fbe9e7; color: #bf360c; border-color: #ffab91; }
    .grade-unparsed { background: #eceff1; color: #455a64; border-color: #b0bec5; }
    .grade-none { background: rgba(0, 0, 0, 0.04); color: rgba(0, 0, 0, 0.45); }
    .grade-unknown { background: rgba(0, 0, 0, 0.06); color: rgba(0, 0, 0, 0.7); }
    .mono {
      font-family: ui-monospace, monospace;
      font-size: 12px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
    }
    .pane {
      max-height: 320px;
      overflow: auto;
      background: #f5f5f5;
      padding: 8px 10px;
      border-radius: 6px;
      margin: 0;
      box-sizing: border-box;
    }
    .marker-list {
      list-style: none;
      margin: 4px 0 0;
      padding: 0;
      max-height: 140px;
      overflow: auto;
      background: #fafafa;
      border: 1px solid rgba(0, 0, 0, 0.08);
      border-radius: 6px;
    }
    .marker-list li {
      padding: 2px 8px;
      font-family: ui-monospace, monospace;
      font-size: 12px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .markers .legend { font-size: 11px; color: rgba(0, 0, 0, 0.55); }
    .marker-list li.quoted { background: #e3f2fd; }
    .marker-list li.invented { background: #fff3e0; }
    .gaps {
      background: #fff8e1;
      border: 1px solid #ffe0a3;
      border-radius: 6px;
      padding: 6px 10px;
      margin: 0 0 8px;
      font-size: 13px;
    }
    .gaps ul { margin: 4px 0 0; padding-left: 1.2rem; }
    .gaps li { margin: 2px 0; }
    .gaps .num { font-weight: 600; }
    .warn {
      background: #fff3e0;
      border: 1px solid #ffcc80;
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 12px;
      margin: 0 0 8px;
    }
    .err {
      background: #ffebee;
      color: #b71c1c;
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 12px;
      margin-bottom: 8px;
    }
    .busy {
      display: flex;
      align-items: center;
      gap: 8px;
      background: #fff8e1;
      color: #8a6100;
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 12px;
      margin-bottom: 8px;
    }
    .hint, .muted { font-size: 12px; color: rgba(0, 0, 0, 0.6); }
    .atts {
      font-size: 12px;
      margin: 8px 0;
      display: flex;
      flex-wrap: wrap;
      gap: 6px 12px;
      align-items: baseline;
    }
    .atts ul {
      list-style: none;
      margin: 4px 0 0;
      padding: 0;
      width: 100%;
      border: 1px solid rgba(0, 0, 0, 0.08);
      border-radius: 6px;
      background: #fff;
    }
    .atts li {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      padding: 4px 8px;
      border-bottom: 1px solid rgba(0, 0, 0, 0.06);
    }
    .atts li:last-child { border-bottom: 0; }
    .atts li.off { opacity: 0.65; }
    mat-dialog-content { min-width: 0; overflow-x: hidden; }
    @media (max-width: 800px) {
      .cols { grid-template-columns: 1fr; }
    }
  `,
})
export class IntakeReviewDialogComponent implements OnDestroy {
  private ref = inject(MatDialogRef<IntakeReviewDialogComponent, IntakeReviewResult | undefined>);
  private fb = inject(FormBuilder);
  private api = inject(ConveyorApiService);
  private ui = inject(UiStateService);
  private dialog = inject(MatDialog);
  private sub?: Subscription;

  form = this.fb.group({
    name: [''],
    text: [''],
    comments: [''],
  });

  data: IntakeReviewData;
  gapLines: GapLine[] = [];
  markedLines: MarkedLine[] = [];
  readySummary = '';
  hasProposalText = false;
  showForce = false;
  forceApprove = false;
  improving = false;
  busy = false;
  actionError = '';

  attachmentLabel = attachmentLabel;
  isHttpUrl = isHttpUrl;

  constructor(@Inject(MAT_DIALOG_DATA) initial: IntakeReviewData) {
    this.data = initial;
    this.applyItem(initial);
    this.sub = this.form.get('text')!.valueChanges.subscribe((text) => {
      this.markedLines = parseMarkedLines(text || '').filter((row) => row.marker);
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  get selectedAttachmentCount(): number {
    return this.data.attachments.filter((a) => a.selected).length;
  }

  get canApprove(): boolean {
    if (this.busy || this.improving) return false;
    if ((this.form.get('comments')?.value || '').trim()) return false;
    return isApprovableGrade(this.data.grade, this.forceApprove);
  }

  get canImprove(): boolean {
    if (this.busy || this.improving) return false;
    return !!(this.form.get('comments')?.value || '').trim();
  }

  gradeInfo(grade: string) {
    return gradeDisplay(grade);
  }

  cancel(): void {
    this.ref.close(undefined);
  }

  skip(): void {
    this.busy = true;
    this.actionError = '';
    this.api.inboxSkip(this.data.id).subscribe({
      next: (r) => {
        this.ui.refresh();
        this.ref.close({ action: 'skipped' });
        this.busy = false;
      },
      error: (e) => this.fail(e, 'Skip failed'),
    });
  }

  improveAgain(): void {
    const comments = (this.form.get('comments')?.value || '').trim();
    if (!comments) return;
    this.improving = true;
    this.busy = true;
    this.actionError = '';
    this.api.intake(this.data.id, true, comments).subscribe({
      next: () => {
        this.form.patchValue({ comments: '' });
        this.reloadItem();
      },
      error: (e) => {
        this.improving = false;
        this.fail(e, 'Improve failed');
      },
    });
  }

  approve(andStart: boolean): void {
    const v = this.form.getRawValue();
    const name = (v.name || '').trim() || suggestTaskName(this.data);
    const text = (v.text || '').trim();
    if (!text) {
      this.actionError = 'Proposed task is empty.';
      return;
    }
    this.busy = true;
    this.actionError = '';
    this.api.inboxApprove(this.data.id, name, text, this.forceApprove).subscribe({
      next: (r) => {
        if (!andStart) {
          this.ui.refresh();
          this.ref.close({ action: 'approved', taskName: name, message: r.message ?? 'Approved' });
          this.busy = false;
          return;
        }
        this.api.startTask(name).subscribe({
          next: (startMsg) => {
            const message = startMsg.message ?? 'Queued';
            if (this.ui.state()?.running) {
              this.ui.refresh();
              this.ref.close({ action: 'started', taskName: name, message });
              this.busy = false;
              return;
            }
            this.dialog
              .open(ConfirmDialogComponent, {
                width: '440px',
                data: {
                  title: 'Start the loops?',
                  body: `${name} is queued, but the loops are stopped so nothing will pick it up yet.`,
                  code: 'conveyor start',
                  confirmLabel: 'Start loops',
                },
              })
              .afterClosed()
              .subscribe((ok) => {
                if (!ok) {
                  this.ui.refresh();
                  this.ref.close({ action: 'started', taskName: name, message });
                  this.busy = false;
                  return;
                }
                this.api.start().subscribe({
                  next: (s) => {
                    this.ui.refresh();
                    this.ref.close({
                      action: 'started',
                      taskName: name,
                      message: s.message ?? message,
                    });
                    this.busy = false;
                  },
                  error: (e) => {
                    this.ui.refresh();
                    this.ref.close({ action: 'started', taskName: name, message });
                    this.fail(e, 'Start loops failed');
                  },
                });
              });
          },
          error: (e) => this.fail(e, 'Start-task failed'),
        });
      },
      error: (e) => this.fail(e, 'Approve failed'),
    });
  }

  private reloadItem(): void {
    this.api.inboxItem(this.data.id).subscribe({
      next: (item) => {
        this.data = { ...this.data, ...item };
        this.applyItem(this.data);
        this.improving = false;
        this.busy = false;
        this.ui.refresh();
      },
      error: (e) => {
        this.improving = false;
        this.fail(e, 'Reload failed');
      },
    });
  }

  private applyItem(item: IntakeReviewData): void {
    const proposal = (item.proposed_md || '').trim();
    const text = proposal || item.source_md || '';
    this.form.patchValue({
      name: suggestTaskName(item),
      text,
    });
    this.hasProposalText = hasProposal(item);
    this.gapLines = parseGapLines(item.grade_md || '');
    this.markedLines = parseMarkedLines(text).filter((row) => row.marker);
    this.readySummary = rubricSummary(item.rubric);
    this.showForce = needsForceByDefault(item.grade);
    this.forceApprove = false;
  }

  private fail(e: { error?: { error?: string }; message?: string }, fallback: string): void {
    this.busy = false;
    this.actionError = e?.error?.error ?? e?.message ?? fallback;
  }
}
