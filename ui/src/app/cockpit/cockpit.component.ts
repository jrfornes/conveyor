import { Component } from '@angular/core';
import { Router, RouterModule } from '@angular/router';
import { MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { UiStateService } from '../services/ui-state.service';
import { InboxItem } from '../models';
import { AttentionStripComponent } from '../attention-strip/attention-strip.component';
import { KanbanBoardComponent } from '../kanban-board/kanban-board.component';
import { InboxTableComponent } from '../inbox-table/inbox-table.component';
import { IntakeSettingsRailComponent } from '../intake/intake-settings-rail.component';
import { TaskDetailDialogComponent } from '../dialogs/task-detail-dialog.component';
import { SpecApproveDialogComponent } from '../dialogs/spec-approve-dialog.component';
import { ConfirmDialogComponent } from '../dialogs/confirm-dialog.component';
import { openImport } from '../import-flow';

@Component({
  selector: 'app-cockpit',
  standalone: true,
  imports: [
    RouterModule,
    MatDialogModule,
    MatSnackBarModule,
    AttentionStripComponent,
    KanbanBoardComponent,
    InboxTableComponent,
    IntakeSettingsRailComponent,
  ],
  template: `
    <app-attention-strip
      [items]="ui.state()?.needs_human ?? []"
      [awaiting]="awaiting"
      [approvals]="ui.state()?.approvals ?? []"
      (resume)="resume($event)"
      (deleteTask)="deleteTask($event)"
      (specApprove)="openSpecApprove($event)"
    ></app-attention-strip>

    @if (view === 'inbox') {
      <div class="inbox-layout" [class.with-rail]="showIntake">
        <div class="inbox-pane">
          <app-inbox-table
            [items]="ui.state()?.inbox ?? []"
            [intakeOpen]="showIntake"
            [intakeBusy]="ui.state()?.intake?.busy ?? false"
            [intakeBusyTask]="ui.state()?.intake?.task ?? null"
            [busy]="ui.busy()"
            [busyMessage]="ui.busyMessage()"
            (toggleIntake)="showIntake = !showIntake"
            (importTickets)="openImport()"
            (grade)="runIntake($event, false)"
            (start)="startWorking($event)"
          ></app-inbox-table>
        </div>
        @if (showIntake) {
          <app-intake-settings-rail></app-intake-settings-rail>
        }
      </div>
    } @else if (ui.state() && !ui.state()!.initialized) {
      <div class="empty">
        <p>Conveyor is not running in this repo yet.</p>
        <p>Run <code>conveyor start</code> or click <strong>Start</strong> in the header.</p>
      </div>
    } @else {
      <div class="board-layout">
        <div class="board-pane" [class.stale]="ui.stale()">
          <app-kanban-board
            [lanes]="ui.state()?.lanes ?? []"
            [avatars]="ui.state()?.avatars ?? {}"
            [tasks]="ui.state()?.tasks ?? []"
            [selectedTask]="selectedTask"
            (selectTask)="openTaskDetail($event)"
            (resumeTask)="resume($event)"
            (deleteTask)="deleteTask($event)"
          ></app-kanban-board>
        </div>
      </div>
    }
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-height: 0;
      height: 100%;
      overflow: hidden;
    }
    .empty {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 8px;
      opacity: 0.8;
    }
    .inbox-layout {
      flex: 1; min-height: 0; display: grid; grid-template-columns: 1fr;
    }
    .inbox-layout.with-rail {
      grid-template-columns: minmax(0, 1fr) minmax(0, 440px);
    }
    @media (max-width: 960px) {
      .inbox-layout.with-rail { grid-template-columns: 1fr; }
    }
    .inbox-pane { min-height: 0; overflow: auto; padding: 8px 12px; }
    .board-layout {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }
    .board-pane { flex: 1; min-height: 0; overflow: hidden; }
    .board-pane.stale { opacity: 0.6; transition: opacity 120ms ease; }
  `,
})
export class CockpitComponent {
  selectedTask: string | null = null;
  showIntake = false;
  private taskDetailRef: MatDialogRef<TaskDetailDialogComponent> | null = null;

  constructor(
    public ui: UiStateService,
    private api: ConveyorApiService,
    private dialog: MatDialog,
    private snack: MatSnackBar,
    private router: Router,
  ) {}

  get view(): 'inbox' | 'board' {
    return this.router.url.includes('/board') ? 'board' : 'inbox';
  }

  get awaiting(): InboxItem[] {
    return (this.ui.state()?.inbox ?? []).filter((i) => i.status === 'awaiting-approval');
  }

  openTaskDetail(taskName: string): void {
    const task = (this.ui.state()?.tasks ?? []).find((t) => t.name === taskName) ?? null;
    this.selectedTask = taskName;
    if (this.taskDetailRef) {
      this.taskDetailRef.close();
      this.taskDetailRef = null;
    }
    this.taskDetailRef = this.dialog.open(TaskDetailDialogComponent, {
      width: '900px',
      maxWidth: '95vw',
      maxHeight: '90vh',
      panelClass: 'task-detail-dialog',
      data: {
        taskName,
        task,
        work: this.ui.state()?.work ?? [],
      },
    });
    this.taskDetailRef.afterClosed().subscribe(() => {
      this.taskDetailRef = null;
      if (this.selectedTask === taskName) this.selectedTask = null;
    });
  }

  openImport(): void {
    openImport(this.dialog, this.api, this.ui);
  }

  runIntake(id: string, improve: boolean): void {
    this.mutate('intake', { id, improve });
  }

  openSpecApprove(id: string): void {
    const approval = (this.ui.state()?.approvals ?? []).find((a) => a.id === id);
    if (!approval) return;
    this.api.task(approval.task).subscribe({
      next: (t) => {
        const ref = this.dialog.open(SpecApproveDialogComponent, {
          width: '640px',
          data: { approval, taskText: t.text },
        });
        ref.afterClosed().subscribe((v) => {
          if (!v) return;
          if (v.action === 'approve') this.mutate('approve', { id });
          else this.mutate('reject', { id, comments: v.comments });
        });
      },
      error: (e) => {
        this.ui.fail(e, 'Load failed');
      },
    });
  }

  startWorking(row: InboxItem): void {
    const name = row.task_name && row.task_name !== '-' ? row.task_name : row.id;
    this.ui.startAction();
    this.api.startTask(name).subscribe({
      next: (r) => {
        this.snack.open(r.message ?? 'Queued', undefined, { duration: 3000 });
        if (this.ui.state()?.running) return this.settleOnBoard();
        this.dialog
          .open(ConfirmDialogComponent, {
            width: '440px',
            data: {
              title: 'Start the loops?',
              body: `${name} is queued, but the loops are stopped so nothing will pick it up yet.`,
              code: 'conveyor start',
              confirmLabel: 'Start loops',
            },
          })
          .afterClosed()
          .subscribe((ok) => {
            if (!ok) return this.settleOnBoard();
            this.api.start().subscribe({
              next: (s) => {
                this.snack.open(s.message ?? 'Started', undefined, { duration: 3000 });
                this.settleOnBoard();
              },
              error: (e) => {
                this.ui.fail(e, 'Start failed');
                this.settleOnBoard();
              },
            });
          });
      },
      error: (e) => {
        this.ui.busy.set(false);
        this.ui.fail(e, 'Start-task failed');
      },
    });
  }

  private settleOnBoard(): void {
    this.ui.busy.set(false);
    this.ui.refresh();
    void this.router.navigateByUrl('/board');
  }

  resume(task: string): void {
    this.mutate('resume', { task });
  }

  deleteTask(name: string): void {
    const parked = (this.ui.state()?.needs_human ?? []).some((i) => i.task === name);
    this.dialog
      .open(ConfirmDialogComponent, {
        width: '440px',
        data: {
          title: `Delete ${name}?`,
          body:
            'Removes the board row' +
            (parked ? ' and its needs-human entry' : '') +
            ' and the audit fingerprints, so re-creating this name is challenged again. ' +
            'tasks/' + name + '.md and the handoffs already in sent/ are kept.',
          code: `conveyor task ${name} --delete`,
          confirmLabel: 'Delete',
          warn: true,
        },
      })
      .afterClosed()
      .subscribe((ok) => {
        if (ok) this.mutate('delete', { name });
      });
  }

  mutate(action: string, payload?: unknown): void {
    this.ui.startAction();
    let req;
    switch (action) {
      case 'delete':
        req = this.api.deleteTask((payload as { name: string }).name);
        break;
      case 'resume':
        req = this.api.resume((payload as { task: string }).task);
        break;
      case 'intake': {
        const p = payload as { id: string; improve?: boolean; comments?: string };
        req = this.api.intake(p.id, !!p.improve, p.comments);
        break;
      }
      case 'approve':
        req = this.api.approve((payload as { id: string }).id);
        break;
      case 'reject': {
        const p = payload as { id: string; comments: string };
        req = this.api.reject(p.id, p.comments);
        break;
      }
      default:
        this.ui.busy.set(false);
        return;
    }
    req.subscribe({
      next: (r) => {
        this.ui.busy.set(false);
        this.snack.open(r.message ?? 'OK', undefined, { duration: 3000 });
        this.ui.refresh();
      },
      error: (e) => {
        this.ui.busy.set(false);
        this.ui.fail(e);
      },
    });
  }
}
