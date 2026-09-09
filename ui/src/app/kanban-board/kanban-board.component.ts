import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { ConveyorTask, RoleAvatar } from '../models';
import { formatTokens } from '../util';

@Component({
  selector: 'app-kanban-board',
  standalone: true,
  imports: [MatCardModule, MatButtonModule, MatIconModule],
  template: `
    <div class="board">
      @for (lane of lanes; track lane) {
        <section class="column">
          <h3>
            @if (avatars[lane]; as av) {
              <span class="lane-avatar" [style.background]="av.color" [title]="av.owns">
                <mat-icon>{{ av.icon }}</mat-icon>
              </span>
            }
            {{ displayLane(lane) }}
            <span class="count">{{ tasksInLane(lane).length }}</span>
          </h3>
          <div class="cards">
            @for (task of tasksInLane(lane); track task.name) {
              <mat-card
                class="card"
                [class.selected]="task.name === selectedTask"
                (click)="selectTask.emit(task.name)"
              >
                <mat-card-header>
                  <mat-card-title>{{ task.name }}</mat-card-title>
                </mat-card-header>
                <mat-card-content>
                  <span class="audit">audit {{ task.audit_count }}</span>
                  @if (task.retry_count > 0) {
                    <span class="retry">retry {{ task.retry_count }}</span>
                  }
                  @if (task.run_count) {
                    <span class="tok" [title]="tokTitle(task)">tok {{ tok(task) }}</span>
                  }
                  <div class="task-id">{{ task.task_id }}</div>
                </mat-card-content>
                @if (lane === 'needs-human' || lane === 'done') {
                  <mat-card-actions>
                    @if (lane === 'needs-human') {
                      <button mat-button (click)="resumeTask.emit(task.name); $event.stopPropagation()">Resume</button>
                    }
                    <button mat-button color="warn" (click)="deleteTask.emit(task.name); $event.stopPropagation()">Delete</button>
                  </mat-card-actions>
                }
              </mat-card>
            }
          </div>
        </section>
      }
    </div>
  `,
  styles: `
    :host {
      display: block;
      height: 100%;
      min-height: 0;
    }
    .board {
      display: flex;
      gap: 8px;
      height: 100%;
      overflow-x: auto;
      padding: 8px 12px;
      box-sizing: border-box;
      background: var(--mat-sys-surface, #faf9fd);
    }
    .column {
      flex: 1 1 184px;
      min-width: 180px;
      display: flex;
      flex-direction: column;
      min-height: 0;
      padding: 6px;
      border-radius: 10px;
      background: var(--mat-sys-surface-container, rgba(0, 0, 0, 0.04));
    }
    h3 {
      margin: 0 0 6px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--mat-sys-on-surface-variant, rgba(0, 0, 0, 0.6));
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .count {
      margin-left: auto;
      font-weight: 500;
      letter-spacing: 0;
      text-transform: none;
      opacity: 0.7;
    }
    .lane-avatar {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      color: #fff;
      flex: none;
      mat-icon { font-size: 13px; width: 13px; height: 13px; }
    }
    .cards {
      flex: 1;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-height: 44px;
    }
    .card {
      cursor: pointer;
      &.selected { outline: 2px solid var(--mat-sys-primary, #1976d2); }
    }
    .retry { font-size: 12px; color: #c62828; margin-left: 8px; }
    /* Steel, the audit/meter end of the semantic palette, not an alarm colour:
       spend is information, and only max_tokens makes it a problem. */
    .tok { font-size: 12px; color: #546e7a; margin-left: 8px; font-family: monospace; }
    .audit { font-size: 12px; color: #1565c0; }
    .task-id { font-size: 11px; font-family: monospace; opacity: 0.7; margin-top: 2px; }
  `,
})
export class KanbanBoardComponent {
  @Input() lanes: string[] = [];
  @Input() avatars: Record<string, RoleAvatar> = {};
  @Input() tasks: ConveyorTask[] = [];
  @Input() selectedTask: string | null = null;
  @Output() selectTask = new EventEmitter<string>();
  @Output() resumeTask = new EventEmitter<string>();
  @Output() deleteTask = new EventEmitter<string>();

  displayLane(lane: string): string {
    if (lane === 'needs-human') return 'Needs human';
    return lane.charAt(0).toUpperCase() + lane.slice(1);
  }

  tasksInLane(lane: string): ConveyorTask[] {
    return this.tasks.filter((t) => t.lane === lane);
  }

  /** `-` when runs happened but none reported usage; never `0` for unknown. */
  tok(task: ConveyorTask): string {
    return formatTokens(task.tokens);
  }

  tokTitle(task: ConveyorTask): string {
    const runs = `${task.run_count} agent run${task.run_count === 1 ? '' : 's'}`;
    return task.tokens == null
      ? `${runs}, none of which reported token usage`
      : `${task.tokens.toLocaleString()} tokens over ${runs}`;
  }
}
