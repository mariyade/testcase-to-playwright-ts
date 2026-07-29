import { expect, type APIRequestContext, type APIResponse } from '@playwright/test';

export interface BookingDetails {
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
}

export class BookingApi {
  readonly request: APIRequestContext;
  readonly apiBaseUrl: string;

  constructor(request: APIRequestContext) {
    this.request = request;
    this.apiBaseUrl = process.env.BOOKING_API_URL ?? 'https://automationintesting.online/api';
  }

  async createBooking(details: BookingDetails): Promise<{ bookingid: number; response: APIResponse }> {
    const response = await this.request.post(`${this.apiBaseUrl}/booking`, { data: details });
    await expect(response).toBeOK();
    const body: unknown = await response.json();
    assertCreatedBookingResponse(body);
    expect(body.bookingid).toEqual(expect.any(Number));
    return { bookingid: body.bookingid, response };
  }

  async getBooking(bookingId: number): Promise<BookingDetails> {
    const response = await this.request.get(`${this.apiBaseUrl}/booking/${String(bookingId)}`);
    await expect(response).toBeOK();
    const body: unknown = await response.json();
    assertBookingDetails(body);
    return body;
  }
}

interface CreatedBookingResponse {
  bookingid: number;
}

function assertCreatedBookingResponse(value: unknown): asserts value is CreatedBookingResponse {
  if (!isRecord(value) || typeof value.bookingid !== 'number') {
    throw new Error('Booking API response did not include a numeric bookingid');
  }
}

function assertBookingDetails(value: unknown): asserts value is BookingDetails {
  if (
    !isRecord(value) ||
    typeof value.roomid !== 'number' ||
    typeof value.firstname !== 'string' ||
    typeof value.lastname !== 'string' ||
    typeof value.depositpaid !== 'boolean' ||
    !isRecord(value.bookingdates) ||
    typeof value.bookingdates.checkin !== 'string' ||
    typeof value.bookingdates.checkout !== 'string'
  ) {
    throw new Error('Booking API response did not match the expected booking shape');
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
