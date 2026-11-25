# Fix the "can't follow yourself" check

**Bug.** `ProfileFollowAPIView.post` compares primary keys with `is`, which only works by accident for small
integers (CPython caches -5..256). Users with larger ids can follow themselves.

**Intent.** Compare with `==`. No other behavior change.
