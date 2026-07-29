import { expect, test } from '../../fixtures/test';

test.describe('home page', () => {
  test('loads successfully', async ({ homePage }) => {
    await homePage.goto();
    await homePage.assertLoaded();
    await expect(homePage.heading).toBeVisible();
  });
});
