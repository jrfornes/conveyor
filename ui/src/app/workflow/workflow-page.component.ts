import { Component, OnInit, computed } from '@angular/core';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { FailureLike, UiStateService, errorMessage } from '../services/ui-state.service';
import { RoleAvatar, WorkflowEdit, WorkflowListResponse, WorkflowState } from '../models';
import { WorkflowTableComponent } from './workflow-table.component';
import {
  WorkflowEditDialogComponent,
  WorkflowEditData,
  WORKFLOW_EDIT_DIALOG_OPTIONS,
} from '../dialogs/workflow-edit-dialog.component';

@Component({
  selector: 'app-workflow-page',
  standalone: true,
  imports: [MatButtonModule, MatSnackBarModule, WorkflowTableComponent],
  template: `
    <div class="page">
      <div class="banner" role="status">
        Workflows save to the repo. Making one active rewrites
        <code>conveyor.conf</code>; it takes effect the next time you Start.
      </div>

      @if (running()) {
        <div class="lock" role="status">
          Stop the loops to make a different workflow active. You can still edit any
          workflow that is not the active one.
        </div>
      }

      @if (error) {
        <div class="err" role="alert">{{ error }}</div>
      }

      @if (list) {
        <div class="head">
          <h3>Workflows</h3>
          <span class="meta mono">.conveyor/workflows/</span>
          <span class="meta right">
            {{ list.workflows.length }} workflows · {{ activeLabel() }}
          </span>
          <button mat-flat-button color="primary" [disabled]="busy" (click)="create()">
            New workflow
          </button>
        </div>

        @if (list.status === 'modified') {
          <div class="note" role="status">
            <code>conveyor.conf</code> no longer matches the workflow it was written
            from. The real belt is <code>{{ list.chain }}</code>. Make a workflow active
            to bring them back in step.
          </div>
        } @else if (list.status === 'custom') {
          <div class="note" role="status">
            <code>conveyor.conf</code> is a custom belt — <code>{{ list.chain }}</code> —
            that no saved workflow describes.
          </div>
        }

        <app-workflow-table
          [items]="list.workflows"
          (open)="open($event)"
          (create)="create()"
        ></app-workflow-table>
      }
    </div>
  `,
  styles: `
    :host { display: block; height: 100%; overflow: auto; background: #f7f8fa; }
    .page { padding: 12px 16px 24px; display: flex; flex-direction: column; gap: 12px; }
    .banner, .lock, .err, .note {
      padding: 8px 12px; border-radius: 8px; font-size: 13px;
    }
    .banner { background: #e3f2fd; color: #0d47a1; }
    .lock { background: #fff8e1; color: #e65100; }
    .err { background: #ffebee; color: #b71c1c; }
    .note { background: #fff8e1; color: #6b4e00; }
    .head { display: flex; align-items: center; gap: 10px; }
    .head .right { margin-left: auto; }
    .meta { font-size: 12px; color: rgba(0,0,0,0.55); }
    .mono { font-family: 'Roboto Mono', ui-monospace, monospace; }
    h3 {
      margin: 0; font-size: 13px; text-transform: uppercase;
      letter-spacing: 0.06em; color: rgba(0,0,0,0.55);
    }
  `,
})
export class WorkflowPageComponent implements OnInit {
  list: WorkflowListResponse | null = null;
  /** Only for the role catalogue and avatars the editor dialog needs. */
  belt: WorkflowState | null = null;
  busy = false;
  error = '';

  running = computed(() => this.ui.state()?.running ?? this.list?.running ?? false);

  constructor(
    private api: ConveyorApiService,
    public ui: UiStateService,
    private snack: MatSnackBar,
    private dialog: MatDialog,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.load();
    this.api.workflow().subscribe({ next: (w) => (this.belt = w), error: () => undefined });
  }

  load(): void {
    this.api.workflows().subscribe({
      next: (l) => {
        this.list = l;
        this.error = '';
      },
      error: (e) => (this.error = this.inline(e, 'Failed to load workflows')),
    });
  }

  activeLabel(): string {
    if (!this.list) return '';
    if (this.list.status === 'custom') return 'active: custom belt';
    const row = this.list.workflows.find((w) => w.slug === this.list!.active);
    const suffix = this.list.status === 'modified' ? ' (modified)' : '';
    return `active: ${row?.name ?? this.list.active}${suffix}`;
  }

  open(slug: string): void {
    void this.router.navigate(['/workflow', slug]);
  }

  create(): void {
    if (!this.list) return;
    const data: WorkflowEditData = {
      title: 'New workflow',
      value: { name: '', description: '', roles: [], gate: null },
      available: this.availableRoles(),
      avatars: this.avatars(),
      marks: this.belt?.marks ?? {
        operator: { icon: 'person', color: '#546e7a', owns: '' },
        done: { icon: 'check_circle', color: '#2e7d32', owns: '' },
      },
      takenNames: this.list.workflows.map((w) => w.name.toLowerCase()),
    };
    this.dialog
      .open(WorkflowEditDialogComponent, { ...WORKFLOW_EDIT_DIALOG_OPTIONS, data })
      .afterClosed()
      .subscribe((v?: WorkflowEdit) => {
        if (v) this.save(v);
      });
  }

  private availableRoles(): string[] {
    if (!this.belt) return [];
    return [...this.belt.roles, ...this.belt.library].map((r) => r.name);
  }

  private avatars(): Record<string, RoleAvatar> {
    const out: Record<string, RoleAvatar> = {};
    for (const r of [...(this.belt?.roles ?? []), ...(this.belt?.library ?? [])]) {
      out[r.name] = r.avatar;
    }
    return out;
  }

  private save(v: WorkflowEdit): void {
    this.busy = true;
    this.api.createWorkflow(v).subscribe({
      next: (r) => {
        this.busy = false;
        this.snack.open(r.message ?? 'Workflow created', undefined, { duration: 3000 });
        this.load();
        if (r.slug) this.open(r.slug);
      },
      error: (e) => {
        this.busy = false;
        this.error = this.inline(e, 'Create failed');
      },
    });
  }

  /** Show the failure inline and record it in the shared error history. */
  private inline(e: FailureLike, fallback: string): string {
    this.ui.note(e, fallback);
    return errorMessage(e, fallback);
  }
}
