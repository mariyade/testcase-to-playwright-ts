import { expect, type Page } from '@playwright/test';

export const visualBreakpoints = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 390, height: 844 },
] as const;

export type VisualBreakpoint = (typeof visualBreakpoints)[number];

export async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
}

export async function assertCriticalContentIsVisible(page: Page): Promise<void> {
  const bodyBox = await page.locator('body').boundingBox();

  expect(bodyBox).not.toBeNull();
  expect(bodyBox?.width ?? 0).toBeGreaterThan(0);
  expect(bodyBox?.height ?? 0).toBeGreaterThan(0);
}

export function screenshotName(pageName: string, breakpoint: VisualBreakpoint): string {
  const width = String(breakpoint.width);
  const height = String(breakpoint.height);

  return `${pageName}-${breakpoint.name}-${width}x${height}.png`;
}
