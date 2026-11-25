# Treat email addresses as case-insensitive

People sign up as `Jane.Doe@Example.com` and later try to sign in as `jane.doe@example.com`, and the login fails. Worse, a second account can be registered with the same address in different letter case. Email addresses should identify an account no matter how they're capitalized.

## Acceptance criteria

1. Registration stores the email address trimmed and in lowercase, and the response shows it that way.
2. Signing in works whatever the letter case of the email the user types, as long as the password is right. A wrong password is still rejected with 401.
3. Registering with an email that's already taken in any letter case is rejected with 409 and `{"errors": {"email": ["has already been taken"]}}`; no second account is created.
4. Accounts created before this change may have mixed-case emails stored. Their owners can sign in with any letter case, and their addresses count as taken for criterion 3. Stored addresses of existing accounts aren't rewritten.
5. Changing your email through `PUT /api/user` stores the new address in lowercase. Changing it to an address another account already uses, in any letter case, is rejected with 409 and the same error body, and your email stays as it was.
