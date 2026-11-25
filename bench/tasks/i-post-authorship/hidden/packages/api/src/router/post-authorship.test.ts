/**
 * Benchmark hidden tests (overlaid at scoring time; not part of the upstream repository).
 *
 * They call the tRPC router the apps use (appRouter) with a signed-in or signed-out context, against a
 * real Postgres (PGlite) whose tables are created from the current Drizzle schema, so they check behaviour
 * rather than column names or query style. Run with the Node test runner through tsx.
 */
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { after, before, beforeEach, describe, it } from "node:test";
import { initTRPC } from "@trpc/server";

import * as schema from "@acme/db/schema";

import type { TestDatabase } from "../../../db/test/pglite-proxy";
import { createTestDatabase } from "../../../db/test/pglite-proxy";
import { appRouter } from "../root";

interface TestUser {
  id: string;
  name: string;
  email: string;
}

const alice: TestUser = { id: "user-alice", name: "Alice Author", email: "alice@example.com" };
const bob: TestUser = { id: "user-bob", name: "Bob Bystander", email: "bob@example.com" };

let database: TestDatabase;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Caller = any;

function callerFor(user: TestUser | null): Caller {
  const now = new Date();
  const session = user
    ? {
        user: { ...user, emailVerified: true, image: null, createdAt: now, updatedAt: now },
        session: {
          id: `session-${user.id}`,
          userId: user.id,
          token: `token-${user.id}`,
          expiresAt: new Date(now.getTime() + 60 * 60 * 1000),
          createdAt: now,
          updatedAt: now,
          ipAddress: null,
          userAgent: null,
        },
      }
    : null;
  const ctx = { db: database.db, session, authApi: {} };
  const factory = initTRPC.context<typeof ctx>().create().createCallerFactory;
  if (typeof factory === "function") {
    return factory(appRouter as never)(ctx);
  }
  return (appRouter as unknown as { createCaller(ctx: unknown): Caller }).createCaller(ctx);
}

const signedOut = () => callerFor(null);

async function rejectsWith(promise: Promise<unknown>, code: string, what: string): Promise<void> {
  await assert.rejects(
    promise,
    (err: unknown) => {
      const actual = (err as { code?: unknown } | null)?.code;
      assert.equal(actual, code, `${what}: expected a ${code} error, got ${String(actual)} (${String(err)})`);
      return true;
    },
    `${what}: expected a ${code} error, but the call succeeded`,
  );
}

interface ListedPost {
  id: string;
  title: string;
  author?: { id?: unknown; name?: unknown } | null;
}

async function listed(): Promise<ListedPost[]> {
  return (await signedOut().post.all()) as ListedPost[];
}

async function create(user: TestUser, title: string, extra: Record<string, unknown> = {}): Promise<void> {
  await callerFor(user).post.create({ title, content: `${title} (content)`, ...extra });
}

async function findListed(title: string): Promise<ListedPost> {
  const post = (await listed()).find((p) => p.title === title);
  assert.ok(post, `post "${title}" should be listed`);
  return post;
}

function assertAuthor(post: ListedPost, user: TestUser, where: string): void {
  assert.ok(post.author, `${where}: post "${post.title}" should include its author`);
  assert.equal(post.author.id, user.id, `${where}: author id of "${post.title}"`);
  assert.equal(post.author.name, user.name, `${where}: author name of "${post.title}"`);
}

describe("post authorship", () => {
  before(async () => {
    database = await createTestDatabase(schema as Record<string, unknown>);
  });

  after(async () => {
    await database.close();
  });

  beforeEach(async () => {
    await database.reset();
    const now = new Date();
    await database.db
      .insert(schema.user)
      .values([alice, bob].map((u) => ({ ...u, emailVerified: true, image: null, createdAt: now, updatedAt: now })));
  });

  it("records the signed-in user as the author, and lists posts with their author", async () => {
    await create(alice, "Alice on dragons");
    assertAuthor(await findListed("Alice on dragons"), alice, "post.all");
  });

  it("returns the author from post.byId too", async () => {
    await create(alice, "Alice on castles");
    const { id } = await findListed("Alice on castles");
    const post = (await signedOut().post.byId({ id })) as ListedPost | undefined;
    assert.ok(post, "post.byId should find the post");
    assertAuthor(post, alice, "post.byId");
  });

  it("keeps each post's own author", async () => {
    await create(alice, "Alice writes");
    await create(bob, "Bob writes");
    assertAuthor(await findListed("Alice writes"), alice, "post.all");
    assertAuthor(await findListed("Bob writes"), bob, "post.all");
  });

  it("never lets the client choose the author", async () => {
    const forged = { authorId: bob.id, userId: bob.id, createdById: bob.id, ownerId: bob.id, author: bob.id };
    let rejected = false;
    try {
      await create(alice, "Forged author", forged);
    } catch (err) {
      rejected = true;
      assert.equal((err as { code?: unknown }).code, "BAD_REQUEST", `a forged author may be rejected, but only as BAD_REQUEST (${String(err)})`);
    }
    const forgedPost = (await listed()).find((p) => p.title === "Forged author");
    if (rejected) {
      assert.equal(forgedPost, undefined, "a rejected create must not store a post");
    } else {
      assert.ok(forgedPost, "the post should be created");
      assertAuthor(forgedPost, alice, "post.all after a forged create");
    }
  });

  it("lets the author delete their own post", async () => {
    await create(alice, "Short-lived");
    const { id } = await findListed("Short-lived");
    await callerFor(alice).post.delete(id);
    assert.equal((await listed()).find((p) => p.id === id), undefined, "the deleted post should be gone");
  });

  it("refuses to delete someone else's post with FORBIDDEN and keeps it", async () => {
    await create(alice, "Not yours");
    const { id } = await findListed("Not yours");
    await rejectsWith(callerFor(bob).post.delete(id), "FORBIDDEN", "bob deletes alice's post");
    assert.ok((await listed()).find((p) => p.id === id), "the post should still be listed");
  });

  it("answers NOT_FOUND when the post doesn't exist", async () => {
    await create(alice, "Bystander post");
    await rejectsWith(callerFor(alice).post.delete(randomUUID()), "NOT_FOUND", "delete an unknown post");
    assert.ok(await findListed("Bystander post"));
  });

  it("still requires a signed-in user to create or delete", async () => {
    await create(alice, "Public post");
    const { id } = await findListed("Public post");
    await rejectsWith(signedOut().post.create({ title: "Anonymous", content: "x" }), "UNAUTHORIZED", "signed-out create");
    await rejectsWith(signedOut().post.delete(id), "UNAUTHORIZED", "signed-out delete");
    assert.ok(await findListed("Public post"));
  });
});
