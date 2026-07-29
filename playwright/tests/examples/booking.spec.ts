import { expect, test } from '../../fixtures/test';
import { expectBookingMatches, futureBookingDates, guestDetails } from '../../support/bookingTestData';

test.describe('room booking', () => {
  test('creates a booking through the UI and verifies the booking API response', async ({ bookingPage }) => {
    const booking = futureBookingDates();
    const guest = guestDetails();

    await bookingPage.gotoReservation(booking);
    await bookingPage.assertLoaded();
    await bookingPage.openReservationForm();
    await bookingPage.fillGuestDetails(guest);

    const createdBooking = await bookingPage.submitReservation();

    await bookingPage.assertBookingConfirmed(booking.checkin, booking.checkout);
    expect(createdBooking.bookingid).toEqual(expect.any(Number));
    expectBookingMatches(createdBooking, guest, booking);
  });
});
