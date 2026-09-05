import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatTabsModule } from '@angular/material/tabs';

@Component({
  selector: 'app-editor-pane',
  standalone: true,
  imports: [FormsModule, MatTabsModule, MatButtonModule],
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
          <div class="actions">
            <button mat-flat-button [disabled]="!projectDirty || busy" (click)="saveProject.emit()">
              Save project.md
            </button>
            <span class="hint">Applies on next Start.</span>
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
  @Input() constitution: string[] = [];
  @Input() busy = false;
  @Output() roleTextChange = new EventEmitter<string>();
  @Output() projectTextChange = new EventEmitter<string>();
  @Output() saveRole = new EventEmitter<void>();
  @Output() saveProject = new EventEmitter<void>();
  tab = 0;
}
