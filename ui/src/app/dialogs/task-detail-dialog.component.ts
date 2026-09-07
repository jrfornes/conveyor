import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { ConveyorTask, WorkEntry } from '../models';
import { DetailRailComponent } from '../detail-rail/detail-rail.component';

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
        [work]="data.work"
        [selectedTask]="data.taskName"
        [task]="data.task"
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
  constructor(@Inject(MAT_DIALOG_DATA) public data: TaskDetailDialogData) {}
}
