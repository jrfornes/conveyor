import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { InboxItem } from '../models';
import { MatTooltipModule } from '@angular/material/tooltip';
import { gradeDisplay } from '../grade';

@Component({
  selector: 'app-inbox-table',
  standalone: true,
  imports: [MatTableModule, MatButtonModule, MatTooltipModule],
  template: `
    <div class="bar">
      <h2>Inbox</h2>
      <span class="grow"></span>
      <button mat-stroked-button (click)="toggleIntake.emit()">
        {{ intakeOpen ? 'Close intake' : 'Intake settings' }}
      </button>
      <button mat-stroked-button (click)="importTickets.emit()">Import</button>
    </div>
    @if (intakeBusy) {
      <div class="busy-note" role="status">
        Ticket-reviewer is busy{{ intakeBusyTask ? ' with ' + intakeBusyTask : '' }} —
        it only handles one item at a time, so Grade and Improve are paused until it finishes.
      </div>
    }
    @if (!items.length) {
      <div class="empty">
        <p>Inbox is empty.</p>
        <button mat-flat-button (click)="importTickets.emit()">Import</button>
      </div>
    } @else {
      <table mat-table [dataSource]="items" class="inbox">
        <ng-container matColumnDef="id">
          <th mat-header-cell *matHeaderCellDef>ID</th>
          <td mat-cell *matCellDef="let row" class="mono" [title]="row.id">{{ displayId(row) }}</td>
        </ng-container>
        <ng-container matColumnDef="title">
          <th mat-header-cell *matHeaderCellDef>Title</th>
          <td mat-cell *matCellDef="let row">
            {{ row.title }}
            @if (row.attachment_count) {
              <span class="badge" [title]="badgeTitle(row)">{{ badge(row) }}</span>
            }
          </td>
        </ng-container>
        <ng-container matColumnDef="source">
          <th mat-header-cell *matHeaderCellDef>Source</th>
          <td mat-cell *matCellDef="let row">{{ row.source }}</td>
        </ng-container>
        <ng-container matColumnDef="grade">
          <th mat-header-cell *matHeaderCellDef>Grade</th>
          <td mat-cell *matCellDef="let row">
            @let g = gradeInfo(row.grade);
            <span class="grade-chip" [class]="g.cssClass" [matTooltip]="g.tooltip">{{ g.label }}</span>
          </td>
        </ng-container>
        <ng-container matColumnDef="status">
          <th mat-header-cell *matHeaderCellDef>Status</th>
          <td mat-cell *matCellDef="let row">{{ row.status }}</td>
        </ng-container>
        <ng-container matColumnDef="actions">
          <th mat-header-cell *matHeaderCellDef>Actions</th>
          <td mat-cell *matCellDef="let row">
            @if (canRefresh(row)) {
              <button mat-button (click)="refresh.emit(row.id)">Fetch again</button>
            }
            @if (canEditSource(row)) {
              <button mat-button (click)="editSource.emit(row.id)">Edit source</button>
            }
            @if (canAttachments(row)) {
              <button mat-button (click)="attachments.emit(row.id)">Attachments</button>
            }
            @if (canGrade(row)) {
              <button mat-button [disabled]="intakeBusy"
                      [matTooltip]="intakeBusy ? 'Ticket-reviewer is busy; wait for it to finish' : ''"
                      (click)="grade.emit(row.id)">Grade</button>
              <button mat-button [disabled]="intakeBusy"
                      [matTooltip]="intakeBusy ? 'Ticket-reviewer is busy; wait for it to finish' : ''"
                      (click)="improve.emit(row.id)">Improve</button>
            }
            @if (canApprove(row)) {
              <button mat-button (click)="approve.emit(row.id)">Approve</button>
            }
            @if (row.status === 'ready') {
              <button mat-flat-button (click)="start.emit(row)">Start</button>
            }
            @if (row.status !== 'started' && row.status !== 'skipped') {
              <button mat-button color="warn" (click)="skip.emit(row.id)">Skip</button>
            }
          </td>
        </ng-container>
        <tr mat-header-row *matHeaderRowDef="cols"></tr>
        <tr mat-row *matRowDef="let row; columns: cols"></tr>
      </table>
    }
  `,
  styles: `
    .bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
    .bar h2 { margin: 0; font-size: 16px; font-weight: 500; }
    .grow { flex: 1; }
    .inbox { width: 100%; }
    .empty {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 12px; padding: 48px; opacity: 0.85;
    }
    .busy-note {
      background: #fff8e1; color: #8a6100; border: 1px solid #ffe0a3;
      border-radius: 6px; padding: 6px 10px; font-size: 12px; margin-bottom: 12px;
    }
    td { font-size: 13px; }
    .badge {
      display: inline-block;
      margin-left: 8px;
      font-size: 11px;
      padding: 1px 6px;
      border-radius: 10px;
      background: rgba(0, 0, 0, 0.08);
      vertical-align: middle;
    }
    .mono {
      font-family: "Roboto Mono", ui-monospace, monospace;
      font-size: 12px;
    }
    .grade-chip {
      display: inline-block;
      font-size: 11px;
      font-weight: 500;
      padding: 2px 8px;
      border-radius: 10px;
      border: 1px solid transparent;
      white-space: nowrap;
    }
    .grade-ready { background: #e8f5e9; color: #1b5e20; border-color: #a5d6a7; }
    .grade-gaps { background: #fff8e1; color: #8a6100; border-color: #ffe0a3; }
    .grade-unusable { background: #fbe9e7; color: #bf360c; border-color: #ffab91; }
    .grade-unparsed { background: #eceff1; color: #455a64; border-color: #b0bec5; }
    .grade-none { background: rgba(0, 0, 0, 0.04); color: rgba(0, 0, 0, 0.45); }
    .grade-unknown { background: rgba(0, 0, 0, 0.06); color: rgba(0, 0, 0, 0.7); }
  `,
})
export class InboxTableComponent {
  @Input() items: InboxItem[] = [];
  @Input() intakeOpen = false;
  @Input() intakeBusy = false;
  @Input() intakeBusyTask: string | null = null;
  @Output() importTickets = new EventEmitter<void>();
  @Output() toggleIntake = new EventEmitter<void>();
  @Output() refresh = new EventEmitter<string>();
  @Output() editSource = new EventEmitter<string>();
  @Output() attachments = new EventEmitter<string>();
  @Output() grade = new EventEmitter<string>();
  @Output() improve = new EventEmitter<string>();
  @Output() approve = new EventEmitter<string>();
  @Output() start = new EventEmitter<InboxItem>();
  @Output() skip = new EventEmitter<string>();
  cols = ['id', 'title', 'source', 'grade', 'status', 'actions'];

