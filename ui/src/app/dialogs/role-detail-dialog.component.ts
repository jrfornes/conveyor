import { Component, EventEmitter, Inject, OnInit, Output, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { SkillInfo } from '../models';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { FailureLike, UiStateService, errorMessage } from '../services/ui-state.service';
import { ConfirmDialogComponent } from './confirm-dialog.component';

export interface RoleDetailDialogData {
  roleName: string;
  roleText: string;
  assignedSkills: string[];
  availableSkills: SkillInfo[];
  /** Generated handoff contract for the active workflow; null when off-belt. */
  contract: string | null;
  /** True when the role file still carries a hand-written Handoff contract. */
  handwrittenContract: boolean;
}

export interface RoleDetailDialogResult {
  saved: boolean;
}

@Component({
  selector: 'app-role-detail-dialog',
  standalone: true,
  imports: [
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatChipsModule,
    MatTooltipModule,
    MatSnackBarModule,
  ],
  template: `
    <h2 mat-dialog-title>roles/{{ data.roleName }}.md</h2>
    <mat-dialog-content>
      @if (error) {
        <div class="err" role="alert">{{ error }}</div>
      }
      <textarea
        class="md"
        [(ngModel)]="roleText"
        spellcheck="false"
      ></textarea>
      <div class="actions">
        <button mat-flat-button [disabled]="!roleDirty || busy" (click)="saveRole()">
          Save prompt
        </button>
        <span class="hint">Applies on next Start. Headings required: Owns, Does not own.</span>
      </div>
      @if (data.handwrittenContract) {
        <div class="warn" role="alert">
          This role file carries a hand-written Handoff contract; the generated one
          overrides it — delete the section.
        </div>
      }
      @if (data.contract) {
        <div class="contract">
          <h4>Handoff contract (generated from the active workflow)</h4>
          <pre class="mdc">{{ data.contract }}</pre>
        </div>
      }
      <div class="skills">
        <h4>Assigned skills</h4>
        @if (!data.availableSkills.length) {
          <p class="hint">No .agents/skills/*/SKILL.md or .cursor/skills/*/SKILL.md in this repo.</p>
        } @else {
          <mat-chip-set>
            @for (s of data.availableSkills; track s.name) {
              <mat-chip
                [highlighted]="assignedSkills.includes(s.name)"
                [matTooltip]="skillTooltip(s)"
                [matTooltipDisabled]="!skillTooltip(s)"
                (click)="toggleSkill(s.name)"
              >
                {{ s.name }}
              </mat-chip>
            }
          </mat-chip-set>
          <div class="actions">
            <button
              mat-stroked-button
              [disabled]="!skillsDirty || busy"
              (click)="saveSkills()"
            >
              Save skills
            </button>
            <span class="hint">Applies on next Start.</span>
          </div>
        }
      </div>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button (click)="tryClose()">Close</button>
    </mat-dialog-actions>
  `,
  styles: `
    mat-dialog-content {
      min-width: 0;
      max-width: 100%;
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-height: min(70vh, 720px);
    }
    .err {
      padding: 8px 12px; border-radius: 8px; font-size: 13px;
      background: #ffebee; color: #b71c1c;
    }
    .md {
      width: 100%; min-height: 280px; flex: 1;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px; line-height: 1.45;
      border: 1px solid rgba(0,0,0,0.16); border-radius: 6px; padding: 8px;
      resize: vertical; box-sizing: border-box;
    }
    .actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .hint { font-size: 12px; color: rgba(0,0,0,0.6); margin: 0; }
    .warn {
      padding: 8px 12px; border-radius: 8px; font-size: 13px;
      background: #fff8e1; color: #8d6e00;
    }
    .contract { display: flex; flex-direction: column; gap: 6px; }
    .contract h4 {
      margin: 0; font-size: 12px; text-transform: uppercase;
      letter-spacing: 0.04em; color: rgba(0,0,0,0.55);
    }
    .mdc {
      margin: 0; white-space: pre-wrap; word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px; line-height: 1.45;
      border: 1px solid rgba(0,0,0,0.12); border-radius: 6px;
      padding: 8px; background: rgba(0,0,0,0.03);
    }
    .skills { display: flex; flex-direction: column; gap: 6px; }
    .skills h4 {
      margin: 0; font-size: 12px; text-transform: uppercase;
      letter-spacing: 0.04em; color: rgba(0,0,0,0.55);
    }
    mat-chip { cursor: pointer; }
  `,
})
export class RoleDetailDialogComponent implements OnInit {
  private ref = inject(MatDialogRef<RoleDetailDialogComponent, RoleDetailDialogResult>);
  private dialog = inject(MatDialog);
  private api = inject(ConveyorApiService);
  private snack = inject(MatSnackBar);
  private ui = inject(UiStateService);

  /** Parent listens so the Roles banner can flip to Saved without closing. */
  @Output() saved = new EventEmitter<void>();

  roleText: string;
  savedRoleText: string;
  assignedSkills: string[];
  savedAssignedSkills: string[];
  busy = false;
  error = '';
  private didSave = false;
  private closing = false;

  constructor(@Inject(MAT_DIALOG_DATA) public data: RoleDetailDialogData) {
    this.roleText = data.roleText;
    this.savedRoleText = data.roleText;
    this.assignedSkills = [...data.assignedSkills];
    this.savedAssignedSkills = [...data.assignedSkills];
  }

  ngOnInit(): void {
    this.ref.disableClose = true;
    this.ref.backdropClick().subscribe(() => this.tryClose());
    this.ref.keydownEvents().subscribe((e: KeyboardEvent) => {
      if (e.key === 'Escape') this.tryClose();
    });
  }

  get roleDirty(): boolean {
    return this.roleText !== this.savedRoleText;
  }

  get skillsDirty(): boolean {
    const a = [...this.assignedSkills].sort().join(',');
    const b = [...this.savedAssignedSkills].sort().join(',');
    return a !== b;
  }

  get dirty(): boolean {
    return this.roleDirty || this.skillsDirty;
  }

  toggleSkill(name: string): void {
    this.assignedSkills = this.assignedSkills.includes(name)
      ? this.assignedSkills.filter((s) => s !== name)
      : [...this.assignedSkills, name];
  }

  skillTooltip(skill: SkillInfo): string {
    const parts: string[] = [];
    if (skill.description) parts.push(skill.description);
    if (skill.source) parts.push(`(${skill.source})`);
    return parts.join(' ');
  }

  saveRole(): void {
    this.busy = true;
    this.error = '';
    this.api.saveRole(this.data.roleName, this.roleText).subscribe({
      next: () => {
        this.busy = false;
        this.savedRoleText = this.roleText;
        this.didSave = true;
        this.snack.open(`roles/${this.data.roleName}.md saved — applies on next Start`, undefined, {
          duration: 3000,
        });
        this.saved.emit();
      },
      error: (e) => {
        this.busy = false;
        this.error = this.inline(e, 'Prompt save failed');
      },
    });
  }

  saveSkills(): void {
    this.busy = true;
    this.error = '';
    this.api.saveRoleSkills(this.data.roleName, this.assignedSkills).subscribe({
      next: () => {
        this.busy = false;
        this.savedAssignedSkills = [...this.assignedSkills];
        this.didSave = true;
        this.snack.open(
          `roles/${this.data.roleName}.skills saved — applies on next Start`,
          undefined,
          { duration: 3000 },
        );
        this.saved.emit();
      },
      error: (e) => {
        this.busy = false;
        this.error = this.inline(e, 'Skills save failed');
      },
    });
  }

  tryClose(): void {
    if (this.closing) return;
    if (!this.dirty) {
      this.ref.close({ saved: this.didSave });
      return;
    }
    this.closing = true;
    this.dialog
      .open(ConfirmDialogComponent, {
        data: {
          title: 'Discard unsaved changes?',
          body: `The prompt or skills for ${this.data.roleName} have not been saved.`,
          confirmLabel: 'Discard',
          warn: true,
        },
      })
      .afterClosed()
      .subscribe((ok) => {
        this.closing = false;
        if (ok) this.ref.close({ saved: this.didSave });
      });
  }

  /** Show the failure inline and record it in the shared error history. */
  private inline(e: FailureLike, fallback: string): string {
    this.ui.note(e, fallback);
    return errorMessage(e, fallback);
  }
}
