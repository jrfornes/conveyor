import { Component, EventEmitter, Input, Output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { ApprovalItem, InboxItem, NeedsHumanEntry } from '../models';

@Component({
  selector: 'app-attention-strip',
  standalone: true,
  imports: [MatChipsModule, MatButtonModule, RouterLink],
  template: `
    @if (items.length || awaiting.length || approvals.length) {
      <div class="strip" role="alert">
        @if (items.length) {
          <strong>Needs human</strong>
          @for (item of items; track item.task) {
            <span class="item">
              <mat-chip-set>
                <mat-chip>{{ item.task }}</mat-chip>
              </mat-chip-set>
              <span class="reason">{{ item.reason }}</span>
              <span class="detail">{{ item.detail }}</span>
              <button mat-stroked-button (click)="resume.emit(item.task)">Resume</button>
              <button mat-button color="warn" (click)="deleteTask.emit(item.task)">Delete</button>
            </span>
          }
        }
        @if (awaiting.length) {
          <strong>Intake approval</strong>
          @for (item of awaiting; track item.id) {
            <span class="item">
              <mat-chip-set>
                <mat-chip>{{ item.title }}</mat-chip>
              </mat-chip-set>
              <a mat-stroked-button [routerLink]="['/inbox', item.id]">Review</a>
            </span>
          }
        }
        @if (approvals.length) {
          <strong>Spec approval</strong>
          @for (item of approvals; track item.id) {
            <span class="item">
              <mat-chip-set>
                <mat-chip>{{ item.task }}</mat-chip>
              </mat-chip-set>
              <button mat-stroked-button (click)="specApprove.emit(item.id)">Review</button>
            </span>
          }
        }
      </div>
    }
  `,
  styles: `
    .strip {
      background: #fff3e0;
      border-bottom: 1px solid #ffcc80;
      padding: 6px 12px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      font-size: 13px;
    }
    .item { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .reason { font-family: monospace; color: #e65100; }
    .detail { color: #5d4037; max-width: 40ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  `,
})
export class AttentionStripComponent {
  @Input() items: NeedsHumanEntry[] = [];
  @Input() awaiting: InboxItem[] = [];
  @Input() approvals: ApprovalItem[] = [];
  @Output() resume = new EventEmitter<string>();
  @Output() deleteTask = new EventEmitter<string>();
  @Output() specApprove = new EventEmitter<string>();
}