  gradeInfo(grade: string) {
    return gradeDisplay(grade);
  }

  displayId(row: InboxItem): string {
    const ext = row.external_id?.trim();
    return ext && ext !== '-' ? ext : row.id;
  }

  canRefresh(row: InboxItem): boolean {
    return row.source === 'jira' && row.status === 'imported';
  }

  canEditSource(row: InboxItem): boolean {
    return row.status === 'imported';
  }

  canAttachments(row: InboxItem): boolean {
    return row.status === 'imported' && (row.attachment_count || 0) > 0;
  }

  badge(row: InboxItem): string {
    const n = row.attachment_count || 0;
    const sel = row.selected_count || 0;
    const vid = row.video_count || 0;
    let s = `${sel}/${n}`;
    if (vid) s += ` · ${vid} video`;
    return s;
  }

  badgeTitle(row: InboxItem): string {
    return `${row.selected_count || 0} selected of ${row.attachment_count || 0}` +
      (row.video_count ? `; ${row.video_count} video not downloaded` : '');
  }

  canGrade(row: InboxItem): boolean {
    return ['imported', 'graded', 'awaiting-approval'].includes(row.status);
  }

  canApprove(row: InboxItem): boolean {
    return ['graded', 'awaiting-approval'].includes(row.status);
  }
}
