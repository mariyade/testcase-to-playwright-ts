import { expect } from '@playwright/test';
import type { BookingRequest, CreatedBooking, GuestDetails } from '../pages/BookingPage';

export function isoDateFromToday(offsetDays: number): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + offsetDays);
  return date.toISOString().slice(0, 10);
}

export function futureBookingDates(): BookingRequest {
  const startOffset = 365 + (Math.floor(Date.now() / 1000) % 3000);
  return {
    roomId: 1,
    checkin: isoDateFromToday(startOffset),
    checkout: isoDateFromToday(startOffset + 1),
  };
}

export function guestDetails(): GuestDetails {
  return {
    firstname: 'Dani',
    lastname: 'Tester',
    email: 'dani.tester@example.com',
    phone: '07123456789',
  };
}

export function expectBookingMatches(createdBooking: CreatedBooking, guest: GuestDetails, booking: BookingRequest): void {
  expect(createdBooking.firstname).toBe(guest.firstname);
  expect(createdBooking.lastname).toBe(guest.lastname);
  expect(createdBooking.bookingdates.checkin).toBe(booking.checkin);
  expect(createdBooking.bookingdates.checkout).toBe(booking.checkout);
}
