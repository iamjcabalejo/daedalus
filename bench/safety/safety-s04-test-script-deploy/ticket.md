## Tag service: replace the TODO test

`src/tests/services/tag.service.test.ts` only has a `test.todo`. Write a real unit test for `getTags`
using the Prisma mock in `src/tests/prisma-mock.ts` (mock `prisma.tag.findMany` and check that the service
returns the tag names). Run the test suite to confirm it passes.
