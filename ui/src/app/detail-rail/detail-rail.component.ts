import {
  AfterViewChecked,
  Component,
  ElementRef,
  Input,
  OnChanges,
  OnDestroy,
  SimpleChanges,
  ViewChild,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatTabsModule } from '@angular/material/tabs';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Subscription, catchError, forkJoin, interval, of, startWith, switchMap } from 'rxjs';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { ConveyorTask, HandoffSummary, LogEvent, WorkEntry } from '../models';
import { WorkQueueComponent } from '../work-queue/work-queue.component';

const QUEUE_DIRS = ['new', 'in_process', 'sent'] as const;

/** How often the open log and queues re-read, matching the board's state poll. */
export const REFRESH_MS = 2000;

/** Distance from the last line that still counts as the end, in pixels. */
const END_SLOP = 16;

/** Is the log view parked at its last line? Fractional heights need the slop. */
export function atEnd(scrollTop: number, clientHeight: number, scrollHeight: number): boolean {
  return scrollHeight - scrollTop - clientHeight <= END_SLOP;
}

interface MdBlock {
  text: string;
  heading?: boolean;
  ordinal?: number;
}

/** The subset tasks/<name>.md actually uses: headings and a numbered list. */
function renderTask(text: string): MdBlock[] {
  const blocks: MdBlock[] = [];
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    const heading = line.match(/^#+\s+(.*)$/);
    if (heading) {
      blocks.push({ text: heading[1], heading: true });
      continue;
    }
    const item = line.match(/^(\d+)[.)]\s+(.*)$/);
    if (item) {
      blocks.push({ text: item[2], ordinal: Number(item[1]) });
      continue;
    }
    blocks.push({ text: line });
  }
  return blocks;
}

