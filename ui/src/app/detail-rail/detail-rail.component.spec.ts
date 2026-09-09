import { discardPeriodicTasks, fakeAsync, tick } from '@angular/core/testing';
import { Observable, of, throwError } from 'rxjs';
import { HandoffSummary, LogEvent, RunLog } from '../models';
import { ConveyorApiService } from '../services/conveyor-api.service';
import { DetailRailComponent, REFRESH_MS, atEnd } from './detail-rail.component';

/** A log read; `prompt` defaults to the pre-recording shape (none). */
type LogsResponse = Omit<RunLog, 'prompt'> & { prompt?: string | null };

function event(detail: string): LogEvent {
  return { type: 'assistant', at: '2026-09-07T12:34:56Z', detail };
}

/** An api whose log read is scripted call by call; queues always come back empty. */
function apiWithLogs(...reads: (LogsResponse | 'fail')[]): ConveyorApiService {
  let n = 0;
  return {
    logs: (): Observable<RunLog> => {
      const r = reads[Math.min(n++, reads.length - 1)];
      return r === 'fail' ? throwError(() => new Error('down')) : of({ prompt: null, ...r });
    },
    handoffs: (): Observable<HandoffSummary[]> => of([]),
  } as unknown as ConveyorApiService;
}

/** Just enough of the <pre> for the tail logic: three numbers it reads and writes. */
function pre(rail: DetailRailComponent, scrollHeight: number, clientHeight: number) {
  const el = { scrollTop: 0, scrollHeight, clientHeight } as HTMLElement;
  (rail as unknown as { logPre: { nativeElement: HTMLElement } }).logPre = { nativeElement: el };
  return el;
}

describe('atEnd', () => {
  it('counts a view parked at the last line, slop included', () => {
    expect(atEnd(400, 100, 500)).toBe(true);
    expect(atEnd(390, 100, 500)).toBe(true);
  });

  it('does not count a view the operator scrolled back', () => {
    expect(atEnd(0, 100, 500)).toBe(false);
    expect(atEnd(200, 100, 500)).toBe(false);
  });
});

describe('DetailRailComponent log refresh', () => {
  it('reads the log as soon as a role is picked', () => {
    const rail = new DetailRailComponent(apiWithLogs({ filename: 'a.jsonl', events: [event('one')] }));
    rail.onSelectRole('coder');
    expect(rail.logFile).toBe('a.jsonl');
    expect(rail.logEvents.length).toBe(1);
    expect(rail.loadingLog).toBe(false);
    rail.ngOnDestroy();
  });

  it('keeps re-reading it, so a growing log needs no second click', fakeAsync(() => {
    const rail = new DetailRailComponent(
      apiWithLogs(
        { filename: 'a.jsonl', events: [event('one')] },
        { filename: 'a.jsonl', events: [event('one'), event('two')] },
      ),
    );
    rail.onSelectRole('coder');
    expect(rail.logEvents.length).toBe(1);
    tick(REFRESH_MS);
    expect(rail.logEvents.length).toBe(2);
    rail.ngOnDestroy();
    discardPeriodicTasks();
  }));

  it('stops reading once the rail goes away', fakeAsync(() => {
    const rail = new DetailRailComponent(
      apiWithLogs(
        { filename: 'a.jsonl', events: [event('one')] },
        { filename: 'a.jsonl', events: [event('one'), event('two')] },
      ),
    );
    rail.onSelectRole('coder');
    rail.ngOnDestroy();
    tick(REFRESH_MS);
    expect(rail.logEvents.length).toBe(1);
    discardPeriodicTasks();
  }));

  it('holds the last good read when a refresh fails', fakeAsync(() => {
    const rail = new DetailRailComponent(
      apiWithLogs({ filename: 'a.jsonl', events: [event('one')] }, 'fail'),
    );
    rail.onSelectRole('coder');
    tick(REFRESH_MS);
    expect(rail.logFile).toBe('a.jsonl');
    expect(rail.logEvents.length).toBe(1);
    rail.ngOnDestroy();
    discardPeriodicTasks();
  }));

  it('carries the run prompt, hidden until asked for, and drops it with the role', fakeAsync(() => {
    const rail = new DetailRailComponent(
      apiWithLogs(
        { filename: 'a.jsonl', events: [event('one')], prompt: 'Re-read your role and constitution.\n\nTask: demo' },
        'fail',
      ),
    );
    rail.onSelectRole('coder');
    expect(rail.logPrompt).toContain('Task: demo');
    expect(rail.showPrompt).toBe(false);
    rail.showPrompt = true;
    // A failed refresh keeps the prompt with the rest of the last good read.
    tick(REFRESH_MS);
    expect(rail.logPrompt).toContain('Task: demo');
    rail.ngOnDestroy();
    discardPeriodicTasks();

    // Picking another role starts collapsed again, and a log without a prompt has none.
    const other = new DetailRailComponent(apiWithLogs({ filename: 'b.jsonl', events: [event('two')] }));
    other.showPrompt = true;
    other.onSelectRole('reviewer');
    expect(other.showPrompt).toBe(false);
    expect(other.logPrompt).toBe(null);
    other.ngOnDestroy();
  }));

  it('shows nothing when the very first read fails', fakeAsync(() => {
    const rail = new DetailRailComponent(apiWithLogs('fail'));
    rail.onSelectRole('coder');
    expect(rail.logFile).toBe(null);
    expect(rail.logEvents).toEqual([]);
    expect(rail.loadingLog).toBe(false);
    rail.ngOnDestroy();
    discardPeriodicTasks();
  }));
});

describe('DetailRailComponent tail', () => {
  it('follows the end of the log as lines arrive', () => {
    const rail = new DetailRailComponent(apiWithLogs({ filename: 'a.jsonl', events: [event('one')] }));
    rail.onSelectRole('coder');
    const el = pre(rail, 500, 100);
    rail.ngAfterViewChecked();
    expect(el.scrollTop).toBe(500);
    rail.ngOnDestroy();
  });

  it('leaves the view alone once the operator scrolls back', () => {
    const rail = new DetailRailComponent(apiWithLogs({ filename: 'a.jsonl', events: [event('one')] }));
    rail.onSelectRole('coder');
    const el = pre(rail, 500, 100);
    el.scrollTop = 40;
    rail.onLogScroll();
    expect(rail.follow).toBe(false);

    rail.logEvents = [event('one'), event('two')];
    rail.ngAfterViewChecked();
    expect(el.scrollTop).toBe(40);

    // Scrolling back to the end resumes the tail.
    el.scrollTop = 400;
    rail.onLogScroll();
    expect(rail.follow).toBe(true);
    rail.logEvents = [event('one'), event('two'), event('three')];
    rail.ngAfterViewChecked();
    expect(el.scrollTop).toBe(500);
    rail.ngOnDestroy();
  });
});
