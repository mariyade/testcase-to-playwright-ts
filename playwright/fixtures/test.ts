import { test as base } from '@playwright/test';
import { AdminPage } from '../pages/AdminPage';
import { BookingApi } from '../pages/BookingApi';
import { BookingPage } from '../pages/BookingPage';
import { HomePage } from '../pages/HomePage';

interface Fixtures {
  adminPage: AdminPage;
  bookingApi: BookingApi;
  bookingPage: BookingPage;
  homePage: HomePage;
}

export const test = base.extend<Fixtures>({
  adminPage: async ({ page }, use) => {
    await use(new AdminPage(page));
  },
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
