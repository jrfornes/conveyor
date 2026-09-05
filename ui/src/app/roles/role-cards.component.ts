import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { AgentModel, RoleRecord } from '../models';

@Component({
  selector: 'app-role-cards',
  standalone: true,
  imports: [
    FormsModule,
    MatCardModule,
    MatButtonModule,
    MatAutocompleteModule,
    MatFormFieldModule,
    MatInputModule,
    MatIconModule,
  ],
  template: `
    <div class="cards">
      @for (role of roles; track role.name) {
        <mat-card
          class="card"
          [class.selected]="role.name === selected"
          [class.library]="!role.in_workflow"
          (click)="select.emit(role.name)"
        >
          <mat-card-header>
            <span class="avatar" mat-card-avatar [style.background]="role.avatar.color">
              <mat-icon>{{ role.avatar.icon }}</mat-icon>
            </span>
            <mat-card-title>{{ role.name }}</mat-card-title>
            <mat-card-subtitle>{{ badge(role) }}</mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            <p class="owns">{{ role.avatar.owns }}</p>
            @if (!role.in_workflow) {
              <p class="not-in">Not in this workflow.</p>
            }
            @if (role.hops.length) {
              <div class="hops">
                @for (hop of role.hops; track hop.to + hop.verdict) {
                  <span class="hop">{{ hop.to }}<span class="verdict">{{ hop.verdict }}</span></span>
                }
              </div>
            }
            @if (role.in_workflow) {
              <div class="runtime" (click)="$event.stopPropagation()">
                <mat-form-field appearance="outline" subscriptSizing="dynamic">
                  <mat-label>Model</mat-label>
                  <input
                    matInput
                    [matAutocomplete]="modelAuto"
                    [(ngModel)]="role.model"
                    [disabled]="locked"
                    autocomplete="off"
                  />
                  <mat-autocomplete #modelAuto="matAutocomplete">
                    @for (m of filteredModels(role.model); track m.id) {
                      <mat-option [value]="m.id">
                        <span class="mid">{{ m.id }}</span>
                        @if (m.label && m.label !== m.id) {
                          <span class="mlabel">{{ m.label }}</span>
                        }
                      </mat-option>
                    }
                  </mat-autocomplete>
                </mat-form-field>
                <div class="ceilings">
                  <mat-form-field appearance="outline" subscriptSizing="dynamic">
                    <mat-label>Retries</mat-label>
                    <input matInput type="number" min="1" [(ngModel)]="role.max_retries" [disabled]="locked" />
                  </mat-form-field>
                  <mat-form-field appearance="outline" subscriptSizing="dynamic">
                    <mat-label>Minutes</mat-label>
                    <input matInput type="number" min="1" [(ngModel)]="role.max_minutes" [disabled]="locked" />
                  </mat-form-field>
                  <mat-form-field appearance="outline" subscriptSizing="dynamic">
                    <mat-label>Attempts</mat-label>
                    <input matInput type="number" min="1" [(ngModel)]="role.max_attempts" [disabled]="locked" />
                  </mat-form-field>
                </div>
                <button
                  mat-stroked-button
                  [disabled]="locked || busy"
                  (click)="saveRuntime.emit(role)"
                >Save runtime</button>
              </div>
            }
          </mat-card-content>
        </mat-card>
      }
    </div>
  `,
  styles: `
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 12px;
    }
    .card { cursor: pointer; }
    .card.library {
      border: 1px dashed rgba(0,0,0,0.28);
      box-shadow: none;
      background: transparent;
    }
    .not-in { font-size: 12px; opacity: 0.6; margin: 0 0 8px; }
    .hops { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
    .hop {
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 11px; padding: 2px 8px; border-radius: 10px;
      background: rgba(0,0,0,0.06);
    }
    .hop .verdict { font-family: ui-monospace, monospace; opacity: 0.65; }
    .card.selected { outline: 2px solid var(--mat-sys-primary, #1976d2); }
    .avatar {
      display: flex; align-items: center; justify-content: center; color: #fff;
      mat-icon { font-size: 20px; width: 20px; height: 20px; }
    }
    .owns { font-size: 13px; color: rgba(0,0,0,0.65); margin: 8px 0 12px; }
    .runtime { display: flex; flex-direction: column; gap: 8px; }
    .ceilings { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
    mat-form-field { width: 100%; }
    .mid { font-family: ui-monospace, monospace; }
    .mlabel { margin-left: 8px; opacity: 0.65; font-size: 12px; }
  `,
})
export class RoleCardsComponent {
  @Input() roles: RoleRecord[] = [];
  @Input() models: AgentModel[] = [];
  @Input() selected: string | null = null;
  @Input() locked = false;
  @Input() busy = false;
  @Output() select = new EventEmitter<string>();
  @Output() saveRuntime = new EventEmitter<RoleRecord>();

  filteredModels(query: string | undefined): AgentModel[] {
    const q = (query ?? '').trim().toLowerCase();
    if (!q || this.models.some((m) => m.id.toLowerCase() === q)) return this.models;
    return this.models.filter(
      (m) => m.id.toLowerCase().includes(q) || m.label.toLowerCase().includes(q),
    );
  }

  badge(role: RoleRecord): string {
    return role.in_workflow ? 'in this workflow' : 'library';
  }
}
