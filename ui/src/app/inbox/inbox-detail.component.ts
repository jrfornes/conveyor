import { Component, DestroyRef, OnInit, computed, effect, inject, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { UiStateService } from '../services/ui-state.service';
import { InboxDetail, InboxItem } from '../models';
import { ConfirmDialogComponent } from '../dialogs/confirm-dialog.component';
import { EditSourceDialogComponent } from '../dialogs/edit-source-dialog.component';
import { AttachmentsDialogComponent } from '../dialogs/attachments-dialog.component';
import { IntakeReviewDialogComponent } from '../dialogs/intake-review-dialog.component';
import { openImportSummary } from '../import-flow';
import {
  attachmentLabel,
  canApproveInbox,
  canEditInboxSource,
  canGradeInbox,
  canRefreshInbox,
  canSkipInbox,
  canStartInbox,
  countsFromAttachments,
  displayInboxId,
  inboxNextStep,
  isHttpUrl,
} from './inbox-actions';

@Component({
  selector: 'app-inbox-detail',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
  template: `
    <div class="page">
      <a mat-button class="crumb" routerLink="/inbox">‹ Inbox</a>

      @if (error) {
        <div class="err" role="alert">{{ error }}</div>
      }

      @if (loading && !item) {
        <mat-spinner diameter="28"></mat-spinner>
      }

      @if (item; as it) {
        <div class="head">
          <h2>{{ it.title || it.id }}</h2>
          <span class="pill" [class]="it.status">{{ it.status }}</span>
          @if (it.grade && it.grade !== '-') {
            <span class="pill grade" [class]="it.grade.toLowerCase()">{{ it.grade }}</span>
          }
        </div>

        <p class="meta mono">
          {{ displayId(it) }}
          @if (displayId(it) !== it.id) {
            <span class="muted"> · {{ it.id }}</span>
          }
          · {{ it.source }}
          @if (it.created_at && it.created_at !== '-') {
            · {{ it.created_at }}
          }
          @if (taskName(it); as name) {
            · task {{ name }}
          }
        </p>
        @if (isHttpUrl(it.url)) {
          <p class="meta">
            <a [href]="it.url" target="_blank" rel="noopener">Open in {{ it.source }}</a>
          </p>
        }

        @if (intakeBusy()) {
          <div class="busy-note" role="status">
            Ticket-reviewer is busy{{ intakeTask() ? ' with ' + intakeTask() : '' }} —
            Grade and Improve wait until it finishes.
          </div>
        }

        <p class="next">{{ inboxNextStep(it) }}</p>

        <div class="actions">
          @if (canRefreshInbox(it)) {
            <button mat-stroked-button [disabled]="busy()" (click)="refreshImport()">
              Fetch again
            </button>
          }
          @if (canEditInboxSource(it)) {
            <button mat-stroked-button [disabled]="busy()" (click)="editSource()">
              Edit source
            </button>
          }
          @if (it.attachments?.length) {
            <button mat-stroked-button [disabled]="busy() || it.status !== 'imported'"
                    (click)="editAttachments()">
              Attachments
            </button>
          }
          @if (canGradeInbox(it)) {
            <button mat-stroked-button [disabled]="busy() || intakeBusy()"
                    [matTooltip]="intakeBusy() ? 'Ticket-reviewer is busy; wait for it to finish' : ''"
                    (click)="runIntake(false)">Grade</button>
            <button mat-stroked-button [disabled]="busy() || intakeBusy()"
                    [matTooltip]="intakeBusy() ? 'Ticket-reviewer is busy; wait for it to finish' : ''"
                    (click)="runIntake(true)">Improve</button>
          }
          @if (canApproveInbox(it)) {
            <button mat-flat-button color="primary" [disabled]="busy()" (click)="review()">
              Review & approve
            </button>
          }
          @if (canStartInbox(it)) {
            <button mat-flat-button color="primary" [disabled]="busy()" (click)="startWorking()">
              Start
            </button>
          }
          @if (it.status === 'started') {
            <a mat-stroked-button routerLink="/board">Open board</a>
          }
          @if (canSkipInbox(it)) {
            <button mat-button color="warn" [disabled]="busy()" (click)="skip()">Skip</button>
          }
        </div>

        @if (canGradeInbox(it)) {
          <mat-form-field appearance="outline" class="full">
            <mat-label>Notes for Improve</mat-label>
            <textarea matInput rows="3" [(ngModel)]="improveComments"
                      [disabled]="busy() || intakeBusy()"></textarea>
            <mat-hint>Written to comments.txt and fed to ticket-reviewer on Improve.</mat-hint>
          </mat-form-field>
        }

        <section>
          <h3>Original</h3>
          <pre class="mono pane">{{ it.source_md || '(empty)' }}</pre>
        </section>

        <section>
          <h3>Grade</h3>
          <pre class="mono pane">{{ it.grade_md || '(no grade yet)' }}</pre>
        </section>

        <section>
          <h3>Proposed task</h3>
          <pre class="mono pane">{{ it.proposed_md || '(none yet)' }}</pre>
        </section>

        @if (it.comments || it.comments_applied) {
          <section>
            <h3>Operator comments</h3>
            @if (it.comments) {
              <p class="caption">Pending — will be sent on the next Improve.</p>
              <pre class="mono pane">{{ it.comments }}</pre>
            }
            @if (it.comments_applied) {
              <p class="caption">Applied on the last Improve run.</p>
              <pre class="mono pane">{{ it.comments_applied }}</pre>
            }
          </section>
        }

        @if (it.attachments?.length) {
          <section>
            <h3>Attachments</h3>
            <p class="caption">
              Ticket-reviewer sees selected files on Grade or Improve.
              Video, audio, archives, and oversize files stay off.
            </p>
            <ul class="atts">
              @for (row of it.attachments; track row.id) {
                <li [class.off]="!row.selected">
                  <span>{{ row.filename }}</span>
                  <span class="muted">{{ attachmentLabel(row) }}{{ row.selected ? ' · selected' : '' }}</span>
                </li>
              }
            </ul>
          </section>
        }
      }
    </div>
  `,
  styles: `
    :host { display: block; height: 100%; overflow: auto; background: #f7f8fa; }
    .page { padding: 16px 20px 32px; display: flex; flex-direction: column; gap: 10px; max-width: 960px; }
    .crumb { align-self: flex-start; padding: 0; min-width: 0; }
    .head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .head h2 { margin: 0; font-size: 20px; font-weight: 500; }
    .pill {
      font-size: 11px; border: 1px solid #546e7a; color: #546e7a;
      border-radius: 10px; padding: 1px 8px;
    }
    .pill.ready, .pill.started, .pill.grade.ready { border-color: #2e7d4f; color: #2e7d4f; }
    .pill.imported, .pill.graded, .pill.awaiting-approval { border-color: #1565c0; color: #1565c0; }
    .pill.grading, .pill.improving, .pill.grade.gaps { border-color: #d6a633; color: #8a6a12; }
    .pill.skipped, .pill.grade.unusable, .pill.grade.unparsed { border-color: #c62828; color: #c62828; }
    .meta { margin: 0; font-size: 12px; color: rgba(0,0,0,0.6); }
    .muted { color: rgba(0,0,0,0.5); }
    .next { margin: 0; font-size: 13px; color: rgba(0,0,0,0.75); }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .busy-note, .err {
      padding: 8px 12px; border-radius: 6px; font-size: 12px;
    }
    .busy-note { background: #fff8e1; color: #8a6100; }
    .err { background: #ffebee; color: #b71c1c; }
    .full { width: 100%; }
    h3 {
      margin: 8px 0 6px; font-size: 12px; text-transform: uppercase;
      letter-spacing: 0.06em; color: rgba(0,0,0,0.55);
    }
    .caption { margin: 0 0 6px; font-size: 12px; color: rgba(0,0,0,0.6); }
    .pane {
      font-family: ui-monospace, monospace; font-size: 12px; white-space: pre-wrap;
      overflow: auto; max-height: 320px; background: #fff; padding: 10px 12px;
      border: 1px solid rgba(0,0,0,0.08); border-radius: 6px; margin: 0;
      overflow-wrap: anywhere;
    }
    .mono { font-family: 'Roboto Mono', ui-monospace, monospace; }
    .atts { list-style: none; margin: 0; padding: 0; background: #fff;
            border: 1px solid rgba(0,0,0,0.08); border-radius: 6px; }
    .atts li {
      display: flex; justify-content: space-between; gap: 12px;
      padding: 8px 12px; font-size: 13px; border-bottom: 1px solid rgba(0,0,0,0.06);
    }
    .atts li:last-child { border-bottom: 0; }
    .atts li.off { opacity: 0.65; }
  `,
})
export class InboxDetailComponent implements OnInit {
  private destroyRef = inject(DestroyRef);

  id = signal('');
  item: InboxDetail | null = null;
  loading = false;
  error = '';
  improveComments = '';
  fingerprint = '';

  displayId = displayInboxId;
  isHttpUrl = isHttpUrl;
  canRefreshInbox = canRefreshInbox;
  canEditInboxSource = canEditInboxSource;
  canGradeInbox = canGradeInbox;
  canApproveInbox = canApproveInbox;
  canStartInbox = canStartInbox;
  canSkipInbox = canSkipInbox;
  inboxNextStep = inboxNextStep;
  attachmentLabel = attachmentLabel;

  intakeBusy = computed(() => this.ui.state()?.intake?.busy ?? false);
  intakeTask = computed(() => this.ui.state()?.intake?.task ?? null);
  busy = computed(() => this.ui.busy());

  constructor(
    private api: ConveyorApiService,
    public ui: UiStateService,
    private snack: MatSnackBar,
    private dialog: MatDialog,
    private route: ActivatedRoute,
    private router: Router,
  ) {
    effect(() => {
      const iid = this.id();
      if (!iid) return;
      const row = (this.ui.state()?.inbox ?? []).find((i) => i.id === iid);
      const fp = row
        ? `${row.status}|${row.grade}|${row.has_grade}|${row.has_proposed}|${row.selected_count}|${row.attachment_count}`
        : '';
      untracked(() => this.reloadIfChanged(fp));
    });
  }

  ngOnInit(): void {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((p) => {
      this.id.set(p.get('id') ?? '');
      this.fingerprint = '';
      this.improveComments = '';
      this.load();
    });
  }

  taskName(it: InboxItem): string {
    const n = (it.task_name || '').trim();
    return n && n !== '-' ? n : '';
  }

  private reloadIfChanged(fp: string): void {
    if (!fp || fp === this.fingerprint) return;
    this.fingerprint = fp;
    this.load();
  }

  load(): void {
    const iid = this.id();
    if (!iid) return;
    this.loading = true;
    this.api.inboxItem(iid).subscribe({
      next: (d) => {
        this.item = d;
        this.error = '';
        this.loading = false;
        const counts = countsFromAttachments(d.attachments || []);
        this.fingerprint =
          `${d.status}|${d.grade}|${!!d.grade_md?.trim()}|${!!d.proposed_md?.trim()}|` +
          `${counts.selected_count}|${counts.attachment_count}`;
        if (!this.improveComments && d.comments) this.improveComments = d.comments;
      },
      error: (e) => {
        this.loading = false;
        this.item = null;
        this.error = e?.error?.error ?? e.message ?? 'Failed to load inbox item';
      },
    });
  }

  refreshImport(): void {
    const iid = this.id();
    this.ui.busy.set(true);
    this.api.refreshImport(iid).subscribe({
      next: (r) => {
        this.ui.busy.set(false);
        openImportSummary(this.dialog, r.message ?? 'Refreshed', 'Refresh complete');
        this.ui.refresh();
        this.load();
      },
      error: (e) => this.fail(e, 'Fetch again failed'),
    });
  }

  editSource(): void {
    const it = this.item;
    if (!it) return;
    this.dialog
      .open(EditSourceDialogComponent, {
        width: '560px',
        data: { id: it.id, title: it.title, text: it.source_md || '' },
      })
      .afterClosed()
      .subscribe((text) => {
        if (text == null) return;
        this.ui.busy.set(true);
        this.api.replaceInboxSource(it.id, text).subscribe({
          next: (r) => this.ok(r.message ?? 'Replaced'),
          error: (e) => this.fail(e, 'Edit source failed'),
        });
      });
  }

  editAttachments(): void {
    const it = this.item;
    if (!it) return;
    this.dialog
      .open(AttachmentsDialogComponent, {
        width: '560px',
        data: {
          id: it.id,
          title: it.title,
          url: it.url,
          attachments: it.attachments || [],
        },
      })
      .afterClosed()
      .subscribe((select) => {
        if (select == null) return;
        this.ui.busy.set(true);
        this.api.inboxAttachments(it.id, select).subscribe({
          next: (r) => this.ok(r.message || 'Attachments updated'),
          error: (e) => this.fail(e, 'Attachments failed'),
        });
      });
  }

  runIntake(improve: boolean): void {
    const iid = this.id();
    this.ui.busy.set(true);
    const comments = improve ? this.improveComments : undefined;
    this.api.intake(iid, improve, comments).subscribe({
      next: (r) => {
        if (improve) this.improveComments = '';
        this.ok(r.message ?? 'OK');
      },
      error: (e) => this.fail(e, improve ? 'Improve failed' : 'Grade failed'),
    });
  }

  review(): void {
    const it = this.item;
    if (!it) return;
    this.api.intakeSettings().subscribe({
      next: (settings) => {
        this.dialog
          .open(IntakeReviewDialogComponent, {
            width: '900px',
            maxWidth: '95vw',
            panelClass: 'intake-review-dialog',
            data: {
              ...it,
              rubric: settings.rubric,
              grade_contract: settings.grade_contract,
            },
          })
          .afterClosed()
          .subscribe((v) => {
            if (!v) return;
            if (v.action === 'skip') {
              this.skip();
              return;
            }
            if (v.action === 'reject') {
              this.ui.busy.set(true);
              this.api.intake(it.id, true, v.comments).subscribe({
                next: (r) => this.ok(r.message ?? 'OK'),
                error: (e) => this.fail(e, 'Improve failed'),
              });
              return;
            }
            this.ui.busy.set(true);
            this.api.inboxApprove(
              it.id,
              v.name,
              v.action === 'edit-approve' ? v.text : undefined,
            ).subscribe({
              next: (r) => this.ok(r.message ?? 'OK'),
              error: (e) => this.fail(e, 'Approve failed'),
            });
          });
      },
      error: (e) => this.fail(e, 'Load failed'),
    });
  }

  skip(): void {
    this.ui.busy.set(true);
    this.api.inboxSkip(this.id()).subscribe({
      next: (r) => this.ok(r.message ?? 'Skipped'),
      error: (e) => this.fail(e, 'Skip failed'),
    });
  }

  startWorking(): void {
    const it = this.item;
    if (!it) return;
    const name = this.taskName(it) || it.id;
    this.ui.busy.set(true);
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
                this.fail(e, 'Start failed');
                this.settleOnBoard();
              },
            });
          });
      },
      error: (e) => this.fail(e, 'Start-task failed'),
    });
  }

  private settleOnBoard(): void {
    this.ui.busy.set(false);
    this.ui.refresh();
    void this.router.navigateByUrl('/board');
  }

  private ok(message: string): void {
    this.ui.busy.set(false);
    this.snack.open(message, undefined, { duration: 3000 });
    this.ui.refresh();
    this.load();
  }

  private fail(e: { error?: { error?: string }; message?: string }, fallback: string): void {
    this.ui.busy.set(false);
    this.ui.fail(e, fallback);
    this.ui.refresh();
  }
}
