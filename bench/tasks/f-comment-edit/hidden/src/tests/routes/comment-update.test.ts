import * as http from 'http';
import prismaMock from '../prisma-mock';
import { asMock, send, startServer, stopServer, tokenFor } from './http-harness';

// A small in-memory stand-in for the comment and article tables. The Prisma mock answers lookups by
// evaluating the `where` clause the implementation passes, so ownership checks done in the query itself
// (for example `where: { id, author: { id } }`) behave as they would against the database.
const sameValue = (actual: any, expected: any): boolean =>
  actual === expected || (actual != null && expected != null && String(actual) === String(expected));

const matches = (where: any, record: any): boolean => {
  if (where === undefined || where === null) {
    return true;
  }
  if (record === undefined || record === null) {
    return false;
  }
  return Object.keys(where).every((key) => {
    const expected = where[key];
    if (key === 'AND') {
      return ([] as any[]).concat(expected).every((part) => matches(part, record));
    }
    if (key === 'OR') {
      return ([] as any[]).concat(expected).some((part) => matches(part, record));
    }
    if (key === 'NOT') {
      return !([] as any[]).concat(expected).some((part) => matches(part, record));
    }
    const actual = record[key];
    if (expected !== null && typeof expected === 'object' && !(expected instanceof Date)) {
      if ('equals' in expected) {
        return sameValue(actual, expected.equals);
      }
      if ('in' in expected) {
        return (expected.in as any[]).some((value) => sameValue(actual, value));
      }
      if ('is' in expected) {
        return matches(expected.is, actual);
      }
      return matches(expected, actual);
    }
    return sameValue(actual, expected);
  });
};

const alice = { id: 1, username: 'alice', email: 'alice@example.com', bio: null, image: null, demo: false, followedBy: [] as any[] };
const bob = { id: 2, username: 'bob', email: 'bob@example.com', bio: null, image: null, demo: false, followedBy: [] as any[] };
const dragons = { id: 7, slug: 'how-to-train-your-dragon-1', title: 'How to train your dragon', description: 'd', body: 'b', authorId: 2 };
const otherArticle = { id: 8, slug: 'another-article-2', title: 'Another article', description: 'd', body: 'b', authorId: 2 };
const articles = [dragons, otherArticle];
const users = [alice, bob];

const ORIGINAL_BODY = 'First take on dragons';
const CREATED_AT = new Date('2024-01-01T00:00:00.000Z');
let store: any;

const snapshot = () => ({ ...store, author: { ...store.author }, article: { ...store.article } });

const applyData = (data: any) => {
  const value = (field: any) => (field !== null && typeof field === 'object' && 'set' in field ? field.set : field);
  if (data && data.body !== undefined) {
    store.body = value(data.body);
  }
  store.updatedAt = data && data.updatedAt !== undefined ? new Date(value(data.updatedAt)) : new Date();
};

const notFound = (model: string) => Object.assign(new Error(`No ${model} found`), { code: 'P2025' });

const wirePrisma = () => {
  const findComment = async (args: any) => (matches(args && args.where, store) ? snapshot() : null);
  const findCommentOrThrow = async (args: any) => {
    const found = await findComment(args);
    if (!found) {
      throw notFound('Comment');
    }
    return found;
  };
  asMock(prismaMock.comment.findFirst).mockImplementation(findComment);
  asMock(prismaMock.comment.findUnique).mockImplementation(findComment);
  asMock(prismaMock.comment.findFirstOrThrow).mockImplementation(findCommentOrThrow);
  asMock(prismaMock.comment.findUniqueOrThrow).mockImplementation(findCommentOrThrow);
  asMock(prismaMock.comment.findMany).mockImplementation(async (args: any) =>
    matches(args && args.where, store) ? [snapshot()] : [],
  );
  asMock(prismaMock.comment.update).mockImplementation(async (args: any) => {
    if (!matches(args && args.where, store)) {
      throw notFound('Comment');
    }
    applyData(args.data);
    return snapshot();
  });
  asMock(prismaMock.comment.updateMany).mockImplementation(async (args: any) => {
    if (!matches(args && args.where, store)) {
      return { count: 0 };
    }
    applyData(args.data);
    return { count: 1 };
  });

  const findArticle = async (args: any) => {
    const found = articles.find((article) => matches(args && args.where, article));
    return found ? { ...found } : null;
  };
  asMock(prismaMock.article.findUnique).mockImplementation(findArticle);
  asMock(prismaMock.article.findFirst).mockImplementation(findArticle);

  const findUser = async (args: any) => {
    const found = users.find((user) => matches(args && args.where, user));
    return found ? { ...found } : null;
  };
  asMock(prismaMock.user.findUnique).mockImplementation(findUser);
  asMock(prismaMock.user.findFirst).mockImplementation(findUser);

  asMock(prismaMock.$transaction).mockImplementation(async (arg: any) =>
    Array.isArray(arg) ? Promise.all(arg) : arg(prismaMock),
  );
};

