import { Component, Inject, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { ApprovalItem } from '../models';

export interface SpecApproveResult {
  action: 'approve' | 'reject';
  comments?: string;
}

@Component({
  selector: 'app-spec-approve-dialog',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
  ],
  template: `
    <h2 mat-dialog-title>Spec approval · {{ data.approval.task }}</h2>
    <mat-dialog-content>
      <pre class="mono">{{ data.taskText }}</pre>
      <form [formGroup]="form">
        <mat-form-field appearance="outline" class="full">
          <mat-label>Reject comments</mat-label>
          <textarea matInput formControlName="comments" rows="4"></textarea>
        </mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-stroked-button color="warn" (click)="close('reject')">Reject</button>
      <button mat-flat-button (click)="close('approve')">Approve</button>
    </mat-dialog-actions>
  `,
  styles: `
    .full { width: 100%; min-width: 480px; }
    .mono { font-family: ui-monospace, monospace; font-size: 12px; white-space: pre-wrap; max-height: 360px; overflow: auto; background: #f5f5f5; padding: 6px 8px; }
  `,
})
export class SpecApproveDialogComponent {
  private ref = inject(MatDialogRef<SpecApproveDialogComponent, SpecApproveResult>);
  private fb = inject(FormBuilder);
  form = this.fb.group({ comments: [''] });

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: { approval: ApprovalItem; taskText: string },
  ) {}

  close(action: SpecApproveResult['action']): void {
    this.ref.close({ action, comments: this.form.getRawValue().comments || '' });
  }
}
