import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { ConveyorTask, RoleAvatar } from '../models';

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
      gap: 12px;
      height: 100%;
      overflow-x: auto;
      padding: 12px 16px;
      box-sizing: border-box;
      background: var(--mat-sys-surface, #faf9fd);
    }
    .column {
      flex: 1 1 200px;
      min-width: 196px;
      display: flex;
      flex-direction: column;
      min-height: 0;
      padding: 8px;
      border-radius: 12px;
      background: var(--mat-sys-surface-container, rgba(0, 0, 0, 0.04));
    }
    h3 {
      margin: 0 0 8px;
      font-size: 13px;
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
      width: 20px;
      height: 20px;
      border-radius: 50%;
      color: #fff;
      flex: none;
      mat-icon { font-size: 14px; width: 14px; height: 14px; }
    }
    .cards {
      flex: 1;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 8px;
      min-height: 64px;
    }
    .card {
      cursor: pointer;
      &.selected { outline: 2px solid var(--mat-sys-primary, #1976d2); }
    }
    .retry { font-size: 12px; color: #c62828; margin-left: 8px; }
    .audit { font-size: 12px; color: #1565c0; }
    .task-id { font-size: 11px; font-family: monospace; opacity: 0.7; margin-top: 4px; }
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
}
