import { Component, EventEmitter, Input, Output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { gradeDisplay } from '../grade';
import { InboxItem } from '../models';
import {
  attachmentBadge,
  attachmentBadgeTitle,
  canGradeInbox,
  canStartInbox,
  displayInboxId,
} from '../inbox/inbox-actions';

@Component({
  selector: 'app-inbox-table',
  standalone: true,
  imports: [MatTableModule, MatButtonModule, MatTooltipModule, RouterLink],
  template: `
    <div class="bar">
      <h2>Inbox</h2>
      <span class="grow"></span>
      <button mat-stroked-button (click)="toggleIntake.emit()" [disabled]="busy">
        {{ intakeOpen ? 'Close intake' : 'Intake settings' }}
      </button>
      <button mat-stroked-button (click)="importTickets.emit()" [disabled]="busy">Import</button>
    </div>
    @if (busyMessage) {
      <div class="busy-note" role="status">{{ busyMessage }}</div>
    }
    @if (intakeBusy) {
      <div class="busy-note" role="status">
        Ticket-reviewer is busy{{ intakeBusyTask ? ' with ' + intakeBusyTask : '' }} —
        it only handles one item at a time, so Grade and Improve are paused until it finishes.
      </div>
    }
    @if (!items.length) {
      <div class="empty">
        <p>Inbox is empty.</p>
        <button mat-flat-button (click)="importTickets.emit()" [disabled]="busy">Import</button>
      </div>
    } @else {
      <table mat-table [dataSource]="items" class="inbox">
        <ng-container matColumnDef="id">
          <th mat-header-cell *matHeaderCellDef>ID</th>
          <td mat-cell *matCellDef="let row" class="mono">
            <a class="itemlink" [routerLink]="['/inbox', row.id]" [title]="row.id">
              {{ displayId(row) }}
            </a>
          </td>
        </ng-container>
        <ng-container matColumnDef="title">
          <th mat-header-cell *matHeaderCellDef>Title</th>
          <td mat-cell *matCellDef="let row">
            <a class="itemlink" [routerLink]="['/inbox', row.id]">{{ row.title }}</a>
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
            @if (canGrade(row)) {
              <button mat-button [disabled]="intakeBusy"
                      [matTooltip]="intakeBusy ? 'Ticket-reviewer is busy; wait for it to finish' : ''"
                      (click)="grade.emit(row.id)">Grade</button>
            }
            @if (row.status === 'graded' || row.status === 'awaiting-approval') {
              <button mat-flat-button (click)="review.emit(row.id)">Review</button>
            }
            @if (canStart(row)) {
              <button mat-flat-button (click)="start.emit(row)">Start</button>
            }
          </td>
        </ng-container>
        <tr mat-header-row *matHeaderRowDef="cols"></tr>
        <tr mat-row *matRowDef="let row; columns: cols"></tr>
      </table>
    }
  `,
  styles: `
    .bar { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
    .bar h2 { margin: 0; font-size: 16px; font-weight: 500; }
    .grow { flex: 1; }
    .inbox { width: 100%; }
    .empty {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 8px; padding: 28px; opacity: 0.85;
    }
    .busy-note {
      background: #fff8e1; color: #8a6100; border: 1px solid #ffe0a3;
      border-radius: 6px; padding: 4px 8px; font-size: 12px; margin-bottom: 8px;
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
    .itemlink {
      color: #1565c0;
      font-weight: 500;
      text-decoration: none;
    }
    .itemlink:hover { text-decoration: underline; }
  `,
})
export class InboxTableComponent {
  @Input() items: InboxItem[] = [];
  @Input() intakeOpen = false;
  @Input() intakeBusy = false;
  @Input() intakeBusyTask: string | null = null;
  @Input() busy = false;
  @Input() busyMessage = '';
  @Output() importTickets = new EventEmitter<void>();
  @Output() toggleIntake = new EventEmitter<void>();
  @Output() grade = new EventEmitter<string>();
  @Output() start = new EventEmitter<InboxItem>();
  @Output() review = new EventEmitter<string>();
  cols = ['id', 'title', 'source', 'grade', 'status', 'actions'];

  gradeInfo(grade: string) {
    return gradeDisplay(grade);
  }

  displayId = displayInboxId;
  canGrade = canGradeInbox;
  canStart = canStartInbox;
  badge = attachmentBadge;
  badgeTitle = attachmentBadgeTitle;
}
