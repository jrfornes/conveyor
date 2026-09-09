import { Injectable, computed, signal } from '@angular/core';
import { Subscription, interval, switchMap, catchError, of, startWith } from 'rxjs';
import { ConveyorState } from '../models';
import { ConveyorApiService } from './conveyor-api.service';

/** Anything HttpErrorResponse-shaped that a failed request hands back. */
export interface FailureLike {
  error?: { error?: string };
  message?: string;
}

/**
 * One recorded failure. A repeat of the newest entry folds into `count` rather
 * than pushing a duplicate — a 2s poll against a dead server would otherwise
 * fill the whole history with one message.
 */
export interface ErrorEntry {
  id: number;
  /** `poll` is the background state poll; `action` is something the operator did. */
  kind: 'action' | 'poll';
  message: string;
  at: Date;
  count: number;
}

/** How many past failures the history keeps. */
export const ERROR_HISTORY_MAX = 20;

/** The server's message if it sent one, else the transport's, else `fallback`. */
export function errorMessage(e: FailureLike | null | undefined, fallback: string): string {
  return e?.error?.error || e?.message || fallback;
}

/** Fold `entry` into `history` (newest first), collapsing a repeat of the head. */
export function pushError(history: ErrorEntry[], entry: ErrorEntry): ErrorEntry[] {
  const head = history[0];
  if (head && head.kind === entry.kind && head.message === entry.message) {
    return [{ ...head, at: entry.at, count: head.count + 1 }, ...history.slice(1)];
  }
  return [entry, ...history].slice(0, ERROR_HISTORY_MAX);
}

@Injectable({ providedIn: 'root' })
export class UiStateService {
  readonly state = signal<ConveyorState | null>(null);
  readonly live = signal(false);
  readonly busy = signal(false);

  /**
   * The last action failure, held until the operator dismisses it or starts the
   * next action. Never cleared on a timer: an error nobody read is
   * indistinguishable from no error at all.
   */
  readonly actionError = signal<ErrorEntry | null>(null);

  /**
   * The current poll failure. Owned by the poll loop alone, which clears it as
   * soon as the poll recovers — this is the one error that *should* self-clear,
   * because the live dot and `stale` already carry the same news.
   */
  readonly pollError = signal('');

  /** Recent failures, newest first, capped at ERROR_HISTORY_MAX. */
  readonly history = signal<ErrorEntry[]>([]);

  /** Poll failing while a previous state is still on screen. */
  readonly stale = computed(() => !this.live() && this.state() !== null);

  private sub?: Subscription;
  private nextId = 1;

  constructor(private api: ConveyorApiService) {}

  startPolling(): void {
    this.stopPolling();
    this.sub = interval(2000)
      .pipe(
        startWith(0),
        switchMap(() =>
          this.api.state().pipe(
            catchError((e) => {
              this.pollFailed(e, 'Poll failed');
              return of(null);
            }),
          ),
        ),
      )
      .subscribe((s) => {
        if (s) {
          this.state.set(s);
          this.live.set(true);
          // Only the poll's own error clears here. An action failure belongs to
          // the operator; a 2s tick must never wipe it off the screen.
          this.pollError.set('');
        }
      });
  }

  stopPolling(): void {
    this.sub?.unsubscribe();
    this.sub = undefined;
  }

  refresh(): void {
    this.api.state().subscribe({
      next: (s) => {
        this.state.set(s);
        this.live.set(true);
        this.pollError.set('');
      },
      error: (e) => this.pollFailed(e, 'Refresh failed'),
    });
  }

  /** Begin an operator action: mark busy and retire the previous action's error. */
  startAction(): void {
    this.busy.set(true);
    this.actionError.set(null);
  }

  /** Report an action failure on the shared, sticky error channel. */
  fail(e: FailureLike, fallback = 'Request failed'): void {
    this.actionError.set(this.record('action', errorMessage(e, fallback)));
  }

  /**
   * Record a failure that a component already shows inline next to its own
   * control, so it reaches the history without being reported twice.
   */
  note(e: FailureLike, fallback = 'Request failed'): void {
    this.record('action', errorMessage(e, fallback));
  }

  dismissError(): void {
    this.actionError.set(null);
  }

  clearHistory(): void {
    this.history.set([]);
  }

  private pollFailed(e: FailureLike, fallback: string): void {
    this.live.set(false);
    const message = errorMessage(e, fallback);
    this.pollError.set(message);
    this.record('poll', message);
  }

  /** Append to the history and hand back the entry now at its head. */
  private record(kind: ErrorEntry['kind'], message: string): ErrorEntry {
    this.history.update((h) =>
      pushError(h, { id: this.nextId++, kind, message, at: new Date(), count: 1 }),
    );
    return this.history()[0];
  }
}
