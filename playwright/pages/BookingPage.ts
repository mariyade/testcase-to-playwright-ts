import { expect, type Locator, type Page } from '@playwright/test';

export type GuestDetails = {
  firstname: string;
  lastname: string;
  email: string;
  phone: string;
};

export type BookingRequest = {
  roomId: number;
  checkin: string;
  checkout: string;
};

export type CreatedBooking = {
  bookingid: number;
  firstname: string;
  lastname: string;
  bookingdates: {
    checkin: string;
    checkout: string;
  };
};

export class BookingPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly roomsSection: Locator;
  readonly reserveButton: Locator;
  readonly firstNameInput: Locator;
  readonly lastNameInput: Locator;
  readonly emailInput: Locator;
  readonly phoneInput: Locator;
  readonly bookingConfirmed: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /shady meadows b&b|welcome to shady meadows/i }).first();
    this.roomsSection = page.locator('#rooms, text=Our Rooms').first();
    this.reserveButton = page.getByRole('button', { name: 'Reserve Now' });
    this.firstNameInput = page.getByLabel('Firstname');
    this.lastNameInput = page.getByLabel('Lastname');
    this.emailInput = page.getByLabel('Email');
    this.phoneInput = page.getByLabel('Phone');
    this.bookingConfirmed = page.getByText('Booking Confirmed');
  }

  async goto(): Promise<void> {
    await this.page.goto('/');
  }

  async gotoReservation({ roomId, checkin, checkout }: BookingRequest): Promise<void> {
    await this.page.goto(`/reservation/${roomId}?checkin=${checkin}&checkout=${checkout}`);
  }

  async assertLoaded(): Promise<void> {
    await expect(this.heading).toBeVisible();
  }

  async assertRoomsVisible(): Promise<void> {
    await expect(this.roomsSection).toBeVisible();
    await expect(this.page.getByRole('link', { name: /book now/i }).first()).toBeVisible();
  }

  async openReservationForm(): Promise<void> {
    await this.reserveButton.click();
    await expect(this.firstNameInput).toBeVisible();
  }

  async fillGuestDetails(guest: GuestDetails): Promise<void> {
    await this.firstNameInput.fill(guest.firstname);
    await this.lastNameInput.fill(guest.lastname);
    await this.emailInput.fill(guest.email);
    await this.phoneInput.fill(guest.phone);
  }

  async submitReservation(): Promise<CreatedBooking> {
    const responsePromise = this.page.waitForResponse(
      response => response.url().includes('/api/booking') && response.request().method() === 'POST',
    );
    await this.reserveButton.click();
    const response = await responsePromise;
    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.bookingid).toEqual(expect.any(Number));
    return body;
  }

  async assertBookingConfirmed(checkin: string, checkout: string): Promise<void> {
    await expect(this.bookingConfirmed).toBeVisible();
    await expect(this.page.getByText(`${checkin} - ${checkout}`)).toBeVisible();
  }
}
