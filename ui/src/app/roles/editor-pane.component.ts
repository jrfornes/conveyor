import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { ProjectGate } from '../models';

@Component({
  selector: 'app-editor-pane',
  standalone: true,
  imports: [FormsModule, MatButtonModule],
  template: `
    <section class="project">
      <h3>Project rules</h3>
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
    </section>
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
    h3 {
      margin: 0 0 8px; font-size: 13px; text-transform: uppercase;
      letter-spacing: 0.06em; color: rgba(0,0,0,0.55);
    }
    .project { display: flex; flex-direction: column; gap: 6px; }
    .md {
      width: 100%; min-height: 240px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px; line-height: 1.45;
      border: 1px solid rgba(0,0,0,0.16); border-radius: 6px; padding: 8px;
      resize: vertical; box-sizing: border-box;
    }
    .actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .hint { font-size: 12px; color: rgba(0,0,0,0.6); margin: 0; }
    .gates { margin-top: 6px; }
    .gates h4 {
      margin: 0 0 6px; font-size: 12px; text-transform: uppercase;
      letter-spacing: 0.04em; color: rgba(0,0,0,0.55);
    }
    .gates ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 6px; }
    .gates li { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; }
    .gates .argv { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: rgba(0,0,0,0.65); }
    .constitution { margin-top: 8px; font-size: 13px; }
    .constitution h4 { margin: 0 0 6px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; color: rgba(0,0,0,0.55); }
    .constitution ul { margin: 0; padding-left: 18px; }
  `,
})
export class EditorPaneComponent {
  @Input() projectText = '';
  @Input() projectDirty = false;
  @Input() projectGates: ProjectGate[] = [];
  @Input() constitution: string[] = [];
  @Input() busy = false;
  @Output() projectTextChange = new EventEmitter<string>();
  @Output() saveProject = new EventEmitter<void>();
  @Output() runGate = new EventEmitter<string>();
}
