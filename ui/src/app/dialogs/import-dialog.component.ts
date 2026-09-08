import { Component, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTabsModule } from '@angular/material/tabs';

@Component({
  selector: 'app-import-dialog',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatTabsModule,
  ],
  template: `
    <h2 mat-dialog-title>Import</h2>
    <mat-dialog-content>
      <mat-tab-group [(selectedIndex)]="tab">
        <mat-tab label="Manual">
          <form [formGroup]="manual" class="tab-body">
            <mat-form-field appearance="outline" class="full">
              <mat-label>Title</mat-label>
              <input matInput formControlName="title" placeholder="login-timeout" />
            </mat-form-field>
            <mat-form-field appearance="outline" class="full">
              <mat-label>Ticket body (markdown)</mat-label>
              <textarea matInput formControlName="body" rows="10"></textarea>
            </mat-form-field>
          </form>
        </mat-tab>
        <mat-tab label="Jira">
          <form [formGroup]="jira" class="tab-body">
            <mat-form-field appearance="outline" class="full">
              <mat-label>Issue keys or browse URLs (one per line)</mat-label>
              <textarea matInput formControlName="lines" rows="8" placeholder="PROJ-123&#10;https://example.atlassian.net/browse/PROJ-124"></textarea>
            </mat-form-field>
            <p class="hint">Jira import needs site, email, and token (Intake settings → Jira). A blank description still creates a row; Grade is skipped only when there is no spec text and no attachments. Videos are listed, not downloaded — watch them in Jira.</p>
          </form>
        </mat-tab>
      </mat-tab-group>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-flat-button [disabled]="invalid" (click)="submit()">Import and grade</button>
    </mat-dialog-actions>
  `,
  styles: `
    .full { width: 100%; min-width: 420px; }
    .tab-body { padding-top: 8px; }
    .hint { font-size: 12px; opacity: 0.7; margin: 0 0 8px; }
  `,
})
export class ImportDialogComponent {
  private ref = inject(MatDialogRef<ImportDialogComponent>);
  private fb = inject(FormBuilder);
  tab = 0;

  manual = this.fb.group({
    title: ['', Validators.required],
    body: ['', Validators.required],
  });
  jira = this.fb.group({
    lines: ['', Validators.required],
  });

  get invalid(): boolean {
    return this.tab === 0 ? this.manual.invalid : this.jira.invalid;
  }

  submit(): void {
    if (this.tab === 0 && this.manual.valid) {
      const v = this.manual.getRawValue();
      this.ref.close({ source: 'manual', title: v.title, body: v.body, grade: true });
    } else if (this.tab === 1 && this.jira.valid) {
      this.ref.close({ source: 'jira', title: '', body: this.jira.getRawValue().lines, grade: true });
    }
  }
}
