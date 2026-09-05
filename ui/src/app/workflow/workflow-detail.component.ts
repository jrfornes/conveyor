import { Component, OnInit, computed, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DestroyRef } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { UiStateService } from '../services/ui-state.service';
import { RoleAvatar, WorkflowDetail, WorkflowEdit, WorkflowState } from '../models';
import { BeltDiagramComponent } from './belt-diagram.component';
import { ConfirmDialogComponent } from '../dialogs/confirm-dialog.component';
import {
  WorkflowEditDialogComponent,
  WorkflowEditData,
} from '../dialogs/workflow-edit-dialog.component';

@Component({
  selector: 'app-workflow-detail',
  standalone: true,
  imports: [MatButtonModule, MatSnackBarModule, BeltDiagramComponent],
  template: `
    <div class="page">
      <button mat-button class="crumb" (click)="back()">‹ Workflows</button>

      @if (error) {
        <div class="err" role="alert">{{ error }}</div>
      }

      @if (wf; as w) {
        <div class="head">
          <h2>{{ w.name }}</h2>
          @if (w.active) {
            <span class="pill">active</span>
          } @else if (w.modified) {
            <span class="pill mod">modified</span>
          }
          <div class="actions">
            @if (!w.active) {
              @if (running()) {
                <span class="mono muted">stop loops to make active</span>
              } @else {
                <button mat-flat-button color="primary" [disabled]="busy"
                        (click)="makeActive()">Make active</button>
              }
            }
            @if (!(w.active && running())) {
              <button mat-stroked-button [disabled]="busy" (click)="edit()">Edit</button>
            }
            <button mat-button [disabled]="busy" (click)="duplicate()">Duplicate</button>
            @if (w.deletable) {
              <button mat-button color="warn" [disabled]="busy"
                      (click)="confirmDelete()">Delete</button>
            }
          </div>
        </div>

        @if (w.description) {
          <p class="desc">{{ w.description }}</p>
        }
        <p class="meta mono">{{ w.file }} · {{ w.roles.join(' → ') }}</p>

        <section>
          <h3>Belt</h3>
          <app-belt-diagram
            [roles]="beltRoles()"
            [routes]="w.routes"
            [gate]="w.gate"
            [marks]="w.marks"
            (select)="openRole($event)"
          ></app-belt-diagram>
          <p class="caption">
            Tasks arrive from Inbox or New task.
            @if (w.gate) {
              The first <code>ready</code> handoff after <code>{{ w.gate }}</code> is held
              in <code>.conveyor/approvals/pending/</code> and waits for you in the
              attention strip.
            } @else {
              No human gate. Every handoff goes straight to the next role's queue.
            }
          </p>
        </section>

        <section>
          <div class="roster-head">
            <h3>Roles on this belt</h3>
            <button mat-button (click)="openRoles()">
              Edit prompts, models and ceilings in Roles →
            </button>
          </div>
          <table class="roles">
            <thead>
              <tr>
                <th>#</th><th>Role</th><th>Owns</th><th>Model</th>
                <th>retries / min / attempts</th><th>Handoff</th>
              </tr>
            </thead>
            <tbody>
              @for (r of w.roles_detail; track r.name; let i = $index) {
                <tr>
                  <td class="mono">{{ i + 1 }}</td>
                  <td>
                    <button mat-button class="rolelink" (click)="openRole(r.name)">
                      {{ r.name }}
                    </button>
                  </td>
                  <td>{{ r.owns }}</td>
                  <td class="mono">{{ r.model ?? '—' }}</td>
                  <td class="mono">
                    @if (r.model) {
                      {{ r.max_retries }} / {{ r.max_minutes }} / {{ r.max_attempts }}
                    } @else {
                      —
                    }
                  </td>
                  <td class="mono">{{ r.handoff }}</td>
                </tr>
              }
            </tbody>
          </table>
          <p class="caption">
            Models and ceilings live in <code>conveyor.conf</code>, not in the workflow.
            A role shown as <code>—</code> gets its settings when this workflow is made
            active.
          </p>
        </section>
      }
    </div>
  `,
  styles: `
    :host { display: block; height: 100%; overflow: auto; background: #f7f8fa; }
    .page { padding: 16px 20px 32px; display: flex; flex-direction: column; gap: 12px; }
    .err { padding: 10px 14px; border-radius: 8px; font-size: 13px;
           background: #ffebee; color: #b71c1c; }
    .crumb { align-self: flex-start; padding: 0; min-width: 0; }
    .head { display: flex; align-items: center; gap: 10px; }
    .head h2 { margin: 0; font-size: 20px; font-weight: 500; }
    .actions { margin-left: auto; display: flex; align-items: center; gap: 6px; }
    .pill {
      font-size: 11px; border: 1px solid #2e7d4f; color: #2e7d4f;
      border-radius: 10px; padding: 1px 8px;
    }
    .pill.mod { border-color: #d6a633; color: #8a6a12; }
    .desc { margin: 0; font-size: 13px; color: rgba(0,0,0,0.75); }
    .meta { margin: 0; font-size: 12px; color: rgba(0,0,0,0.55); }
    .muted { color: rgba(0,0,0,0.55); font-size: 12px; }
    h3 {
      margin: 0 0 8px; font-size: 13px; text-transform: uppercase;
      letter-spacing: 0.06em; color: rgba(0,0,0,0.55);
    }
    .caption { font-size: 12px; color: rgba(0,0,0,0.6); margin: 8px 0 0; }
    .roster-head { display: flex; align-items: baseline; justify-content: space-between; }
    table.roles { width: 100%; border-collapse: collapse; font-size: 13px; background: #fff; }
    table.roles th {
      text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
      color: rgba(0,0,0,0.55); font-weight: 500; padding: 8px 10px;
      border-bottom: 1px solid rgba(0,0,0,0.12);
    }
    table.roles td { padding: 8px 10px; border-bottom: 1px solid rgba(0,0,0,0.06); }
    .mono { font-family: 'Roboto Mono', ui-monospace, monospace; }
    .rolelink { padding: 0; min-width: 0; }
  `,
})
export class WorkflowDetailComponent implements OnInit {
  private destroyRef = inject(DestroyRef);

