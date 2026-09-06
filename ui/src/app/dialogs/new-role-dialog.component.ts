import { Component, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';

export interface NewRoleDialogData {
  existing: string[];
}

export interface NewRoleResult {
  name: string;
  from?: string;
}

@Component({
  selector: 'app-new-role-dialog',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
  ],
  template: `
    <h2 mat-dialog-title>New role</h2>
    <mat-dialog-content>
      <form [formGroup]="form">
        <mat-form-field appearance="outline" class="full">
          <mat-label>Name</mat-label>
          <input matInput formControlName="name" placeholder="tester" />
          @if (form.controls.name.hasError('pattern')) {
            <mat-error>Name must match ^[a-z][a-z0-9-]*$</mat-error>
          }
        </mat-form-field>
        <mat-form-field appearance="outline" class="full">
          <mat-label>Copy from (optional)</mat-label>
          <mat-select formControlName="from">
            <mat-option [value]="''">Blank stub</mat-option>
            @for (r of data.existing; track r) {
              <mat-option [value]="r">{{ r }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-flat-button [disabled]="form.invalid" (click)="submit()">Create</button>
    </mat-dialog-actions>
  `,
  styles: `.full { width: 100%; min-width: 360px; }`,
})
export class NewRoleDialogComponent {
  private ref = inject(MatDialogRef<NewRoleDialogComponent, NewRoleResult>);
  data = inject<NewRoleDialogData>(MAT_DIALOG_DATA);
  private fb = inject(FormBuilder);

  form = this.fb.group({
    name: ['', [Validators.required, Validators.pattern(/^[a-z][a-z0-9-]*$/)]],
    from: [''],
  });

  submit(): void {
    if (!this.form.valid) return;
    const v = this.form.getRawValue();
    this.ref.close({ name: v.name!, ...(v.from ? { from: v.from } : {}) });
  }
}
