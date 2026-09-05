import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router, RouterModule } from '@angular/router';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { UiStateService } from '../services/ui-state.service';
import { HeaderComponent } from '../header/header.component';
import { NewTaskDialogComponent } from '../dialogs/new-task-dialog.component';
import { ImportDialogComponent } from '../dialogs/import-dialog.component';
import { ConfirmDialogComponent } from '../dialogs/confirm-dialog.component';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    RouterModule,
    MatDialogModule,
    MatSnackBarModule,
    HeaderComponent,
  ],
  template: `
    <app-header
      [title]="ui.state()?.title ?? '…'"
      [workflow]="ui.state()?.workflow ?? null"
      [view]="view"
      [live]="ui.live()"
      [running]="ui.state()?.running ?? false"
      [initialized]="ui.state()?.initialized ?? false"
      [busy]="ui.busy()"
      [stale]="ui.stale()"
      (newTask)="openNewTask()"
      (importTickets)="openImport()"
      (start)="mutate('start')"
      (stop)="onStop()"
    ></app-header>

    @if (ui.error()) {
      <div class="error-strip" role="alert">{{ ui.error() }}</div>
    }

    <div class="shell-body">
      <router-outlet />
    </div>
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }
    .error-strip {
      background: #ffebee;
      color: #b71c1c;
      padding: 6px 16px;
      font-size: 13px;
      border-bottom: 1px solid #ef9a9a;
    }
    .shell-body {
      flex: 1;
      min-height: 0;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .shell-body > *:not(router-outlet) {
      flex: 1;
      min-height: 0;
    }
  `,
})
export class AppShellComponent implements OnInit, OnDestroy {
  constructor(
    public ui: UiStateService,
    private api: ConveyorApiService,
    private dialog: MatDialog,
    private snack: MatSnackBar,
    private router: Router,
  ) {}

  get view(): 'inbox' | 'board' | 'workflow' | 'roles' {
    // First segment, not `includes`: a slug like /workflow/board-refresh must
    // not light the Board toggle.
    const seg = this.router.url.split(/[?#]/)[0].split('/')[1] ?? '';
    return seg === 'board' || seg === 'workflow' || seg === 'roles' ? seg : 'inbox';
  }

  ngOnInit(): void {
    this.ui.startPolling();
  }

  ngOnDestroy(): void {
    this.ui.stopPolling();
  }

  onStop(): void {
    const busy = (this.ui.state()?.work ?? []).filter((w) => w.state === 'busy');
    if (!busy.length) {
      this.mutate('stop', false);
      return;
    }
    this.dialog
      .open(ConfirmDialogComponent, {
        width: '440px',
        data: {
          title: 'Stop loops?',
          body:
            'The current agent run will finish unless you stop now. ' +
            'If you stop now, whatever is in in_process is retried on the next Start.',
          items: busy.map((w) => {
            const parts = [w.role];
            if (w.task) parts.push(w.task);
            if (w.attempt && w.max_attempts) parts.push(`attempt ${w.attempt}/${w.max_attempts}`);
            return parts.join(' · ');
          }),
          code: 'conveyor stop\nconveyor stop --now',
          confirmLabel: 'Stop',
          secondaryLabel: 'Stop now',
        },
      })
      .afterClosed()
      .subscribe((ok) => {
        if (ok === true) this.mutate('stop', false);
        else if (ok === 'secondary') this.mutate('stop', true);
      });
  }

  openNewTask(): void {
    const ref = this.dialog.open(NewTaskDialogComponent, { width: '520px' });
    ref.afterClosed().subscribe((v) => {
      if (v) this.mutate('task', v);
    });
  }

  openImport(): void {
    const ref = this.dialog.open(ImportDialogComponent, { width: '560px' });
    ref.afterClosed().subscribe((v) => {
      if (!v) return;
      this.ui.busy.set(true);
      this.api.importTickets(v.source, v.title, v.body).subscribe({
        next: (r) => {
          this.snack.open(r.message || 'Imported', undefined, { duration: 3000 });
          const ids = (r.message || '')
            .split('\n')
            .map((line) => line.match(/^imported (\S+)/)?.[1])
            .filter((x): x is string => !!x);
          const gradeNext = (i: number) => {
            if (!v.grade || i >= ids.length) {
              this.ui.busy.set(false);
              this.ui.refresh();
              return;
            }
            this.api.intake(ids[i], false).subscribe({
              next: () => gradeNext(i + 1),
              error: (e) => {
                this.ui.busy.set(false);
                this.ui.fail(e, 'Grade failed');
                this.ui.refresh();
              },
            });
          };
          gradeNext(0);
        },
        error: (e) => {
          this.ui.busy.set(false);
          this.ui.fail(e, 'Import failed');
        },
      });
    });
  }

  mutate(action: string, payload?: unknown): void {
    this.ui.busy.set(true);
    let req;
    switch (action) {
      case 'start':
        req = this.api.start();
        break;
      case 'stop':
        req = this.api.stop(!!payload);
        break;
      case 'task':
        req = this.api.createTask(
          (payload as { name: string; text: string }).name,
          (payload as { name: string; text: string }).text,
        );
        break;
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
