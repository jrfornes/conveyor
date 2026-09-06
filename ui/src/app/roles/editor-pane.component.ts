import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatTabsModule } from '@angular/material/tabs';
import { SkillInfo } from '../models';

@Component({
  selector: 'app-editor-pane',
  standalone: true,
  imports: [FormsModule, MatTabsModule, MatButtonModule, MatChipsModule],
  template: `
    <mat-tab-group [(selectedIndex)]="tab" animationDuration="0">
      <mat-tab [label]="roleName ? 'roles/' + roleName + '.md' : 'Role prompt'">
        <div class="pane">
          @if (!roleName) {
            <p class="hint">Select a role on the belt or a card to edit its prompt.</p>
          } @else {
            <textarea
              class="md"
              [ngModel]="roleText"
              (ngModelChange)="roleTextChange.emit($event)"
              spellcheck="false"
            ></textarea>
            <div class="actions">
              <button mat-flat-button [disabled]="!roleDirty || busy" (click)="saveRole.emit()">
                Save prompt
              </button>
              <span class="hint">Applies on next Start. Headings required: Owns, Does not own, Handoff contract.</span>
            </div>
            <div class="skills">
              <h4>Assigned skills</h4>
              @if (!availableSkills.length) {
                <p class="hint">No .agents/skills/*/SKILL.md or .cursor/skills/*/SKILL.md in this repo.</p>
              } @else {
                <mat-chip-set>
                  @for (s of availableSkills; track s.name) {
                    <mat-chip
                      [highlighted]="assignedSkills.includes(s.name)"
                      (click)="toggleSkill(s.name)"
                    >
                      {{ s.name }}
                      @if (s.description) {
                        <span class="desc"> — {{ s.description }}</span>
                      }
                      @if (s.source) {
                        <span class="desc"> ({{ s.source }})</span>
                      }
                    </mat-chip>
                  }
                </mat-chip-set>
                <div class="actions">
                  <button
                    mat-stroked-button
                    [disabled]="!skillsDirty || busy"
                    (click)="saveSkills.emit(assignedSkills)"
                  >
                    Save skills
                  </button>
                  <span class="hint">Applies on next Start.</span>
                </div>
              }
            </div>
          }
        </div>
      </mat-tab>
      <mat-tab label="project.md">
        <div class="pane">
          <textarea
            class="md"
            [ngModel]="projectText"
            (ngModelChange)="projectTextChange.emit($event)"
            spellcheck="false"
          ></textarea>
          @if (projectGates.length) {
            <div class="gates">
              <h4>Named gates</h4>
              <ul>
                @for (g of projectGates; track g.name) {
                  <li>
                    <code>{{ g.name }}</code>
                    <span class="argv">{{ g.argv || '(empty)' }}</span>
                    <button
                      mat-stroked-button
                      [disabled]="busy || !g.argv"
                      (click)="runGate.emit(g.name)"
                    >
                      Run now
                    </button>
                  </li>
                }
              </ul>
            </div>
          }
          <div class="actions">
            <button mat-flat-button [disabled]="!projectDirty || busy" (click)="saveProject.emit()">
              Save project.md
            </button>
            <span class="hint">Gate catalog applies on next Start; Run now uses saved file on disk.</span>
          </div>
        </div>
      </mat-tab>
    </mat-tab-group>
    @if (constitution.length) {
      <div class="constitution">
        <h4>Constitution (read-only)</h4>
        <ul>
          @for (f of constitution; track f) {
            <li><code>{{ f }}</code></li>
          }
        </ul>
      </div>
    }
  `,
  styles: `
    :host { display: flex; flex-direction: column; min-height: 0; }
    .pane { display: flex; flex-direction: column; gap: 8px; padding-top: 12px; min-height: 280px; }
    .md {
      width: 100%; min-height: 280px; flex: 1;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px; line-height: 1.45;
      border: 1px solid rgba(0,0,0,0.16); border-radius: 6px; padding: 10px;
      resize: vertical; box-sizing: border-box;
    }
    .actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .hint { font-size: 12px; color: rgba(0,0,0,0.6); margin: 0; }
    .skills { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
    .skills h4 {
      margin: 0; font-size: 12px; text-transform: uppercase;
      letter-spacing: 0.04em; color: rgba(0,0,0,0.55);
    }
    .desc { font-size: 11px; opacity: 0.7; }
    mat-chip { cursor: pointer; }
    .gates { margin-top: 8px; }
    .gates h4 {
      margin: 0 0 6px; font-size: 12px; text-transform: uppercase;
      letter-spacing: 0.04em; color: rgba(0,0,0,0.55);
    }
    .gates ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; }
    .gates li { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 13px; }
    .gates .argv { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: rgba(0,0,0,0.65); }
    .constitution { margin-top: 12px; font-size: 13px; }
    .constitution h4 { margin: 0 0 6px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; color: rgba(0,0,0,0.55); }
    .constitution ul { margin: 0; padding-left: 18px; }
  `,
})
export class EditorPaneComponent {
  @Input() roleName: string | null = null;
  @Input() roleText = '';
  @Input() roleDirty = false;
  @Input() projectText = '';
  @Input() projectDirty = false;
  @Input() projectGates: { name: string; argv: string }[] = [];
  @Input() constitution: string[] = [];
  @Input() busy = false;
  @Input() availableSkills: SkillInfo[] = [];
  @Input() assignedSkills: string[] = [];
  @Input() savedAssignedSkills: string[] = [];
  @Input() skillsDirty = false;
  @Output() roleTextChange = new EventEmitter<string>();
  @Output() projectTextChange = new EventEmitter<string>();
  @Output() saveRole = new EventEmitter<void>();
  @Output() saveProject = new EventEmitter<void>();
  @Output() runGate = new EventEmitter<string>();
  @Output() assignedSkillsChange = new EventEmitter<string[]>();
  @Output() saveSkills = new EventEmitter<string[]>();
  tab = 0;

  toggleSkill(name: string): void {
    const next = this.assignedSkills.includes(name)
      ? this.assignedSkills.filter((s) => s !== name)
      : [...this.assignedSkills, name];
    this.assignedSkillsChange.emit(next);
  }
}
