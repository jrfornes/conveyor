import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { WorkflowPreset } from '../models';

@Component({
  selector: 'app-workflow-table',
  standalone: true,
  imports: [MatTableModule, MatButtonModule],
  template: `
    @if (!items.length) {
      <div class="empty">
        <p>No workflows yet.</p>
        <button mat-flat-button (click)="create.emit()">New workflow</button>
      </div>
    } @else {
      <table mat-table [dataSource]="items" class="workflows">
        <ng-container matColumnDef="name">
          <th mat-header-cell *matHeaderCellDef>Name</th>
          <td mat-cell *matCellDef="let row">
            <button mat-button class="namelink" (click)="open.emit(row.slug)">
              {{ row.name }}
            </button>
            @if (row.description) {
              <div class="desc">{{ row.description }}</div>
            }
          </td>
        </ng-container>

        <ng-container matColumnDef="roles">
          <th mat-header-cell *matHeaderCellDef>Roles</th>
          <td mat-cell *matCellDef="let row" class="mono">{{ row.roles.join(' → ') }}</td>
        </ng-container>

        <ng-container matColumnDef="gate">
          <th mat-header-cell *matHeaderCellDef>Gate</th>
          <td mat-cell *matCellDef="let row" class="mono">
            @if (row.gate) {
              <span class="gate">after {{ row.gate }}</span>
            } @else {
              <span class="muted">—</span>
            }
          </td>
        </ng-container>

        <ng-container matColumnDef="status">
          <th mat-header-cell *matHeaderCellDef>Status</th>
          <td mat-cell *matCellDef="let row">
            @if (row.active) {
              <span class="dot live"></span><span class="mono">active</span>
            } @else if (row.modified) {
              <span class="dot mod"></span><span class="mono">modified</span>
            }
          </td>
        </ng-container>

        <ng-container matColumnDef="file">
          <th mat-header-cell *matHeaderCellDef>File</th>
          <td mat-cell *matCellDef="let row" class="mono muted">{{ row.file }}</td>
        </ng-container>

        <tr mat-header-row *matHeaderRowDef="cols"></tr>
        <tr mat-row *matRowDef="let row; columns: cols"></tr>
      </table>
    }
  `,
  styles: `
    .workflows { width: 100%; background: #fff; }
    td { font-size: 13px; }
    .namelink { padding: 0; min-width: 0; font-weight: 500; }
    .desc { font-size: 12px; color: rgba(0,0,0,0.6); padding-bottom: 6px; }
    .mono { font-family: 'Roboto Mono', ui-monospace, monospace; }
    .muted { color: rgba(0,0,0,0.5); }
    .gate { color: #8a6a12; }
    .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
    .dot.live { background: #2e7d4f; }
    .dot.mod { background: #d6a633; }
    .empty { padding: 48px; text-align: center; opacity: 0.85; }
  `,
})
export class WorkflowTableComponent {
  @Input() items: WorkflowPreset[] = [];
  @Output() open = new EventEmitter<string>();
  @Output() create = new EventEmitter<void>();

  cols = ['name', 'roles', 'gate', 'status', 'file'];
}
