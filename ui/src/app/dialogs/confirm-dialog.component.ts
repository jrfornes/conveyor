import { Component, Inject, inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';

export type ConfirmResult = true | 'secondary';

export interface ConfirmData {
  title: string;
  body: string;
  /** Shown under the body in a mono block: the command or path the action writes. */
  code?: string;
  /** Short list under the body, e.g. busy work about to be interrupted. */
  items?: string[];
  confirmLabel: string;
  /** Extra action; closes with `'secondary'`. Existing `if (ok)` callers stay boolean-only. */
  secondaryLabel?: string;
  /** Red confirm button for anything that kills a process or removes state. */
  warn?: boolean;
}

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  imports: [MatDialogModule, MatButtonModule],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content>
      <p>{{ data.body }}</p>
      @if (data.items?.length) {
        <ul class="items">
          @for (item of data.items; track item) {
            <li>{{ item }}</li>
          }
        </ul>
      }
      @if (data.code) {
        <pre class="mono">{{ data.code }}</pre>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button
        mat-flat-button
        [color]="data.warn ? 'warn' : 'primary'"
        cdkFocusInitial
        (click)="ref.close(true)"
      >
        {{ data.confirmLabel }}
      </button>
      @if (data.secondaryLabel) {
        <button mat-flat-button color="warn" (click)="ref.close('secondary')">
          {{ data.secondaryLabel }}
        </button>
      }
    </mat-dialog-actions>
  `,
  styles: `
    p { margin: 0 0 8px; font-size: 14px; }
    .items {
      margin: 0 0 8px;
      padding-left: 18px;
      font-size: 13px;
    }
    .mono {
      font-family: ui-monospace, monospace;
      font-size: 12px;
      white-space: pre-wrap;
      background: #f5f5f5;
      padding: 6px 8px;
      margin: 0;
      border-radius: 4px;
    }
  `,
})
export class ConfirmDialogComponent {
  ref = inject(MatDialogRef<ConfirmDialogComponent, ConfirmResult>);

  constructor(@Inject(MAT_DIALOG_DATA) public data: ConfirmData) {}
}
