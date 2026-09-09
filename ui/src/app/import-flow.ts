import { MatDialog } from '@angular/material/dialog';
import { ConveyorApiService } from './services/conveyor-api.service';
import { UiStateService } from './services/ui-state.service';
import {
  ImportSummaryDialogComponent,
  ImportSummaryDialogData,
} from './dialogs/import-summary-dialog.component';
import { ImportDialogComponent } from './dialogs/import-dialog.component';
import { importedIds, parseImportMessage, importBusyMessage, gradingBusyMessage } from './util';

export interface ImportDialogResult {
  source: string;
  title: string;
  body: string;
  grade: boolean;
}

export interface ImportDialogCloseResult extends ImportDialogResult {
  message: string;
}

export function openImportSummary(
  dialog: MatDialog,
  message: string,
  title = 'Import complete',
): void {
  const summary = parseImportMessage(message);
  const data: ImportSummaryDialogData = { title, ...summary };
  dialog.open(ImportSummaryDialogComponent, {
    width: '560px',
    maxWidth: '95vw',
    data,
  });
}

export function openImport(
  dialog: MatDialog,
  api: ConveyorApiService,
  ui: UiStateService,
): void {
  const ref = dialog.open(ImportDialogComponent, { width: '560px' });
  ref.afterClosed().subscribe((v: ImportDialogCloseResult | undefined) => {
    if (!v?.message) return;
    openImportSummary(dialog, v.message);
    runPostImportGrading(api, ui, v.message, v.grade);
  });
}

export function runPostImportGrading(
  api: ConveyorApiService,
  ui: UiStateService,
  message: string,
  grade: boolean,
): void {
  const ids = importedIds(parseImportMessage(message));
  const gradeNext = (i: number) => {
    if (!grade || i >= ids.length) {
      ui.busy.set(false);
      ui.busyMessage.set('');
      ui.refresh();
      return;
    }
    ui.busyMessage.set(gradingBusyMessage(i, ids.length));
    api.inboxItem(ids[i]).subscribe({
      next: (item) => {
        if (!(item.source_md || '').trim()) {
          gradeNext(i + 1);
          return;
        }
        api.intake(ids[i], false).subscribe({
          next: () => gradeNext(i + 1),
          error: (e) => {
            ui.busy.set(false);
            ui.busyMessage.set('');
            ui.fail(e, 'Grade failed');
            ui.refresh();
          },
        });
      },
      error: (e) => {
        ui.busy.set(false);
        ui.busyMessage.set('');
        ui.fail(e, 'Import failed');
        ui.refresh();
      },
    });
  };
  gradeNext(0);
}
