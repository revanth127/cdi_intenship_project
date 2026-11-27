import { test, expect } from '@playwright/test';

test.describe('Salesman Offline Order Booking Flow', () => {
  test('toggles offline, submits an order, goes online and checks the order appears in My orders', async ({
    page,
    context,
  }) => {
    // 1. Open the New Order page
    await page.goto('/orders/new');
    await expect(page.locator('h1')).toContainText('New Sales Order');

    // 2. Toggle offline in browser context
    await context.setOffline(true);
    await page.evaluate(() => window.dispatchEvent(new Event('offline')));

    // Verify offline UI indicators
    await expect(page.getByTestId('topbar-connectivity')).toContainText('Offline');
    await expect(page.getByTestId('offline-prices-banner')).toBeVisible();
    await expect(page.getByTestId('offline-review-strip')).toBeVisible();
    await expect(page.getByTestId('order-submit-button')).toContainText('Save order');

    // 3. Take order while offline
    const notesField = page.locator('textarea');
    await notesField.fill('Urgent delivery for Pongal festival festival booking');

    // Submit while offline
    await page.getByTestId('order-submit-button').click();

    // 4. Verify Success screen displays "Saved on this phone"
    await expect(page.getByTestId('order-success-screen')).toBeVisible();
    await expect(page.getByTestId('success-title')).toHaveTextContent('Saved on this phone');

    // 5. Navigate to My Orders
    await page.getByRole('button', { name: 'View My Orders' }).click();
    await expect(page).toHaveURL(/\/orders\/my/);

    // Order should appear in My Orders with "Waiting to send" chip
    await expect(page.getByTestId('chip-waiting-to-send')).toBeVisible();
    await expect(page.locator('table')).toContainText('Annapoorna Sweets');

    // 6. Toggle back online
    await context.setOffline(false);
    await page.evaluate(() => window.dispatchEvent(new Event('online')));

    // Top bar connectivity should transition to Online or Sending
    await expect(page.getByTestId('topbar-connectivity')).not.toContainText('Offline');

    // Order remains visible in My Orders table
    await expect(page.locator('table')).toContainText('Annapoorna Sweets');
  });
});
