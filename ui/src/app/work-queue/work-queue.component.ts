import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatTableModule } from '@angular/material/table';
import { WorkEntry } from '../models';

@Component({
  selector: 'app-work-queue',
  standalone: true,
  imports: [MatTableModule],
  template: `
    <table mat-table [dataSource]="work" class="queue-table">
      <ng-container matColumnDef="role">
        <th mat-header-cell *matHeaderCellDef>Role</th>
        <td mat-cell *matCellDef="let row">
          <button type="button" class="role-btn" (click)="selectRole.emit(row.role)">{{ row.role }}</button>
        </td>
      </ng-container>
      <ng-container matColumnDef="task">
        <th mat-header-cell *matHeaderCellDef>Task</th>
        <td mat-cell *matCellDef="let row">
          {{ row.task || '—' }}
          @if (sub(row); as line) {
            <div class="sub">{{ line }}</div>
          }
        </td>
      </ng-container>
      <ng-container matColumnDef="state">
        <th mat-header-cell *matHeaderCellDef>State</th>
        <td mat-cell *matCellDef="let row">
          <span class="dot" [class]="row.state"></span>{{ row.state }}
        </td>
      </ng-container>
      <ng-container matColumnDef="age">
        <th mat-header-cell *matHeaderCellDef>Age</th>
        <td mat-cell *matCellDef="let row">{{ formatAge(row.age_seconds) }}</td>
      </ng-container>
      <ng-container matColumnDef="new">
        <th mat-header-cell *matHeaderCellDef>New</th>
        <td mat-cell *matCellDef="let row">{{ row.new_count }}</td>
      </ng-container>
      <tr mat-header-row *matHeaderRowDef="cols"></tr>
      <tr mat-row *matRowDef="let row; columns: cols"></tr>
    </table>
  `,
  styles: `
    .queue-table { width: 100%; font-size: 13px; }
    .sub { font-size: 11px; opacity: 0.7; }
    .role-btn {
      background: none; border: none; color: inherit; cursor: pointer;
      text-decoration: underline; font: inherit; padding: 0;
    }
    .dot {
      display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px;
      &.busy { background: #2e7d32; }
      &.idle { background: #fbc02d; }
      &.stopped { background: #bdbdbd; }
    }
  `,
})
export class WorkQueueComponent {
  @Input() work: WorkEntry[] = [];
  @Output() selectRole = new EventEmitter<string>();
  cols = ['role', 'task', 'state', 'age', 'new'];

  /** Busy: how close this run is to max_attempts. Idle: what it finished last. */
  sub(row: WorkEntry): string {
    if (row.task) {
      return row.attempt && row.max_attempts ? `attempt ${row.attempt}/${row.max_attempts}` : '';
    }
    return row.last_completed ? `last: ${row.last_completed}` : '';
  }

  formatAge(seconds?: number): string {
    if (seconds == null) return '—';
    if (seconds < 60) return `${seconds}s`;
    const m = Math.floor(seconds / 60);
    if (m < 60) return `${m}m`;
    return `${Math.floor(m / 60)}h ${m % 60}m`;
  }
}
