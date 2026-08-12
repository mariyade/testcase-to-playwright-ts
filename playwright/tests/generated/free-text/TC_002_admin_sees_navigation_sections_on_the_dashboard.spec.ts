import { test } from "../../../fixtures/test";

test('Admin sees navigation sections on the dashboard', { tag: '@e2e' }, async ({ adminPage }) => {
  // TC_002
  await adminPage.goto();
  await adminPage.expectNavigationVisible(['Rooms', 'Report', 'Branding', 'Messages', 'Front Page']);
});
