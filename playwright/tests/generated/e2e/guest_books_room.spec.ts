import { test, expect } from '../../../fixtures/test';
import { expectBookingMatches, futureBookingDates, guestDetails } from '../../../support/bookingTestData';

test.describe('Guest booking flow', () => {
  test('create a booking with valid details', { tag: '@smoke' }, async ({ bookingPage }) => {
    const booking = futureBookingDates();
    const guest = guestDetails();

    await bookingPage.gotoReservation(booking);
    await bookingPage.assertLoaded();
    await bookingPage.openReservationForm();
    await bookingPage.fillGuestDetails(guest);

    const createdBooking = await bookingPage.submitReservation();
    await bookingPage.assertBookingConfirmed(booking.checkin, booking.checkout);
    expectBookingMatches(createdBooking, guest, booking);
  });

  test('attempt booking with overlapping reservation', { tag: '@e2e' }, async () => {
    test.skip(true, 'Missing page-object/API helper to create a known overlapping reservation precondition.');
  });

  test('validate required fields during booking', { tag: '@e2e' }, async () => {
    test.skip(true, 'Missing page-object helper to assert booking validation errors.');
  });
});
