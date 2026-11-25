# Log failed logins for brute-force alerting

**Intent.** Security wants to see brute-force attempts. Log every failed login at WARNING, with the client
address and the submitted account, and route the `conduit` loggers to the console so the log pipeline picks
them up. The API response doesn't change.
