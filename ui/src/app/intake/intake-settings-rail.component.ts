import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { AgentModel, IntakeState, RoleAvatar } from '../models';
import { ConveyorApiService } from '../services/conveyor-api.service';

@Component({
  selector: 'app-intake-settings-rail',
  standalone: true,
  imports: [
    FormsModule,
    MatTabsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatIconModule,
    MatSnackBarModule,
  ],
  template: `
    <aside class="rail">
      <header class="head">
        <span class="avatar" [style.background]="avatar.color">
          <mat-icon>{{ avatar.icon }}</mat-icon>
        </span>
        <div>
          <h3>Intake</h3>
          <p class="tag">Runs on Import. Not a coding role; not part of the workflow.</p>
          <code class="path">{{ path }}</code>
        </div>
      </header>

      <div class="fields">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="model-field">
          <mat-label>Model</mat-label>
          <mat-select [(ngModel)]="model" (ngModelChange)="configDirty = true">
            @for (m of modelOptions(model); track m.id) {
              <mat-option [value]="m.id">
                <span class="mid">{{ m.id }}</span>
                @if (m.label && m.label !== m.id) {
                  <span class="mlabel">{{ m.label }}</span>
                }
              </mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="num-field">
          <mat-label>Minutes</mat-label>
          <input matInput type="number" min="0" [(ngModel)]="minutes" (ngModelChange)="configDirty = true" />
        </mat-form-field>
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="num-field">
          <mat-label>Attempts</mat-label>
          <input matInput type="number" min="0" [(ngModel)]="attempts" (ngModelChange)="configDirty = true" />
        </mat-form-field>
        <button mat-stroked-button [disabled]="!configDirty || configBusy" (click)="saveConfig()">
          Save
        </button>
      </div>
      @if (configError) {
        <p class="err" role="alert">{{ configError }}</p>
      }

      <mat-tab-group [(selectedIndex)]="tab" animationDuration="0">
        <mat-tab label="Reviewer prompt">
          <div class="pane">
            <mat-form-field appearance="outline" class="md-field">
              <textarea matInput rows="14" [(ngModel)]="prompt" (ngModelChange)="promptDirty = true" spellcheck="false"></textarea>
            </mat-form-field>
            <div class="actions">
              <button mat-flat-button [disabled]="!promptDirty || promptBusy" (click)="savePrompt()">
                Save prompt
              </button>
              <span class="hint">Must contain headings Owns, Does not own, Handoff contract.</span>
            </div>
            @if (promptError) {
              <p class="err" role="alert">{{ promptError }}</p>
            }
          </div>
        </mat-tab>
        <mat-tab label="Grading rubric">
          <div class="pane">
            @if (gradeContract) {
              <p class="explainer">{{ contractSummary }}</p>
            }
            <mat-form-field appearance="outline" class="md-field">
              <textarea matInput rows="14" [(ngModel)]="rubric" (ngModelChange)="rubricDirty = true" spellcheck="false"></textarea>
            </mat-form-field>
            <div class="actions">
              <button mat-flat-button [disabled]="!rubricDirty || rubricBusy" (click)="saveRubric()">
                Save rubric
              </button>
              <span class="hint">Applies to the next Grade / Improve / Import. No restart.</span>
            </div>
            @if (rubricError) {
              <p class="err" role="alert">{{ rubricError }}</p>
            }
          </div>
        </mat-tab>
        <mat-tab label="Jira">
          <div class="pane jira">
            <mat-form-field appearance="outline" subscriptSizing="dynamic">
              <mat-label>Site URL</mat-label>
              <input matInput [(ngModel)]="jiraSite" (ngModelChange)="jiraDirty = true"
                     placeholder="https://your.atlassian.net" />
            </mat-form-field>
            <mat-form-field appearance="outline" subscriptSizing="dynamic">
              <mat-label>Email</mat-label>
              <input matInput [(ngModel)]="jiraEmail" (ngModelChange)="jiraDirty = true" />
            </mat-form-field>
            <mat-form-field appearance="outline" subscriptSizing="dynamic">
              <mat-label>API token</mat-label>
              <input matInput type="password" [(ngModel)]="jiraToken" (ngModelChange)="jiraDirty = true"
                     [placeholder]="jiraTokenSet ? 'unchanged' : ''" />
            </mat-form-field>
            <p class="hint">
              Stored in <code>.conveyor/local/jira.json</code>, gitignored.
              Use <code>https://your.atlassian.net</code> (not a bare host).
              Jira import needs site, email, and token. A blank Jira description
              still creates a row but is not auto-graded.
              Test writes <code>jira.json</code> first, like
              <code>conveyor intake jira --site … --test</code>.
            </p>
            <div class="actions">
              <button mat-flat-button [disabled]="!jiraDirty || jiraBusy" (click)="saveJira()">Save Jira</button>
              <button mat-stroked-button [disabled]="jiraBusy" (click)="testJira()">
                {{ jiraDirty ? 'Save and test' : 'Test connection' }}
              </button>
              <button mat-button [disabled]="jiraBusy" (click)="clearJira()">Clear</button>
            </div>
            @if (jiraError) {
              <p class="err" role="alert">{{ jiraError }}</p>
            }
            @if (jiraTest) {
              <p class="test" [class.fail]="!jiraTestOk" role="status">{{ jiraTest }}</p>
            }
          </div>
        </mat-tab>
      </mat-tab-group>
      <p class="foot">Applies to the next Import. No restart.</p>
    </aside>
  `,
  styles: `
    :host { display: block; min-width: 0; border-left: 1px solid rgba(0,0,0,0.08); background: #fafafa; }
    .rail { display: flex; flex-direction: column; gap: 12px; padding: 16px; min-height: 0; }
    .head { display: flex; gap: 12px; align-items: flex-start; }
    .avatar {
      width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center; color: #fff;
      mat-icon { font-size: 20px; width: 20px; height: 20px; }
    }
    h3 { margin: 0; font-size: 16px; }
    .tag { margin: 2px 0 0; font-size: 12px; color: rgba(0,0,0,0.6); }
    .path { font-size: 11px; color: rgba(0,0,0,0.5); }
    .fields {
      display: grid;
      grid-template-columns: minmax(160px, 1fr) minmax(72px, 88px) minmax(72px, 88px) auto;
      gap: 8px; align-items: end;
    }
    .model-field { min-width: 0; }
    .num-field { width: 100%; }
    .mid { font-family: ui-monospace, monospace; }
    .mlabel { margin-left: 8px; opacity: 0.65; font-size: 12px; }
    .pane { display: flex; flex-direction: column; gap: 8px; padding-top: 12px; min-height: 240px; }
    .pane.jira { min-height: 0; }
    .md-field { width: 100%; flex: 1; }
    .md-field textarea {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px; line-height: 1.45;
    }
    .actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .hint { font-size: 12px; color: rgba(0,0,0,0.6); margin: 0; }
    .explainer {
      font-size: 12px;
      color: rgba(0,0,0,0.75);
      margin: 0;
      padding: 8px 10px;
      background: #eceff1;
      border-radius: 6px;
      line-height: 1.45;
    }
    .err { font-size: 12px; color: #b71c1c; margin: 0; }
    .test { font-size: 12px; color: #1b5e20; margin: 0; }
    .test.fail { color: #b71c1c; }
    .foot { font-size: 12px; color: rgba(0,0,0,0.55); margin: 0; }
    mat-form-field { width: 100%; }
    @media (max-width: 960px) {
      .fields { grid-template-columns: 1fr 1fr; }
    }
  `,
})
export class IntakeSettingsRailComponent implements OnInit {
  avatar: RoleAvatar = { icon: 'inbox', color: '#7b1fa2', owns: '' };
  path = 'intake/';
  models: AgentModel[] = [];
  model = '';
  minutes = 30;
  attempts = 2;
  prompt = '';
  rubric = '';
  gradeContract = '';
  contractSummary = '';
  jiraSite = '';
  jiraEmail = '';
  jiraToken = '';
  jiraTokenSet = false;
  tab = 0;

