export interface ConveyorTask {
  name: string;
  lane: string;
  task_id: string;
  audit_count: number;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface WorkEntry {
  role: string;
  state: 'busy' | 'idle' | 'stopped';
  running: boolean;
  stopped: boolean;
  new_count: number;
  last_completed: string | null;
  task?: string;
  task_id?: string;
  handoff_id?: string;
  age_seconds?: number;
  attempt?: number;
  max_attempts?: number;
}

export interface NeedsHumanEntry {
  task: string;
  reason: string;
  detail: string;
}

export interface InboxAttachment {
  id: string;
  filename: string;
  mime: string;
  size: number;
  kind: string;
  selected: boolean;
  downloadable: boolean;
  skip_reason: string;
}

export interface InboxItem {
  id: string;
  source: string;
  title: string;
  url: string;
  external_id: string;
  status: string;
  grade: string;
  created_at: string;
  task_name: string;
  has_grade: boolean;
  has_proposed: boolean;
  attachment_count: number;
  video_count: number;
  selected_count: number;
}

export interface InboxDetail extends InboxItem {
  source_md: string;
  grade_md: string;
  proposed_md: string;
  comments: string;
  attachments: InboxAttachment[];
}

export interface ApprovalItem {
  id: string;
  task: string;
  from: string;
  to: string;
  commit: string;
  file: string;
}

/** ticket-reviewer's loop lock is shared across every inbox item; only one
 * grade/improve can run at a time. */
export interface IntakeStatus {
  busy: boolean;
  task: string | null;
}

export interface ConveyorState {
  title: string;
  root: string;
  initialized: boolean;
  lanes: string[];
  /** One avatar per lane, keyed by lane name (needs-human and done included). */
  avatars: Record<string, RoleAvatar>;
  roles: string[];
  workflow: WorkflowRef;
  tasks: ConveyorTask[];
  work: WorkEntry[];
  needs_human: NeedsHumanEntry[];
  running: boolean;
  inbox: InboxItem[];
  approvals: ApprovalItem[];
  intake: IntakeStatus;
}

export interface LogEvent {
  type: string;
  detail?: string;
  text?: string;
}

export interface HandoffSummary {
  file: string;
  id?: string;
  from?: string;
  to?: string;
  task?: string;
  task_id?: string;
  verdict?: string;
  commit?: string;
}

export interface WorkflowRef {
  /** The active preset's slug, or "custom" when conveyor.conf matches none. */
  id: string;
  name: string;
  chain: string;
  status: 'active' | 'modified' | 'custom';
}

export interface RoleAvatar {
  icon: string;
  color: string;
  owns: string;
}

export interface Hop {
  from: string;
  to: string;
  verdict: string;
}

/** One saved preset in `.conveyor/workflows/<slug>.json`. */
export interface WorkflowPreset {
  slug: string;
  name: string;
  description: string;
  roles: string[];
  gate: string | null;
  file: string;
  /** conveyor.conf matches this preset's (roles, gate). */
  active: boolean;
  /** `.conveyor/active` names this preset but conveyor.conf no longer matches. */
  modified: boolean;
}

export interface WorkflowListResponse {
  active: string | null;
  status: 'active' | 'modified' | 'custom';
  /** The real chain from conveyor.conf, which may differ from any preset. */
  chain: string;
  gate: string | null;
  running: boolean;
  workflows: WorkflowPreset[];
}

export interface WorkflowRoleDetail {
  name: string;
  avatar: RoleAvatar;
  owns: string;
  /** null until the workflow is made active: models live in conveyor.conf. */
  model: string | null;
  max_retries: number | null;
  max_minutes: number | null;
  max_attempts: number | null;
  handoff: string;
}

export interface WorkflowDetail extends WorkflowPreset {
  running: boolean;
  deletable: boolean;
  roles_detail: WorkflowRoleDetail[];
  routes: Hop[];
  marks: { operator: RoleAvatar; done: RoleAvatar };
}

/** Payload for creating or editing a preset. */
export interface WorkflowEdit {
  name: string;
  description: string;
  roles: string[];
  gate: string | null;
}

export interface SkillInfo {
  name: string;
  description: string;
  source?: string;
}

export interface RoleRecord {
  name: string;
  avatar: RoleAvatar;
  in_workflow: boolean;
  text: string;
  hops: Hop[];
  skills?: string[];
  model?: string;
  max_retries?: number;
  max_minutes?: number;
  max_attempts?: number;
}

export interface IntakeJira {
  site: string;
  email: string;
  token_set: boolean;
}

export interface IntakeState {
  prompt: string;
  rubric: string;
  avatar: RoleAvatar;
  path: string;
  config: {
    model: string;
    max_minutes: number;
    max_attempts: number;
  };
  jira: IntakeJira;
}

export interface ProjectGate {
  name: string;
  argv: string;
}

export interface WorkflowState {
  workflow: WorkflowRef;
  /** Role whose outbound `ready` is held for the operator, or null. */
  gate: string | null;
  running: boolean;
  routes: Hop[];
  roles: RoleRecord[];
  library: RoleRecord[];
  available_skills: SkillInfo[];
  constitution: string[];
  project: string;
  project_gates: ProjectGate[];
  marks: {
    operator: RoleAvatar;
    done: RoleAvatar;
  };
}

export interface AgentModel {
  id: string;
  label: string;
}

export interface ModelsResponse {
  models: AgentModel[];
  error: string | null;
}

export const TASK_NAME_RE = /^[a-z0-9][a-z0-9.-]*$/;
