import { test as base } from '@playwright/test';
import { BookingApi } from '../pages/BookingApi';
import { BookingPage } from '../pages/BookingPage';
import { HomePage } from '../pages/HomePage';

interface Fixtures {
  bookingApi: BookingApi;
  bookingPage: BookingPage;
  homePage: HomePage;
}

export const test = base.extend<Fixtures>({
  bookingApi: async ({ request }, use) => {
    await use(new BookingApi(request));
  },
  bookingPage: async ({ page }, use) => {
    await use(new BookingPage(page));
  },
  homePage: async ({ page }, use) => {
    await use(new HomePage(page));
  },
});

export { expect } from '@playwright/test';
