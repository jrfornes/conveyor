import { Component, Inject, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { InboxDetail } from '../models';

export interface IntakeReviewResult {
  action: 'approve' | 'edit-approve' | 'reject' | 'skip';
  name?: string;
  text?: string;
  comments?: string;
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
        <h3>Gaps</h3>
        <pre class="mono">{{ data.grade_md || '(no grade yet)' }}</pre>
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
    .full { width: 100%; }
    .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    h3 { margin: 8px 0 4px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; }
    .mono { font-family: ui-monospace, monospace; font-size: 12px; white-space: pre-wrap; max-height: 240px; overflow: auto; background: #f5f5f5; padding: 8px; }
    mat-dialog-content { min-width: 720px; max-width: 900px; }
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

  constructor(@Inject(MAT_DIALOG_DATA) public data: InboxDetail) {
    this.form.patchValue({
      name: data.task_name && data.task_name !== '-' ? data.task_name : data.id,
      text: data.proposed_md || data.source_md,
    });
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
