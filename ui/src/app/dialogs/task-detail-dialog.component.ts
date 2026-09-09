import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { ConveyorTask, WorkEntry } from '../models';
import { DetailRailComponent } from '../detail-rail/detail-rail.component';
import { UiStateService } from '../services/ui-state.service';

/** Opening snapshot; the dialog reads live values off the state poll where it can. */
export interface TaskDetailDialogData {
  taskName: string;
  task: ConveyorTask | null;
  work: WorkEntry[];
}

@Component({
  selector: 'app-task-detail-dialog',
  standalone: true,
  imports: [MatDialogModule, MatButtonModule, DetailRailComponent],
  template: `
    <h2 mat-dialog-title>{{ data.taskName }}</h2>
    <mat-dialog-content>
      <app-detail-rail
        [work]="work"
        [selectedTask]="data.taskName"
        [task]="task"
      ></app-detail-rail>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Close</button>
    </mat-dialog-actions>
  `,
  styles: `
    mat-dialog-content {
      padding-top: 4px;
      max-height: min(70vh, 720px);
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    app-detail-rail {
      flex: 1;
      min-height: 0;
      display: block;
    }
  `,
})
export class TaskDetailDialogComponent {
  constructor(
    @Inject(MAT_DIALOG_DATA) public data: TaskDetailDialogData,
    private ui: UiStateService,
  ) {}

  /** Live off the state poll: the queue keeps moving while the dialog is open. */
  get work(): WorkEntry[] {
    return this.ui.state()?.work ?? this.data.work;
  }

  /** Same for the board row, whose audit and retry counts change mid-run. */
  get task(): ConveyorTask | null {
    const tasks = this.ui.state()?.tasks;
    if (!tasks) return this.data.task;
    return tasks.find((t) => t.name === this.data.taskName) ?? this.data.task;
  }
}
