import { Component, Inject, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { InboxDetail } from '../models';
import { displayGradeMd, gradeDisplay } from '../grade';

export interface IntakeReviewResult {
  action: 'approve' | 'edit-approve' | 'reject' | 'skip';
  name?: string;
  text?: string;
  comments?: string;
}

export interface IntakeReviewData extends InboxDetail {
  rubric: string;
  grade_contract: string;
}

@Component({
  selector: 'app-intake-review-dialog',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatTooltipModule,
  ],
  template: `
    <h2 mat-dialog-title>Review {{ data.title }}</h2>
    <mat-dialog-content>
      <form [formGroup]="form">
        <mat-form-field appearance="outline" class="full">
          <mat-label>Task name</mat-label>
          <input matInput formControlName="name" />
        </mat-form-field>
        <div class="cols">
          <div>
            <h3>Original</h3>
            <pre class="mono">{{ data.source_md || '(empty)' }}</pre>
          </div>
          <div>
            <h3>Proposed task</h3>
            <mat-form-field appearance="outline" class="full">
              <textarea matInput formControlName="text" rows="14"></textarea>
            </mat-form-field>
          </div>
        </div>
        <div class="grade-head">
          <h3>Grade</h3>
          @let g = gradeInfo(data.grade);
          <span class="grade-chip" [class]="g.cssClass" [matTooltip]="g.tooltip">{{ g.label }}</span>
        </div>
        @if (gradeBody) {
          <pre class="mono">{{ gradeBody }}</pre>
        } @else if (!data.grade_md) {
          <p class="muted">(no grade yet)</p>
        }
        <h3>Ready requires</h3>
        <pre class="mono rubric">{{ data.rubric || '(no rubric file)' }}</pre>
        <p class="contract-hint">{{ contractSummary }}</p>
        <mat-form-field appearance="outline" class="full">
          <mat-label>Reject comments (Improve retry)</mat-label>
          <textarea matInput formControlName="comments" rows="3"></textarea>
        </mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button (click)="close('skip')">Skip</button>
      <button mat-button (click)="close('reject')">Reject</button>
      <button mat-stroked-button (click)="close('edit-approve')">Edit then approve</button>
      <button mat-flat-button (click)="close('approve')">Approve</button>
    </mat-dialog-actions>
  `,
  styles: `
    .full {
      width: 100%;
      box-sizing: border-box;
    }
    .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .cols > div {
      min-width: 0;
      overflow: hidden;
    }
    h3 { margin: 8px 0 4px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; }
    .grade-head {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-top: 8px;
    }
    .grade-head h3 { margin: 0; }
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
      font-family: ui-monospace, monospace; font-size: 12px; white-space: pre-wrap;
      max-height: 240px; overflow: auto; background: #f5f5f5; padding: 8px;
      max-width: 100%;
      overflow-wrap: anywhere;
      word-break: break-word;
      box-sizing: border-box;
    }
    .rubric { max-height: 180px; }
    .muted, .contract-hint {
      font-size: 12px;
      color: rgba(0, 0, 0, 0.6);
      margin: 4px 0 0;
    }
    mat-dialog-content {
      min-width: 0;
      overflow-x: hidden;
    }
    @media (max-width: 720px) {
      .cols { grid-template-columns: 1fr; }
    }
  `,
})
export class IntakeReviewDialogComponent {
  private ref = inject(MatDialogRef<IntakeReviewDialogComponent, IntakeReviewResult>);
  private fb = inject(FormBuilder);
  form = this.fb.group({
    name: [''],
    text: [''],
    comments: [''],
  });
  gradeBody = '';
  contractSummary = '';

  constructor(@Inject(MAT_DIALOG_DATA) public data: IntakeReviewData) {
    this.form.patchValue({
      name: data.task_name && data.task_name !== '-' ? data.task_name : data.id,
      text: data.proposed_md || data.source_md,
    });
    this.gradeBody = displayGradeMd(data.grade, data.grade_md);
    this.contractSummary = this.summarizeContract(data.grade_contract);
  }

  gradeInfo(grade: string) {
    return gradeDisplay(grade);
  }

  private summarizeContract(contract: string): string {
    const line = contract.split('\n').find((l) => l.includes('Grade: Ready'));
    return line
      ? `Fixed by Conveyor: ${line.trim()}`
      : 'Ready / Gaps / Unusable and the Grade: line are fixed by Conveyor; edit the checklist above.';
  }

  close(action: IntakeReviewResult['action']): void {
    const v = this.form.getRawValue();
    this.ref.close({
      action,
      name: v.name || this.data.id,
      text: v.text || '',
      comments: v.comments || '',
    });
  }
}
