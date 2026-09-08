import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Hop, RoleAvatar, RoleRecord } from '../models';

interface BeltNode {
  name: string;
  avatar: RoleAvatar;
  selectable: boolean;
}

@Component({
  selector: 'app-belt-diagram',
  standalone: true,
  imports: [MatIconModule, MatTooltipModule],
  template: `
    <div class="belt" role="list">
      @for (node of nodes; track node.name; let i = $index; let last = $last) {
        <button
          type="button"
          class="node"
          role="listitem"
          [attr.aria-label]="node.name"
          [class.selected]="node.name === selected"
          [class.mark]="!node.selectable"
          [disabled]="!node.selectable"
          [matTooltip]="node.avatar.owns"
          (click)="node.selectable && select.emit(node.name)"
        >
          <span class="avatar" [style.background]="node.avatar.color">
            <mat-icon>{{ node.avatar.icon }}</mat-icon>
          </span>
          <span class="label">{{ node.name }}</span>
        </button>
        @if (!last) {
          <div class="edge">
            @if (gatedAfter(i)) {
              <mat-icon class="diamond" matTooltip="Handoff held until you approve">diamond</mat-icon>
            }
            <span class="verdict">{{ forwardVerdict(i) }}</span>
            <span class="arrow">→</span>
          </div>
        }
      }
    </div>
    @if (findingsHop; as hop) {
      <div class="findings">
        <span class="verdict">{{ hop.verdict }}</span>
        {{ hop.from }} → {{ hop.to }}
      </div>
    }
  `,
  styles: `
    .belt {
      display: flex;
      align-items: center;
      gap: 4px;
      overflow-x: auto;
      padding: 6px 0;
    }
    .node {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      border: 2px solid transparent;
      background: #fff;
      border-radius: 10px;
      padding: 6px 10px;
      cursor: pointer;
      font: inherit;
      min-width: 80px;
    }
    .node.mark { cursor: default; opacity: 0.85; }
    .node.selected { border-color: var(--mat-sys-primary, #1976d2); }
    .avatar {
      width: 30px; height: 30px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      color: #fff;
      mat-icon { font-size: 18px; width: 18px; height: 18px; }
    }
    .label { font-size: 12px; font-weight: 500; }
    .hint { display: block; font-size: 11px; opacity: 0.65; }
    .edge {
      display: flex; flex-direction: column; align-items: center;
      min-width: 56px; color: rgba(0,0,0,0.55); font-size: 11px;
    }
    .arrow { font-size: 16px; line-height: 1; }
    .verdict { text-transform: uppercase; letter-spacing: 0.04em; }
    .diamond { font-size: 18px; width: 18px; height: 18px; color: #f9a825; }
    .findings {
      font-size: 12px; color: rgba(0,0,0,0.6); margin-top: 4px;
      .verdict { margin-right: 6px; color: #c62828; }
    }
  `,
})
export class BeltDiagramComponent {
  @Input() roles: RoleRecord[] = [];
  @Input() routes: Hop[] = [];
  /** Role whose outbound `ready` is held for the operator, or null. */
  @Input() gate: string | null = null;
  @Input() marks: { operator: RoleAvatar; done: RoleAvatar } | null = null;
  @Input() selected: string | null = null;
  @Output() select = new EventEmitter<string>();

  get nodes(): BeltNode[] {
    const op = this.marks?.operator ?? { icon: 'person', color: '#546e7a', owns: '' };
    const doneAv = this.marks?.done ?? { icon: 'check_circle', color: '#2e7d32', owns: '' };
    const marks: BeltNode[] = [
      { name: 'operator', avatar: op, selectable: false },
    ];
    const coding = this.roles.map((r) => ({ name: r.name, avatar: r.avatar, selectable: true }));
    const done: BeltNode = { name: 'done', avatar: doneAv, selectable: false };
    return [...marks, ...coding, done];
  }

  get findingsHop(): Hop | undefined {
    return this.routes.find((r) => r.verdict === 'findings');
  }

  /** True when the edge leaving node `i` is the gated one. */
  gatedAfter(i: number): boolean {
    return this.gate !== null && this.nodes[i]?.name === this.gate;
  }

  forwardVerdict(i: number): string {
    const from = this.nodes[i]?.name;
    const to = this.nodes[i + 1]?.name;
    const hit = this.routes.find((r) => r.from === from && r.to === to);
    return hit?.verdict ?? 'ready';
  }
}
