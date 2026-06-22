import { expect, type Locator, type Page } from '@playwright/test';

export class HomePage {
  readonly page: Page;
  readonly heading: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
  }

  async goto(): Promise<void> {
    await this.page.goto('/');
  }

  async assertLoaded(): Promise<void> {
    await expect(this.heading).toBeVisible();
  }
}

