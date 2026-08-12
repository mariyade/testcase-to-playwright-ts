import { test } from "../../../fixtures/test";

test('Admin login fails with invalid credentials', { tag: '@e2e' }, async ({ adminPage }) => {
  // TC_004
  await adminPage.goto();
  await adminPage.login({ username: 'invalid_user', password: 'invalid_password' });
  await adminPage.expectInvalidLoginError();
});
