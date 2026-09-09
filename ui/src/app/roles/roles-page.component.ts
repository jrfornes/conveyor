import { Component, OnInit, computed } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { FailureLike, UiStateService, errorMessage } from '../services/ui-state.service';
import { AgentModel, RoleRecord, WorkflowState } from '../models';
import { RoleCardsComponent } from './role-cards.component';
import { EditorPaneComponent } from './editor-pane.component';
import { ConfirmDialogComponent } from '../dialogs/confirm-dialog.component';
import { NewRoleDialogComponent } from '../dialogs/new-role-dialog.component';
import {
  RoleDetailDialogComponent,
  RoleDetailDialogResult,
} from '../dialogs/role-detail-dialog.component';

@Component({
  selector: 'app-roles-page',
  standalone: true,
  imports: [MatSnackBarModule, MatButtonModule, RoleCardsComponent, EditorPaneComponent],
  template: `
    <div class="page">
      <div class="banner" [class.saved]="saved" role="status">
        @if (saved) {
          Saved. Applies the next time you Start.
        } @else {
          Prompts, models, ceilings, and skills save to the repo. They apply the next time you Start.
        }
      </div>

      @if (running()) {
        <div class="lock" role="status">
          Loops running: models and ceilings are read-only. Prompts save now and apply on
          next Start.
        </div>
      }

      @if (error) {
        <div class="err" role="alert">{{ error }}</div>
      }

      @if (modelsError) {
        <div class="err" role="status">{{ modelsError }}</div>
      }

      @if (workflow) {
        <div class="head">
          <h3>Coding roles</h3>
          <button mat-stroked-button (click)="newRole()" [disabled]="busy">New role</button>
          <span class="meta mono">
            roles/ · one file per job · on the belt now: {{ workflow.workflow.chain }}
          </span>
          <span class="meta mono right">
            {{ running() ? 'read only while loops run' : 'editable · loops stopped' }}
          </span>
        </div>

        <app-role-cards
          [roles]="allRoles"
          [models]="models"
          [selected]="selected"
          [locked]="running()"
          [busy]="busy"
          (select)="openRole($event)"
          (saveRuntime)="saveRuntime($event)"
          (deleteRole)="deleteRole($event)"
        ></app-role-cards>

        <app-editor-pane
          [projectText]="projectDraft"
          [projectDirty]="projectDirty"
          [projectGates]="workflow.project_gates"
          [constitution]="workflow.constitution"
          [busy]="busy"
          (projectTextChange)="projectDraft = $event; saved = false"
          (saveProject)="saveProject()"
          (runGate)="runGate($event)"
        ></app-editor-pane>
      }
    </div>
  `,
  styles: `
    :host { display: block; height: 100%; overflow: auto; background: #f7f8fa; }
    .page { padding: 12px 16px 24px; display: flex; flex-direction: column; gap: 12px; }
    .banner, .lock, .err { padding: 8px 12px; border-radius: 8px; font-size: 13px; }
    .banner { background: #e3f2fd; color: #0d47a1; }
    .banner.saved { background: #e8f5e9; color: #1b5e20; }
    .lock { background: #fff8e1; color: #e65100; }
    .err { background: #ffebee; color: #b71c1c; }
    .head { display: flex; align-items: baseline; gap: 10px; }
    .head .right { margin-left: auto; }
    .meta { font-size: 12px; color: rgba(0,0,0,0.55); }
    .mono { font-family: 'Roboto Mono', ui-monospace, monospace; }
    h3 {
      margin: 0; font-size: 13px; text-transform: uppercase;
      letter-spacing: 0.06em; color: rgba(0,0,0,0.55);
    }
  `,
})
export class RolesPageComponent implements OnInit {
  workflow: WorkflowState | null = null;
  selected: string | null = null;
  projectDraft = '';
  savedProjectText = '';
  busy = false;
  error = '';
  models: AgentModel[] = [];
  modelsError = '';
  saved = false;

  /** Set from ?role=<name> on first load, then cleared. */
  private requested: string | null = null;
  private roleDialog: MatDialogRef<RoleDetailDialogComponent, RoleDetailDialogResult> | null = null;

  running = computed(() => this.ui.state()?.running ?? this.workflow?.running ?? false);

  constructor(
    private api: ConveyorApiService,
    public ui: UiStateService,
    private snack: MatSnackBar,
    private route: ActivatedRoute,
    private router: Router,
    private dialog: MatDialog,
  ) {}

  get allRoles(): RoleRecord[] {
    if (!this.workflow) return [];
    return [...this.workflow.roles, ...this.workflow.library];
  }

  get projectDirty(): boolean {
    return this.projectDraft !== this.savedProjectText;
  }

  ngOnInit(): void {
    this.requested = this.route.snapshot.queryParamMap.get('role');
    this.load();
    this.loadModels();
  }

  private loadModels(): void {
    this.api.models().subscribe({
      next: (r) => {
        this.models = r.models ?? [];
        this.modelsError = r.error ?? '';
      },
      error: (e) => {
        this.models = [];
        this.modelsError = this.inline(e, 'Failed to list models');
      },
    });
  }

