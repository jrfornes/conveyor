import { Injectable, computed, signal } from '@angular/core';
import { Subscription, interval, switchMap, catchError, of, startWith } from 'rxjs';
import { ConveyorState } from '../models';
import { ConveyorApiService } from './conveyor-api.service';

@Injectable({ providedIn: 'root' })
export class UiStateService {
  readonly state = signal<ConveyorState | null>(null);
  readonly live = signal(false);
  readonly error = signal('');
  readonly busy = signal(false);
  /** Poll failing while a previous state is still on screen. */
  readonly stale = computed(() => !this.live() && this.state() !== null);
  private sub?: Subscription;

  constructor(private api: ConveyorApiService) {}

  startPolling(): void {
    this.stopPolling();
    this.sub = interval(2000)
      .pipe(
        startWith(0),
        switchMap(() =>
          this.api.state().pipe(
            catchError((e) => {
              this.live.set(false);
              this.error.set(e?.error?.error ?? e.message ?? 'Poll failed');
              return of(null);
            }),
          ),
        ),
      )
      .subscribe((s) => {
        if (s) {
          this.state.set(s);
          this.live.set(true);
          this.error.set('');
        }
      });
  }

  stopPolling(): void {
    this.sub?.unsubscribe();
    this.sub = undefined;
  }

  refresh(): void {
    this.api.state().subscribe((s) => this.state.set(s));
  }

  fail(e: { error?: { error?: string }; message?: string }, fallback = 'Request failed'): void {
    this.error.set(e?.error?.error ?? e.message ?? fallback);
  }
}
