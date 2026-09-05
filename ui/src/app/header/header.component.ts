import { Component, EventEmitter, Input, Output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatIconModule } from '@angular/material/icon';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { WorkflowRef } from '../models';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [
    RouterLink,
    MatToolbarModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatIconModule,
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
      <button mat-stroked-button (click)="importTickets.emit()" [disabled]="busy">Import</button>
      <button mat-stroked-button (click)="start.emit()" [disabled]="busy || running">Start</button>
      <button mat-stroked-button (click)="stop.emit()" [disabled]="busy || !running">Stop</button>
      <button mat-flat-button (click)="newTask.emit()" [disabled]="busy">New task</button>
    </mat-toolbar>
  `,
  styles: `
    .header { gap: 8px; min-height: 56px; }
    .title { font-weight: 600; letter-spacing: 0.02em; }
    .sep, .repo { opacity: 0.85; }
    .workflow { font-size: 12px; opacity: 0.8; margin-left: 8px; }
    .spacer { flex: 1; }
    .running-label { font-size: 13px; margin-right: 12px; opacity: 0.9; }
    .view-toggle { margin-left: 16px; }
    .live-dot {
      width: 10px; height: 10px; border-radius: 50%; margin-left: 8px;
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
  @Output() newTask = new EventEmitter<void>();
  @Output() importTickets = new EventEmitter<void>();
  @Output() start = new EventEmitter<void>();
  @Output() stop = new EventEmitter<void>();

  get statusText(): string {
    if (!this.initialized) return 'not initialized';
    const loops = this.running ? 'loops running' : 'loops stopped';
    return this.stale ? `last known: ${loops}` : loops;
  }
}
