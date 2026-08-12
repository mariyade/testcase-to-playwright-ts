import { test } from "../../../fixtures/test";

test('Admin sees Rooms table with correct columns', { tag: '@e2e' }, async ({ adminPage }) => {
  // TC_003
  await adminPage.goto();
  await adminPage.expectRoomsTableColumns(['Room #', 'Type', 'Accessible', 'Price', 'Room details']);
});
