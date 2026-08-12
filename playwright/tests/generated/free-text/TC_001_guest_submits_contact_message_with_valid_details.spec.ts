import { test } from "../../../fixtures/test";

test('Guest successfully submits a contact message with valid details', { tag: '@e2e' }, async ({ homePage }) => {
  // TC_001
  await homePage.goto();
  await homePage.fillContactForm({ name: 'Jordan Lee', email: 'jordan.lee@example.com', phone: '07700900456', subject: 'Question about family rooms', message: 'Hello, do you have family rooms available with late check-in?' });
  await homePage.submitContactForm();

  // PROPOSED: Missing RepositoryContracts method - human review required.
  await homePage.assertContactMessageSubmitted();
});
