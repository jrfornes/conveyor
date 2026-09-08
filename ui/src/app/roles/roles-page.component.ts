import { Component, OnInit, computed } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { UiStateService } from '../services/ui-state.service';
import { AgentModel, RoleRecord, WorkflowState } from '../models';
import { RoleCardsComponent } from './role-cards.component';
import { EditorPaneComponent } from './editor-pane.component';
import { ConfirmDialogComponent } from '../dialogs/confirm-dialog.component';
import { NewRoleDialogComponent } from '../dialogs/new-role-dialog.component';

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

        <section class="studio">
          <div class="left">
            <app-role-cards
              [roles]="allRoles"
              [models]="models"
              [selected]="selected"
              [locked]="running()"
              [busy]="busy"
              (select)="selectRole($event)"
              (saveRuntime)="saveRuntime($event)"
              (deleteRole)="deleteRole($event)"
            ></app-role-cards>
          </div>
          <div class="right">
            <app-editor-pane
              [roleName]="selected"
              [roleText]="roleDraft"
              [roleDirty]="roleDirty"
              [projectText]="projectDraft"
              [projectDirty]="projectDirty"
              [projectGates]="workflow.project_gates"
              [constitution]="workflow.constitution"
              [availableSkills]="workflow.available_skills"
              [assignedSkills]="assignedSkills"
              [savedAssignedSkills]="savedAssignedSkills"
              [skillsDirty]="skillsDirty"
              [busy]="busy"
              (roleTextChange)="roleDraft = $event; saved = false"
              (projectTextChange)="projectDraft = $event; saved = false"
              (assignedSkillsChange)="assignedSkills = $event"
              (saveRole)="saveRole()"
              (saveProject)="saveProject()"
              (runGate)="runGate($event)"
              (saveSkills)="saveSkills($event)"
            ></app-editor-pane>
          </div>
        </section>
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
    .studio {
      display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 440px);
      gap: 16px; align-items: start;
    }
    .left, .right { min-width: 0; }
    @media (max-width: 960px) { .studio { grid-template-columns: 1fr; } }
  `,
})
export class RolesPageComponent implements OnInit {
  workflow: WorkflowState | null = null;
  selected: string | null = null;
  roleDraft = '';
  savedRoleText = '';
  assignedSkills: string[] = [];
  savedAssignedSkills: string[] = [];
  projectDraft = '';
  savedProjectText = '';
  busy = false;
  error = '';
  models: AgentModel[] = [];
  modelsError = '';
  saved = false;

  /** Set from ?role=<name> on first load, then cleared. */
  private requested: string | null = null;

  running = computed(() => this.ui.state()?.running ?? this.workflow?.running ?? false);

  get skillsDirty(): boolean {
    const a = [...this.assignedSkills].sort().join(',');
    const b = [...this.savedAssignedSkills].sort().join(',');
    return a !== b;
  }

  constructor(
    private api: ConveyorApiService,
    public ui: UiStateService,
    private snack: MatSnackBar,
    private route: ActivatedRoute,
    private dialog: MatDialog,
  ) {}

  get allRoles(): RoleRecord[] {
    if (!this.workflow) return [];
    return [...this.workflow.roles, ...this.workflow.library];
  }

  get roleDirty(): boolean {
    return this.roleDraft !== this.savedRoleText;
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
        this.modelsError = e?.error?.error ?? e.message ?? 'Failed to list models';
      },
    });
  }

  load(keepSelection = false): void {
    this.api.workflow().subscribe({
      next: (w) => {
        this.workflow = w;
        this.error = '';
        const keepProject = this.projectDirty && this.projectDraft !== '';
        this.savedProjectText = w.project;
        if (!keepProject) this.projectDraft = w.project;
        const names = this.allRoles.map((r) => r.name);
        if (this.requested && names.includes(this.requested)) {
          this.selected = this.requested;
          this.requested = null;
          this.applySelectedText();
        } else if (!keepSelection || !this.selected || !names.includes(this.selected)) {
          this.selected = w.roles[0]?.name ?? names[0] ?? null;
          this.applySelectedText();
        } else if (!this.roleDirty) {
          this.applySelectedText();
        }
      },
      error: (e) => {
        this.error = e?.error?.error ?? e.message ?? 'Failed to load roles';
      },
    });
  }

  selectRole(name: string): void {
    this.selected = name;
    this.applySelectedText();
  }

  private applySelectedText(): void {
    const role = this.allRoles.find((r) => r.name === this.selected);
    this.savedRoleText = role?.text ?? '';
    this.roleDraft = this.savedRoleText;
    this.savedAssignedSkills = [...(role?.skills ?? [])];
    this.assignedSkills = [...this.savedAssignedSkills];
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
            this.load(true);
          },
          error: (e) => {
            this.busy = false;
            this.error = e?.error?.error ?? e.message ?? 'Create failed';
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
            if (this.selected === role.name) this.selected = null;
            this.load();
          },
          error: (e) => {
            this.busy = false;
            this.snack.open(e?.error?.error ?? e.message ?? 'Delete failed', undefined,
                            { duration: 5000 });
          },
        });
      });
  }

  saveSkills(skills: string[]): void {
    if (!this.selected) return;
    this.busy = true;
    this.api.saveRoleSkills(this.selected, skills).subscribe({
      next: () => {
        this.busy = false;
        this.savedAssignedSkills = [...skills];
        this.saved = true;
        this.snack.open(`roles/${this.selected}.skills saved — applies on next Start`, undefined,
                        { duration: 3000 });
        this.load(true);
      },
      error: (e) => {
        this.busy = false;
        this.error = e?.error?.error ?? e.message ?? 'Skills save failed';
      },
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
          this.load(true);
        },
        error: (e) => {
          this.busy = false;
          this.error = e?.error?.error ?? e.message ?? 'Runtime save failed';
        },
      });
  }

  saveRole(): void {
    if (!this.selected) return;
    this.busy = true;
    this.api.saveRole(this.selected, this.roleDraft).subscribe({
      next: () => {
        this.busy = false;
        this.savedRoleText = this.roleDraft;
        this.saved = true;
        this.snack.open(`roles/${this.selected}.md saved — applies on next Start`, undefined,
                        { duration: 3000 });
        this.load(true);
      },
      error: (e) => {
        this.busy = false;
        this.error = e?.error?.error ?? e.message ?? 'Prompt save failed';
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
        this.load(true);
      },
      error: (e) => {
        this.busy = false;
        this.error = e?.error?.error ?? e.message ?? 'project.md save failed';
      },
    });
  }

  runGate(name: string): void {
    this.busy = true;
    this.api.runGate(name, this.selected ?? undefined).subscribe({
      next: (r) => {
        this.busy = false;
        this.snack.open(r.message || `${name}: ok`, undefined, { duration: 4000 });
      },
      error: (e) => {
        this.busy = false;
        this.error = e?.error?.error ?? e.message ?? 'Gate run failed';
      },
    });
  }
}
