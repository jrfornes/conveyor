import { Component, Inject, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { InboxAttachment } from '../models';

export interface AttachmentsDialogData {
  id: string;
  title: string;
  url: string;
  attachments: InboxAttachment[];
}

@Component({
  selector: 'app-attachments-dialog',
  standalone: true,
  imports: [FormsModule, MatDialogModule, MatButtonModule, MatCheckboxModule],
  template: `
    <h2 mat-dialog-title>Attachments</h2>
    <mat-dialog-content>
      <p class="hint">{{ data.id }}{{ data.title ? ' — ' + data.title : '' }}</p>
      <p class="hint">Ticket-reviewer sees checked files on Grade or Improve. Video, audio, archives, and oversize files stay off.</p>
      <ul class="list">
        @for (row of rows; track row.id) {
          <li [class.blocked]="!row.downloadable">
            <mat-checkbox
              [(ngModel)]="row.selected"
              [disabled]="!row.downloadable"
            >{{ row.filename }}</mat-checkbox>
            <span class="meta">{{ label(row) }}</span>
          </li>
        }
      </ul>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-flat-button (click)="save()">Save</button>
    </mat-dialog-actions>
  `,
  styles: `
    .hint { margin: 0 0 8px; font-size: 12px; opacity: 0.7; }
    .list { list-style: none; margin: 0; padding: 0; }
    li {
      display: flex; align-items: center; justify-content: space-between;
      gap: 10px; padding: 3px 0; font-size: 13px;
    }
    li.blocked { opacity: 0.65; }
    .meta { font-size: 12px; opacity: 0.7; white-space: nowrap; }
  `,
})
export class AttachmentsDialogComponent {
  private ref = inject(MatDialogRef<AttachmentsDialogComponent, string[] | 'none'>);
  rows: InboxAttachment[];

  constructor(@Inject(MAT_DIALOG_DATA) public data: AttachmentsDialogData) {
    this.rows = (data.attachments || []).map((a) => ({ ...a }));
  }

  label(row: InboxAttachment): string {
    const size = this.fmtSize(row.size);
    if (row.kind === 'video' || row.kind === 'audio') {
      return `${row.kind} · ${size} · watch in Jira`;
    }
    if (row.skip_reason === 'oversize') return `${row.kind} · ${size} · oversize`;
    if (row.skip_reason === 'archive') return `archive · ${size}`;
    return `${row.kind} · ${size}`;
  }

  fmtSize(n: number): string {
    if (!n) return '0 B';
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  }

  save(): void {
    const ids = this.rows.filter((r) => r.selected && r.downloadable).map((r) => r.id);
    this.ref.close(ids.length ? ids : 'none');
  }
}