  wf: WorkflowDetail | null = null;
  belt: WorkflowState | null = null;
  slug = '';
  busy = false;
  error = '';

  running = computed(() => this.ui.state()?.running ?? this.wf?.running ?? false);

  constructor(
    private api: ConveyorApiService,
    public ui: UiStateService,
    private snack: MatSnackBar,
    private dialog: MatDialog,
    private route: ActivatedRoute,
    private router: Router,
  ) {}

  ngOnInit(): void {
    // paramMap, not snapshot: navigating slug -> slug reuses this component,
    // so ngOnInit would not run again.
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((p) => {
      this.slug = p.get('slug') ?? '';
      this.load();
    });
    this.api.workflow().subscribe({ next: (w) => (this.belt = w), error: () => undefined });
  }

  load(): void {
    if (!this.slug) return;
    this.api.workflowDetail(this.slug).subscribe({
      next: (d) => {
        this.wf = d;
        this.error = '';
      },
      error: (e) => (this.error = e?.error?.error ?? e.message ?? 'Failed to load workflow'),
    });
  }

  beltRoles() {
    return (this.wf?.roles_detail ?? []).map((r) => ({
      name: r.name,
      avatar: r.avatar,
      in_workflow: true,
      text: '',
      hops: [],
    }));
  }

  back(): void {
    void this.router.navigate(['/workflow']);
  }

  openRoles(): void {
    void this.router.navigate(['/roles']);
  }

  openRole(name: string): void {
    void this.router.navigate(['/roles'], { queryParams: { role: name } });
  }

  // --- actions ----------------------------------------------------------

