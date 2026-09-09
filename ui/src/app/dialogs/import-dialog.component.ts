import { Component, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTabsModule } from '@angular/material/tabs';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { UiStateService } from '../services/ui-state.service';
import { ImportDialogCloseResult } from '../import-flow';
import { importBusyMessage } from '../util';

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
    MatProgressSpinnerModule,
  ],
  template: `
    <h2 mat-dialog-title>Import</h2>
    <mat-dialog-content>
      <mat-tab-group [(selectedIndex)]="tab" [class.dimmed]="loading">
        <mat-tab label="Manual">
          <form [formGroup]="manual" class="tab-body">
            <mat-form-field appearance="outline" class="full">
              <mat-label>Title</mat-label>
              <input matInput formControlName="title" placeholder="login-timeout" [readonly]="loading" />
            </mat-form-field>
            <mat-form-field appearance="outline" class="full">
              <mat-label>Ticket body (markdown)</mat-label>
              <textarea matInput formControlName="body" rows="10" [readonly]="loading"></textarea>
            </mat-form-field>
          </form>
        </mat-tab>
        <mat-tab label="Jira">
          <form [formGroup]="jira" class="tab-body">
            <mat-form-field appearance="outline" class="full">
              <mat-label>Issue keys or browse URLs (one per line)</mat-label>
              <textarea matInput formControlName="lines" rows="8" placeholder="PROJ-123&#10;https://example.atlassian.net/browse/PROJ-124" [readonly]="loading"></textarea>
            </mat-form-field>
            <p class="hint">Jira import needs site, email, and token (Intake settings → Jira). A blank description still creates a row; Grade is skipped only when there is no spec text and no attachments. Videos are listed, not downloaded — watch them in Jira.</p>
          </form>
        </mat-tab>
      </mat-tab-group>
      @if (error) {
        <div class="err" role="alert">{{ error }}</div>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close [disabled]="loading">Cancel</button>
      <button mat-flat-button [disabled]="invalid || loading" (click)="submit()">
        @if (loading) {
          <span class="submit-loading">
            <mat-spinner diameter="18"></mat-spinner>
            {{ loadingLabel }}
          </span>
        } @else {
          Import and grade
        }
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    .full { width: 100%; min-width: 420px; }
    .tab-body { padding-top: 8px; }
    .hint { font-size: 12px; opacity: 0.7; margin: 0 0 8px; }
    .dimmed { opacity: 0.65; pointer-events: none; }
    .err {
      background: #ffebee; color: #b71c1c; border: 1px solid #ef9a9a;
      border-radius: 6px; padding: 6px 10px; font-size: 13px; margin-top: 8px;
    }
    .submit-loading {
      display: inline-flex; align-items: center; gap: 8px;
    }
  `,
})
export class ImportDialogComponent {
  private ref = inject(MatDialogRef<ImportDialogComponent, ImportDialogCloseResult | undefined>);
  private fb = inject(FormBuilder);
  private api = inject(ConveyorApiService);
  private ui = inject(UiStateService);
  tab = 0;
  loading = false;
  error = '';
  loadingLabel = 'Importing…';

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
    if (this.invalid || this.loading) return;
    let source = '';
    let title = '';
    let body = '';
    if (this.tab === 0 && this.manual.valid) {
      const v = this.manual.getRawValue();
      source = 'manual';
      title = v.title ?? '';
      body = v.body ?? '';
    } else if (this.tab === 1 && this.jira.valid) {
      source = 'jira';
      body = this.jira.getRawValue().lines ?? '';
    } else {
      return;
    }

    this.loading = true;
    this.error = '';
    this.loadingLabel = importBusyMessage(source);
    this.ref.disableClose = true;
    this.ui.busy.set(true);
    this.ui.busyMessage.set(this.loadingLabel);

    this.api.importTickets(source, title, body).subscribe({
      next: (r) => {
        this.ref.close({ source, title, body, grade: true, message: r.message || 'Imported' });
      },
      error: (e) => {
        this.loading = false;
        this.ref.disableClose = false;
        this.ui.busy.set(false);
        this.ui.busyMessage.set('');
        this.error = e?.error?.error ?? e.message ?? 'Import failed';
      },
    });
  }
}
