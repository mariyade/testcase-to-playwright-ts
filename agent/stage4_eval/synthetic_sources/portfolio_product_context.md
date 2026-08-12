# Restful Booker Portfolio Context

The demo application lets guests browse hotel rooms, create bookings, and send
contact messages. Admin stories may use supplied credentials to review room
configuration, but generated tests should not invent admin credentials.

Guest booking tests should use future dates, generated guest details, and the
existing BookingPage or BookingApi abstractions. Contact-form tests should use
HomePage methods for filling and submitting messages, then assert success or
validation feedback.

Generated Playwright tests should prefer repository fixtures and page objects,
avoid raw selectors when a helper exists, and report genuinely missing helpers
instead of inventing unsupported methods.
