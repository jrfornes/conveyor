import { Observable, of, throwError } from 'rxjs';
import { ConveyorState } from '../models';
import { ConveyorApiService } from './conveyor-api.service';
import {
  ERROR_HISTORY_MAX,
  ErrorEntry,
  UiStateService,
  errorMessage,
  pushError,
} from './ui-state.service';

function apiReturning(state: () => Observable<ConveyorState>): ConveyorApiService {
  return { state } as unknown as ConveyorApiService;
}

/** An api whose poll always succeeds, as it does whenever the server is up. */
const healthy = apiReturning(() => of({} as ConveyorState));

function entry(partial: Partial<ErrorEntry>): ErrorEntry {
  return { id: 1, kind: 'action', message: 'boom', at: new Date(0), count: 1, ...partial };
}

describe('errorMessage', () => {
  it('prefers the server message, then the transport, then the fallback', () => {
    expect(errorMessage({ error: { error: 'conveyor.conf missing' } }, 'Start failed'))
      .toBe('conveyor.conf missing');
    expect(errorMessage({ message: 'Http failure response' }, 'Start failed'))
      .toBe('Http failure response');
    expect(errorMessage({}, 'Start failed')).toBe('Start failed');
    expect(errorMessage(undefined, 'Start failed')).toBe('Start failed');
  });

  it('falls through empty strings instead of reporting a blank error', () => {
    expect(errorMessage({ error: { error: '' }, message: '' }, 'Start failed'))
      .toBe('Start failed');
  });
});

describe('pushError', () => {
  it('keeps the newest entry first', () => {
    const one = entry({ id: 1, message: 'first' });
    const two = entry({ id: 2, message: 'second' });
    expect(pushError(pushError([], one), two).map((e) => e.message)).toEqual(['second', 'first']);
  });

  it('folds a repeat of the head into a count rather than duplicating it', () => {
    const at = new Date(1000);
    const history = pushError(pushError([], entry({ id: 1 })), entry({ id: 2, at }));
    expect(history.length).toBe(1);
    expect(history[0].count).toBe(2);
    expect(history[0].at).toBe(at);
    // The fold keeps the original id so the entry stays identifiable.
    expect(history[0].id).toBe(1);
  });

  it('does not fold across kinds or across an intervening message', () => {
    const action = pushError([], entry({ id: 1, kind: 'action' }));
    expect(pushError(action, entry({ id: 2, kind: 'poll' })).length).toBe(2);

    const other = pushError(action, entry({ id: 2, message: 'other' }));
    expect(pushError(other, entry({ id: 3, message: 'boom' })).length).toBe(3);
  });

  it('caps the history and drops the oldest entry', () => {
    let history: ErrorEntry[] = [];
    for (let i = 0; i < ERROR_HISTORY_MAX + 5; i++) {
      history = pushError(history, entry({ id: i, message: `boom ${i}` }));
    }
    expect(history.length).toBe(ERROR_HISTORY_MAX);
    expect(history[0].message).toBe(`boom ${ERROR_HISTORY_MAX + 4}`);
    expect(history[history.length - 1].message).toBe('boom 5');
  });
});

describe('UiStateService error channels', () => {
  it('holds an action error through a successful poll', () => {
    // The regression this split exists for: the poll used to clear one shared
    // error signal every 2s, so an action failure vanished before it was read.
    const ui = new UiStateService(healthy);
    ui.fail({ error: { error: 'conveyor.conf missing' } }, 'Start failed');

    ui.startPolling(); // startWith(0) polls immediately, and succeeds.
    expect(ui.live()).toBe(true);
    expect(ui.actionError()?.message).toBe('conveyor.conf missing');
    ui.stopPolling();
  });

  it('holds an action error through a successful refresh', () => {
    const ui = new UiStateService(healthy);
    ui.fail({ error: { error: 'conveyor.conf missing' } }, 'Start failed');

    ui.refresh();
    expect(ui.actionError()?.message).toBe('conveyor.conf missing');
  });

  it('clears the action error only on dismiss or on the next action', () => {
    const ui = new UiStateService(healthy);

    ui.fail({ message: 'Approve failed' });
    ui.dismissError();
    expect(ui.actionError()).toBeNull();

    ui.fail({ message: 'Approve failed' });
    ui.startAction();
    expect(ui.actionError()).toBeNull();
    expect(ui.busy()).toBe(true);
  });

  it('counts a repeated action error instead of looking like a fresh one', () => {
    const ui = new UiStateService(healthy);
    ui.fail({ message: 'Approve failed' });
    ui.fail({ message: 'Approve failed' });
    expect(ui.actionError()?.count).toBe(2);
    expect(ui.history().length).toBe(1);
  });

  it('owns the poll error separately and clears it on recovery', () => {
    let up = false;
    const ui = new UiStateService(
      apiReturning(() => (up ? of({} as ConveyorState) : throwError(() => ({ message: 'down' })))),
    );

    ui.startPolling();
    expect(ui.live()).toBe(false);
    expect(ui.pollError()).toBe('down');
    ui.stopPolling();

    up = true;
    ui.refresh();
    expect(ui.live()).toBe(true);
    expect(ui.pollError()).toBe('');
  });

  it('records inline failures in the history without hijacking the strip', () => {
    const ui = new UiStateService(healthy);
    ui.note({ message: 'Skills save failed' });
    expect(ui.actionError()).toBeNull();
    expect(ui.history()[0].message).toBe('Skills save failed');
  });

  it('keeps a cleared history from resurrecting the dismissed error', () => {
    const ui = new UiStateService(healthy);
    ui.fail({ message: 'Approve failed' });
    ui.clearHistory();
    expect(ui.history()).toEqual([]);
    expect(ui.actionError()?.message).toBe('Approve failed');
  });
});
