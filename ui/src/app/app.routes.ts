import { Routes } from '@angular/router';
import { AppShellComponent } from './app-shell/app-shell.component';
import { CockpitComponent } from './cockpit/cockpit.component';
import { InboxDetailComponent } from './inbox/inbox-detail.component';
import { WorkflowPageComponent } from './workflow/workflow-page.component';
import { WorkflowDetailComponent } from './workflow/workflow-detail.component';
import { RolesPageComponent } from './roles/roles-page.component';

export const routes: Routes = [
  {
    path: '',
    component: AppShellComponent,
    children: [
      { path: '', redirectTo: 'inbox', pathMatch: 'full' },
      { path: 'inbox', component: CockpitComponent },
      { path: 'inbox/:id', component: InboxDetailComponent },
      { path: 'board', component: CockpitComponent },
      { path: 'workflow', component: WorkflowPageComponent },
      { path: 'workflow/:slug', component: WorkflowDetailComponent },
      { path: 'roles', component: RolesPageComponent },
    ],
  },
];
