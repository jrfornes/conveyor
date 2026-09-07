import { Component, Inject, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

export interface EditSourceData {
  id: string;
  title: string;
  text: string;
}

@Component({
  selector: 'app-edit-source-dialog',
  standalone: true,
  imports: [
    FormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
  ],
  template: `
    <h2 mat-dialog-title>Edit source</h2>
    <mat-dialog-content>
      <p class="hint">{{ data.id }}{{ data.title ? ' — ' + data.title : '' }}</p>
      <mat-form-field appearance="outline" class="full">
        <mat-label>source.md</mat-label>
        <textarea matInput [(ngModel)]="text" rows="12"></textarea>
      </mat-form-field>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-flat-button [disabled]="!text.trim()" (click)="save()">Save</button>
    </mat-dialog-actions>
  `,
  styles: `
    .full { width: 100%; min-width: 420px; }
    .hint { margin: 0 0 8px; font-size: 12px; opacity: 0.7; }
  `,
})
export class EditSourceDialogComponent {
  private ref = inject(MatDialogRef<EditSourceDialogComponent, string>);
  text: string;

  constructor(@Inject(MAT_DIALOG_DATA) public data: EditSourceData) {
    this.text = data.text || '';
  }

  save(): void {
    if (this.text.trim()) {
      this.ref.close(this.text);
    }
  }
}
