import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { InboxItem } from '../models';
import { MatTooltipModule } from '@angular/material/tooltip';

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
        <ng-container matColumnDef="title">
          <th mat-header-cell *matHeaderCellDef>Title</th>
          <td mat-cell *matCellDef="let row">{{ row.title }}</td>
        </ng-container>
        <ng-container matColumnDef="source">
          <th mat-header-cell *matHeaderCellDef>Source</th>
          <td mat-cell *matCellDef="let row">{{ row.source }}</td>
        </ng-container>
        <ng-container matColumnDef="grade">
          <th mat-header-cell *matHeaderCellDef>Grade</th>
          <td mat-cell *matCellDef="let row">{{ row.grade }}</td>
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
  @Output() grade = new EventEmitter<string>();
  @Output() improve = new EventEmitter<string>();
  @Output() approve = new EventEmitter<string>();
  @Output() start = new EventEmitter<InboxItem>();
  @Output() skip = new EventEmitter<string>();
  cols = ['title', 'source', 'grade', 'status', 'actions'];

  canRefresh(row: InboxItem): boolean {
    return row.source === 'jira' && row.status === 'imported';
  }

  canEditSource(row: InboxItem): boolean {
    return row.status === 'imported';
  }

  canGrade(row: InboxItem): boolean {
    return ['imported', 'graded', 'awaiting-approval'].includes(row.status);
  }

  canApprove(row: InboxItem): boolean {
    return ['graded', 'awaiting-approval'].includes(row.status);
  }
}