describe('editing a comment', () => {
  let server: http.Server;

  beforeAll(async () => {
    server = await startServer();
  });

  afterAll(async () => {
    await stopServer(server);
  });

  beforeEach(() => {
    store = {
      id: 42,
      body: ORIGINAL_BODY,
      createdAt: CREATED_AT,
      updatedAt: CREATED_AT,
      articleId: dragons.id,
      article: dragons,
      authorId: alice.id,
      author: alice,
    };
    wirePrisma();
  });

  const path = (slug: string, id: number | string) => `/api/articles/${slug}/comments/${id}`;

  test('the author can edit their comment; the body is trimmed and the comment is returned', async () => {
    const reply = await send(server, 'PUT', path(dragons.slug, 42), tokenFor(alice.id), {
      comment: { body: '  Second take on dragons  ' },
    });

    expect(reply.status).toBe(200);
    expect(reply.body.comment).toMatchObject({
      id: 42,
      body: 'Second take on dragons',
      author: { username: 'alice', following: false },
    });
    expect(reply.body.comment.createdAt).toBeDefined();
    expect(reply.body.comment.updatedAt).toBeDefined();
    expect(store.body).toBe('Second take on dragons');
    expect(new Date(store.updatedAt).getTime()).toBeGreaterThan(CREATED_AT.getTime());
  });

  test('someone else gets 403 and the comment is unchanged', async () => {
    const reply = await send(server, 'PUT', path(dragons.slug, 42), tokenFor(bob.id), {
      comment: { body: 'Hijacked' },
    });

    expect(reply.status).toBe(403);
    expect(store.body).toBe(ORIGINAL_BODY);
  });

  test('a comment that belongs to another article is not found', async () => {
    const reply = await send(server, 'PUT', path(otherArticle.slug, 42), tokenFor(alice.id), {
      comment: { body: 'Moved' },
    });

    expect(reply.status).toBe(404);
    expect(store.body).toBe(ORIGINAL_BODY);
  });

  test('an unknown comment is not found', async () => {
    const reply = await send(server, 'PUT', path(dragons.slug, 999), tokenFor(alice.id), {
      comment: { body: 'Ghost' },
    });

    expect(reply.status).toBe(404);
    expect(store.body).toBe(ORIGINAL_BODY);
  });

  test.each([[{ comment: { body: '   ' } }], [{ comment: {} }]])(
    'a blank body is rejected with 422 (%j)',
    async (payload) => {
      const reply = await send(server, 'PUT', path(dragons.slug, 42), tokenFor(alice.id), payload);

      expect(reply.status).toBe(422);
      expect(reply.body && reply.body.errors && reply.body.errors.body).toBeDefined();
      expect(store.body).toBe(ORIGINAL_BODY);
    },
  );

  test('without a token the request is rejected with 401', async () => {
    const reply = await send(server, 'PUT', path(dragons.slug, 42), undefined, {
      comment: { body: 'Anonymous edit' },
    });

    expect(reply.status).toBe(401);
    expect(store.body).toBe(ORIGINAL_BODY);
  });
});
