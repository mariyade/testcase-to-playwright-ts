import { test } from '../../../fixtures/test';

const contactMessage = {
  name: 'Jane Guest',
  email: 'jane.guest@example.com',
  phone: '07123456789',
  subject: 'Booking question',
  message: 'Could you confirm whether late check-in is available?',
};

test('guest opens home page and finds contact form', { tag: '@smoke' }, async ({ homePage }) => {
  console.log('Open the home page');
  await homePage.goto();

  console.log('Verify the contact form is visible');
  await homePage.assertLoaded();
  await homePage.assertContactFormVisible();
});

test('guest submits contact form with valid details', { tag: '@e2e' }, async ({ homePage }) => {
  console.log('Open the home page');
  await homePage.goto();

  console.log('Submit a valid contact message');
  await homePage.sendContactMessage(contactMessage);

  console.log('Verify the message confirmation');
  await homePage.assertContactMessageSubmitted();
});

test('guest sees validation for missing contact fields', { tag: '@e2e' }, async ({ homePage }) => {
  console.log('Open the home page');
  await homePage.goto();

  console.log('Submit the empty contact form');
  await homePage.submitContactForm();

  console.log('Verify validation feedback is visible');
  await homePage.assertContactValidationVisible();
});

test('guest sees validation for invalid contact email', { tag: '@e2e' }, async ({ homePage }) => {
  console.log('Open the home page');
  await homePage.goto();

  console.log('Fill the contact form with an invalid email');
  await homePage.fillContactForm({ ...contactMessage, email: 'not-an-email' });

  console.log('Submit the contact form');
  await homePage.submitContactForm();

  console.log('Verify validation feedback is visible');
  await homePage.assertContactValidationVisible();
});
