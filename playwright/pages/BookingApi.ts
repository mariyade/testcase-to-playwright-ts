import { expect, type APIRequestContext, type APIResponse } from '@playwright/test';

export type BookingDetails = {
  roomid: number;
  firstname: string;
  lastname: string;
  depositpaid: boolean;
  bookingdates: {
    checkin: string;
    checkout: string;
  };
  email?: string;
  phone?: string;
};

export class BookingApi {
  readonly request: APIRequestContext;
  readonly apiBaseUrl: string;

  constructor(request: APIRequestContext) {
    this.request = request;
    this.apiBaseUrl = process.env.BOOKING_API_URL || 'https://automationintesting.online/api';
  }

  async createBooking(details: BookingDetails): Promise<{ bookingid: number; response: APIResponse }> {
    const response = await this.request.post(`${this.apiBaseUrl}/booking`, { data: details });
    await expect(response).toBeOK();
    const body = await response.json();
    expect(body.bookingid).toEqual(expect.any(Number));
    return { bookingid: body.bookingid, response };
  }

  async getBooking(bookingId: number): Promise<BookingDetails> {
    const response = await this.request.get(`${this.apiBaseUrl}/booking/${bookingId}`);
    await expect(response).toBeOK();
    return response.json();
  }
}