  configDirty = false;
  promptDirty = false;
  rubricDirty = false;
  jiraDirty = false;
  configBusy = false;
  promptBusy = false;
  rubricBusy = false;
  jiraBusy = false;
  configError = '';
  promptError = '';
  rubricError = '';
  jiraError = '';
  jiraTest = '';
  jiraTestOk = false;

  constructor(private api: ConveyorApiService, private snack: MatSnackBar) {}

  modelOptions(current: string | undefined): AgentModel[] {
    const id = (current ?? '').trim();
    if (!id || this.models.some((m) => m.id === id)) return this.models;
    return [...this.models, { id, label: id }];
  }

  ngOnInit(): void {
    this.api.intakeSettings().subscribe({
      next: (s) => this.apply(s),
      error: (e) => {
        this.configError = e?.error?.error ?? e.message ?? 'Failed to load intake';
      },
    });
    this.api.models().subscribe({
      next: (r) => (this.models = r.models ?? []),
    });
  }

  private apply(s: IntakeState): void {
    this.avatar = s.avatar;
    this.path = s.path || 'intake/';
    this.model = s.config.model;
    this.minutes = s.config.max_minutes;
    this.attempts = s.config.max_attempts;
    this.prompt = s.prompt;
    this.rubric = s.rubric;
    this.gradeContract = s.grade_contract ?? '';
    this.contractSummary = this.summarizeContract(this.gradeContract);
    this.jiraSite = s.jira.site;
    this.jiraEmail = s.jira.email;
    this.jiraTokenSet = s.jira.token_set;
    this.jiraToken = '';
    this.configDirty = this.promptDirty = this.rubricDirty = this.jiraDirty = false;
  }

