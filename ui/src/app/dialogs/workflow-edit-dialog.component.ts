import { Component, Inject, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatRadioModule } from '@angular/material/radio';
import { RoleAvatar, WorkflowEdit } from '../models';
import { beltRoutes, slugify } from '../util';
import { BeltDiagramComponent } from '../workflow/belt-diagram.component';

export interface WorkflowEditData {
  title: string;
  /** Slug being edited; absent when creating. Used to exclude self from the name check. */
  slug?: string;
  value: WorkflowEdit;
  /** Every role with a file in roles/, for the `add:` chips. */
  available: string[];
  avatars: Record<string, RoleAvatar>;
  marks: { operator: RoleAvatar; done: RoleAvatar };
  /** Existing names, lowercased, for the uniqueness check. */
  takenNames: string[];
}

/** Shared open() options so create / edit / duplicate cannot drift on width. */
export const WORKFLOW_EDIT_DIALOG_OPTIONS = {
  width: '720px',
  maxWidth: '95vw',
  panelClass: 'workflow-edit-dialog',
};

@Component({
  selector: 'app-workflow-edit-dialog',
  standalone: true,
  imports: [
    FormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatRadioModule,
    BeltDiagramComponent,
  ],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content>
      <mat-form-field appearance="outline" class="full">
        <mat-label>Name</mat-label>
        <input matInput [(ngModel)]="name" (ngModelChange)="onName()" />
        @if (nameError()) {
          <mat-error>{{ nameError() }}</mat-error>
        }
      </mat-form-field>

      <mat-form-field appearance="outline" class="full">
        <mat-label>Description</mat-label>
        <input matInput [(ngModel)]="description" />
      </mat-form-field>

      <h4>Roles, in order</h4>
      <div class="chips">
        @for (r of roles(); track r; let i = $index) {
          <span class="chip">
            <span class="avatar" [style.background]="avatar(r).color"></span>
            <span class="mono">{{ r }}</span>
            <button mat-button class="mini" [disabled]="i === 0"
                    (click)="move(i, -1)" aria-label="Move earlier">◂</button>
            <button mat-button class="mini" [disabled]="i === roles().length - 1"
                    (click)="move(i, 1)" aria-label="Move later">▸</button>
            <button mat-button class="mini" (click)="remove(i)" aria-label="Remove">✕</button>
          </span>
        }
      </div>
      @if (unused().length) {
        <div class="chips add">
          <span class="label mono">add:</span>
          @for (r of unused(); track r) {
            <button class="chip dashed" (click)="add(r)">
              <span class="avatar" [style.background]="avatar(r).color"></span>
              <span class="mono">{{ r }}</span>
            </button>
          }
        </div>
      }
      <p class="help">
        Each role from <code>roles/</code> at most once. The last role decides
        <code>pass</code>; its <code>findings</code> always return to the role before it.
      </p>

      <h4>Human gate</h4>
      <mat-radio-group class="gates" [(ngModel)]="gate">
        <mat-radio-button [value]="null">no gate</mat-radio-button>
        @for (r of gateable(); track r) {
          <mat-radio-button [value]="r">hold the first handoff after {{ r }}</mat-radio-button>
        }
      </mat-radio-group>

      <h4>Preview</h4>
      <app-belt-diagram
        [roles]="previewRoles()"
        [routes]="previewRoutes()"
        [gate]="gate"
        [marks]="data.marks"
      ></app-belt-diagram>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <span class="file mono">{{ filePreview() }}</span>
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-flat-button color="primary" [disabled]="invalid()" (click)="submit()">
        Save
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    :host { display: block; max-width: 100%; }
    mat-dialog-content {
      min-width: 0;
      max-width: 100%;
      box-sizing: border-box;
      overflow-x: hidden;
    }
    .full { width: 100%; }
    h4 {
      margin: 8px 0 4px; font-size: 12px; text-transform: uppercase;
      letter-spacing: 0.08em; color: rgba(0,0,0,0.55);
    }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
    .chips.add { margin-top: 6px; }
    .chip {
      display: inline-flex; align-items: center; gap: 6px;
      border: 1px solid rgba(0,0,0,0.2); border-radius: 4px; padding: 2px 6px;
      background: #fff; font-size: 13px;
    }
    .chip.dashed { border-style: dashed; cursor: pointer; }
    .avatar { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .mini { min-width: 0; padding: 0 4px; line-height: 20px; }
    .mono { font-family: 'Roboto Mono', ui-monospace, monospace; }
    .label { font-size: 12px; color: rgba(0,0,0,0.55); }
    .help { font-size: 12px; color: rgba(0,0,0,0.6); margin: 8px 0 0; }
    .gates { display: flex; flex-direction: column; gap: 2px; }
    .gates mat-radio-button { white-space: normal; }
    .file {
      margin-right: auto; font-size: 12px; color: rgba(0,0,0,0.55);
      overflow-wrap: anywhere;
    }
  `,
})
export class WorkflowEditDialogComponent {
  private ref = inject(MatDialogRef<WorkflowEditDialogComponent, WorkflowEdit>);

  name: string;
  description: string;
  gate: string | null;
  roles = signal<string[]>([]);

  previewRoles = computed(() =>
    this.roles().map((r) => ({ name: r, avatar: this.avatar(r) })),
  );
  previewRoutes = computed(() => beltRoutes(this.roles()));
  unused = computed(() => this.data.available.filter((r) => !this.roles().includes(r)));
  /** Every role but the last: the last one's handoff goes to done, not onward. */
  gateable = computed(() => this.roles().slice(0, -1));

  constructor(@Inject(MAT_DIALOG_DATA) public data: WorkflowEditData) {
    this.name = data.value.name;
    this.description = data.value.description;
    this.gate = data.value.gate;
    this.roles.set([...data.value.roles]);
  }

  avatar(name: string): RoleAvatar {
    return this.data.avatars[name] ?? { icon: 'person_outline', color: '#78909c', owns: '' };
  }

  nameError(): string {
    const n = this.name.trim();
    if (!n) return 'Name is required';
    if (!slugify(n)) return 'Name must contain at least one letter or digit';
    if (this.data.takenNames.includes(n.toLowerCase())) return 'That name is taken';
    return '';
  }

  filePreview(): string {
    const s = slugify(this.name);
    return s ? `.conveyor/workflows/${s}.json` : '';
  }

  invalid(): boolean {
    return !!this.nameError() || this.roles().length === 0;
  }

  onName(): void {
    // no-op hook; keeps the error message reactive under default change detection
  }

  private normalizeGate(next: string[]): void {
    // A reorder or removal can make the gated role the last one, which the
    // server rejects. Clear it here so the form cannot submit a bad shape.
    if (this.gate && (!next.includes(this.gate) || next[next.length - 1] === this.gate)) {
      this.gate = null;
    }
  }

  move(i: number, delta: number): void {
    const next = [...this.roles()];
    const j = i + delta;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    this.roles.set(next);
    this.normalizeGate(next);
  }

  remove(i: number): void {
    const next = this.roles().filter((_, k) => k !== i);
    this.roles.set(next);
    this.normalizeGate(next);
  }

  add(name: string): void {
    const next = [...this.roles(), name];
    this.roles.set(next);
    this.normalizeGate(next);
  }

  submit(): void {
    if (this.invalid()) return;
    this.ref.close({
      name: this.name.trim(),
      description: this.description.trim(),
      roles: this.roles(),
      gate: this.gate,
    });
  }
}
