import { expect, type Locator, type Page } from '@playwright/test';

export interface AdminCredentials {
  username: string;
  password: string;
}

export class AdminPage {
  readonly page: Page;
  readonly usernameInput: Locator;
  readonly passwordInput: Locator;
  readonly loginButton: Locator;
  readonly dashboardHeading: Locator;
  readonly roomsTable: Locator;

  constructor(page: Page) {
    this.page = page;
    this.usernameInput = page.getByLabel(/username/i).or(page.getByPlaceholder(/username/i)).first();
    this.passwordInput = page.getByLabel(/password/i).or(page.getByPlaceholder(/password/i)).first();
    this.loginButton = page.getByRole('button', { name: /login/i });
    this.dashboardHeading = page.getByRole('heading', { name: /restful booker platform demo/i }).first();
    this.roomsTable = page.locator('table').filter({ hasText: /Room #|Type|Accessible|Price/i }).first();
  }

  async goto(): Promise<void> {
    await this.page.goto('/admin');
  }

  async login(credentials: AdminCredentials): Promise<void> {
    await this.usernameInput.fill(credentials.username);
    await this.passwordInput.fill(credentials.password);
    await this.loginButton.click();
  }

  async expectDashboardVisible(): Promise<void> {
    await expect(this.dashboardHeading).toBeVisible();
  }

  async expectNavigationVisible(items: string[]): Promise<void> {
    for (const item of items) {
      await expect(this.page.getByRole('link', { name: item }).or(this.page.getByText(item, { exact: true })).first()).toBeVisible();
    }
  }

  async expectMessagesCount(count: number): Promise<void> {
    await expect(this.page.getByText(new RegExp(`Messages\\s*${String(count)}`))).toBeVisible();
  }

  async expectRoomsTableColumns(columns: string[]): Promise<void> {
    await expect(this.roomsTable).toBeVisible();
    for (const column of columns) {
      await expect(this.roomsTable.getByText(column, { exact: true })).toBeVisible();
    }
  }

  async expectInvalidLoginError(): Promise<void> {
  await expect(this.page.getByText(/invalid|incorrect|error|failed/i).first()).toBeVisible();
}
}
