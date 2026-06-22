import { test } from '../../fixtures/test';

test.describe('home page', () => {
  test('loads successfully', async ({ homePage }) => {
    await homePage.goto();
    await homePage.assertLoaded();
  });
});

