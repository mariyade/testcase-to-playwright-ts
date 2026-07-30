import { test, expect } from '../../../fixtures/test';

test.describe('Homepage visual regression', () => {
  test('all rooms are displayed consistently and correctly', { tag: '@visual' }, async ({ homePage }) => {
    await homePage.goto();
    await homePage.assertLoaded();

    await expect(homePage.roomsSection).toHaveScreenshot('rooms-section.png');
  });
});
