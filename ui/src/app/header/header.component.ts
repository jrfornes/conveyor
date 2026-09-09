import { Component, EventEmitter, Input, Output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatBadgeModule } from '@angular/material/badge';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { WorkflowRef } from '../models';
import { ErrorEntry } from '../services/ui-state.service';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [
    RouterLink,
    MatToolbarModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatBadgeModule,
    MatIconModule,
    MatMenuModule,
    MatTooltipModule,
  ],
  template: `
    <mat-toolbar color="primary" class="header">
      <span class="title">Conveyor</span>
      <span class="sep">·</span>
      <span class="repo">{{ title }}</span>
      @if (workflow) {
        <span class="workflow" [matTooltip]="workflow.chain">{{ workflow.name }}</span>
      }
      <span
        class="live-dot"
        [class.live]="live"
        [class.dead]="!live"
        matTooltip="{{ live ? 'Connected' : 'Poll failed — showing the last known state' }}"
      ></span>
      <mat-button-toggle-group [value]="view" class="view-toggle" hideSingleSelectionIndicator>
        <mat-button-toggle value="inbox" routerLink="/inbox">Inbox</mat-button-toggle>
        <mat-button-toggle value="board" routerLink="/board">Board</mat-button-toggle>
        <mat-button-toggle value="workflow" routerLink="/workflow">Workflow</mat-button-toggle>
        <mat-button-toggle value="roles" routerLink="/roles">Roles</mat-button-toggle>
      </mat-button-toggle-group>
      <span class="spacer"></span>
      <span class="running-label">{{ statusText }}</span>
      @if (errors.length) {
        <button
          mat-icon-button
          class="error-log-button"
          [matMenuTriggerFor]="errorMenu"
          [matBadge]="errors.length"
          matBadgeSize="small"
          matBadgeColor="warn"
          matTooltip="Recent failures"
          aria-label="Recent failures"
        >
          <mat-icon>history</mat-icon>
        </button>
        <mat-menu #errorMenu="matMenu">
          <div class="error-log">
            <div class="error-log-head">Recent failures</div>
            @for (e of errors; track e.id) {
              <div class="error-log-row" [class.poll]="e.kind === 'poll'">
                <span class="when">{{ clock(e.at) }}</span>
                <span class="what">{{ e.message }}</span>
                @if (e.count > 1) {
                  <span class="times">×{{ e.count }}</span>
                }
              </div>
            }
          </div>
          <button mat-menu-item (click)="clearErrors.emit()">Clear</button>
        </mat-menu>
      }
      <button mat-stroked-button (click)="importTickets.emit()" [disabled]="busy">Import</button>
      <button mat-stroked-button (click)="start.emit()" [disabled]="busy || running">Start</button>
      <button mat-stroked-button (click)="stop.emit()" [disabled]="busy || !running">Stop</button>
      <button mat-flat-button (click)="newTask.emit()" [disabled]="busy">New task</button>
    </mat-toolbar>
  `,
  styles: `
    .header { gap: 6px; }
    .title { font-weight: 600; letter-spacing: 0.02em; }
    .sep, .repo { opacity: 0.85; }
    .workflow { font-size: 12px; opacity: 0.8; margin-left: 6px; }
    .spacer { flex: 1; }
    .running-label { font-size: 13px; margin-right: 8px; opacity: 0.9; }
    .view-toggle { margin-left: 12px; }
    .error-log-button { margin-right: 10px; }
    .error-log { max-width: 460px; padding: 4px 0; }
    .error-log-head {
      padding: 4px 14px 6px;
      font-size: 11px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      opacity: 0.6;
    }
    .error-log-row {
      display: flex;
      gap: 8px;
      padding: 4px 14px;
      font-size: 12px;
      line-height: 1.35;
      color: #b71c1c;
      /* Poll drop-outs are noise next to a failed action; keep them legible
         but visibly secondary. */
      &.poll { color: rgba(0, 0, 0, 0.6); }
    }
    .error-log-row .when { flex: none; font-variant-numeric: tabular-nums; opacity: 0.7; }
    .error-log-row .what { flex: 1; min-width: 0; overflow-wrap: anywhere; }
    .error-log-row .times { flex: none; font-variant-numeric: tabular-nums; opacity: 0.7; }
    .live-dot {
      width: 8px; height: 8px; border-radius: 50%; margin-left: 6px;
      &.live { background: #2e7d32; box-shadow: 0 0 6px #2e7d32; }
      &.dead { background: #9e9e9e; }
    }
  `,
})
export class HeaderComponent {
  @Input() title = '';
  @Input() workflow: WorkflowRef | null = null;
  @Input() view: 'inbox' | 'board' | 'workflow' | 'roles' = 'inbox';
  @Input() live = false;
  @Input() running = false;
  @Input() initialized = false;
  @Input() busy = false;
  /** Poll is failing but a previous state is still on screen. */
  @Input() stale = false;
  /** Recent failures, newest first. */
  @Input() errors: ErrorEntry[] = [];
  @Output() newTask = new EventEmitter<void>();
  @Output() importTickets = new EventEmitter<void>();
  @Output() start = new EventEmitter<void>();
  @Output() stop = new EventEmitter<void>();
  @Output() clearErrors = new EventEmitter<void>();

  clock(at: Date): string {
    return at.toLocaleTimeString([], { hour12: false });
  }

  get statusText(): string {
    if (!this.initialized) return 'not initialized';
    const loops = this.running ? 'loops running' : 'loops stopped';
    return this.stale ? `last known: ${loops}` : loops;
  }
}
