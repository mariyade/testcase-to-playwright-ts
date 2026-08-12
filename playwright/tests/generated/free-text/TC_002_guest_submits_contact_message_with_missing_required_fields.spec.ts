import { test } from "../../../fixtures/test";

test('Guest attempts to submit a contact message with missing required fields', { tag: '@e2e' }, async ({ homePage }) => {
  // TC_002
  await homePage.goto();
  await homePage.fillContactForm({ name: '', email: '', phone: '', subject: '', message: '' });
  await homePage.submitContactForm();

  // PROPOSED: Missing RepositoryContracts method - human review required.
  await homePage.assertContactValidationVisible();
});
