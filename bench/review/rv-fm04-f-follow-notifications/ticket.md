# Notify users when someone follows them

**Intent.** When a user follows another user, the followed user gets a `FOLLOW` notification. Add
`GET /api/notifications` (auth required) that returns the current user's latest 20 notifications, newest
first, with the actor's username and image.

**Scope.**
- New `Notification` model and migration.
- Create the notification in the follow flow.
- New notifications route.