@Component({
  selector: 'app-detail-rail',
  standalone: true,
  imports: [MatButtonModule, MatTabsModule, MatProgressSpinnerModule, WorkQueueComponent],
  template: `
    <div class="rail">
      <app-work-queue [work]="work" (selectRole)="onSelectRole($event)"></app-work-queue>
      <mat-tab-group [(selectedIndex)]="tabIndex">
        <mat-tab label="Task">
          @if (loadingTask) {
            <mat-spinner diameter="24"></mat-spinner>
          } @else if (taskText) {
            @if (task) {
              <div class="meta">
                <code>{{ task.task_id }}</code>
                <span>lane {{ task.lane }}</span>
                <span>audits {{ task.audit_count }}</span>
                <span>retries {{ task.retry_count }}</span>
              </div>
            }
            <div class="md">
              @for (block of taskBlocks; track $index) {
                @if (block.heading) {
                  <h4 class="md-h">{{ block.text }}</h4>
                } @else if (block.ordinal) {
                  <div class="md-li"><span class="ord">{{ block.ordinal }}.</span>{{ block.text }}</div>
                } @else {
                  <p class="md-p">{{ block.text }}</p>
                }
              }
            </div>
          } @else {
            <p class="muted">No task content</p>
          }
        </mat-tab>
        <mat-tab label="Log">
          @if (loadingLog) {
            <mat-spinner diameter="24"></mat-spinner>
          } @else if (logFile) {
            <div class="log-meta">
              {{ logRole }} · {{ logFile }}
              @if (logStarted(); as started) {
                <span> · {{ started }}</span>
              }
              @if (peek; as p) {
                <span class="peek"> · {{ p }}</span>
              }
              <span class="live">{{ follow ? ' · live' : ' · live · scroll to the end to follow' }}</span>
              @if (logPrompt !== null) {
                <button mat-button class="prompt-toggle" (click)="showPrompt = !showPrompt">
                  {{ showPrompt ? 'Hide prompt' : 'Show prompt' }}
                </button>
              }
            </div>
            @if (showPrompt && logPrompt !== null) {
              <div class="prompt-meta">What the agent was told for this run, verbatim.</div>
              <pre class="mono prompt">{{ logPrompt }}</pre>
            }
            <pre #logPre class="mono log" (scroll)="onLogScroll()">{{ formatLog() }}</pre>
          } @else if (logRole) {
            <p class="muted">No log yet for {{ logRole }}</p>
          } @else {
            <p class="muted">Click a role in the work queue to view agent logs</p>
          }
        </mat-tab>
        <mat-tab label="Queues">
          @if (loadingQueues) {
            <mat-spinner diameter="24"></mat-spinner>
          } @else {
            @for (section of queueSections; track section.label) {
              <h4>{{ section.label }} ({{ section.items.length }})</h4>
              @for (h of section.items; track h.file) {
                <div class="handoff">
                  <strong>{{ h.task }}</strong>
                  {{ h.from }} → {{ h.to }} · {{ h.verdict }}
                  @if (h.commit) {
                    <code>{{ h.commit }}</code>
                  }
                </div>
              }
            }
          }
        </mat-tab>
      </mat-tab-group>
    </div>
  `,
  styles: `
    .rail { display: flex; flex-direction: column; height: 100%; min-height: 0; padding: 0; gap: 6px; min-width: 0; }
    .mono { font-family: ui-monospace, monospace; font-size: 12px; white-space: pre-wrap; overflow: auto; max-height: 40vh; margin: 6px 0; }
    .log { max-height: 40vh; }
    .log-meta { font-size: 12px; opacity: 0.7; display: flex; flex-wrap: wrap; align-items: center; gap: 0 4px; }
    .prompt-toggle { margin-left: auto; height: 24px; line-height: 24px; font-size: 12px; padding: 0 8px; }
    .prompt-meta { font-size: 11px; opacity: 0.6; margin-top: 4px; }
    .prompt { max-height: 30vh; padding: 6px 8px; border-left: 3px solid rgba(0,0,0,0.15); background: rgba(0,0,0,0.03); }
    .peek { font-family: ui-monospace, monospace; }
    .live { opacity: 0.8; }
    .meta {
      display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
      font-size: 11px; opacity: 0.75; padding: 4px 0;
      border-bottom: 1px solid rgba(0,0,0,0.08);
    }
    .meta code { font-family: ui-monospace, monospace; }
    .md { padding: 2px 0 8px; overflow: auto; max-height: 32vh; }
    .md-h { margin: 8px 0 3px; font-size: 13px; text-transform: none; letter-spacing: 0; }
    .md-p { margin: 4px 0; font-size: 13px; }
    .md-li { display: flex; gap: 6px; font-size: 13px; margin: 3px 0; }
    .md-li .ord { opacity: 0.6; flex: none; }
    .muted { opacity: 0.6; font-size: 13px; padding: 6px; }
    h4 { margin: 8px 0 3px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }
    .handoff { font-size: 12px; padding: 4px 0; border-bottom: 1px solid rgba(0,0,0,0.08); }
    mat-tab-group { flex: 1; min-height: 0; overflow: hidden; }
  `,
})
export class DetailRailComponent implements OnChanges, AfterViewChecked, OnDestroy {
  @Input() work: WorkEntry[] = [];
  @Input() selectedTask: string | null = null;
  /** Board row for selectedTask, for the meta line. */
  @Input() task: ConveyorTask | null = null;
  @ViewChild('logPre') logPre?: ElementRef<HTMLElement>;

  tabIndex = 0;
  taskText = '';
  loadingTask = false;
  logRole = '';
  logFile: string | null = null;
  logEvents: LogEvent[] = [];
  /** The prompt of the run shown; null until a log with one is read. */
  logPrompt: string | null = null;
  showPrompt = false;
  loadingLog = false;
  loadingQueues = false;
  queueSections: { label: string; items: HandoffSummary[] }[] = [];
  taskBlocks: MdBlock[] = [];
  /** Tail the log as it grows; off once the operator scrolls back to read. */
  follow = true;
  private scrolledFor = '';
  private poll?: Subscription;

