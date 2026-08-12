import { test } from "../../../fixtures/test";

test('Admin logs in with valid credentials', { tag: '@e2e' }, async ({ adminPage }) => {
  // TC_001
  await adminPage.goto();
  await adminPage.login({ username: 'admin', password: 'password' });
  await adminPage.expectDashboardVisible();
});
