import { expect, type Locator, type Page } from '@playwright/test';

export interface ContactMessage {
  name: string;
  email: string;
  phone: string;
  subject: string;
  message: string;
}

export class HomePage {
  readonly page: Page;
  readonly heading: Locator;
  readonly roomsSection: Locator;
  readonly contactNameInput: Locator;
  readonly contactEmailInput: Locator;
  readonly contactPhoneInput: Locator;
  readonly contactSubjectInput: Locator;
  readonly contactMessageInput: Locator;
  readonly contactSubmitButton: Locator;
  readonly contactSuccessMessage: Locator;
  readonly contactValidationMessages: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.roomsSection = page.locator('#rooms');
    this.contactNameInput = page.getByLabel(/name/i).or(page.getByPlaceholder(/name/i)).first();
    this.contactEmailInput = page.getByLabel(/email/i).or(page.getByPlaceholder(/email/i)).first();
    this.contactPhoneInput = page.getByLabel(/phone/i).or(page.getByPlaceholder(/phone/i)).first();
    this.contactSubjectInput = page.getByLabel(/subject/i).or(page.getByPlaceholder(/subject/i)).first();
    this.contactMessageInput = page
      .getByLabel(/message|description/i)
      .or(page.getByPlaceholder(/message|description/i))
      .or(page.locator('textarea'))
      .first();
    this.contactSubmitButton = page.getByRole('button', { name: /submit/i }).last();
    this.contactSuccessMessage = page.getByText(/thanks|success|sent|submitted/i).first();
    this.contactValidationMessages = page.locator('[role="alert"], .alert-danger, .invalid-feedback');
  }

  async goto(): Promise<void> {
    await this.page.goto('/');
  }

  async assertLoaded(): Promise<void> {
    await expect(this.heading).toBeVisible();
  }

  async assertContactFormVisible(): Promise<void> {
    await expect(this.contactNameInput).toBeVisible();
    await expect(this.contactEmailInput).toBeVisible();
    await expect(this.contactPhoneInput).toBeVisible();
    await expect(this.contactSubjectInput).toBeVisible();
    await expect(this.contactMessageInput).toBeVisible();
    await expect(this.contactSubmitButton).toBeVisible();
  }

  async fillContactForm(message: ContactMessage): Promise<void> {
    await this.contactNameInput.fill(message.name);
    await this.contactEmailInput.fill(message.email);
    await this.contactPhoneInput.fill(message.phone);
    await this.contactSubjectInput.fill(message.subject);
    await this.contactMessageInput.fill(message.message);
  }

  async submitContactForm(): Promise<void> {
    await this.contactSubmitButton.click();
  }

  async sendContactMessage(message: ContactMessage): Promise<void> {
    const responsePromise = this.page
      .waitForResponse(response => response.url().includes('/api/message') && response.request().method() === 'POST')
      .catch(() => null);

    await this.fillContactForm(message);
    await this.submitContactForm();

    const response = await responsePromise;
    if (response) {
      expect(response.status()).toBeGreaterThanOrEqual(200);
      expect(response.status()).toBeLessThan(300);
    }
  }

  async assertContactMessageSubmitted(): Promise<void> {
    await expect(this.contactSuccessMessage).toBeVisible();
  }

  async assertContactValidationVisible(): Promise<void> {
    await expect(this.contactValidationMessages.first()).toBeVisible();
  }
}
