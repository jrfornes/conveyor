import { InboxAttachment, InboxItem } from '../models';
import {
  attachmentBadge,
  attachmentLabel,
  canApproveInbox,
  canEditInboxSource,
  canGradeInbox,
  canInboxAttachments,
  canRefreshInbox,
  canSkipInbox,
  canStartInbox,
  countsFromAttachments,
  dash,
  displayInboxId,
  fmtSize,
  inboxBusy,
  inboxNextStep,
  isHttpUrl,
} from './inbox-actions';

function row(partial: Partial<InboxItem>): InboxItem {
  return {
    id: 'cave-lights',
    source: 'manual',
    title: 'Cave lighting',
    url: '-',
    external_id: '-',
    status: 'imported',
    grade: '-',
    created_at: '2026-09-07T00:00:00Z',
    task_name: '-',
    has_grade: false,
    has_proposed: false,
    attachment_count: 0,
    video_count: 0,
    selected_count: 0,
    ...partial,
  };
}

describe('inbox-actions', () => {
  it('prefers the external id when it is a real key', () => {
    expect(displayInboxId(row({}))).toBe('cave-lights');
    expect(displayInboxId(row({ external_id: 'PROJ-9' }))).toBe('PROJ-9');
    expect(displayInboxId(row({ external_id: '-' }))).toBe('cave-lights');
  });

  it('dashes empty protocol sentinels', () => {
    expect(dash('-')).toBe('—');
    expect(dash('')).toBe('—');
    expect(dash('Ready')).toBe('Ready');
  });

  it('detects http(s) ticket urls', () => {
    expect(isHttpUrl('https://example.atlassian.net/browse/PROJ-9')).toBe(true);
    expect(isHttpUrl('-')).toBe(false);
  });

  it('gates actions on status the way the table did', () => {
    const imported = row({ status: 'imported', source: 'jira', attachment_count: 2 });
    expect(canRefreshInbox(imported)).toBe(true);
    expect(canEditInboxSource(imported)).toBe(true);
    expect(canInboxAttachments(imported)).toBe(true);
    expect(canGradeInbox(imported)).toBe(true);
    expect(canApproveInbox(imported)).toBe(false);
    expect(canStartInbox(imported)).toBe(false);
    expect(canSkipInbox(imported)).toBe(true);

    const awaiting = row({ status: 'awaiting-approval' });
    expect(canGradeInbox(awaiting)).toBe(true);
    expect(canApproveInbox(awaiting)).toBe(true);
    expect(canEditInboxSource(awaiting)).toBe(false);

    const ready = row({ status: 'ready', task_name: 'cave-lights' });
    expect(canStartInbox(ready)).toBe(true);
    expect(canGradeInbox(ready)).toBe(false);
    expect(canSkipInbox(ready)).toBe(true);

    const started = row({ status: 'started' });
    expect(canSkipInbox(started)).toBe(false);
    expect(canGradeInbox(row({ status: 'skipped' }))).toBe(true);
    expect(inboxBusy(row({ status: 'grading' }))).toBe(true);
  });

  it('explains the next operator step from status', () => {
    expect(inboxNextStep(row({ status: 'imported' }))).toContain('Grade');
    expect(inboxNextStep(row({ status: 'ready', task_name: 'cave-lights' })))
      .toContain('cave-lights');
    expect(inboxNextStep(row({ status: 'started', task_name: 'cave-lights' })))
      .toContain('board');
  });

  it('labels attachments the way the dialog did', () => {
    expect(fmtSize(12)).toBe('12 B');
    expect(fmtSize(2048)).toBe('2 KB');
    const video: InboxAttachment = {
      id: '1', filename: 'a.mp4', mime: 'video/mp4', size: 99,
      kind: 'video', selected: false, downloadable: false, skip_reason: '',
    };
    expect(attachmentLabel(video)).toContain('watch in Jira');
    expect(attachmentBadge(row({ attachment_count: 2, selected_count: 1, video_count: 1 })))
      .toBe('1/2 · 1 video');
    expect(countsFromAttachments([video]).video_count).toBe(1);
  });
});