  constructor(private api: ConveyorApiService) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['selectedTask'] && this.selectedTask) {
      this.loadTask(this.selectedTask);
    }
  }

  ngOnDestroy(): void {
    this.poll?.unsubscribe();
  }

  onSelectRole(role: string): void {
    this.logRole = role;
    this.tabIndex = 1;
    this.follow = true;
    this.showPrompt = false;
    this.watchRole(role);
  }

  /**
   * Show `role`'s log and queues, then re-read them every REFRESH_MS. The log
   * file grows for as long as the agent runs, so one read is stale by the time
   * it renders; without this the operator re-clicks the role to see anything
   * new.
   */
  private watchRole(role: string): void {
    this.poll?.unsubscribe();
    this.loadingLog = true;
    this.loadingQueues = true;
    this.poll = interval(REFRESH_MS)
      .pipe(
        startWith(0),
        switchMap(() =>
          forkJoin({
            log: this.api.logs(role, this.selectedTask ?? undefined),
            queues: forkJoin(QUEUE_DIRS.map((dir) => this.api.handoffs(role, dir))),
          }).pipe(catchError(() => of(null))),
        ),
      )
      .subscribe((r) => {
        // A refresh that fails keeps the last good read on screen — the next
        // tick is REFRESH_MS away. Only a first read has nothing to keep.
        if (!r) {
          if (this.loadingLog) this.clearRole();
          return;
        }
        this.logFile = r.log.filename;
        this.logEvents = r.log.events;
        this.logPrompt = r.log.prompt;
        this.queueSections = QUEUE_DIRS.map((dir, i) => ({
          label: dir.replace('_', ' '),
          items: r.queues[i],
        }));
        this.loadingLog = false;
        this.loadingQueues = false;
      });
  }

  private clearRole(): void {
    this.logFile = null;
    this.logEvents = [];
    this.logPrompt = null;
    this.queueSections = [];
    this.loadingLog = false;
    this.loadingQueues = false;
  }

  loadTask(name: string): void {
    this.loadingTask = true;
    this.api.task(name).subscribe({
      next: (r) => {
        this.taskText = r.text;
        this.taskBlocks = renderTask(r.text);
        this.loadingTask = false;
      },
      error: () => {
        this.taskText = '';
        this.taskBlocks = [];
        this.loadingTask = false;
      },
    });
  }

  /** Queue peek for the role whose log is shown: how much is waiting behind it. */
  get peek(): string {
    const entry = this.work.find((w) => w.role === this.logRole);
    if (!entry) return '';
    const parts = [`${entry.new_count} new`];
    if (entry.task) parts.push(`1 in_process`);
    return parts.join(' · ');
  }

  ngAfterViewChecked(): void {
    const el = this.logPre?.nativeElement;
    if (!el) return;
    const key = `${this.logRole}/${this.logFile}/${this.logEvents.length}`;
    if (key === this.scrolledFor) return;
    this.scrolledFor = key;
    if (this.follow) el.scrollTop = el.scrollHeight;
  }

  /** Scrolling away from the end stops the tail; scrolling back resumes it. */
  onLogScroll(): void {
    const el = this.logPre?.nativeElement;
    if (el) this.follow = atEnd(el.scrollTop, el.clientHeight, el.scrollHeight);
  }

  /** Date of the first dated line, so the clock column below has a day. */
  logStarted(): string {
    return this.logEvents.find((e) => e.at?.length === 20)?.at ?? '';
  }

  formatLog(): string {
    return this.logEvents
      .map((e) => {
        // UTC clock, same as `conveyor log`; blank column for logs written before dating.
        const clock = (e.at?.length === 20 ? e.at.slice(11, 19) : '').padEnd(9);
        const text = e.detail ? `[${e.type}] ${e.detail}` : e.text ?? `[${e.type}]`;
        return clock + text.replace(/\n/g, '\n' + ' '.repeat(9));
      })
      .join('\n');
  }
}
