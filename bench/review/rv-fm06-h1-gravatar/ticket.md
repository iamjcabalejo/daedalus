# Use the user's Gravatar as their profile image

**Intent.** New users get the generic smiley avatar. When a user registers, use their Gravatar as the
profile image if one exists (Gravatar answers 404 for `?d=404` when the email has no avatar); otherwise
keep the default image. Registration must still succeed when the lookup fails.
