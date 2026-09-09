import { Component, OnDestroy, OnInit, effect } from '@angular/core';
import { Router, RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import {
  MatSnackBar,
  MatSnackBarModule,
  MatSnackBarRef,
  TextOnlySnackBar,
} from '@angular/material/snack-bar';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { UiStateService } from '../services/ui-state.service';
import { HeaderComponent } from '../header/header.component';
import { NewTaskDialogComponent } from '../dialogs/new-task-dialog.component';
import { ImportDialogComponent } from '../dialogs/import-dialog.component';
import { ConfirmDialogComponent } from '../dialogs/confirm-dialog.component';
import { openImportSummary, runPostImportGrading } from '../import-flow';

/**
 * How long the mirrored error snackbar stays up. Long enough to read a server
 * message without hurrying, short enough that an ignored one stops covering the
 * page. The strip above it has no timer at all.
 */
const ERROR_SNACK_MS = 12000;

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    RouterModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
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
      [errors]="ui.history()"
      (newTask)="openNewTask()"
      (importTickets)="openImport()"
      (start)="mutate('start')"
      (stop)="onStop()"
      (clearErrors)="ui.clearHistory()"
    ></app-header>

    @if (ui.actionError(); as err) {
      <div class="error-strip" role="alert">
        <span class="error-text">{{ err.message }}</span>
        @if (err.count > 1) {
          <span class="error-count">×{{ err.count }}</span>
        }
        <button
          mat-icon-button
          class="error-dismiss"
          aria-label="Dismiss error"
          (click)="ui.dismissError()"
        >
          <mat-icon>close</mat-icon>
        </button>
      </div>
    }

    @if (ui.pollError(); as poll) {
      <div class="poll-strip" role="status">
        {{ poll }} — showing the last known state
      </div>
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
      display: flex;
      align-items: center;
      gap: 8px;
      background: #ffebee;
      color: #b71c1c;
      padding: 6px 6px 6px 12px;
      font-size: 13px;
      border-bottom: 1px solid #ef9a9a;
    }
    .error-text { flex: 1; min-width: 0; overflow-wrap: anywhere; }
    .error-count { font-variant-numeric: tabular-nums; opacity: 0.75; }
    .error-dismiss { flex: none; color: inherit; }
    .poll-strip {
      background: #fff8e1;
      color: #8d6e00;
      padding: 4px 12px;
      font-size: 12px;
      border-bottom: 1px solid #ffe082;
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
  /** The snackbar mirroring the current action error, while one is on screen. */
  private errRef?: MatSnackBarRef<TextOnlySnackBar>;

  constructor(
    public ui: UiStateService,
    private api: ConveyorApiService,
    private dialog: MatDialog,
    private snack: MatSnackBar,
    private router: Router,
  ) {
    // The strip sits at the top of the shell, but most actions fire from a rail
    // or a dialog far away from it. Mirror the error into the snackbar the
    // success toasts already use, so it lands where the operator is looking.
    //
    // This copy times out, unlike the strip: it overlays the bottom of the
    // page, so leaving it up forever would cover the very controls the operator
    // needs to recover. Nothing is lost when it goes — the strip holds the
    // error until it is dismissed, and the history holds it after that. Only an
    // explicit Dismiss clears the error itself.
    effect(() => {
      const err = this.ui.actionError();
      this.errRef?.dismiss();
      this.errRef = undefined;
      if (!err) return;
      const label = err.count > 1 ? `${err.message} (×${err.count})` : err.message;
      const ref = this.snack.open(label, 'Dismiss', {
        duration: ERROR_SNACK_MS,
        panelClass: 'error-snack',
      });
      ref.onAction().subscribe(() => this.ui.dismissError());
      this.errRef = ref;
    });
  }

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
    this.errRef?.dismiss();
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
      this.ui.startAction();
      this.api.importTickets(v.source, v.title, v.body).subscribe({
        next: (r) => {
          openImportSummary(this.dialog, r.message || 'Imported');
          runPostImportGrading(this.api, this.ui, r.message || '', v.grade);
        },
        error: (e) => {
          this.ui.busy.set(false);
          this.ui.fail(e, 'Import failed');
        },
      });
    });
  }

  mutate(action: string, payload?: unknown): void {
    this.ui.startAction();
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
