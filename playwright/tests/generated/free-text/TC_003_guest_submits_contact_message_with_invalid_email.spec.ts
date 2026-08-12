import { test } from "../../../fixtures/test";

test('Guest attempts to submit a contact message with an invalid email format', { tag: '@e2e' }, async ({ homePage }) => {
  // TC_003
  await homePage.goto();
  await homePage.fillContactForm({ name: 'Jordan Lee', email: 'invalid-email', phone: '07700900456', subject: 'Question about family rooms', message: 'Hello, do you have family rooms available with late check-in?' });
  await homePage.submitContactForm();

  // PROPOSED: Missing RepositoryContracts method - human review required.
  await homePage.assertContactValidationVisible();
});