  load(): void {
    this.api.workflow().subscribe({
      next: (w) => {
        this.workflow = w;
        this.error = '';
        const keepProject = this.projectDirty && this.projectDraft !== '';
        this.savedProjectText = w.project;
        if (!keepProject) this.projectDraft = w.project;
        const names = this.allRoles.map((r) => r.name);
        if (this.requested && names.includes(this.requested)) {
          const name = this.requested;
          this.requested = null;
          this.openRole(name);
        }
      },
      error: (e) => {
        this.error = this.inline(e, 'Failed to load roles');
      },
    });
  }

  openRole(name: string): void {
    if (!this.workflow) return;
    const role = this.allRoles.find((r) => r.name === name);
    if (!role) return;
    this.roleDialog?.close();
    this.selected = name;
    const ref = this.dialog.open(RoleDetailDialogComponent, {
      width: '720px',
      maxWidth: '95vw',
      maxHeight: '90vh',
      panelClass: 'role-detail-dialog',
      data: {
        roleName: name,
        roleText: role.text,
        assignedSkills: [...(role.skills ?? [])],
        availableSkills: this.workflow.available_skills,
      },
    });
    this.roleDialog = ref;
    ref.componentInstance.saved.subscribe(() => {
      this.saved = true;
      this.load();
    });
    ref.afterClosed().subscribe(() => {
      if (this.roleDialog !== ref) return;
      this.roleDialog = null;
      this.selected = null;
      if (this.route.snapshot.queryParamMap.has('role')) {
        void this.router.navigate([], {
          relativeTo: this.route,
          queryParams: {},
          replaceUrl: true,
        });
      }
    });
  }

  newRole(): void {
    this.dialog
      .open(NewRoleDialogComponent, {
        data: { existing: this.allRoles.map((r) => r.name) },
        width: '420px',
      })
      .afterClosed()
      .subscribe((v) => {
        if (!v) return;
        this.busy = true;
        this.api.createRole(v.name, v.from).subscribe({
          next: () => {
            this.busy = false;
            this.snack.open(`roles/${v.name}.md created`, undefined, { duration: 3000 });
            this.requested = v.name;
            this.load();
          },
          error: (e) => {
            this.busy = false;
            this.error = this.inline(e, 'Create failed');
          },
        });
      });
  }

  deleteRole(role: RoleRecord): void {
    this.dialog
      .open(ConfirmDialogComponent, {
        data: {
          title: `Delete ${role.name}?`,
          body: `Remove roles/${role.name}.md from the library. Queues and worktrees are untouched.`,
          confirmLabel: 'Delete',
          warn: true,
        },
      })
      .afterClosed()
      .subscribe((ok) => {
        if (!ok) return;
        this.busy = true;
        this.api.deleteRole(role.name).subscribe({
          next: () => {
            this.busy = false;
            this.snack.open(`roles/${role.name}.md deleted`, undefined, { duration: 2500 });
            if (this.selected === role.name) {
              this.roleDialog?.close();
              this.selected = null;
            }
            this.load();
          },
          error: (e) => {
            this.busy = false;
            // Delete has no inline error slot of its own, so it goes on the
            // shared sticky channel rather than a toast that times out.
            this.ui.fail(e, 'Delete failed');
          },
        });
      });
  }

  saveRuntime(role: RoleRecord): void {
    this.busy = true;
    this.api
      .saveRoleRuntime(
        role.name,
        role.model ?? '',
        role.max_retries ?? 1,
        role.max_minutes ?? 1,
        role.max_attempts ?? 1,
      )
      .subscribe({
        next: () => {
          this.busy = false;
          this.snack.open(`${role.name} runtime saved`, undefined, { duration: 2500 });
          this.ui.refresh();
          this.load();
        },
        error: (e) => {
          this.busy = false;
          this.error = this.inline(e, 'Runtime save failed');
        },
      });
  }

  saveProject(): void {
    this.busy = true;
    this.api.saveProject(this.projectDraft).subscribe({
      next: () => {
        this.busy = false;
        this.savedProjectText = this.projectDraft;
        this.saved = true;
        this.snack.open('project.md saved — applies on next Start', undefined, { duration: 3000 });
        this.load();
      },
      error: (e) => {
        this.busy = false;
        this.error = this.inline(e, 'project.md save failed');
      },
    });
  }

  runGate(name: string): void {
    this.busy = true;
    this.api.runGate(name, this.selected ?? this.workflow?.roles[0]?.name).subscribe({
      next: (r) => {
        this.busy = false;
        this.snack.open(r.message || `${name}: ok`, undefined, { duration: 4000 });
      },
      error: (e) => {
        this.busy = false;
        this.error = this.inline(e, 'Gate run failed');
      },
    });
  }

  /** Show the failure inline and record it in the shared error history. */
  private inline(e: FailureLike, fallback: string): string {
    this.ui.note(e, fallback);
    return errorMessage(e, fallback);
  }
}
