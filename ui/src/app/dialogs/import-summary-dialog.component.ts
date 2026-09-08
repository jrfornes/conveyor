import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { ImportSummary } from '../util';

export interface ImportSummaryDialogData extends ImportSummary {
  title: string;
}

@Component({
  selector: 'app-import-summary-dialog',
  standalone: true,
  imports: [MatDialogModule, MatButtonModule],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content>
      @if (data.imported.length) {
        <section>
          <h3 class="section-title">Imported ({{ data.imported.length }})</h3>
          <ul class="result-list">
            @for (row of data.imported; track row.id) {
              <li>
                <code class="id">{{ row.id }}</code>
                <span class="title">{{ row.title }}</span>
              </li>
            }
          </ul>
        </section>
      }
      @if (data.refreshed.length) {
        <section>
          <h3 class="section-title">Refreshed ({{ data.refreshed.length }})</h3>
          <ul class="result-list">
            @for (row of data.refreshed; track row.id) {
              <li>
                <code class="id">{{ row.id }}</code>
                <span class="title">{{ row.title }}</span>
              </li>
            }
          </ul>
        </section>
      }
      @if (data.failed.length) {
        <section class="failed">
          <h3 class="section-title">Failed ({{ data.failed.length }})</h3>
          <ul class="result-list">
            @for (row of data.failed; track row.key) {
              <li>
                <code class="id">{{ row.key }}</code>
                <span class="detail">{{ row.detail }}</span>
              </li>
            }
          </ul>
        </section>
      }
      @if (data.notices.length) {
        <section class="notices">
          <h3 class="section-title">Notices</h3>
          <ul class="notice-list">
            @for (notice of data.notices; track notice) {
              <li>{{ notice }}</li>
            }
          </ul>
        </section>
      }
      @if (!hasRows) {
        <p class="empty">No import details were returned.</p>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-flat-button mat-dialog-close cdkFocusInitial>OK</button>
    </mat-dialog-actions>
  `,
  styles: `
    mat-dialog-content {
      min-width: min(520px, 92vw);
      max-height: min(70vh, 560px);
      padding-top: 4px;
    }
    section {
      margin-bottom: 12px;
    }
    section:last-child {
      margin-bottom: 0;
    }
    .section-title {
      margin: 0 0 8px;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.02em;
      text-transform: uppercase;
      opacity: 0.7;
    }
    .result-list,
    .notice-list {
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .result-list li {
      display: grid;
      grid-template-columns: minmax(96px, 140px) minmax(0, 1fr);
      gap: 10px;
      align-items: start;
      padding: 6px 0;
      border-bottom: 1px solid rgba(0, 0, 0, 0.08);
      font-size: 14px;
    }
    .result-list li:last-child {
      border-bottom: none;
      padding-bottom: 0;
    }
    .id {
      font-family: ui-monospace, monospace;
      font-size: 12px;
      background: #f5f5f5;
      border-radius: 4px;
      padding: 2px 6px;
      word-break: break-all;
    }
    .title,
    .detail {
      line-height: 1.4;
      word-break: break-word;
    }
    .failed .section-title {
      color: #b71c1c;
      opacity: 1;
    }
    .failed .detail {
      color: #b71c1c;
    }
    .notice-list li {
      font-size: 13px;
      line-height: 1.45;
      padding: 4px 0;
      border-bottom: 1px solid rgba(0, 0, 0, 0.06);
    }
    .notice-list li:last-child {
      border-bottom: none;
      padding-bottom: 0;
    }
    .empty {
      margin: 0;
      font-size: 14px;
      opacity: 0.75;
    }
  `,
})
export class ImportSummaryDialogComponent {
  constructor(@Inject(MAT_DIALOG_DATA) public data: ImportSummaryDialogData) {}

  get hasRows(): boolean {
    return (
      this.data.imported.length > 0 ||
      this.data.refreshed.length > 0 ||
      this.data.failed.length > 0 ||
      this.data.notices.length > 0
    );
  }
}
