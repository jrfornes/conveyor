import { InboxAttachment, InboxItem } from '../models';

/** Prefer the vendor key (PROJ-9) when the operator would recognize it. */
export function displayInboxId(row: Pick<InboxItem, 'id' | 'external_id'>): string {
  const ext = (row.external_id || '').trim();
  return ext && ext !== '-' ? ext : row.id;
}

export function dash(value?: string | null): string {
  const v = (value || '').trim();
  return !v || v === '-' ? '—' : v;
}

export function isHttpUrl(value?: string | null): boolean {
  return /^https?:\/\//i.test((value || '').trim());
}

export function canRefreshInbox(row: Pick<InboxItem, 'source' | 'status'>): boolean {
  return row.source === 'jira' && row.status === 'imported';
}

export function canEditInboxSource(row: Pick<InboxItem, 'status'>): boolean {
  return row.status === 'imported';
}

export function canInboxAttachments(
  row: Pick<InboxItem, 'status'> & { attachment_count?: number },
): boolean {
  return row.status === 'imported' && (row.attachment_count || 0) > 0;
}

export function canGradeInbox(row: Pick<InboxItem, 'status'>): boolean {
  return ['imported', 'graded', 'awaiting-approval', 'skipped'].includes(row.status);
}

export function canApproveInbox(row: Pick<InboxItem, 'status'>): boolean {
  return ['graded', 'awaiting-approval'].includes(row.status);
}

export function canStartInbox(row: Pick<InboxItem, 'status'>): boolean {
  return row.status === 'ready';
}

export function canSkipInbox(row: Pick<InboxItem, 'status'>): boolean {
  return row.status !== 'started' && row.status !== 'skipped';
}

export function inboxBusy(row: Pick<InboxItem, 'status'>): boolean {
  return row.status === 'grading' || row.status === 'improving';
}

/** One-line operator hint; protocol §2.4 status is the only input. */
export function inboxNextStep(row: Pick<InboxItem, 'status' | 'task_name'>): string {
  const task = dash(row.task_name);
  switch (row.status) {
    case 'imported':
      return 'Grade this ticket, or edit the source first.';
    case 'grading':
      return 'Ticket-reviewer is grading this item.';
    case 'graded':
      return 'Review the grade. Approve writes tasks/<name>.md; it does not enqueue yet.';
    case 'improving':
      return 'Ticket-reviewer is rewriting the proposal.';
    case 'awaiting-approval':
      return 'A proposed task is ready. Approve commits it; Start puts it on the board.';
    case 'ready':
      return `Approved as ${task}. Start queues it on the board.`;
    case 'started':
      return `On the board as ${task}.`;
    case 'skipped':
      return 'Skipped. You can still Grade it again.';
    default:
      return '';
  }
}

export function attachmentBadge(
  row: Pick<InboxItem, 'attachment_count' | 'selected_count' | 'video_count'>,
): string {
  const n = row.attachment_count || 0;
  const sel = row.selected_count || 0;
  const vid = row.video_count || 0;
  let s = `${sel}/${n}`;
  if (vid) s += ` · ${vid} video`;
  return s;
}

export function attachmentBadgeTitle(
  row: Pick<InboxItem, 'attachment_count' | 'selected_count' | 'video_count'>,
): string {
  return `${row.selected_count || 0} selected of ${row.attachment_count || 0}` +
    (row.video_count ? `; ${row.video_count} video not downloaded` : '');
}

export function fmtSize(n: number): string {
  if (!n) return '0 B';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function attachmentLabel(row: InboxAttachment): string {
  const size = fmtSize(row.size);
  if (row.kind === 'video' || row.kind === 'audio') {
    return `${row.kind} · ${size} · watch in Jira`;
  }
  if (row.skip_reason === 'oversize') return `${row.kind} · ${size} · oversize`;
  if (row.skip_reason === 'archive') return `archive · ${size}`;
  return `${row.kind} · ${size}`;
}

export function countsFromAttachments(rows: InboxAttachment[]): {
  attachment_count: number;
  selected_count: number;
  video_count: number;
} {
  return {
    attachment_count: rows.length,
    selected_count: rows.filter((r) => r.selected).length,
    video_count: rows.filter((r) => r.kind === 'video').length,
  };
}
