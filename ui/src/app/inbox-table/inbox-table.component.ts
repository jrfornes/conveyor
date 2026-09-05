import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { InboxItem } from '../models';

@Component({
  selector: 'app-inbox-table',
  standalone: true,
  imports: [MatTableModule, MatButtonModule],
  template: `
    <div class="bar">
      <h2>Inbox</h2>
      <span class="grow"></span>
      <button mat-stroked-button (click)="toggleIntake.emit()">
        {{ intakeOpen ? 'Close intake' : 'Intake settings' }}
      </button>
      <button mat-stroked-button (click)="importTickets.emit()">Import</button>
    </div>
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
            @if (canGrade(row)) {
              <button mat-button (click)="grade.emit(row.id)">Grade</button>
              <button mat-button (click)="improve.emit(row.id)">Improve</button>
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
    td { font-size: 13px; }
  `,
})
export class InboxTableComponent {
  @Input() items: InboxItem[] = [];
  @Input() intakeOpen = false;
  @Output() importTickets = new EventEmitter<void>();
  @Output() toggleIntake = new EventEmitter<void>();
  @Output() grade = new EventEmitter<string>();
  @Output() improve = new EventEmitter<string>();
  @Output() approve = new EventEmitter<string>();
  @Output() start = new EventEmitter<InboxItem>();
  @Output() skip = new EventEmitter<string>();
  cols = ['title', 'source', 'grade', 'status', 'actions'];

  canGrade(row: InboxItem): boolean {
    return ['imported', 'graded', 'awaiting-approval'].includes(row.status);
  }

  canApprove(row: InboxItem): boolean {
    return ['graded', 'awaiting-approval'].includes(row.status);
  }
}