  private saved(path: string): void {
    this.snack.open(`${path} saved — applies to the next Import`, undefined, { duration: 3000 });
  }

  private summarizeContract(contract: string): string {
    if (!contract.trim()) {
      return 'These checklist items define Ready. Ready / Gaps / Unusable and the Grade: line are fixed by Conveyor.';
    }
    const grades = contract.split('\n').find((l) => l.startsWith('- **Ready**'));
    const gradeLine = contract.split('\n').find((l) => l.includes('Grade: Ready'));
    const parts = ['These checklist items define Ready.'];
    if (grades) parts.push(grades.replace(/^- /, ''));
    if (gradeLine) parts.push(`Fixed: ${gradeLine.trim()}`);
    else parts.push('Ready / Gaps / Unusable and the Grade: line are fixed by Conveyor.');
    return parts.join(' ');
  }

  saveConfig(): void {
    this.configBusy = true;
    this.configError = '';
    this.api.saveIntakeConfig(this.model, Number(this.minutes), Number(this.attempts)).subscribe({
      next: (r) => {
        this.configBusy = false;
        this.configDirty = false;
        this.saved(r.path || 'conveyor.conf');
      },
      error: (e) => {
        this.configBusy = false;
        this.configError = e?.error?.error ?? e.message ?? 'Save failed';
      },
    });
  }

  savePrompt(): void {
    this.promptBusy = true;
    this.promptError = '';
    this.api.saveIntakePrompt(this.prompt).subscribe({
      next: (r) => {
        this.promptBusy = false;
        this.promptDirty = false;
        this.saved(r.path || 'intake/ticket-reviewer.md');
      },
      error: (e) => {
        this.promptBusy = false;
        this.promptError = e?.error?.error ?? e.message ?? 'Save failed';
      },
    });
  }

  saveRubric(): void {
    this.rubricBusy = true;
    this.rubricError = '';
    this.api.saveIntakeRubric(this.rubric).subscribe({
      next: (r) => {
        this.rubricBusy = false;
        this.rubricDirty = false;
        this.saved(r.path || 'intake/rubric.md');
      },
      error: (e) => {
        this.rubricBusy = false;
        this.rubricError = e?.error?.error ?? e.message ?? 'Save failed';
      },
    });
  }

  saveJira(): void {
    this.jiraBusy = true;
    this.jiraError = '';
    this.api.saveIntakeJira(this.jiraSite, this.jiraEmail, this.jiraToken || undefined).subscribe({
      next: (r) => {
        this.jiraBusy = false;
        this.jiraDirty = false;
        this.jiraToken = '';
        this.jiraTokenSet = r.token_set;
        this.saved('.conveyor/local/jira.json');
      },
      error: (e) => {
        this.jiraBusy = false;
        this.jiraError = e?.error?.error ?? e.message ?? 'Save failed';
      },
    });
  }

  testJira(): void {
    this.jiraBusy = true;
    this.jiraTest = '';
    this.api.testIntakeJira(this.jiraSite, this.jiraEmail, this.jiraToken || undefined).subscribe({
      next: (r) => {
        this.jiraBusy = false;
        this.jiraDirty = false;
        this.jiraToken = '';
        this.jiraTokenSet = r.token_set;
        this.jiraTestOk = r.ok;
        this.jiraTest = r.ok ? `Connected (${r.status})` : `${r.message || 'failed'} (${r.status})`;
      },
      error: (e) => {
        this.jiraBusy = false;
        this.jiraTestOk = false;
        this.jiraTest = e?.error?.error ?? e.message ?? 'Test failed';
      },
    });
  }

  clearJira(): void {
    this.jiraBusy = true;
    this.jiraError = '';
    this.api.clearIntakeJira().subscribe({
      next: () => {
        this.jiraBusy = false;
        this.jiraSite = '';
        this.jiraEmail = '';
        this.jiraToken = '';
        this.jiraTokenSet = false;
        this.jiraDirty = false;
        this.saved('.conveyor/local/jira.json');
      },
      error: (e) => {
        this.jiraBusy = false;
        this.jiraError = e?.error?.error ?? e.message ?? 'Clear failed';
      },
    });
  }
}