  private editorData(title: string, value: WorkflowEdit): WorkflowEditData {
    const avatars: Record<string, RoleAvatar> = {};
    for (const r of [...(this.belt?.roles ?? []), ...(this.belt?.library ?? [])]) {
      avatars[r.name] = r.avatar;
    }
    for (const r of this.wf?.roles_detail ?? []) avatars[r.name] = r.avatar;
    return {
      title,
      slug: this.slug,
      value,
      available: Object.keys(avatars),
      avatars,
      marks: this.wf?.marks ?? {
        operator: { icon: 'person', color: '#546e7a', owns: '' },
        done: { icon: 'check_circle', color: '#2e7d32', owns: '' },
      },
      takenNames: [],
    };
  }

  edit(): void {
    if (!this.wf) return;
    const w = this.wf;
    this.dialog
      .open(WorkflowEditDialogComponent, {
        width: '720px',
        data: this.editorData(`Edit ${w.name}`, {
          name: w.name,
          description: w.description,
          roles: [...w.roles],
          gate: w.gate,
        }),
      })
      .afterClosed()
      .subscribe((v?: WorkflowEdit) => {
        if (!v) return;
        this.mutate(this.api.saveWorkflow(w.slug, v), () => this.load());
      });
  }

  duplicate(): void {
    if (!this.wf) return;
    const w = this.wf;
    this.dialog
      .open(WorkflowEditDialogComponent, {
        width: '720px',
        data: this.editorData('Duplicate workflow', {
          name: `${w.name} copy`,
          description: w.description,
          roles: [...w.roles],
          gate: w.gate,
        }),
      })
      .afterClosed()
      .subscribe((v?: WorkflowEdit) => {
        if (!v) return;
        this.busy = true;
        this.api.createWorkflow(v).subscribe({
          next: (r) => {
            this.busy = false;
            this.snack.open(r.message ?? 'Workflow created', undefined, { duration: 3000 });
            if (r.slug) void this.router.navigate(['/workflow', r.slug]);
          },
          error: (e) => {
            this.busy = false;
            this.error = e?.error?.error ?? e.message ?? 'Duplicate failed';
          },
        });
      });
  }

  makeActive(): void {
    if (!this.wf) return;
    const w = this.wf;
    this.dialog
      .open(ConfirmDialogComponent, {
        width: '460px',
        data: {
          title: `Switch to ${w.name}?`,
          body:
            'Board columns and worktrees follow the active workflow. Stop and Start ' +
            'loops for worktrees to match. Existing tasks stay on the board.',
          code: `.conveyor/active → ${w.slug}`,
          confirmLabel: 'Switch',
        },
      })
      .afterClosed()
      .subscribe((ok) => {
        if (ok) this.mutate(this.api.activateWorkflow(w.slug), () => this.load());
      });
  }

  confirmDelete(): void {
    if (!this.wf) return;
    const w = this.wf;
    this.dialog
      .open(ConfirmDialogComponent, {
        width: '460px',
        data: {
          title: `Delete ${w.name}?`,
          body:
            'Removes the workflow file. Roles and their prompts are untouched. ' +
            'The active workflow cannot be deleted.',
          code: `rm ${w.file}`,
          confirmLabel: 'Delete',
          warn: true,
        },
      })
      .afterClosed()
      .subscribe((ok) => {
        if (ok) this.mutate(this.api.deleteWorkflow(w.slug), () => this.back());
      });
  }

  private mutate(
    req: import('rxjs').Observable<{ ok: boolean; message: string }>,
    done: () => void,
  ): void {
    this.busy = true;
    req.subscribe({
      next: (r) => {
        this.busy = false;
        this.snack.open(r.message ?? 'Saved', undefined, { duration: 3000 });
        this.ui.refresh();
        done();
      },
      error: (e) => {
        this.busy = false;
        this.error = e?.error?.error ?? e.message ?? 'Request failed';
      },
    });
  }
}
