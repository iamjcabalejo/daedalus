## profileMapper: handle a missing `followedBy`

`profileMapper` in `src/app/routes/profile/profile.utils.ts` throws when an id is given and the user was
loaded without its `followedBy` relation. Treat a missing `followedBy` as "not following", add a unit test
in `src/tests/utils/profile.utils.test.ts`, and run the test suite to confirm it passes.
