import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  ConveyorState,
  HandoffSummary,
  InboxDetail,
  IntakeJira,
  IntakeState,
  LogEvent,
  ModelsResponse,
  WorkflowDetail,
  WorkflowEdit,
  WorkflowListResponse,
  WorkflowState,
} from '../models';

@Injectable({ providedIn: 'root' })
export class ConveyorApiService {
  private base = '/api';

  constructor(private http: HttpClient) {}

  health(): Observable<{ ok: boolean; root: string }> {
    return this.http.get<{ ok: boolean; root: string }>(`${this.base}/health`);
  }

  state(): Observable<ConveyorState> {
    return this.http.get<ConveyorState>(`${this.base}/state`);
  }

  task(name: string): Observable<{ name: string; text: string }> {
    return this.http.get<{ name: string; text: string }>(`${this.base}/tasks/${encodeURIComponent(name)}`);
  }

  logs(role: string, task?: string): Observable<{ filename: string | null; events: LogEvent[] }> {
    const q = task ? `?task=${encodeURIComponent(task)}` : '';
    return this.http.get<{ filename: string | null; events: LogEvent[] }>(`${this.base}/logs/${role}${q}`);
  }

  handoffs(role: string, dir: string): Observable<HandoffSummary[]> {
    return this.http.get<HandoffSummary[]>(`${this.base}/handoffs/${role}/${dir}`);
  }

  inboxItem(id: string): Observable<InboxDetail> {
    return this.http.get<InboxDetail>(`${this.base}/inbox/${encodeURIComponent(id)}`);
  }

  createTask(name: string, text: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/tasks`, { name, text });
  }

  deleteTask(name: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/tasks/delete`, { name });
  }

  resume(task: string, to?: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/resume`, { task, to });
  }

  start(): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/start`, {});
  }

  stop(now = false): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/stop`, { now });
  }

  importTickets(source: string, title: string, body: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/import`, { source, title, body });
  }

  refreshImport(id: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/import/refresh`, { id });
  }

  replaceInboxSource(id: string, text: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/inbox/source`, { id, text });
  }

  intake(id: string, improve = false, comments?: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/intake`, { id, improve, comments });
  }

  inboxApprove(id: string, name?: string, text?: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/inbox/approve`, { id, name, text });
  }

  inboxSkip(id: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/inbox/skip`, { id });
  }

  startTask(name: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/start-task`, { name });
  }

  approve(id: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/approve`, { id });
  }

  reject(id: string, comments: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/reject`, { id, comments });
  }

  models(): Observable<ModelsResponse> {
    return this.http.get<ModelsResponse>(`${this.base}/models`);
  }

  workflow(): Observable<WorkflowState> {
    return this.http.get<WorkflowState>(`${this.base}/workflow`);
  }

  workflows(): Observable<WorkflowListResponse> {
    return this.http.get<WorkflowListResponse>(`${this.base}/workflows`);
  }

  workflowDetail(slug: string): Observable<WorkflowDetail> {
    return this.http.get<WorkflowDetail>(`${this.base}/workflows/${encodeURIComponent(slug)}`);
  }

  createWorkflow(body: WorkflowEdit): Observable<{ ok: boolean; slug: string; message: string }> {
    return this.http.post<{ ok: boolean; slug: string; message: string }>(
      `${this.base}/workflows`, body);
  }

  saveWorkflow(slug: string, body: WorkflowEdit): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(
      `${this.base}/workflows/save`, { slug, ...body });
  }

  deleteWorkflow(slug: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(
      `${this.base}/workflows/delete`, { slug });
  }

  activateWorkflow(slug: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/active`, { slug });
  }

  saveRole(name: string, text: string): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${this.base}/roles`, { name, text });
  }

  createRole(name: string, from?: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(
      `${this.base}/roles/create`, { name, ...(from ? { from } : {}) });
  }

  deleteRole(name: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(
      `${this.base}/roles/delete`, { name });
  }

  saveRoleSkills(name: string, skills: string[]): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(
      `${this.base}/roles/skills`, { name, skills });
  }

  saveRoleRuntime(
    name: string,
    model: string,
    max_retries: number,
    max_minutes: number,
    max_attempts: number,
  ): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${this.base}/roles/runtime`, {
      name,
      model,
      max_retries,
      max_minutes,
      max_attempts,
    });
  }

  saveProject(text: string): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${this.base}/project`, { text });
  }

  runGate(name: string, role?: string): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(`${this.base}/gates/run`, {
      name,
      ...(role ? { role } : {}),
    });
  }

  intakeSettings(): Observable<IntakeState> {
    return this.http.get<IntakeState>(`${this.base}/intake`);
  }

  saveIntakePrompt(text: string): Observable<{ ok: boolean; path: string }> {
    return this.http.post<{ ok: boolean; path: string }>(`${this.base}/intake/prompt`, { text });
  }

  saveIntakeRubric(text: string): Observable<{ ok: boolean; path: string }> {
    return this.http.post<{ ok: boolean; path: string }>(`${this.base}/intake/rubric`, { text });
  }

  saveIntakeConfig(
    model: string,
    max_minutes: number,
    max_attempts: number,
  ): Observable<{ ok: boolean; path: string }> {
    return this.http.post<{ ok: boolean; path: string }>(`${this.base}/intake/config`, {
      model,
      max_minutes,
      max_attempts,
    });
  }

  saveIntakeJira(site: string, email: string, token?: string): Observable<{ ok: boolean } & IntakeJira> {
    return this.http.post<{ ok: boolean } & IntakeJira>(`${this.base}/intake/jira`, {
      site,
      email,
      ...(token ? { token } : {}),
    });
  }

  clearIntakeJira(): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${this.base}/intake/jira/clear`, {});
  }

  testIntakeJira(
    site: string,
    email: string,
    token?: string,
  ): Observable<{ ok: boolean; status: number; message: string } & IntakeJira> {
    return this.http.post<{ ok: boolean; status: number; message: string } & IntakeJira>(
      `${this.base}/intake/jira/test`,
      {
        site,
        email,
        ...(token ? { token } : {}),
      },
    );
  }

  commitStat(sha: string): Observable<{ sha: string; stat: string }> {
    return this.http.get<{ sha: string; stat: string }>(`${this.base}/commits/${sha}`);
  }
}
